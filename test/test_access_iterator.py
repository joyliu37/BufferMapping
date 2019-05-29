from magma import *
from magma.clock import *
from magma.backend.coreir_ import CoreIRBackend, compile
from buffer_mapping.generator.access_iterator import DefineAccessIterator
from coreir.context import *
from magma.simulator.coreir_simulator import CoreIRSimulator
import coreir
from magma.scope import Scope
from magma.bitutils import *
from buffer_mapping.virtualbuffer import AccessIter
from functools import reduce

def test_access_iterator():
    c = coreir.Context()
    cirb = CoreIRBackend(c)
    scope = Scope()
    _range = (24, 3, 4, 4)
    stride = (1, 48, 8, 48)
    start = 0
    bit_width = 16

    testcircuit = DefineAccessIterator(_range, stride, start, bit_width)
    func_model = AccessIter(list(_range), list(stride), list((start,)))
    total_iter = reduce(lambda x, y: x*y, _range)

    sim = CoreIRSimulator(testcircuit, testcircuit.CLK, context=cirb.context)

    sim.set_value(testcircuit.CE, True, scope)

    for clock_index in range(total_iter):
        # for each cycle, input every other of first half
        '''

        if clock_index % 12 < 6 and clock_index % 2 == 0:
            sim.set_value(testcircuit.WE, True, scope)
            sim.set_value(testcircuit.I[0], int2seq(last_input, 8), scope)
            last_input += 1
        else:
            sim.set_value(testcircuit.WE, False, scope)
        sim.evaluate()

        if clock_index % 4 == 0:
            assert sim.get_value(testcircuit.valid, scope) == True
            assert seq2int(sim.get_value(testcircuit.O, scope)[0]) == last_output
            last_output += 1
        else:
            assert sim.get_value(testcircuit.valid, scope) == False
        '''
        sim.evaluate()
        hw_addr = seq2int(sim.get_value(testcircuit.ADDR, scope) )

        #sw will give a list for banking, currently just test one iterator
        #we take the first element
        sw_addr = func_model.getaddr()

        assert hw_addr == sw_addr[0]


       #print ("hw: {}, sw: {}".format(hw_addr, sw_addr))

        sim.advance_cycle()
        func_model.update()
        '''

def test_delayed_buffer_parallel():
    c = coreir.Context()
    cirb = CoreIRBackend(c)
    scope = Scope()
    testcircuit = DefineDelayedBuffer(cirb, Array[8, Bit], 4, 2, 16)

    sim = CoreIRSimulator(testcircuit, testcircuit.CLK, context=cirb.context)

    sim.set_value(testcircuit.CE, True, scope)
    last_output = 2
    last_input = 2
    # do two cycles
    for clock_index in range(32):
        # for each cycle, input every other of first half
        if clock_index % 16 < 4 and clock_index % 2 == 0:
            sim.set_value(testcircuit.WE, True, scope)
            sim.set_value(testcircuit.I[0], int2seq(last_input, 8), scope)
            sim.set_value(testcircuit.I[1], int2seq(last_input + 1, 8), scope)
            last_input += 2
        else:
            sim.set_value(testcircuit.WE, False, scope)
        sim.evaluate()

        if clock_index % 4 == 0:
            assert sim.get_value(testcircuit.valid, scope) == True
            assert seq2int(sim.get_value(testcircuit.O, scope)[0]) == last_output
            last_output += 1
        else:
            assert sim.get_value(testcircuit.valid, scope) == False
        sim.advance_cycle()
        sim.evaluate()
        '''


if __name__ == "__main__":
    test_access_iterator()
