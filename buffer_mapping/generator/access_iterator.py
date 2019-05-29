from typing import List
from aetherling.helpers.nameCleanup import cleanName
from magma import *
from magma.backend.coreir_ import CoreIRBackend
from mantle import DefineCoreirConst, Add, Mul
from mantle.common.countermod import CounterModM
from functools import reduce

__all__ = ['DefineAccessIterator', 'AccessIterator']

@cache_definition
def DefineAccessIterator(_range: tuple, stride: tuple, start: int, bit_width: int):
    """
    Access Pattern generator that emits the address you are visiting
    if it goes to the last iteration, the done signal will go to high
    All the address space is set to 16 bit, to prevent overflow.
    CE : In(Bit),  addr : Out(Uint[bit_width])
    """


    class _AccessIterator(Circuit):

        #valid check
        if len(_range) != len(stride):
            raise Exception("The access pattern configuration should have same dimension."
                            "while range have dim={}, stride have dim={}."
                            .format(len(_range), len(stride)))

        name = 'AccessIterator_{}D'.format(len(_range))
        IO = ['ADDR', Out(UInt[bit_width]), 'DONE', Out(Bit)] + ClockInterface(has_ce=True) + ['debug', Out(UInt[bit_width])]
        @classmethod
        def definition(cls):
            '''
            valid_counter = SizedCounterModM(num_clocks_delay + 1, has_ce=True)
            delay_const = DefineCoreirConst(len(valid_counter.O), num_clocks_delay)()
            wire(enable(bit(cls.CE) & (valid_counter.O < delay_const.O)), valid_counter.CE)
            wire(valid_counter.O == delay_const.O, cls.valid)
            '''
            iter_dim = len(_range)

            if iter_dim == 1:
                iter_counter = CounterModM(n=iter_range[0]*stride[0], m=bit_width, cout=False, has_ce=True, incr=stride[0])
                #what if i did not call bit.()
                wire(bit(cls.CE), iter_counter.CE)
                wire(cls.ADDR, iter_counter.O)
            else:
                #define all the range comparator
                iter_counter_list = [ CounterModM(iter_range, bit_width, cout=False, has_ce=True)
                                    for iter_range in _range ]
                range_const_list = [ DefineCoreirConst(bit_width, iter_range-1)()
                                    for iter_counter, iter_range
                                    in zip(iter_counter_list, _range) ]
                stride_const_list = [ DefineCoreirConst(bit_width, stride_range)()
                                    for iter_counter, stride_range
                                    in zip(iter_counter_list, stride) ]
                print (type(iter_counter_list[0]))
                wire(bit(cls.CE), iter_counter_list[0].CE)

                #create the logic to update the CE port in counter chain
                for i in range(len(_range) - 1):
                    wire(reduce(lambda x, y: x&y,
                                [
                                    iter_counter.O == range_const.O
                                    for iter_counter, range_const
                                    in zip(iter_counter_list[0:i+1], range_const_list[0:i+1])
                                 ]
                                ),
                         iter_counter_list[i+1].CE
                         )

                #TODO:Possible bug, if we achieve done we should frozen the iterator
                wire(reduce(lambda x, y: x&y,
                            [
                                iter_counter.O == range_const.O
                                for iter_counter, range_const
                                in zip(iter_counter_list, range_const_list)
                            ]
                            ),
                     bit(cls.DONE)
                     )

                #create the adder and multiplier chain, we need <dim-1> adder and >dim> mul
                multiplier_list = [Mul(len(iter_counter.O)) for iter_counter in iter_counter_list]
                adder_list = [Add(len(mul.O)) for mul in multiplier_list[0: -1]]

                #create the first counter
                wire(iter_counter_list[0].O, multiplier_list[0].I0)
                wire(stride_const_list[0].O, multiplier_list[0].I1)
                wire(multiplier_list[0].O, adder_list[0].I1)

                #create the following couter chain
                for i in range(len(iter_counter_list)-1):
                    wire(iter_counter_list[i + 1].O, multiplier_list[i + 1].I0)
                    wire(stride_const_list[i + 1].O, multiplier_list[i + 1].I1)
                    wire(multiplier_list[i+1].O, adder_list[i].I0)
                    if i > 0:
                        wire(adder_list[i-1].O, adder_list[i].I1)

                #wire output
                wire(adder_list[-1].O, cls.ADDR)
                wire(multiplier_list[2].O, cls.debug)

    return _AccessIterator

def AccessIterator(_range: tuple, stride: tuple, start: int = 0, bit_width: int = 16):
    return DefineAccessIterator(_range, stride, start, bit_width)()
