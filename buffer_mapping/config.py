from functools import reduce
from buffer_mapping.flatten import EliminateRedundancyForAccessPattern, FlattenAccessPattern

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

        #dimensionality is the number of loop iterator instead of dimension of the buffer

        stride = []
        rng = []
        input_port = self.config_dict["num_input_ports"][1]
        output_port = self.config_dict["num_output_ports"][1]
        capacity_list = self.config_dict["logical_size"][1]["capacity"]
        capacity_dimension = len(capacity_list)
        acc_capacity = [ reduce(lambda x, y : x*y, capacity_list[0:i+1]) for i in range(capacity_dimension) ]
        self.acc_capacity = [1] + acc_capacity
        #capacity = reduce(lambda x, y: x*y, capacity_list)
        capacity = self.acc_capacity[-1]
        start = self.config_dict["output_starting_addrs"][1]["output_start"]
        for i in range(dimension):
            stride.append(self.config_dict["stride_"+str(i)][1])
            rng.append(self.config_dict["range_"+str(i)][1])
        rng, stride = EliminateRedundancyForAccessPattern(rng, stride)
        print (rng, stride)
        self.stride_in_dim = [st // acc_cap for st, acc_cap in zip(stride, self.acc_capacity)]


        return VirtualBufferConfig(input_port, output_port, capacity, rng, stride, start)

    def getVirtualBufferConfigNew(self):
        #input_port = self.config_dict["istream"][1]["input"]["num_input_ports"]
        input_port = 1
        capacity_list = self.config_dict["logical_size"][1]["capacity"]
        capacity_dimension = len(capacity_list)
        acc_capacity = [ reduce(lambda x, y : x*y, capacity_list[0:i+1]) for i in range(capacity_dimension) ]
        self.acc_capacity = [1] + acc_capacity
        capacity = self.acc_capacity[-1]
        out_streams = self.config_dict["ostreams"][1]
        out_access_pattern = {}
        assert len(out_access_pattern.items()) <= 1, "Not Support more than one stream now"
        for key, out_stream in out_streams.items():
            start = out_stream["output_starting_addrs"]
            output_port = out_stream["num_output_ports"]
            stride = out_stream["output_stride"]
            rng = out_stream["output_range"]
            rng, stride = EliminateRedundancyForAccessPattern(rng, stride)
            out_access_pattern[key] = {"start": start, "stride": stride, "range": rng, "port_width": output_port}
            self.stride_in_dim = [st // acc_cap for st, acc_cap in zip(stride, self.acc_capacity)]

        return {key: VirtualBufferConfig(input_port, dic["port_width"], capacity, dic["range"], dic["stride"], dic["start"]) \
                for key, dic in out_access_pattern.items()}

def IR2Interface(setup):
    '''
    The function mapping halide IR buffer parameter to
    1D memory tile interface, which doing 2 steps
    1. Flatten access pattern into 1D and merge iterator
    recursively
    2. Change high dimensional data cube into 1D
    '''

    #get the stride of iteration in each dimension
    accumulate_dim = [ reduce(lambda x, y: x*y, setup['capacity'][0:i+1]) \
                      for i in range(len(setup['capacity']) - 1)]
    accumulate_dim = [1] + accumulate_dim


    #check the input legality
    access_dict = setup['access_pattern']
    assert len(access_dict["range"]) == len(access_dict["ref_dim"]), \
        "Check json file, range length not equal to ref_dim"
    assert len(access_dict["range"]) == len(access_dict["stride_in_dim"]),\
        "Check json file, range length not equal to stride in dim"

    #Calculate absolute stride in 1D for each iterator
    abs_stride = [ accumulate_dim[ref_dim] * stride_in_dim \
              for ref_dim, stride_in_dim \
              in zip(access_dict['ref_dim'], access_dict['stride_in_dim'])]

    '''
    #range in 1D for each iterator
    abs_range = [stride * _range for stride, _range in zip(abs_stride, access_dict['range'])]

    iteration = deepcopy(access_dict["range"])

    #walk from the lower loop up and finding the iterator could be merged
    for dim in range(len(abs_range)-1):
        if abs_range[dim] == abs_stride[dim + 1]:
            MergeIterator(abs_range, abs_stride, iteration, dim)

    SimplifyIterator(abs_range, abs_stride, iteration)

    '''
    iteration, abs_stride = FlattenAccessPattern(access_dict['range'], abs_stride)

    input_port_1D = reduce(lambda x, y: x*y, setup["input_port"])
    output_port_1D = reduce(lambda x, y: x*y, setup["output_port"])
    capacity_1D = reduce(lambda x, y: x*y, setup["capacity"])

    #caculate the start position for output_port
    start_addr = [0]
    for dim, port_in_dim in enumerate(setup['output_port']):
        start_addr_addition = [start * accumulate_dim[dim] for start in range(port_in_dim)
                               for _ in range(len(start_addr))]
        start_addr = [x + y for x, y in zip(start_addr * port_in_dim, start_addr_addition)]

    return VirtualBufferConfig(input_port_1D, output_port_1D, capacity_1D, iteration, abs_stride, start_addr)
