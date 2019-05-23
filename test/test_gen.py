import sys
sys.path.insert(0,'..')
from functools import reduce
import json
import pdb

from buffer_mapping.flatten import IR2Interface
from buffer_mapping.virtualbuffer import VirtualDoubleBuffer

def test_doublebuffer():
    dir_path = '/users/joeyliu/Documents/work/DBmapping/'
    with open(dir_path+'config/testIR.json') as json_file:
        setup= json.load(json_file)
    #v_setup = setup["virtual buffer"]
    #v_buf = CreateVirtualBuffer(setup["virtual buffer"])

    IR_setup = setup['line buffer']
    v_setup = IR2Interface(IR_setup)
    v_buf = VirtualDoubleBuffer(v_setup)

    for blockid in range(3):
        for i in range(v_setup._capacity // v_setup._input_port):
            tmp = [i*v_setup._input_port + j for j in range(v_setup._input_port)]
            v_buf.write(tmp)
        print("Finish write to buffer, switch 2 banks.")

        read_iteration = reduce((lambda x, y: x * y), v_setup._range)
        read_stream = []
        for i in range(read_iteration):
            data_out = v_buf.read()
            read_stream.append(data_out)

        print ("Virtual buffer read stream: ", read_stream)

    #one extra read, uncomment will lead error
    #print ("Hardware buffer read: ", mem_tile_hw.read())


if __name__ == '__main__':
    test_doublebuffer()
