from buffer_mapping.hardware import *
from buffer_mapping.virtualbuffer import *
from buffer_mapping.config import HWBufferConfig

def CreateVirtualBuffer(setup):
    return VirtualDoubleBuffer(setup['input_port'],
                               setup['output_port'],
                               setup['capacity'],
                               setup['access_pattern']['range'],
                               setup['access_pattern']['stride'],
                               setup['access_pattern']['start'],
                               setup['manual_switch'])

def CreateHWConfig(setup):
    return HWBufferConfig(setup['input_port'],
                          setup['output_port'],
                          setup['capacity'])

def SliceAccessPattern(_range, stride, start, num_bank, num_port) -> AccessPattern:
    bank_stride = []
    for st_in_dim in stride:
        assert st_in_dim % num_bank == 0, "stride is not divisible by number of bank.\n"
        bank_stride.append(st_in_dim // num_bank)

    bank_start = start[0:num_port]

    return AccessPattern(_range, bank_stride, bank_start)

def HWMap(buf: VirtualDoubleBuffer, mem_config):
    # return value hold the banking and chainer mem_tile
    mem_tile_list = []

    #TODO: need a pass to optimize the port number for linebuffer

    #check the bandwidth requirement to create banking
    input_multiplier = buf._input_port // mem_config._input_port
    output_multiplier = buf._output_port // mem_config._output_port
    num_bank = max(input_multiplier, output_multiplier)

    #TODO: need a pass to get the access pattern for each port, we need to split the stride
    bank_access_pattern = SliceAccessPattern(buf.read_iterator._rng,
                                             buf.read_iterator._st,
                                             buf.read_iterator._start,
                                             num_bank,
                                             mem_config._output_port)

    #check capacity requirement to do chaining
    capacity_per_bank = buf._capacity / num_bank
    if capacity_per_bank > mem_config._capacity:
        #FIXME: need more test case to try if this heruistic based capacity assign is bug free
        # Assign the data with the granularity at the largest stride
        '''
        max_stride = max(buf.read_iterator._st)
        capacity_per_tile =int( mem_config._capacity / max_stride) * max_stride
        '''
        capacity_per_tile = mem_config._capacity
        capacity_reminder = capacity_per_bank
        capacity_start_addr = 0

        #chaining the tile
        while capacity_reminder > capacity_per_tile:

            # create a memory tile instance and chained with the previous block if exist
            mem_tile = MemoryTile(mem_config,
                                  bank_access_pattern,
                                  capacity_start_addr,
                                  capacity_start_addr + capacity_per_tile,
                                  capacity_per_bank)
            mem_tile_list.append(mem_tile)

            capacity_reminder -= capacity_per_tile
            capacity_start_addr += capacity_per_tile

        #add last memory tile into list
        mem_tile = MemoryTile(mem_config,
                              bank_access_pattern,
                              capacity_start_addr,
                              capacity_start_addr + capacity_per_tile,
                              capacity_per_bank)
        mem_tile_list.append(mem_tile)

    else:
        mem_tile = MemoryTile(mem_config, bank_access_pattern, 0, capacity_per_bank, capacity_per_bank)
        mem_tile_list.append(mem_tile)

    #create the chained memory tile from a list
    mem_chain = ChainedMemoryTile(mem_tile_list)

    #create the banking
    mem_chain_bank = BankedChainedMemoryTile(mem_chain, num_bank, buf._input_port, buf._output_port)

    return mem_chain_bank


