from buffer_mapping.hardware import HardwareWire, BufferNode, RegNode, FlushNode
from buffer_mapping.util import AccessPattern
from buffer_mapping.virtualbuffer import VirtualValidBuffer

def connectValidSignal(node_dict, connection_dict, valid_node_list):
    for key, node in node_dict.items():
        if type(node) == BufferNode:
            if node.last_in_chain:
                for valid_node in valid_node_list:
                    connection_dict.update(valid_node.connectNode(node))
    return node_dict, connection_dict

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

def flattenValidBuffer(node_dict, connection_dict):
    for key, node in list(node_dict.items()):
        if type(node) == BufferNode:
            if type(node.kernel) == VirtualValidBuffer:
                if node.kernel.isPassThrough():
                    #TODO: build a graph class and make this delete node method
                    '''
                    node.pred.removeSucc(node)
                    for succ in node.succ:
                        succ.makePred(node.pred)
                        node.pred.addSucc(succ)
                    for connection in connection_dict:
                        if connection.isLinkedTo(node.name):
                    '''
                    for succ in node.succ:
                        entry_connection_dict = succ.connectNode(node.pred)
                        connection_dict.update(entry_connection_dict)
                    #remove the node connection and get the wire delete key list
                    del_connection_key_list = node.removeConnection()
                    # remove connection
                    for del_key in del_connection_key_list:
                        connection_dict.pop(del_key)
                    # delete node
                    del node_dict[key]
    return node_dict, connection_dict

def addFlush(node_dict, connection_dict):
    for key, node in list(node_dict.items()):
        if type(node) == BufferNode:
            dummy_node_name = key+"_flush"
            node_dict[dummy_node_name] = FlushNode(dummy_node_name)
            connection_dict.update(node_dict[dummy_node_name].connectNode(node))
    return node_dict, connection_dict

def banking(node_dict, connection_dict, mem_config):
    #TODO: currently it's buggy need to rewrite this not support double buffer well
    '''
    [Call this method before regOptimiztion]
    Go over the buffer node in dictionary, finding if kernel port number is larger than
    HW port number. Then this node will be divided into mutiple node with smaller port
    width and do a DFS
    '''
    new_connection_dict = {}
    new_node_dict = {}
    for key, node in node_dict.items():
        if type(node) == BufferNode:
            vbuffer = node.kernel
            def check_bank(vbuffer_):
                #check the bandwidth requirement to create banking
                input_multiplier = vbuffer_._input_port // mem_config._input_port
                output_multiplier = vbuffer_._output_port // mem_config._output_port
                num_bank = max(input_multiplier, output_multiplier)
                return num_bank
            def createBankFromNode(node):

                capacity_per_bank = node.kernel._capacity // num_bank

                if capacity_per_bank > mem_config._capacity:
                    assert True, "Need chaining which is not implemented. \n"

                #create the set of memory node and recursive connect to its successor
                banked_buffer_node = [BufferNode(node.name+"_bank_"+str(bank_id), node.kernel, num_bank)
                                      for bank_id in range(num_bank)]

                return banked_buffer_node
            num_bank = check_bank(vbuffer)
            if num_bank == 1:
                continue
            banked_buffer_node = createBankFromNode(node)
            banked_buffer_node_dict = {node.name: node for node in banked_buffer_node}
            new_node_dict.update(banked_buffer_node_dict)
            #TODO connect to input

            #FIXME: Maybe do not need thisThe DFS to create graoh
            def connect2succ(node, bank_node_list):
                for succ in node.succ:
                    if check_bank(succ) == 1:
                        continue
                    succ_banked_buffer_node = createBankFromNode(node)
                    succ_banked_buffer_node_dict = {node.name: node for node in succ_banked_buffer_node}
                    new_node_dict.update(succ_banked_buffer_node_dict)
                    for idx, (wire_in, wire_out) in enumerate(zip(banked_buffer_node, succ_banked_buffer_node)):
                       new_connection_dict.update(wire_out.connectNode(wire_in))
                    connect2succ(succ, succ_banked_buffer_node)

            connect2succ(node, banked_buffer_node_dict)
    return new_node_dict, connection_dict



