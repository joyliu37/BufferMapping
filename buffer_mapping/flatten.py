from copy import deepcopy
from functools import reduce
from buffer_mapping.config import VirtualBufferConfig

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

    #range in 1D for each iterator
    abs_range = [stride * _range for stride, _range in zip(abs_stride, access_dict['range'])]

    iteration = deepcopy(access_dict["range"])

    #walk from the lower loop up and finding the iterator could be merged
    for dim in range(len(abs_range)-1):
        if abs_range[dim] == abs_stride[dim + 1]:
            MergeIterator(abs_range, abs_stride, iteration, dim)

    SimplifyIterator(abs_range, abs_stride, iteration)

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


def MergeIterator(_range, stride, iteration, i):
    iteration[i+1] *= iteration[i]
    iteration[i] = 0
    stride[i+1] = stride[i]
    stride[i] = 0
    _range[i] = 0

def SimplifyIterator(_range, stride, iteration):
    '''
    Simplify the access iterator we merged
    condition: All 3 value is 0,
    note: There is a special situation when _range and stride is 0 but iteration is not 0,
          which is revisit the same address
    '''
    eliminate_list = []
    for idx, (r, s, t) in enumerate(zip(_range, stride, iteration)):
        if (r or s or t) == 0:
            eliminate_list.append(idx)

    for eliminate_id in eliminate_list:
        del _range[eliminate_id]
        del stride[eliminate_id]
        del iteration[eliminate_id]
