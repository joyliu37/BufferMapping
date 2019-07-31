import sys
import os
sys.path.insert(0,'..')
import json

from buffer_mapping.flatten import IR2Interface
from buffer_mapping.virtualbuffer import VirtualBuffer
from buffer_mapping.linebuffer import VirtualLineBuffer
from buffer_mapping.hardware import HardwarePort
from buffer_mapping.rewrite import regOptmization

def test_linebuffer():
    dir_path = os.path.dirname(os.path.realpath(__file__))
    with open(dir_path+'/../config/test_linebuffer.json') as json_file:
        setup= json.load(json_file)
    #v_setup = setup["virtual buffer"]
    #v_buf = CreateVirtualBuffer(setup["virtual buffer"])

    for key, IR_setup in setup.items():
        if key != "2D line buffer":
            continue
        v_setup = IR2Interface(IR_setup)
        v_buf = VirtualBuffer(v_setup._input_port,
                              v_setup._output_port,
                              v_setup._capacity,
                              v_setup._range,
                              v_setup._stride,
                              v_setup._start)

        #define what underline hw like
        hw_input_port = 1
        hw_output_port = 1
        linebuffer = VirtualLineBuffer(v_buf, hw_input_port, hw_output_port, IR_setup['capacity'], IR_setup['access_pattern']['stride_in_dim'])

        with open(dir_path + '/../config/conv_3_3_handcraft.json') as hand_craft_json:
            hand_craft = json.load(hand_craft_json)
        '''
        core = hand_craft["namespaces"]["global"]["modules"]["DesignTop"]
        instance = core["instances"]
        connection = core["connections"]
        def preprocessHandCraftJson():
            mul_list = []
            #remove reg and general buffer
            for key, value in list(instance.items()):
                if value.get("genref"):
                    if value["genref"] == "coreir.reg" or value["genref"] == "commonlib.unified_buffer":
                        core["connections"] = [wire for wire in core["connections"] if key not in wire[0] and key not in wire[1]]
                        del instance[key]

                #get multiplier list
                if "mul" in key:
                    mul_list.append(key)
            return mul_list
        mul_list = preprocessHandCraftJson()
        print(mul_list)

        reversed_mul_list = [mul for mul  in reversed(mul_list)]
        new_buffer_dict = linebuffer.dump_json("linebuffer", "self.in_arg_0_0_0", "self.in_en", reversed_mul_list)
        instance.update(new_buffer_dict["instances"])
        core["connections"].extend(new_buffer_dict["connections"])
        '''

        data_in = HardwarePort("self.datain", 0)
        valid = HardwarePort("self.inen", True)
        node_dict, connection_dict = linebuffer.GenGraph("linebuffer", data_in, valid)

        #set of compiler pass optimize the graph
        node_dict, connection_dict = regOptmization(node_dict, connection_dict)
        #node_dict, connection_dict = Banking(node_dict, connection_dict)

        connection_list = [(key[0], key[1]) for key, _ in connection_dict.items()]

        print (node_dict, connection_list)
        '''
        dump the generated coreIR file
        with open(dir_path + '/../config/lb_coreir.json' , 'w') as json_out_file:
            data = json.dumps(hand_craft, indent=4)
            json_out_file.write(data)
        '''

        for blockid in range(3):
            for i in range(v_setup._capacity // v_setup._input_port):
                tmp = [i*v_setup._input_port + j for j in range(v_setup._input_port)]
                #print (tmp)
                v_buf.write(tmp)
                valid, data_out = linebuffer.read_write(tmp)
                if valid:
                    data_out_ref = v_buf.read()
                    assert data_out_ref== data_out,\
                    "Data read is not matched, \nLine buffer read data ="+ str(data_out) + "\n, virtual buffer read data = " + str(data_out_ref)
                    #print (data_out_ref)
            #print("Finish read all data from line buffer, move to the next tile.")
        print("Finish test for", key)

if __name__ == '__main__':
    test_linebuffer()
