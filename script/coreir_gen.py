import sys
import os
sys.path.insert(0,'..')
import json
import argparse
import copy

from buffer_mapping.virtualbuffer import VirtualBuffer
from buffer_mapping.linebuffer import VirtualLineBuffer
from buffer_mapping.hardware import InputNode, OutputNode, OutputValidNode, SelectorNode, HardwareNode
from buffer_mapping.graph import initializeGraph
from buffer_mapping.rewrite import connectValidSignal, regOptmization, banking, flattenValidBuffer, addFlush
from buffer_mapping.mapping import CreateHWConfig
from buffer_mapping.config import CoreIRUnifiedBufferConfig


def processCoreIR(hand_craft, hw_setup):
    #get memory configuration
    mem_config = CreateHWConfig(hw_setup["hw config"])

    #TODO: make this a method, parse the input coreIR get the buffer module, get the input port and output port, and put them in a dictionary
    core = hand_craft["namespaces"]["global"]["modules"]["DesignTop"]
    instance = core["instances"]
    instance_iterate = copy.deepcopy(instance)
    connection = core["connections"]
     #remove reg and general buffer
    for key, value in list(instance_iterate.items()):
        if value.get("genref"):
            if value["genref"] == "commonlib.abstract_unified_buffer":
                del instance[key]

            elif value["genref"] == "commonlib.unified_buffer":
                #get the unified_buffer node
                buffer_config = CoreIRUnifiedBufferConfig(value["genargs"])
                v_buf_config = buffer_config.getVirtualBufferConfig()
                v_buf_config.pretty_print()

                new_connection = [wire for wire in core["connections"] if key != wire[0].split(".")[0] and key != wire[1].split(".")[0]]
                valid_list = []
                output_list = []
                input_port = []
                inen_port = []

                #add ren port for cases that wiring ren
                ren_port = []

                for wire in core["connections"]:
                    def findConnection(name):
                        target_list = []
                        if wire[0].split(".")[0] == key and (name in wire[0].split(".")[1]):
                            target_list.append((wire[1].split(".", 1)[0], wire[1].split(".", 1)[1]))
                        elif wire[1].split(".")[0] == key and (name in wire[1].split(".")[1]):
                            target_list.append((wire[0].split(".", 1)[0], wire[0].split(".", 1)[1]))
                        return target_list
                    valid_list.extend(findConnection("valid"))
                    output_list.extend(findConnection("dataout"))
                    input_port.extend(findConnection("datain"))
                    inen_port.extend(findConnection("wen"))
                    ren_port.extend(findConnection("ren"))
                #create a dictr for all the rewrite information
                buf_data = {}
                buf_data["valid_list"] = valid_list
                buf_data["output_list"] = output_list
                buf_data["input_port"] = input_port[0]
                buf_data["inen_port"] = inen_port[0]
                if len(ren_port) == 1:
                    buf_data["ren_port"] = ren_port[0]
                else:
                    buf_data["ren_port"] = buf_data["inen_port"]
                buf_data["config"] = buffer_config
                buf_data["v_config"] = v_buf_config

                def rewritePass(key, data_dict):
                    valid_node_list = [OutputValidNode(valid_instance_name[0], valid_instance_name[1]) for valid_instance_name in data_dict["valid_list"]]

                    node_dict, connection_dict = initializeGraph(data_dict["v_config"], mem_config, data_dict["config"], data_dict["output_list"], data_dict["valid_list"], data_dict["input_port"], data_dict["inen_port"], data_dict["ren_port"], key)

                    #set of compiler pass optimize the graph
                    capacity_per_dim = data_dict["config"].config_dict["logical_size"][1]['capacity']
                    node_dict, connection_dict = banking(node_dict, connection_dict, mem_config, data_dict["config"].acc_capacity, capacity_per_dim)
                    node_dict, connection_dict = flattenValidBuffer(node_dict, connection_dict)
                    node_dict, connection_dict = regOptmization(node_dict, connection_dict)
                    node_dict, connection_dict = connectValidSignal(node_dict, connection_dict, valid_node_list)
                    node_dict, connection_dict = addFlush(node_dict, connection_dict)

                    #create connection list
                    connection_list = [[key[0], key[1]] for key, _ in connection_dict.items()]

                    #update instance and connections
                    for key, node in node_dict.items():
                        if node.contain_node:
                            bank_selector, internal_connection = node.dump_json()
                            print (bank_selector)
                            instance.update(bank_selector)
                            connection_list.extend(internal_connection)
                        else:
                            instance.update({node.name: node.dump_json()})
                        element = {}

                        if type(node) == HardwareNode:
                            if node.pred:
                                element["pred"] = node.pred.name
                            element["succ"] = [succ.name for succ in node.succ]
                    #print (connection_list)
                    #print (instance)
                    new_connection.extend(connection_list)


                rewritePass(key, buf_data)

                #write into the dict
                #rewrite_dict[key] = buf_data

                core["connections"] = new_connection
                del instance[key]
    connection = core["connections"]
    return instance, connection



def test_buffer_mapping():
    parser = argparse.ArgumentParser()
    parser.add_argument("file_dir", help="input coreir file", type=str)
    args = parser.parse_args()
    dir_path = os.path.dirname(os.path.realpath(__file__))
    with open(dir_path+'/HWConfig.json') as setup_file:
        setup = json.load(setup_file)
    with open(args.file_dir) as coreir_file:
        input_coreir = json.load(coreir_file)

    with open(dir_path + '/output/output_coreir_golden.json' , 'w') as json_out_file:
        data = json.dumps(input_coreir, indent=4)
        json_out_file.write(data)
    print("Json File dump to " + dir_path +"/output")
    #IR_setup, v_setup, instance, connection, valid_list, output_list, input_port, inen_port = preprocessCoreIR(input_coreir)
    instance, connection = processCoreIR(input_coreir, setup)

    #define what underline hw like
    '''
    dump the generated coreIR file
    '''
    with open(dir_path + '/output/output_coreir.json' , 'w') as json_out_file:
        data = json.dumps(input_coreir, indent=4)
        json_out_file.write(data)
    print("Json File dump to " + dir_path +"/output")


if __name__ == '__main__':
    test_buffer_mapping()
