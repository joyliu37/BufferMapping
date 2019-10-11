from buffer_mapping.linebuffer import VirtualLineBuffer
from buffer_mapping.hardware import InputNode, OutputNode, OutputValidNode, BufferNode
from buffer_mapping.virtualbuffer import VirtualBuffer, VirtualDoubleBuffer

def initializeGraph(v_setup, mem_config, IR_setup,
                    output_list, valid_list, input_port, inen_port, ren_port, origin_key, enable_port_opt = True):
    node_dict = {}
    connection_dict = {}
    v_buf = v_buf = VirtualBuffer(v_setup._input_port,
                                v_setup._output_port,
                                v_setup._capacity,
                                v_setup._range,
                                v_setup._stride,
                                v_setup._start)
    print ("stride in dim", IR_setup.stride_in_dim)

    linebuffer = VirtualLineBuffer(v_buf, mem_config._input_port, mem_config._output_port, IR_setup.config_dict["logical_size"][1]['capacity'], IR_setup.stride_in_dim)

    input_node = InputNode("self",
                           input_port[0]+"."+input_port[1],
                           inen_port[0]+"."+inen_port[1],
                           ren_port[0]+"."+ren_port[1])

    if linebuffer.meta_fifo_dict and enable_port_opt:
    #if False:
        #has the port optimization and create a line buffer
        output_dict = {}
        print (linebuffer.port_map)
        output_dict_tmp = {start_addr: [OutputNode(out_instance_name[0],out_instance_name[1])] for out_instance_name, start_addr in zip(output_list, v_setup._start)}
        for start_addr, port_list in linebuffer.port_map.items():
            output_dict[start_addr] = []
            for port in port_list:
                output_dict[start_addr].append(output_dict_tmp[port])
        print (output_dict)
        #data_in = HardwarePort("self.datain", 0)
        #valid = HardwarePort("self.inen", True)
        node_dict, connection_dict = linebuffer.GenGraph(origin_key+"linebuffer", input_node, output_dict)
        print (node_dict)
    else:
        connection = {}
        node_dict = {}
        double_buffer = VirtualDoubleBuffer(v_setup)
        double_buffer_node = BufferNode(origin_key+"double_buffer", double_buffer)
        double_buffer_node.assertLastOfChain()
        connection.update(double_buffer_node.connectNode(input_node))
        node_dict[double_buffer_node.name] = double_buffer_node
        output_list = [OutputNode(out_instance_name[0], out_instance_name[1]) for i, out_instance_name in enumerate(output_list)]
        for idx, node in enumerate(output_list):
            print (node.name)
            connection_dict.update(node.connectNode(double_buffer_node, idx))

        #connect input port and connect the valid signal
        connection_dict.update(double_buffer_node.connectNode(input_node))
        double_buffer_node.last_in_chain = True

    return node_dict, connection_dict
