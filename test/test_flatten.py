import sys
sys.path.insert(0,'..')
from functools import reduce
import json
import pdb

from buffer_mapping.flatten import IR2Interface

def test_flatten():
    dir_path = '/users/joeyliu/Documents/work/DBmapping/'
    with open(dir_path+'config/testIR.json') as json_file:
        setup= json.load(json_file)

    for key, buffer_setup in setup.items():
        vbuf_config = IR2Interface(buffer_setup)
        print("\n-----buffer params----\nname: {}".format(key))
        vbuf_config.pretty_print()

'''
    for i in range(v_setup['capacity'] // v_setup['input_port']):
        tmp = [i*v_setup['input_port'] + j for j in range(v_setup['input_port'])]
        v_buf.write(tmp)
    print("Finish write to buffer, switch 2 banks.")

    read_iteration = reduce((lambda x, y: x * y), v_setup['access_pattern']['range'])
    read_stream = []
    for i in range(read_iteration):
        data_out = v_buf.read()
        read_stream.extend(data_out)

    print ("Virtual buffer read stream: ", read_stream)

    #one extra read, uncomment will lead error
    #print ("Hardware buffer read: ", mem_tile_hw.read())
'''

if __name__ == '__main__':
    test_flatten()
