from buffer_mapping.hardware import HardwareWire, BufferNode, RegNode

def regOptmization(node_dict, connection_dict):
    for key, node in node_dict.items():
        if type(node) == BufferNode:
            #TODO: adding a bank parameter for virtual buffer
            fifo_size = node.kernel._capacity // node.kernel._input_port
            if fifo_size == 1:
                new_node = RegNode(node.name, node.kernel)
                new_node.connect(node, connection_dict)
                node_dict[key] = new_node
    return node_dict, connection_dict
