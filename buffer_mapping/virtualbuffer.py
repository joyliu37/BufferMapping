from buffer_mapping.config import VirtualBufferConfig
from buffer_mapping.util import AccessIter, Counter
from functools import reduce
from buffer_mapping.flatten import FlattenAccessPattern
import copy

class VirtualBuffer:
    def __init__(self, input_port, output_port, capacity, _range, stride, start, manual_switch=0, arbitrary_addr=0):
        '''
        The base class of double buffer and line buffer, a dual port sram
        Has method read and write, has a valid field which prevent read before write
        '''
        #TODO: Add constrain of the initial parameter to the base class
        self._chain_id = 0
        self._chain_en = False
        self._input_port = input_port
        self._output_port = output_port
        self._capacity = capacity
        self.read_iterator = AccessIter(_range, stride, start, manual_switch)
        self.write_iterator = AccessIter([capacity // input_port], [input_port], list(range(input_port)), manual_switch)
        self._data = [65535 for _ in range(self._capacity)]
        self._manual_switch = manual_switch
        self._arbitrary_addr = arbitrary_addr

    def check_switch(self):
        if self.read_iterator._done and self.write_iterator._done:
            self.read_iterator.restart()
            self.write_iterator.restart()

    def getReadBank(self):
        return self._data

    def getWriteBank(self):
        return self._data

    def read(self, offset = 0, read_addr = 0):
        '''
        read a list data:<out_data> out of virtual buffer, return data_out
        '''
        if(self._manual_switch == 0):
            assert self.read_iterator._done == 0, "No more read allowed!\n"
        if(self._arbitrary_addr):
            #FIXME: I change the output rule to specify multiple port access by
            #using an array of starting address
            start_addr = read_addr
            end_addr = start_addr + self._output_port
            out_data = self.getReadBank()[start_addr: end_addr]
        else:
            out_data = [self.getReadBank()[(addr_in_word - offset) % self._capacity] for addr_in_word in self.read_iterator._addr]
        self.read_iterator.update()
        if(self._manual_switch == 0):
            self.check_switch()
        return out_data

    def write(self, data_in, offset = 0):
        '''
        write a list of data: <data_in> into virtual buffer
        '''
        assert self.write_iterator._done == 0, "No more write allowed!\n"
        write_bank = self.getWriteBank()
        if isinstance(data_in, int):
            #addr always is a list, since we are dealing with multiple port
            assert self._input_port == 1
            write_bank[(self.write_iterator._addr[0] - offset)] = data_in
        else:
            assert len(data_in) == self._input_port, "Input data size:"+str(len(data_in))+\
            " not match port number"+str(self._input_port)+"!\n"
            wr_addr = self.write_iterator._addr
            for addr ,word_data in zip(wr_addr, data_in):
                write_bank[(addr - offset) % self._capacity] = word_data
        self.write_iterator.update()
        #print ("base class write: size: ",self._capacity, self.write_iterator._done, self.write_iterator._iter, self.read_iterator._done, self.read_iterator._iter)
        if(self._manual_switch == 0):
            self.check_switch()

    def produce_banking(self, num_bank, bank_per_dim, capacity_per_dim, acc_capacity, bank_stride, bank_id):
        bank_buffer = copy.deepcopy(self)
        if bank_buffer._input_port < num_bank:
            bank_buffer._chain_id = bank_id
            bank_buffer._chain_en = True
        write_range = []
        write_stride = []
        acc_bank = 1
        for idx, (bank, capacity) in enumerate(zip(bank_per_dim, capacity_per_dim)):
            if bank_buffer._input_port < num_bank:
                assert capacity % bank == 0, "capacity in dimension should be divisible by bank number"
                if bank != 1:
                    write_range.append(bank)
                    write_stride.append(bank_stride * acc_bank)
                write_range.append(capacity // bank)
                write_stride.append(acc_capacity[idx] // acc_bank)
                #update bank we current use
            else:
                write_range.append(capacity // bank)
                write_stride.append(acc_capacity[idx] // acc_bank)
                #update assigned bank
            acc_bank *= bank

        for st_dim, st in enumerate(bank_buffer.read_iterator._st):
            stride_divisor = 1
            for idx, acc_capacity_per_dim in enumerate(acc_capacity):
                if st > acc_capacity_per_dim:
                    stride_divisor *= bank_per_dim[idx]
            bank_buffer.read_iterator._st[st_dim] //= stride_divisor
        bank_buffer.read_iterator._start = [bank_stride * bank_id]
        bank_buffer.write_iterator._rng = write_range
        bank_buffer.write_iterator._st = write_stride
        bank_buffer._capacity //= num_bank
        bank_buffer._output_port //= num_bank

        return bank_buffer


class VirtualValidBuffer(VirtualBuffer):
    '''
    This is the buffer with read valid not synchronized for every output port.
    It's the base buffer in swap buffer/line buffer, which has output port = stride size
    It will be the data layout transformation buffer in the future
    '''
    def __init__(self, input_port, output_port, capacity, _range, stride, start, manual_switch=0, arbitrary_addr=0):
        super().__init__(input_port, output_port, capacity, _range, stride, start, manual_switch, arbitrary_addr)
        #TODO: Add constrain
        self._data_valid = [True for _ in self._data]

    def shiftTopLeft(self, offset, capacity_dim):
        '''
        This method will add an invalid boundary pad to the top-left of the area
        which will responsible for the situation with output stencil not divisible by input chunk
        '''
        #invalid the position within -offset to the left top boudary
        for idx, data_valid in enumerate(self._data_valid):
            idx_copy = idx
            for dim in capacity_dim:
                if idx_copy % dim == dim - offset:
                    self._data_valid[idx] = False
                else:
                    idx_copy //= dim

    def isPassThrough(self):
        read_rng_flatten, read_st_flatten = FlattenAccessPattern(self.read_iterator._rng, self.read_iterator._st)
        write_rng_flatten, write_st_flatten = FlattenAccessPattern(self.write_iterator._rng, self.write_iterator._st)
        isPassThrough = True
        isPassThrough &= (read_rng_flatten == write_rng_flatten)
        isPassThrough &= (read_st_flatten == write_st_flatten)
        return isPassThrough


    def read(self, offset = 0, read_addr = 0):
        '''
        read a list data:<out_data> out of virtual buffer, return data_out
        '''
        out_data = []
        valid = []
        if(self._manual_switch == 0):
            assert self.read_iterator._done == 0, "No more read allowed!\n"
        if(self._arbitrary_addr):
            #FIXME: I change the output rule to specify multiple port access by
            #using an array of starting address
            start_addr = read_addr
            end_addr = start_addr + self._output_port
            valid = True
            out_data = self.getReadBank()[start_addr: end_addr]
        else:
            for addr_in_word in self.read_iterator._addr:
                if self._data_valid[(addr_in_word - offset) % self._capacity]:
                    valid.append(True)
                    out_data.append(self.getReadBank()[(addr_in_word - offset) % self._capacity])
                else:
                    valid.append(False)
                    out_data.append(65536)

        self.read_iterator.update()
        if(self._manual_switch == 0):
            self.check_switch()

        return valid, out_data



class VirtualDoubleBuffer(VirtualBuffer):

    def __init__(self, *args, **kwargs):
        if len(args) == 1:
            self.initFromConfig(args[0])
        else:
            self.initFromParams(*args)

    def initFromParams(self, input_port, output_port, capacity, _range, stride, start, manual_switch=0, arbitrary_addr=0):
        assert capacity % input_port == 0, "capacity is not divisible by input_port number!\n"
        assert capacity % output_port == 0, "capacity is not divisible by output_port number!\n"
        super().__init__(input_port, output_port, capacity, _range, stride, start, manual_switch, arbitrary_addr)
        self._bank_num = 2
        self._select = 0
        #no read need for empty buffer
        self.read_iterator._done = 1
        # Rewrite data domain to be multiple bank
        self._data = [[65535 for _ in range(self._capacity)] for _ in range(self._bank_num)]

    # Another object constructor from config
    def initFromConfig(self, config: VirtualBufferConfig):
        self._bank_num = 2
        self._select = 0
        super().__init__(config._input_port, config._output_port, config._capacity,
                       config._range, config._stride, config._start,
                       config._manual_switch, config._arbitrary_addr)
        #no read need for empty buffer
        self.read_iterator._done = 1
        # Rewrite data domain to be multiple bank
        self._data = [[655355 for _ in range(self._capacity)] for _ in range(self._bank_num)]

    def switch(self):
      if (self._manual_switch == 1):
        self._select= self._select ^ 1
        self.read_iterator.restart()
        self.write_iterator.restart()

    def check_switch(self):
        if self.read_iterator._done and self.write_iterator._done:
            self._select = self._select ^ 1
            self.read_iterator.restart()
            self.write_iterator.restart()

    def getReadBank(self):
        return self._data[self._select]

    def getWriteBank(self):
        return self._data[1-self._select]

class VirtualRowBuffer(VirtualBuffer):
    '''
    Row buffer is a contrained buffer, you have a read delay and also a stencil valid signal.
    Read and write access iterator can only be contiguous
    '''
    def __init__(self, input_port, output_port, capacity, _range, stride, start, read_delay, counter_bound,
                 manual_switch=0, arbitrary_addr=0):
        '''
        When you create the row buffer, you keep the range in each dimension,
        and flatten it in the very end
        '''
        super().__init__(input_port, output_port, capacity, _range, stride, start, manual_switch, arbitrary_addr)
        #count how much write you need to wait beforeread out data
        self._read_delay = read_delay
        self._counter_bound = counter_bound
        self.write_iterator._rng[0] = reduce((lambda x,y : x*y), self.read_iterator._rng)
        self.stencil_valid_counter = Counter(counter_bound)
        self.delay_counter = 0

    def write(self, valid, data_in, offset = 0):
        if valid == False:
            return
        self.delay_counter += 1
        #print ("write to row buffer:",self._output_port, data_in)
        super().write(data_in, offset)
        #print ("size: ",self._capacity,
        #       self.write_iterator._done, self.write_iterator._iter, self.read_iterator._done, self.read_iterator._iter)

    def read(self, offset = 0, read_addr = 0):
        #need to return two valid, one for read valid, one for stencil valid
        data = []
        stencil_valid = self.stencil_valid_counter.read() >= self._read_delay
        read_valid = self.delay_counter >= self._capacity
        self.stencil_valid_counter.update()
        #if read_valid:
        #no matter if it's valid, we will read the row buffer and may get invalid data
        data = super().read(offset, read_addr)
        return stencil_valid, read_valid, data

    def check_switch(self):
        if self.write_iterator._done and self.read_iterator._done:
            self.delay_counter = 0
            self.stencil_valid_counter.restart()
            self.read_iterator.restart()
            self.write_iterator.restart()

    def dump_json(self, last_in_chain:bool):
        mem_tile = {}
        #name = ''.join([random.choice(string.acii_letters + string.digits) for n in range(6)])
        if self._capacity == 1:
            mem_tile["modref"] = "coreir.reg"
            args = {"width" : ["Int", 16]}
            mem_tile["genargs"] = args
            mem_tile["modargs"] = {"clk_posedge": ["Bool", True], "init": [["BitVector", 16], "16'hxxxx"]}
            #in_port.extend(["in", "clk"])
            #out_port.extend(["out"])
        else:
            mem_tile["genref"] = "commonlib.unified_buffer"
            args = {}
            args["width"] = ["Int", 16]
            args["depth"] = ["Int", self._capacity]
            args["rate_matched"] = ["Bool", True]
            dimension = len(self.read_iterator._rng)
            args["dimensionality"] = ["Int", dimension]
            #FIXME: hack
            args["iter_cnt"] = ['Int', self._capacity]
            #args["iter_cnt"] = ['Int', reduce((lambda x, y: x* y), self.read_iterator._rng)]
            if last_in_chain:
                #FIXME:hardcode here, we need child node information
                args["stencil_width"] = ['Int', 2]
            else:
                args["stencil_width"] = ['Int', 2]

            for idx in range(dimension):
                args["stride_"+str(idx)] = ['Int', self.read_iterator._st[idx]]
                #FIXME: hack, why 64
                args["range_"+str(idx)] = ['Int', self._capacity]
            #FIXME: hardcode variable
            args["chain_en"] = ["Bool", False]
            args["chain_idx"] = ["Int", 0]
            assert len(self.read_iterator._start) == 1, "Need banking!\n"
            args["starting_addr"] = ["Int", self.read_iterator._start[0]]
            #args["init"] = ["Json", {"init":[0]}]
            mem_tile["genargs"] = args


        return mem_tile, self._capacity == 1



