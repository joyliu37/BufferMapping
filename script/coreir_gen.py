import sys
import os
sys.path.insert(0,'..')
import json

from buffer_mapping.flatten import IR2Interface
from buffer_mapping.virtualbuffer import VirtualBuffer
from buffer_mapping.linebuffer import VirtualLineBuffer
from buffer_mapping.hardware import InputNode, OutputNode, OutputValidNode
from buffer_mapping.rewrite import connectValidSignal, regOptmization, banking, flattenValidBuffer
from buffer_mapping.mapping import CreateHWConfig
from buffer_mapping.config import CoreIRUnifiedBufferConfig


def preprocessCoreIR(hand_craft):
    #TODO: make this a method, parse the input coreIR get the buffer module, get the input port and output port, and put them in a dictionary
    core = hand_craft["namespaces"]["global"]["modules"]["DesignTop"]
    instance = core["instances"]
    connection = core["connections"]
    valid_list = []
     #remove reg and general buffer
    for key, value in list(instance.items()):
        if value.get("genref"):
            if value["genref"] == "commonlib.unified_buffer":
                #get the unified_buffer node
                buffer_config = CoreIRUnifiedBufferConfig(value["genargs"])
                v_buf_config = buffer_config.getVirtualBufferConfig()
                v_buf_config.pretty_print()

                new_connection = [wire for wire in core["connections"] if key != wire[0].split(".")[0] and key != wire[1].split(".")[0]]
                valid_list = []
                output_list = []
                input_port = []
                inen_port = []
                for wire in core["connections"]:
                    def findConnection(name):
                        target_list = []
                        if wire[0].split(".")[0] == key and wire[0].split(".")[1] == name:
                            target_list.append((wire[1].split(".", 1)[0], wire[1].split(".", 1)[1]))
                        elif wire[1].split(".")[0] == key and wire[1].split(".")[1] == name:
                            target_list.append((wire[0].split(".", 1)[0], wire[0].split(".", 1)[1]))
                        return target_list
                    valid_list.extend(findConnection("valid"))
                    output_list.extend(findConnection("dataout"))
                    input_port.extend(findConnection("datain"))
                    inen_port.extend(findConnection("wen"))

                core["connections"] = new_connection
                del instance[key]
    connection = core["connections"]
    return buffer_config, v_buf_config, instance, connection , valid_list, output_list, input_port[0], inen_port[0]



def test_linebuffer():
    dir_path = os.path.dirname(os.path.realpath(__file__))
    with open(dir_path+'/HWConfig.json') as setup_file:
        setup = json.load(setup_file)
    with open(dir_path+'/coreir_input.json') as coreir_file:
        input_coreir = json.load(coreir_file)
    mem_config = CreateHWConfig(setup["hw config"])

    with open(dir_path + '/output/output_coreir_golden.json' , 'w') as json_out_file:
        data = json.dumps(input_coreir, indent=4)
        json_out_file.write(data)
    print("Json File dump to " + dir_path +"/output")
    IR_setup, v_setup, instance, connection, valid_list, output_list, input_port, inen_port = preprocessCoreIR(input_coreir)

        #v_setup = IR2Interface(IR_setup)
    v_buf = VirtualBuffer(v_setup._input_port,
                              v_setup._output_port,
                              v_setup._capacity,
                              v_setup._range,
                              v_setup._stride,
                              v_setup._start)

    #define what underline hw like
    #TODO: make this a rewrite pass
    linebuffer = VirtualLineBuffer(v_buf, mem_config._input_port, mem_config._output_port, IR_setup.config_dict["logical_size"][1]['capacity'], IR_setup.stride_in_dim)
    #print (output_list, valid_list)

    output_dict = {}
    output_dict[0] = [[OutputNode(out_instance_name[0],out_instance_name[1]+"."+str(i)) for out_instance_name in output_list] for i in range(v_setup._output_port)]
    valid_node_list = [OutputValidNode(valid_instance_name[0], valid_instance_name[1]) for valid_instance_name in valid_list]
    #data_in = HardwarePort("self.datain", 0)
    #valid = HardwarePort("self.inen", True)
    input_node = InputNode("self", input_port[0]+"."+input_port[1]+'.0', inen_port[0]+"."+inen_port[1])
    node_dict, connection_dict = linebuffer.GenGraph("linebuffer", input_node, output_dict)

    #set of compiler pass optimize the graph
    node_dict, connection_dict = flattenValidBuffer(node_dict, connection_dict)
    node_dict, connection_dict = regOptmization(node_dict, connection_dict)
    node_dict, connection_dict = connectValidSignal(node_dict, connection_dict, valid_node_list)
    #node_dict, connection_dict = banking(node_dict, connection_dict, mem_config)

    connection_list = [[key[0], key[1]] for key, _ in connection_dict.items()]

    node_list_dict = {}
    for key, node in node_dict.items():
        instance.update({node.name: node.dump_json()})
        element = {}
        if node.pred:
            element["pred"] = node.pred.name
        element["succ"] = [succ.name for succ in node.succ]
        node_list_dict.update({key: element})
    print (node_list_dict)
    print (connection_list)
    #print (instance)
    connection.extend(connection_list)
    '''
    dump the generated coreIR file
    '''
    with open(dir_path + '/output/output_coreir.json' , 'w') as json_out_file:
        data = json.dumps(input_coreir, indent=4)
        json_out_file.write(data)
    print("Json File dump to " + dir_path +"/output")

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
    print("Internal Fucntionality test passed.")

if __name__ == '__main__':
    test_linebuffer()
