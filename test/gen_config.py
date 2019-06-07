import sys
sys.path.insert(0, '..')
from functools import reduce
import json
import pdb

from buffer_mapping.mapping import *
from buffer_mapping.pretty_print import MyEncoder

def test_buffer_mapping():
    dir_path = '/Users/joeyliu/Documents/work/Mapper/DBmapping/'
    with open(dir_path+'config/simpleMM.json') as json_file:
        setup= json.load(json_file)
    v_setup = {}
    v_setup.update({"input_buffer": setup["input buffer"]})
    v_setup.update({"weight_buffer": setup["weight buffer"]})
    v_setup.update({"output_buffer": setup["output buffer"]})
    hw_setup = setup["hw config"]
    output_json_dict = {}

    for key, buffer_setup in v_setup.items():
        v_buf = CreateVirtualBuffer(buffer_setup)
        mem_tile_config = CreateHWConfig(hw_setup)
        mem_tile_hw = HWMap(v_buf, mem_tile_config)

    #buf = VirtualDoubleBuffer(16, 16, 34*34*32, [6,3,32,32], [1, 68, 2, 68], 0)
    #mem_tile_config = HWBufferConfig(1, 1, 512)

        output_json_dict[key] = mem_tile_hw.dump_json()

        for i in range(buffer_setup['capacity'] // buffer_setup['input_port']):
            tmp = [i*buffer_setup['input_port'] + j for j in range(buffer_setup['input_port'])]
            v_buf.write(tmp)
            mem_tile_hw.write(tmp)
        print("Finish write to buffer, switch 2 banks.")

        read_iteration = reduce((lambda x, y: x * y), buffer_setup['access_pattern']['range'])
        for i in range(read_iteration):
            if v_buf.read() != mem_tile_hw.read():
                print ("Virtual buffer read: ", v_buf.read())
                print ("Hardware buffer read: ", mem_tile_hw.read())

        print ("Read match between <hw buffer> and <virtual buffer>.\n")

    with open(dir_path + 'config/mm_mem.json', 'w') as out_file:
        data = json.dumps(output_json_dict, cls=MyEncoder, indent=4, separators=(',', ': '))
        out_file.write(data)

if __name__ == '__main__':
    test_buffer_mapping()
