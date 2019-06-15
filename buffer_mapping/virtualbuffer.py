from buffer_mapping.config import VirtualBufferConfig
from buffer_mapping.util import AccessIter, Counter

class VirtualBuffer:
    def __init__(self, input_port, output_port, capacity, _range, stride, start, manual_switch=0, arbitrary_addr=0):
        '''
        The base class of double buffer and line buffer, a dual port sram
        Has method read and write, has a valid field which prevent read before write
        '''
        self._input_port = input_port
        self._output_port = output_port
        self._capacity = capacity
        self.read_iterator = AccessIter(_range, stride, start, manual_switch)
        self.write_iterator = AccessIter([capacity / input_port], [input_port], list(range(input_port)), manual_switch)
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
            assert len(data_in) == self._input_port, "Input data size not match port number!\n"
            wr_addr = self.write_iterator._addr
            for addr ,word_data in zip(wr_addr, data_in):
                write_bank[(addr - offset) % self._capacity] = word_data
        self.write_iterator.update()
        if(self._manual_switch == 0):
            self.check_switch()

class VirtualDoubleBuffer(VirtualBuffer):

    def __init__(self, *args, **kwargs):
        if len(args) == 1:
            self.initFromConfig(args[0])
        else:
            self.initFromParams(*args)

    def initFromParams(self, input_port, output_port, capacity, _range, stride, start, manual_switch=0, arbitrary_addr=0):
        assert capacity % input_port == 0, "capacity is not divisible by input_port number!\n"
        assert capacity % output_port == 0, "capacity is not divisible by output_port number!\n"
        super().__init__(input_port, output_port, capacity, _range, stride, start, manual_switch)
        self._bank_num = 2
        self._select = 0
        #no read need for empty buffer
        self.read_iterator._done = 1
        # Rewrite data domain to be multiple bank
        self._data = [[65535 for _ in range(self._capacity)] for _ in range(self._bank_num)]

    # Another object constructor from config
    def initFromConfig(self, config:VirtualBufferConfig):
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




