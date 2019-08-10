from functools import reduce
class VirtualBufferConfig:
    def __init__(self, input_port, output_port, capacity, _range, stride, start=[0], manual_switch=0, arbitrary_addr=0):
        assert capacity % input_port == 0, "capacity is not divisible by input_port number!\n"
        self._input_port = input_port
        self._output_port = output_port
        self._capacity = capacity
        self._range = _range
        self._stride = stride
        self._start = start
        self._manual_switch = manual_switch
        self._arbitrary_addr = arbitrary_addr

    def pretty_print(self):
        print ("**********************************")
        print ("*The Virtual Buffer Configuration*")
        print ("**********************************")
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

class CoreIRUnifiedBufferConfig:
    def __init__(self, param_dict):
        '''
        parse the coreIR json parameter
        '''
        self.config_dict = param_dict
        self.acc_capacity = []
        self.stride_in_dim = []

    def getVirtualBufferConfig(self):
        dimension = self.config_dict["dimensionality"][1]
        stride = []
        rng = []
        input_port = self.config_dict["num_input_ports"][1]
        output_port = self.config_dict["num_output_ports"][1]
        capacity_list = self.config_dict["logical_size"][1]["capacity"]
        acc_capacity = [ reduce(lambda x, y : x*y, capacity_list[0:i+1]) for i in range(dimension) ]
        self.acc_capacity = [1] + acc_capacity
        #capacity = reduce(lambda x, y: x*y, capacity_list)
        capacity = self.acc_capacity[-1]
        start = self.config_dict["output_starting_addrs"][1]["output_start"]
        for i in range(dimension):
            stride.append(self.config_dict["stride_"+str(i)][1])
            rng.append(self.config_dict["range_"+str(i)][1])
        self.stride_in_dim = [st // acc_cap for st, acc_cap in zip(stride, self.acc_capacity)]


        return VirtualBufferConfig(input_port, output_port, capacity, rng, stride, start)


