from buffer_mapping.virtualbuffer import VirtualDoubleBuffer, AccessIter
from buffer_mapping.util import Counter
from buffer_mapping.pretty_print import NoIndent
import copy
from functools import reduce


class BankedChainedMemoryTile:
    '''
    class wrap on Chained Memory Tile, use multiple parallel bank to increase the bandwidth
    '''
    def __init__(self, chained_mem_tile, num_bank, in_port, out_port):
        #create a list to save all the chained memory_tile
        self.banked_mem_tile = []
        for _ in range(num_bank):
            self.banked_mem_tile.append(copy.deepcopy(chained_mem_tile))
        self._num_bank = num_bank
        self._in_port_per_bank = chained_mem_tile._input_port
        self._out_port_per_bank = chained_mem_tile._output_port
        self._in_port = in_port
        self._out_port = out_port

        self.write_counter = Counter(self._num_bank // self._in_port)
        self.read_counter = Counter(self._num_bank // self._out_port)

    def dump_json(self)->dict:
        mem_bank = {}
        for idx, mem_chain in enumerate(self.banked_mem_tile):
            mem_bank["mem_bankid_"+str(idx)] = mem_chain.dump_json()
        return mem_bank

    def read(self):
        out_data_chain = []
        start_bank = self.read_counter.read() * self._out_port
        end_bank = (self.read_counter.read() + 1 ) * self._out_port
        for bank in self.banked_mem_tile[start_bank: end_bank]:
            out_data_chain.extend(bank.read())
        self.read_counter.update()
        return out_data_chain


    def write(self, data):
        start_bank = self.write_counter.read() * self._in_port
        end_bank = (self.write_counter.read() + 1 ) * self._in_port
        for bank_id, bank in enumerate(self.banked_mem_tile[start_bank: end_bank]):
            #TODO: currently only support contigous write pattern
            start = bank_id * self._in_port_per_bank
            end = (bank_id + 1) * self._in_port_per_bank
            bank.write(data[start: end])
        self.write_counter.update()

    def write_bank(self, data, bank_no):
        '''
        helper function to write a portion of bank in case of virtual in port is not equal to out port
        '''
        assert  bank_no < self._num_bank, "write bank exceeded the total bank amount!\n"
        self.banked_mem_tile[bank_no].write(data)

    def write_partial(self, data):
        '''
        Write function if in port less than out port
        '''
        pass

    def read_bank(self, bank_no):
        '''
        helper function for reading a portion of banks
        '''
        assert bank_no < self._num_bank, "read bank exceeded the total bank amount!\n"
        data = self.banked_mem_tile[bank_no].read()
        return data

class ChainedMemoryTile:
    '''
    class wrap on memory tile, chain for larger capacity
    '''
    def __init__(self, mem_tile_list):
        self._mem_tile_chain = mem_tile_list
        self._input_port = mem_tile_list[0]._input_port
        self._output_port = mem_tile_list[0]._output_port

    def dump_json(self)->dict:
        mem_chain = {}
        for idx, mem_tile in enumerate(self._mem_tile_chain):
            mem_tile_config = mem_tile.dump_json()
            mem_tile_config.update({'chain_idx':  NoIndent(['int', idx])})
            mem_chain["mem_chainid" + str(idx)] = mem_tile_config

        return mem_chain

    def read(self):
        '''
        This should be a mux in the CGRA with valid signal from memory tile as control
        '''
        valid_tile_id = -1
        out_data = 0
        for idx, mem_tile in enumerate(self._mem_tile_chain):
            #read all memory tile, to update the iterator
            read_valid, out_data_tmp = mem_tile.read()
            if read_valid:
                out_data = out_data_tmp
                assert valid_tile_id == -1, \
                    "Multiple valid tile in the chain available, check chaining mapping algorithm!\n"
                valid_tile_id = idx
        return out_data

    def write(self, data):
        '''
        data will be broad cast to different tile,
        only the bank with write valid can be written
        '''
        valid_tile_id = -1
        for idx, mem_tile in enumerate(self._mem_tile_chain):
            write_success= mem_tile.write(data)

            #debug: to see if there is multiple valid tile to write
            if write_success:
                assert valid_tile_id == -1,\
                    "Multiple valid tile in the chain available, check chaining mapping algorithm!\n"
                valid_tile_id = idx
                #print ("valide id = ", idx)
        assert valid_tile_id != -1, "No valid tile to write."


class MemoryTile(VirtualDoubleBuffer):
    '''
    memory tile functional model
    has the valid signal for chaining
    '''
    #FIXME mem_tile_config should be only one, not share by all mem_tile
    def __init__(self, mem_tile_config, read_access_pattern, start_addr, end_addr, chain_capacity, manual_switch=0):
        super().__init__(mem_tile_config._input_port,
                         mem_tile_config._output_port,
                         mem_tile_config._capacity,
                         read_access_pattern._rng,
                         read_access_pattern._st,
                         read_access_pattern._start,
                         manual_switch)
        #overwrite the write iterator
        #FIXME Possible bug if input port not equals output_port
        self.write_iterator = AccessIter([int(chain_capacity / self._input_port)],
                                         [1],
                                         list(range(self._input_port)),
                                         manual_switch)

        #control signal tell if we read the valid signal
        self.addr_domain = [start_addr, end_addr]
        self.read_val = 0
        self.write_val = 0

    def dump_json(self)->dict:
        '''
        Method to dump a diction into json
        '''
        mem_tile = {}
        dimension = len(self.read_iterator._rng)
        mem_tile['dimensionality'] = NoIndent(['int', dimension])
        for idx in range(dimension):
            mem_tile['stride_'+str(idx)] = NoIndent(['int', self.read_iterator._st[idx]])
            mem_tile['range_'+str(idx)] = NoIndent(['int', self.read_iterator._rng[idx]])
        #TODO: not hardcode if we are going to support line buffer
        mem_tile['depth'] = NoIndent(['int', 0])
        mem_tile['mode'] = NoIndent(['int', 3]) # DB is mode = 3
        mem_tile['tile_en'] = NoIndent(['bool', 1])
        mem_tile['rate_matched'] = NoIndent(['bool', 0])
        mem_tile['stencil_width'] = NoIndent(['int', 0])
        mem_tile['iter_cnt'] = NoIndent(['int', reduce((lambda x, y: x * y), self.read_iterator._rng)])
        return mem_tile

    def read(self):
        '''
        return the read data with valid signal
        wrapper the super class read method
        return type: valid, data_out
        '''
        if self.read_iterator._addr[0] >= self.addr_domain[0] and\
                self.read_iterator._addr[-1] < self.addr_domain[1]:
            self.read_val = 1
        else:
            self.read_val = 0

        if self.read_val:
            data_out = super().read(self.addr_domain[0])
        else:
            self.read_iterator.update()
            self.check_switch()
            data_out = None

        return self.read_val, data_out

    def write(self, data_in):
        '''
        write the data if signal is valid
        wrap the super class write method
        return type: if write is valid
        '''
        if self.write_iterator._addr[0] >= self.addr_domain[0] and\
                self.write_iterator._addr[-1] < self.addr_domain[1]:
            self.write_val = 1
        else:
            self.write_val = 0

        if self.write_val:
            super().write(data_in, self.addr_domain[0])
        else:
            self.write_iterator.update()
            self.check_switch()


        return self.write_val




