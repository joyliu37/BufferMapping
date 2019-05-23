from buffer_mapping.config import VirtualBufferConfig

class VirtualDoubleBuffer:

    def __init__(self, *args, **kwargs):
        if len(args) == 1:
            self.initFromConfig(args[0])
        else:
            self.initFromParams(*args)

    def initFromParams(self, input_port, output_port, capacity, _range, stride, start, manual_switch):
        assert capacity % input_port == 0, "capacity is not divisible by input_port number!\n"
        assert capacity % output_port == 0, "capacity is not divisible by output_port number!\n"
        self._bank_num = 2
        self._select = 0
        self._input_port = input_port
        self._output_port = output_port
        self._capacity = capacity
        self.read_iterator = AccessIter(_range, stride, start, manual_switch)
        #no read need for empty buffer
        self.read_iterator._done = 1
        #initial all read access pattern to be linear contiguous
        self.write_iterator = AccessIter([capacity / input_port], [input_port], list(range(input_port)), manual_switch)
        self._data = [[655355 for _ in range(self._capacity)] for _ in range(self._bank_num)]
        self._manual_switch = manual_switch

    # Another object constructor from config
    def initFromConfig(self, config:VirtualBufferConfig):
        self._bank_num = 2
        self._select = 0
        self._input_port = config._input_port
        self._output_port = config._output_port
        self._capacity = config._capacity
        self.read_iterator = AccessIter(config._range, config._stride, config._start, config._manual_switch)
        #no read need for empty buffer
        self.read_iterator._done = 1
        #initial all read access pattern to be linear contiguous
        self.write_iterator = AccessIter([config._capacity / config._input_port],
                                         [1],
                                         [0]*config._input_port,
                                         config._manual_switch)
        self._data = [[655355 for _ in range(self._capacity)] for _ in range(self._bank_num)]
        self._manual_switch = config._manual_switch

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

    def read(self, offset = 0):
        '''
        read a list data:<out_data> out of virtual buffer, return data_out
        '''
        if(self._manual_switch == 0):
            assert self.read_iterator._done == 0, "No more read allowed!\n"
        '''
        start_addr = (self.read_iterator._addr - offset) * self._output_port
        end_addr = start_addr + self._output_port
        out = self._data[self._select][start_addr: end_addr]
        '''
        #print (self.read_iterator._addr)
        out_data = [self._data[self._select][addr_in_word - offset] for addr_in_word in self.read_iterator._addr]
        self.read_iterator.update()
        if(self._manual_switch == 0):
            self.check_switch()
        return out_data

    def write(self, data_in, offset = 0):
        '''
        write a list of data: <data_in> into virtual buffer
        '''
        assert self.write_iterator._done == 0, "No more write allowed!\n"
        if isinstance(data_in, int):
            #addr always is a list, since we are dealing with multiple port
            assert self._input_port == 1
            self._data[1-self._select][(self.write_iterator._addr[0] - offset)]\
                    = data_in
        else:
            assert len(data_in) == self._input_port, "Input data size not match port number!\n"
            wr_addr = self.write_iterator._addr
            for addr ,word_data in zip(wr_addr, data_in):
                self._data[1-self._select][addr - offset] = word_data

        self.write_iterator.update()
        if(self._manual_switch == 0):
            self.check_switch()


class AccessPattern:
    def __init__(self, _range, stride, start):
        '''
        all three variable is a list
        '''
        self._rng = _range
        self._st = stride
        self._start = start

class AccessIter(AccessPattern):
    def __init__(self, _range, stride, start, manual_switch=0):
        '''
        It will return a addr with the length equals to start_addr,
        which is also equals to the port number
        '''
        super().__init__(_range, stride, start)
        '''
        self._iter = [0 for _ in range(len(_range))]
        addr_offset = sum([i*j for i, j in zip(self._iter, self._st)])
        self._addr = [addr_offset + start_pos for start_pos in self._start]
        self._done = 0
        '''
        self.restart()
        self._manual_switch = manual_switch

    def getaddr(self):
        return self._addr

    def restart(self):
        self._iter = [0 for _ in range(len(self._rng))]
        addr_offset = sum([i*j for i, j in zip(self._iter, self._st)])
        self._addr = [addr_offset + start_pos for start_pos in self._start]
        self._done = 0
        '''
        self._iter = [0 for _ in range(len(self._rng))]
        self._done = 0
        self._addr = sum([i*j for i, j in zip(self._iter, self._st)]) + self._start

        '''

    def update(self):
        assert self._done == 0, "Error: no more read can make according to access pattern"
        for dim in range(len(self._iter)):
            self._iter[dim] += 1
            if dim > 0:
                self._iter[dim - 1] = 0
            if dim <len(self._iter) - 1:
                if self._iter[dim] < self._rng[dim]:
                    break
                elif self._rng[dim + 1] == 0:
                    self._done = 1
                    if self._manual_switch:
                        self.restart()
                    break
            else:
                if self._iter[dim] == self._rng[dim]:
                    self._done = 1
                    if self._manual_switch:
                        self.restart()
                    break
        addr_offset = sum([i*j for i, j in zip(self._iter, self._st)])
        self._addr = [addr_offset + start_pos for start_pos in self._start]



