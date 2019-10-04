from copy import deepcopy

def EliminateRedundancyForAccessPattern(acc_range, acc_stride):
    eliminate_list = []
    for dim, acc_range_per_dim in enumerate(acc_range):
        if acc_range_per_dim == 1:
            eliminate_list.append(dim)

    for eliminate_id in reversed(eliminate_list):
        del acc_range[eliminate_id]
        del acc_stride[eliminate_id]

    return acc_range, acc_stride


def FlattenAccessPattern(acc_range, acc_stride):
    #range in 1D for each iterator
    abs_range = [stride * _range for stride, _range in zip(acc_stride, acc_range)]

    iteration = deepcopy(acc_range)
    stride = deepcopy(acc_stride)

    #walk from the lower loop up and finding the iterator could be merged
    for dim in range(len(abs_range)-1):
        if abs_range[dim] == stride[dim + 1]:
            MergeIterator(abs_range, stride, iteration, dim)

    SimplifyIterator(abs_range, stride, iteration)

    return iteration, stride


def MergeIterator(_range, stride, iteration, i):
    iteration[i+1] *= iteration[i]
    iteration[i] = 1
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
        if t == 1:
            eliminate_list.append(idx)

    #delete from back to the beginning
    for eliminate_id in reversed(eliminate_list):
        del _range[eliminate_id]
        del stride[eliminate_id]
        del iteration[eliminate_id]
