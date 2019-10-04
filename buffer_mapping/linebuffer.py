from buffer_mapping.virtualbuffer import VirtualBuffer, VirtualValidBuffer, VirtualRowBuffer
from buffer_mapping.hardware import HardwarePort, HardwareNode, BufferNode, HardwareWire
from functools import reduce
from collections import defaultdict
from copy import deepcopy
from buffer_mapping.flatten import FlattenAccessPattern

class LineBufferNode:

    def __init__(self, input_port, output_port, read_iterator_range, read_iterator_stride,
                 buf_list=[], stride_dim=0, fifo_depth=0, fifo_size = 0):

        #print ("read_iterator_range", read_iterator_range, fifo_depth, fifo_size, "stride_dim", stride_dim)

        #get the valid counter bound, and stencil delay, meta data to create the valid counter
        self._counter_bound = reduce(lambda x, y: x*y, read_iterator_range[:stride_dim+1])
        self._read_delay = fifo_depth*fifo_size
        #fifo size and fifo depth
        self._fifo_depth = fifo_depth
        self._fifo_size = fifo_size
        '''
        use the recursive data structure to save the row buffer that are hooked up,
        There is <fifo_depth> + 1 child of row buffer hooked up
        which are all the output of fifo + one input
        '''
        read_delay = 0
        self.child_fifo = buf_list
        if self.child_fifo:
            self.child_read_delay = buf_list[0]._fifo_depth * buf_list[0]._fifo_size
        else:
            self.child_read_delay = 0
        read_delay = fifo_depth * fifo_size

        print ("read_delay",read_delay)

        #a list of VirtualRowBuffer that save data
        self.row_buffer_chain = [ VirtualRowBuffer(input_port,
                                                   output_port,
                                                   fifo_size,
                                                   # python transfer reference for any non unary object
                                                   read_iterator_range.copy(),
                                                   read_iterator_stride.copy(),
                                                   [0] * output_port,
                                                   read_delay * (idx == (self._fifo_depth - 1)),
                                                   self._counter_bound)
                                 for idx in range(self._fifo_depth)]
        '''
        move the update iterator to out side
        #changing range of address pattern to adapt to the fifo input
        for depth, row_buffer in enumerate(reversed(self.row_buffer_chain)):
            row_buffer.read_iterator._rng[stride_dim] += self._fifo_depth

        '''

    def GenGraph(self, name, input_node, output_node_list, outside_bank_id = 0):
        node_dict = {}
        connection_dict = {}
        prev_buffer = None
        for idx, row_buffer in enumerate(self.row_buffer_chain):
            node_name = name+"_"+str(idx)
            node_dict[node_name] = BufferNode(node_name, row_buffer, self.child_read_delay)

            #FIXME: need a beautiful data embedded schema for stencil valid signal
            node_dict[node_name].setStencilConfig(self._counter_bound, self._fifo_depth)

            if idx == len(self.row_buffer_chain) - 1:
                node_dict[node_name].assertLastOfChain()
            if idx == 0:
                if len(self.child_fifo):
                    node, connection = self.child_fifo[0].GenGraph(node_name, input_node, output_node_list, outside_bank_id)
                    node_dict.update(node)
                    connection_dict.update(connection)
                connection_dict.update(node_dict[node_name].connectNode(input_node, outside_bank_id))
            else:
                connection_dict.update(node_dict[node_name].connectNode(prev_buffer))

            #Connect to the output
            cur_output_node_list = output_node_list.pop()
            for output_node in cur_output_node_list:
                connection_dict.update(output_node.connectNode(node_dict[node_name]))
            if len(self.child_fifo):
                #update the name for child buffer
                child_node_name = name+"_"+str(idx+1)
                node, connection = self.child_fifo[idx+1].GenGraph(child_node_name, node_dict[node_name], output_node_list)
                node_dict.update(node)
                connection_dict.update(connection)

            #update the prev node
            prev_buffer = node_dict[node_name]
        '''
        for idx, child in enumerate(self.child_fifo):
            node_name = name + "_" + str(idx)
            node = {}
            connection = {}
            if idx == 0:
                node, connection = child.GenGraph(node_name, input_node, output_node_list)
            else:
                node, connection = child.GenGraph(node_name, buffer_list[idx-1], output_node_list)
            node_dict.update(node)
            connection_dict.update(connection)

        '''

        return node_dict, connection_dict

    def reset(self):
        for row_buffer in self.row_buffer_chain:
            row_buffer.reset()
        for child_node in self.child_fifo:
            child_node.reset()


    def dump_json(self, name, data_in, valid, out_id, port_list):
        #do not forget add top level connection
        instance = {}
        connection = []
        for idx, row_buffer in enumerate(self.row_buffer_chain):
            #add connect from input to
            buffer_instance, is_reg = row_buffer.dump_json(idx == len(self.row_buffer_chain) - 1)
            buffer_name = name + "_" + str(idx)
            instance[buffer_name] = buffer_instance
            #FIXME connection to output id is not clear
            if is_reg:
                if idx == 0:
                    #connect the input with this in
                    connection.append([data_in, buffer_name+".in"])
                else:
                    #connect previou out with this datain
                    connection.append([name+"_"+str(idx-1)+".out", buffer_name+".in"])
                connection.append([name+"_"+str(idx)+".out",str(port_list[out_id] + ".in")])
                connection.append([name+"_"+str(idx)+".clk", "self.clk"])
                out_id += 1
            else:
                if idx == 0:
                    instance_child , connection_child, out_id = self.child_fifo[idx].dump_json(buffer_name, data_in, valid, out_id, port_list)
                    instance.update(instance_child)
                    connection.extend(connection_child)
                    #connect the input with this in
                    connection.append([data_in, buffer_name+".data_in"])
                    connection.append([valid, buffer_name+".wen"])
                    connection.append([valid, buffer_name+".ren"])
                else:
                    #connect previou out with this datain
                    connection.append([name+"_"+str(idx-1)+".dataout", buffer_name+".datain"])
                    connection.append([name+"_"+str(idx-1)+".valid", buffer_name+".wen"])
                    connection.append([name+"_"+str(idx-1)+".valid", buffer_name+".ren"])
                connection.append([name+"_"+str(idx)+".dataout", str(port_list[out_id])+".in"])
                connection.append([name+"_"+str(idx)+".flush", "self.flush"])
                out_id += 1
                prev_buffer_name = name + "_" + str(idx)
                next_buffer_name = name + "_" + str(idx+1)
                instance_child , connection_child, out_id = self.child_fifo[idx+1].dump_json(next_buffer_name, prev_buffer_name+".dataout", valid, out_id, port_list)
                instance.update(instance_child)
                connection.extend(connection_child)


        return instance, connection, out_id

    def recursive_update_read_iterator(self, dim, fifo_depth):
        '''
        Helper function when we doing fifo optimization
        '''
        for row_buffer in self.row_buffer_chain:
            row_buffer.read_iterator._rng[dim] += fifo_depth
            #row_buffer.write_iterator._rng[0] = reduce((lambda x,y : x*y), row_buffer.read_iterator._rng)
        if len(self.child_fifo) > 0:
            for child in self.child_fifo:
                child.recursive_update_read_iterator(dim, fifo_depth)

    def recursive_postprocess_iterator(self, incremental_delay=0):
        '''
        Helper function when we finish create line buffer tree
        We need to update write iterator,
        because not all node has same amount of write iteration
        '''
        for idx, row_buffer in enumerate(self.row_buffer_chain):
            #TODO: clean this up. Put this update into a VirtualRowBuffer method
            deduct = incremental_delay + idx * self._fifo_size
            row_buffer.write_iterator._rng[0] = reduce((lambda x, y: x * y),
                                                       row_buffer.read_iterator._rng) - deduct
            row_buffer.read_iterator._rng = [reduce((lambda x, y: x* y),
                                                    row_buffer.read_iterator._rng)]
            row_buffer.read_iterator._st = [row_buffer._output_port]
            row_buffer.read_iterator.restart()
        for idx, child in enumerate(self.child_fifo):
            child.recursive_postprocess_iterator(incremental_delay + idx*self._fifo_size)


    def read_write(self, data_in, in_valid = True):
        '''
        This method recursively walk through the tree and update the row buffer value
        write to the row buffer with valid data
        return a list of data associated a valid signal.
        '''
        #initial the return data, and stencil valid
        valid = True
        data_out = []

        child_size = len(self.child_fifo)
        #print ("row buffer size: ",len(self.row_buffer_chain), child_size)

        #pull the last data read from the last chain into to the next level fifo
        stencil_valid, read_valid, last_data_read = self.row_buffer_chain[-1].read()
        valid &= stencil_valid
        valid &= read_valid
        #print ("counter_bound:", self.row_buffer_chain[-1].stencil_valid_counter._bound,"fifo_size: ",self._fifo_size,  stencil_valid,  read_valid, last_data_read)
        if (child_size > 0):
            #always read and write the child node, because we need to update the read iterator
            child_valid, data_from_child =  self.child_fifo[-1].read_write(last_data_read, read_valid)
            #And valid signal from children node
            valid &= child_valid
            #pad data into the out put(this is the oldest data)
            data_out.extend(data_from_child)
        else:
            #pad the data from node, because there is child node
            data_out.extend(last_data_read)

        # update data in the current level row buffer chain, from the last fifo to the first
        for idx, row_buffer in enumerate(reversed(self.row_buffer_chain)):
            if idx == self._fifo_depth - 1:
                #write data in to the first fifo
                #if in_valid:
                    #print ("write to fifo, size = ", self._fifo_size)
                row_buffer.write(in_valid, data_in)
                if child_size > 0:
                    child_valid, data_from_child =  self.child_fifo[-idx - 2].read_write(data_in, in_valid)
                    valid &= child_valid
                    data_out.extend(data_from_child)
                else:
                    data_out.extend(data_in)
            else:
                stencil_valid, read_valid, data_from_prev_fifo = self.row_buffer_chain[-idx-2].read()
                #do not need this valid signal because buffer chain valid will depend on the last one
                #valid &= stencil_valid
                #print ("fifo_size: ",self._fifo_size, "fifo id:", idx, stencil_valid,  read_valid, data_from_prev_fifo)
                #if read_valid:
                row_buffer.write(read_valid, data_from_prev_fifo)
                if child_size > 0:
                    child_valid, data_from_child = self.child_fifo[-idx - 2].read_write(data_from_prev_fifo, read_valid)
                    valid &= child_valid
                    data_out.extend(data_from_child)
                else:
                    data_out.extend(data_from_prev_fifo)

        return valid, data_out

class VirtualLineBuffer:
    '''
    The class where fifo optimization operated on.
    This class has a tree structure, each node has a list of Line buffer node
    providing the entry to the next level.
    And we merge the line buffer node into subtree with row buffer and shrink the port number,
    through the fifo optimization method until nothing can be merged.
    '''

    def __init__(self, v_lb: VirtualBuffer, hw_input_port, hw_output_port, capacity_dim, stride_in_dim):
        '''
        Initialized from a VirtualBuffer Class
        '''
        #get a copy of the original virtual buffer
        self.base_buf = VirtualValidBuffer(v_lb._input_port, v_lb._output_port, v_lb._capacity,
                         v_lb.read_iterator._rng.copy(), v_lb.read_iterator._st.copy(),
                         v_lb.read_iterator._start.copy(),
                         v_lb._manual_switch, v_lb._arbitrary_addr)

        #Get a original copy of the start address
        self.original_start = self.base_buf.read_iterator._start.copy()
        #print (self.original_start)

        #the entry to root of line buffer tree
        self.meta_fifo_dict = {}
        #the starting port to original port map
        self.port_map = {start: [start] for start in self.base_buf.read_iterator._start}

        #A dictionary to track the range for each input port
        #and a dictionary to track the corresponding port number
        #self.port_access_iter = {start_port: deepcopy(self.base_buf.read_iterator)
        #                         for start_port in self.base_buf.read_iterator._start}
        #Only use one base_access_iter
        self.base_access_iter = deepcopy(self.base_buf.read_iterator)

        #get the incremental dimension for this high dimensional buffer
        self._capacity_dim = [reduce((lambda x, y: x*y), capacity_dim[:dim+1]) for dim in range(len(capacity_dim))]
        self._stride_in_dim = [reduce((lambda x, y: x*y), stride_in_dim[:dim + 1]) for dim in range(len(stride_in_dim))]

        self.fifo_optimize(hw_input_port, hw_output_port)
        print (self.meta_fifo_dict)

        #shift the starting port in the situation that optimized port number is not divisible by original port size
        #TODO: make this in a method
        '''

        if old_start_size % new_start_size:
            #FIXME:should we use the single dimension size?
            self.base_buf.shiftTopLeft(old_start_size % new_start_size, capacity_dim)
            for idx_port, start in enumerate(self.base_buf.read_iterator._start):
                #compare with the base buf iterator rang to change the starting pos of base buf
                shift_start = start
                for idx_dim, (base_rng_in_dim, start_port_rng_in_dim) in enumerate(zip(self.base_buf.read_iterator._rng,
                                                                  self.port_access_iter[start]._rng)):
                    stride_in_dim = self.base_buf.read_iterator._st[idx_dim]
                    shift_start -= (base_rng_in_dim - start_port_rng_in_dim) * stride_in_dim
                if start in self.meta_fifo_dict:
                    #chances are the start point do not have fifo
                    self.meta_fifo_dict[shift_start] = self.meta_fifo_dict.pop(start)
                if start in self.port_map:
                    self.port_map[shift_start] = self.port_map.pop(start)

                self.base_buf.read_iterator._start[idx_port] = shift_start

        self.base_buf.read_iterator.restart()
        '''

    def dump_json(self, name, data_in, valid, port_list):
        instance = {}
        connection = []
        out_id = 0
        connection.append([data_in, "self.out"+str(port_list[out_id])])
        out_id += 1
        for _, buffer_node in self.meta_fifo_dict.items():
            entry_instance, entry_connection, out_id= buffer_node.dump_json(name, data_in, valid, out_id, port_list)
            instance.update(entry_instance)
            connection.extend(entry_connection)

        #FIXME: for the base buf, currently just hack
        json_dict = {}
        json_dict["instances"] = instance
        json_dict["connections"] = connection
        return json_dict

    def GenGraph(self, name, input_node, output_node_dict):
        node_dict = {}
        connection = {}

        #gen node for base buffer and add to the graph:
        base_buf_node = BufferNode(name+"_base", self.base_buf)
        connection.update(base_buf_node.connectNode(input_node))
        node_dict[base_buf_node.name] = base_buf_node

        for idx, bank_idx in enumerate(self.base_buf.read_iterator._start):
        #for idx, (bank_idx, buffer_node) in enumerate(self.meta_fifo_dict.items()):
            #this is a 2D list each contains the set of line buffer output port from which it can have fanout
            output_node_list = output_node_dict[bank_idx]
            for output_node in output_node_list[-1]:
                connection.update(output_node.connectNode(base_buf_node, idx))
            output_node_list.pop()
            if bank_idx in self.meta_fifo_dict.keys():
                buffer_node = self.meta_fifo_dict[bank_idx]
                entry_node, entry_connection = buffer_node.GenGraph(name+"_bank_"+str(bank_idx), base_buf_node, output_node_list, idx)
                node_dict.update(entry_node)
                connection.update(entry_connection)
        return node_dict, connection

    def fifo_optimize(self, hw_input_port, hw_output_port):

        #update the port number
        for stride_dim, stride in enumerate(self.base_buf.read_iterator._st):
            if stride == 0:
                continue
            #dictionary from original port to the connected fifo start addr
            root = {addr: addr for addr in self.base_buf.read_iterator._start}
            next_start = self.base_buf.read_iterator._start.copy()

            #get next start addr
            next_start = [addr + stride for addr in next_start]

            #find overlap
            for idx, shift_addr in enumerate(next_start):
                if shift_addr in self.base_buf.read_iterator._start:
                    origin_addr = self.base_buf.read_iterator._start[idx]
                    root[shift_addr] = root[origin_addr]

            # transform the root dictionary structure
            # {port#: root port#} -> {root port#: list of merge port}
            root_dict = defaultdict(list)
            for key, root_port in root.items():
                root_dict[root_port].append(key)

            #use to save the non_merge_port_list
            non_merge_port_list = []
            longest_merge_port_list_size = 0

            # mutate the buffer tree
            for new_start_port_idx, (new_start_port, merge_port_list) in enumerate(root_dict.items()):

                #update the longest fifo length for range update
                if len(merge_port_list) > longest_merge_port_list_size:
                    longest_merge_port_list_size = len(merge_port_list)

                #nothing to merge just a single port, put into a shift list
                if len(merge_port_list) == 1:
                    print ("new start port: ", new_start_port)
                    non_merge_port_list.append(new_start_port)
                    continue

                child_buf_list = [self.meta_fifo_dict.pop(port) for port in merge_port_list if port in self.meta_fifo_dict]

                #update the port map
                for merge_port in merge_port_list:
                    if new_start_port != merge_port:
                        self.port_map[new_start_port].extend(self.port_map.pop(merge_port))

                #update the read iterator in child fifo, because of the merge
                for child_buf in child_buf_list:
                    child_buf.recursive_update_read_iterator(stride_dim, len(merge_port_list) - 1)

                #update the range
                #FIXME possible bug: currently just consider all the merge points have the same overlap
                if new_start_port_idx == 0:
                    self.base_access_iter._rng[stride_dim] += len(merge_port_list) - 1
                    '''
                    for merge_port in merge_port_list:
                        #pop all old merge_port
                        if merge_port != new_start_port:
                            self.port_access_iter.pop(merge_port)
                        #update the new start port
                        else:
                            self.port_access_iter[merge_port]._rng[stride_dim] += len(merge_port_list) - 1
                    '''

                # use a virtual stride here
                row_buf_stride = []
                #row_buf_range = self.port_access_iter[new_start_port]._rng.copy()
                row_buf_range = self.base_access_iter._rng.copy()

                #size for nd line buffer component, could be reg row or plane
                row_buf_size = 1 if stride_dim == 0 \
                else reduce((lambda x,y : x*y), self.base_access_iter._rng[:stride_dim])

                self.meta_fifo_dict.update(
                    {
                        new_start_port:
                        LineBufferNode(hw_input_port, hw_output_port,
                                       row_buf_range,
                                       row_buf_stride,
                                       #self._capacity_dim[stride_dim]//self._stride_in_dim[stride_dim],
                                       child_buf_list,
                                       stride_dim, len(merge_port_list)-1,
                                       row_buf_size)
                                       #stride // (self._stride_in_dim[stride_dim] ** (stride_dim + 1)))
                    }
                )
            #update the non merge port id in root_dict and port_map
            if longest_merge_port_list_size > 1:
                for update_id in non_merge_port_list:
                    root_dict[update_id - stride] = root_dict.pop(update_id)
                    self.port_map[update_id - stride] = self.port_map.pop(update_id)
                    if update_id in self.meta_fifo_dict.keys():
                        self.meta_fifo_dict[update_id - stride] = self.meta_fifo_dict.pop(update_id)

            #update the meta_fifo_dict and start address
            #self.meta_fifo_dict = new_meta_fifo_dict
            self.base_buf.read_iterator._start = list(root_dict.keys())

            # update the iterator range for the base buffer, it will keep the largest range
            # Further in the final it will be the reference to shift the start
            self.base_buf.read_iterator._rng[stride_dim] += longest_merge_port_list_size - 1

        print ("base_buffer read range",self.base_buf.read_iterator._rng)

        #update the write iterator because of the delay
        for _, root in self.meta_fifo_dict.items():
            root.recursive_postprocess_iterator()


        #print("1 chain size: ", len(self.meta_fifo_dict[1].row_buffer_chain))
        self.base_buf._output_port = len(self.base_buf.read_iterator._start)
        self.base_buf.read_iterator.restart()

    def read_write(self, data_in):
        '''
        The only method for line buffer, will write a data and read out a data,
        also associate with a valid signal
        '''
        self.base_buf.write(data_in)
        valid_from_base, data_from_base = self.base_buf.read()
        #print (valid_from_base, data_from_base)

        valid = True
        data = []
        data_dict = {}
        #transfer the data read from base buffer to fifo
        for idx, start_addr_after_opt in enumerate(self.base_buf.read_iterator._start):
            #print ("read n write port number: ", start_addr_after_opt)
            if valid_from_base[idx]:
                if start_addr_after_opt in self.meta_fifo_dict:
                #read data from fifo
                    fifo_entry = self.meta_fifo_dict[start_addr_after_opt]
                    valid_from_port, data_from_port = fifo_entry.read_write([data_from_base[idx]])
                    valid &= valid_from_port
                    for idx, port in enumerate(self.port_map[start_addr_after_opt]):
                        data_dict[port] = [data_from_port[idx]]
                    #data.extend(data_from_port)
                    #print("port ", idx, data_from_port, valid_from_port)
                else:
                    #there is no fifo, add the data from base buffer directly to output
                    #change the to the port map version
                    data_dict[self.port_map[start_addr_after_opt][0]] = [data_from_base[idx]]
            else:
                valid = False

        for port in self.original_start:
            if port in data_dict:
                data.extend(data_dict[port])
        return valid, data

    #TODO: double check if we are going to reset the buffer once we finish a tile of mem
    def reset(self):
        for _, fifo_entry in self.meta_fifo_dict.items():
            fifo_entry.reset()

