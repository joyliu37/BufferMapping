from buffer_mapping.hardware import HardwareWire, BufferNode, RegNode, FlushNode, SelectorNode, ValidGenNode
from buffer_mapping.util import AccessPattern
from buffer_mapping.virtualbuffer import VirtualValidBuffer, VirtualRowBuffer, VirtualDoubleBuffer
from functools import reduce
import copy

def connectValidSignal(node_dict, connection_dict, valid_node_list):
    #valid_pred_node_list = []
    for key, node in node_dict.items():
        #FIXME: cannot support multiple output valid
        if type(node) == BufferNode:
            if node.last_in_chain:
                #valid_pred_node_list.append(node)
                print ("Connect valid signal of [", key, "] BUF for the last bank")
                for valid_node in valid_node_list:
                    connection_dict.update(valid_node.connectNode(node))
        elif type(node) == ValidGenNode:
            #valid_pred_node_list.append(node)
            for valid_node in valid_node_list:
                print ("Connect valid signal of [", key, "] validGen for the last bank")
                connection_dict.update(valid_node.connectNode(node))

    #Adding a AND node valid node
    #for node in valid_pred_node_list:
    #    print (node.name)

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
                if type(new_node.pred.kernel) != VirtualRowBuffer:
                    if node.last_in_chain:
                        #Add the valid logic
                        print ("Generate valid signal for [", new_node.name, "]")
                        valid_gen = ValidGenNode(key+"_val_gen", new_node.stencil_delay-1, new_node.counter_bound)
                        new_node_dict[valid_gen.name] = valid_gen
                        connection_dict.update(valid_gen.connectNode(new_node.pred))
    node_dict.update(new_node_dict)
    return node_dict, connection_dict

def flattenValidBuffer(node_dict, connection_dict, valid_node_list):
    for key, node in list(node_dict.items()):
        if type(node) == BufferNode:
            if type(node.kernel) == VirtualValidBuffer or type(node.kernel) == VirtualDoubleBuffer:
                if node.kernel.isPassThrough():
                    print ("Flatten Valid buffer!")
                    print (node.last_in_chain)
                    if node.last_in_chain:
                        #valid_pred_node_list.append(node)
                        print ("Connect valid signal of [", key, "] BUF for the last bank")
                        for valid_node in valid_node_list:
                            connection_dict.update(valid_node.connectNode(node.pred))
                            print(node.pred)
                    #TODO: build a graph class and make this delete node method
                    '''
                    node.pred.removeSucc(node)
                    for succ in node.succ:
                        succ.makePred(node.pred)
                        node.pred.addSucc(succ)
                    for connection in connection_dict:
                        if connection.isLinkedTo(node.name):
                    '''
                    for port, succ_list in node.succ.items():
                        for succ in succ_list:
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
    for key, node in list(node_dict.items()):
        if type(node) == BufferNode:
            vbuffer = node.kernel
            def check_bank(vbuffer_):
                #check the bandwidth requirement to create banking

                #node.kernel.read_iterator._start.sort(key = lambda x: max(x, -x))

                def check_bank_for_dim(iterator, capacity_prev_dim, capacity_this_dim):
                    cnt = 0
                    capacity = capacity_this_dim // capacity_prev_dim

                    #keep track of the port that are reduced
                    recur_list = []

                    #get the port number in each dimension
                    for start_addr in iterator._start:
                        if start_addr < 0:
                            start_addr = -start_addr
                        if start_addr // capacity_prev_dim < capacity:
                            if start_addr//capacity_prev_dim not in recur_list:
                                cnt += 1
                                recur_list.append(start_addr//capacity_prev_dim)
                    return cnt

                print (acc_capacity)
                read_bank_per_dim = [check_bank_for_dim(vbuffer_.read_iterator, acc_capacity[i], acc_capacity[i+1]) for i in range(len(capacity_per_dim))]
                write_bank_per_dim = [check_bank_for_dim(vbuffer_.write_iterator, acc_capacity[i], acc_capacity[i+1]) for i in range(len(capacity_per_dim))]
                print ("read_bank:", read_bank_per_dim, "write_bank: " ,write_bank_per_dim)

                bank_per_dim = [max(max(read_bank, write_bank), 1) for read_bank, write_bank in zip(read_bank_per_dim, write_bank_per_dim)]

                #input_multiplier = vbuffer_._input_port // mem_config._input_port
                #output_multiplier = vbuffer_._output_port // mem_config._output_port
                num_bank = reduce(lambda x, y: x*y, bank_per_dim)
                return num_bank, bank_per_dim
            num_bank, bank_per_dim = check_bank(vbuffer)
            print ("bank number:",num_bank)
            if num_bank == 1:
                continue
            def createBankFromNode(node, num_bank):
                capacity_per_bank = node.kernel._capacity // num_bank

                if capacity_per_bank > mem_config._capacity:
                    assert True, "Need chaining which is not implemented. \n"

                #create the set of memory node and recursive connect to its successor
                banked_buffer_node = []
                for bank_id in range(num_bank):
                    banked_buffer = vbuffer.produce_banking_duplicate(num_bank, bank_per_dim, capacity_per_dim, acc_capacity, 512, bank_id)
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

            #remove the node connection and get the wire delete key list
            del_connection_key_list = node.removeConnection()
            # remove connection
            for del_key in del_connection_key_list:
                print (del_key)
                connection_dict.pop(del_key)

            #mark the last of chain which is the valid control bank
            max_start_addr = -512
            min_id = -1
            for idx, bank_buffer_node in enumerate(banked_buffer_node_list):
                temp = min(banked_buffer_node.kernel.read_iterator._start)
                if temp > max_start_addr:
                    min_id = idx
                    max_start_addr = temp
            banked_buffer_node_list[min_id].assertLastOfChain()

            #connect the banked buffer node with input and output
            #print ("output node list:", node.succ)
            for buffer_node, (port_id, output_node_list) in zip(banked_buffer_node_list, node.succ.items()):
                new_connection_dict.update(buffer_node.connectNode(node.pred))

                #update the last of chain information
                if buffer_node.last_in_chain == False:
                    for output_node in output_node_list:
                        if type(output_node) == BufferNode:
                            output_node.last_in_chain = False
                else:
                    #FIXME Possible bug in wiring of valid signal
                    exist_pred_buffer = False
                    for output_node in output_node_list:
                        if type(output_node) == BufferNode:
                            output_node.last_in_chain = True
                            exist_pred_buffer = True
                    if exist_pred_buffer:
                        buffer_node.last_in_chain = False
                #connecting all the wire
                for output_node in output_node_list:
                    print ("succ node:[", output_node.name,"], connected bank name:[", buffer_node.name,"]")
                    new_connection_dict.update(output_node.connectNode(buffer_node))

            #transform negative starting address to positive
            #TODO: make this a rewrite rule in the future
            for banked_buffer_node in banked_buffer_node_list:
                for idx, start in enumerate(banked_buffer_node.kernel.read_iterator._start):
                    if start < 0:
                        start += 512

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
            node_dict.pop(node.name)
    node_dict.update(new_node_dict)
    connection_dict.update(new_connection_dict)

    return node_dict, connection_dict



