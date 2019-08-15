from buffer_mapping.hardware import HardwareWire, BufferNode, RegNode, FlushNode, SelectorNode, ValidGenNode
from buffer_mapping.util import AccessPattern
from buffer_mapping.virtualbuffer import VirtualValidBuffer, VirtualRowBuffer
from functools import reduce
import copy

def connectValidSignal(node_dict, connection_dict, valid_node_list):
    for key, node in node_dict.items():
        #FIXME: cannot support multiple output valid
        if type(node) == BufferNode:
            if node.last_in_chain:
                for valid_node in valid_node_list:
                    connection_dict.update(valid_node.connectNode(node))
        elif type(node) == ValidGenNode:
            for valid_node in valid_node_list:
                connection_dict.update(valid_node.connectNode(node))
    return node_dict, connection_dict

def regOptmization(node_dict, connection_dict):
    new_node_dict = {}
    for key, node in node_dict.items():
        if type(node) == BufferNode:
            #TODO: adding a bank parameter for virtual buffer
            fifo_size = node.kernel._capacity // node.kernel._input_port
            if fifo_size == 1:
                new_node = RegNode(node.name, node.kernel)
                new_node.connect(node, connection_dict)
                node_dict[key] = new_node
                if type(new_node.pred.kernel) != VirtualRowBuffer and new_node.pred.kernel:
                    #Add the valid logic
                    print (new_node.pred.name)
                    valid_gen = ValidGenNode(key+"_val_gen", new_node.stencil_delay-1, new_node.counter_bound)
                    new_node_dict[valid_gen.name] = valid_gen
                    connection_dict.update(valid_gen.connectNode(new_node.pred))
    node_dict.update(new_node_dict)
    return node_dict, connection_dict

def flattenValidBuffer(node_dict, connection_dict):
    for key, node in list(node_dict.items()):
        if type(node) == BufferNode:
            if type(node.kernel) == VirtualValidBuffer:
                if node.kernel.isPassThrough():
                    print ("Flatten Valid buffer!")
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
'''

def chaining(node_dict, connection_dict, mem_config):
    #FIXME not finish this chaining pass
    new_connection_dict = {}
    new_node_dict = {}
    for key, node in node_dict.items():
        if type(node) == BufferNode:
            vbuffer = node.kernel
            if vbuffer._capacity > mem_config._capacity:
                #TODO: add rewrite rule if cannot divisible need to rewrite the access pattern
                assert mem_config._capacity % vbuffer._capacity == 0, "virtual capacity must large than memtile capacit."
                chain_num = vbuffer._capacity // mem_config._capacity
                for chain_id in range(chain_num):
                   chain_buffer = copy.deep_copy(node.kernel)
                   chain_buffer._chain_en = True
                   chain_buffer._chain_id = chain_id
                   chain_node = BufferNode(node.name+"_chain_"+str(chain_id), chain_buffer)
                   new_node_dict[chain_node.name] = chain_node
                   new_connection_dict.update(chain_node.coonectNode(node.pred))
                   if chain_id > 0:
                       new_connection_dict.update(chain_node.connectChainNode(new_node_dict[node.name +"_chain_"+str(chain_id-1)]))
                       #TODO: finish this method
'''


def banking(node_dict, connection_dict, mem_config, acc_capacity, capacity_per_dim):
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

                def check_bank_for_dim(iterator, capacity_prev_dim, capacity_this_dim):
                    cnt = 0
                    for start_addr in iterator._start:
                        if start_addr // capacity_this_dim == 0 and (start_addr+1) // capacity_prev_dim > 0:
                            cnt += 1
                    return cnt

                print (acc_capacity)
                read_bank_per_dim = [check_bank_for_dim(vbuffer_.read_iterator, acc_capacity[i], acc_capacity[i+1]) for i in range(len(capacity_per_dim))]
                write_bank_per_dim = [check_bank_for_dim(vbuffer_.write_iterator, acc_capacity[i], acc_capacity[i+1]) for i in range(len(capacity_per_dim))]
                print (read_bank_per_dim, write_bank_per_dim)

                bank_per_dim = [max(max(read_bank, write_bank), 1) for read_bank, write_bank in zip(read_bank_per_dim, write_bank_per_dim)]

                #input_multiplier = vbuffer_._input_port // mem_config._input_port
                #output_multiplier = vbuffer_._output_port // mem_config._output_port
                num_bank = reduce(lambda x, y: x*y, bank_per_dim)
                return num_bank, bank_per_dim
            num_bank, bank_per_dim = check_bank(vbuffer)
            if num_bank == 1:
                continue
            def createBankFromNode(node, num_bank):
                print (num_bank)
                capacity_per_bank = node.kernel._capacity // num_bank

                if capacity_per_bank > mem_config._capacity:
                    assert True, "Need chaining which is not implemented. \n"

                #create the set of memory node and recursive connect to its successor
                banked_buffer_node = []
                for bank_id in range(num_bank):
                    banked_buffer = vbuffer.produce_banking(num_bank, bank_per_dim, capacity_per_dim, acc_capacity, 512, bank_id)
                    banked_buffer_node.append(BufferNode(node.name+"_bank_"+str(bank_id), banked_buffer, bank_id))

                return banked_buffer_node
            banked_buffer_node_list = createBankFromNode(node, num_bank)
            for banked_buffer_node in banked_buffer_node_list:
                new_node_dict[banked_buffer_node.name] = banked_buffer_node
            '''

            if banked_buffer_node[0].input_bank_select[0]:
                #create the bank select node
                #TODO, use bank_in_dim and capacity_
                bankselect_tmp = SelectorNode(key+ "_selector", num_bank, banked_buffer_node[0].bank_in_dim, capacity_per_dim)
                new_connection_dict.update( bankselect_tmp.connectNode(node.pred) )
                new_connection_dict.update( bankselect_tmp.connectOutput(banked_buffer_node) )
                new_node_dict[bankselect_tmp.name] = bankselect_tmp
                banked_buffer_node_dict = {node.name: node for node in banked_buffer_node}
                new_node_dict.update(banked_buffer_node_dict)
            if banked_buffer_node[0].output_bank_select[0]:
                assert False, "Not implemented output bank selector"
            '''
            #TODO connect to input, also need to connect the bank slector

            #connect the banked buffer node with input and output
            for buffer_node, output_node in zip(banked_buffer_node_list, node.succ):
                #only connect data port
                print (node.pred)
                new_connection_dict.update(buffer_node.connectNode(node.pred))
                new_connection_dict.update(output_node.connectNode(buffer_node))

            banked_buffer_node_list[-1].assertLastOfChain()

            #FIXME: Maybe do not need thisThe DFS to create graoh
            '''
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
            '''
    if new_node_dict == {}:
        new_node_dict = node_dict
    if new_connection_dict == {}:
        new_connection_dict = connection_dict

    return new_node_dict, new_connection_dict



