class VirtualBufferConfig:
    def __init__(self, input_port, output_port, capacity, _range, stride, start=[0], manual_switch=0):
        assert capacity % input_port == 0, "capacity is not divisible by input_port number!\n"
        assert capacity % output_port == 0, "capacity is not divisible by output_port number!\n"
        self._input_port = input_port
        self._output_port = output_port
        self._capacity = capacity
        self._range = _range
        self._stride = stride
        self._start = start
        self._manual_switch = manual_switch

    def pretty_print(self):
        print ("Input Port:", self._input_port)
        print ("Output Port:", self._output_port)
        print ("Capacity:", self._capacity)
        print ("Range:", self._range)
        print ("Stride:",self._stride)
        print ("Start Addr:", self._start)
        print ("Manual Switch:", self._manual_switch)

    #def write_json(self, filename):


class HWBufferConfig:
    def __init__(self, input_port, output_port, capacity):
        self._input_port = input_port
        self._output_port = output_port
        self._capacity = capacity

