import sys
sys.path.insert(0,'..')
from functools import reduce
import json
import pdb

from buffer_mapping.config import IR2Interface

def test_flatten():
    dir_path = '/users/joeyliu/Documents/work/mapper/DBmapping/'
    with open(dir_path+'config/testIR.json') as json_file:
        setup= json.load(json_file)

    for key, buffer_setup in setup.items():
        vbuf_config = IR2Interface(buffer_setup)
        print("\n-----buffer params----\nname: {}".format(key))
        vbuf_config.pretty_print()


if __name__ == '__main__':
    test_flatten()
