from buffer_mapping.virtualbuffer import VirtualBuffer, VirtualValidBuffer, VirtualRowBuffer
from functools import reduce
from collections import defaultdict
from copy import deepcopy

class LineBufferNode:

    def __init__(self, input_port, output_port, read_iterator_range, read_iterator_stride,
                 counter_bound, buf_list=[], stride_dim=0, fifo_depth=0, fifo_size = 0):

        #fifo size and fifo depth
        self._fifo_depth = fifo_depth
        self._fifo_size = fifo_size

        #a list of VirtualRowBuffer that save data
        self.row_buffer_chain = [ VirtualRowBuffer(input_port,
                                                   output_port,
                                                   fifo_size,
                                                   # python transfer reference for any non unary object
                                                   read_iterator_range.copy(),
                                                   read_iterator_stride.copy(),
                                                   [0] * output_port,
                                                   fifo_depth * fifo_size,
                                                   counter_bound)
                                 for _ in range(self._fifo_depth)]
        '''
        move the update iterator to out side
        #changing range of address pattern to adapt to the fifo input
        for depth, row_buffer in enumerate(reversed(self.row_buffer_chain)):
            row_buffer.read_iterator._rng[stride_dim] += self._fifo_depth

        '''
        '''
        use the recursive data structure to save the row buffer that are hooked up,
        There is <fifo_depth> + 1 child of row buffer hooked up
        which are all the output of fifo + one input
        '''
        self.child_fifo = buf_list

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
            row_buffer.read_iterator._st = [1]
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
        #print ("fifo_size: ",self._fifo_size,  stencil_valid,  read_valid, last_data_read)
        if (child_size > 0):
            #always read and write the child node, because we need to update the read iterator
            child_valid, data_from_child =  self.child_fifo[-1].read_write(last_data_read, read_valid)
            valid &= child_valid
            data_out.extend(data_from_child)
        else:
            data_out.extend(last_data_read)

        # update data in the current level row buffer chain, from the last fifo to the first
        for idx, row_buffer in enumerate(reversed(self.row_buffer_chain)):
            if idx == self._fifo_depth - 1:
                #write data in to the first fifo
                if in_valid:
                    #print ("write to fifo, size = ", self._fifo_size)
                    row_buffer.write(data_in)
                if child_size > 0:
                    child_valid, data_from_child =  self.child_fifo[-idx - 2].read_write(data_in, in_valid)
                    valid &= child_valid
                    data_out.extend(data_from_child)
                else:
                    data_out.extend(data_in)
            else:
                stencil_valid, read_valid, data_from_prev_fifo = self.row_buffer_chain[-idx-2].read()
                valid &= stencil_valid
                #print ("fifo_size: ",self._fifo_size, "fifo id:", idx, stencil_valid,  read_valid, data_from_prev_fifo)
                if read_valid:
                    row_buffer.write(data_from_prev_fifo)
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
        print (self.original_start)

        #the entry to root of line buffer tree
        self.meta_fifo_dict = {}
        #the starting port to original port map
        self.port_map = {start: [start] for start in self.base_buf.read_iterator._start}

        #A dictionary to track the range for each input port
        #and a dictionary to track the corresponding port number
        self.port_access_iter = {start_port: deepcopy(self.base_buf.read_iterator)
                                 for start_port in self.base_buf.read_iterator._start}

        #get the incremental dimension for this high dimensional buffer
        self._capacity_dim = [reduce((lambda x, y: x*y), capacity_dim[:dim+1]) for dim in range(len(capacity_dim))]
        self._stride_in_dim = [reduce((lambda x, y: x*y), stride_in_dim[:dim + 1]) for dim in range(len(stride_in_dim))]

        #FIXME: not thoroughly test for this condition
        old_start_size = len(self.base_buf.read_iterator._start)

        self.fifo_optimize(hw_input_port, hw_output_port)

        new_start_size = len(self.base_buf.read_iterator._start)

        #TODO: make this in a method
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

    def fifo_optimize(self, hw_input_port, hw_output_port):

        #update the port number
        for stride_dim, stride in enumerate(self.base_buf.read_iterator._st):
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

            longest_merge_port_list_size = 0

            # mutate the buffer tree
            for new_start_port, merge_port_list in root_dict.items():
                #update the longest fifo length for range update
                if len(merge_port_list) > longest_merge_port_list_size:
                    longest_merge_port_list_size = len(merge_port_list)

                #nothing to merge just single port
                if len(merge_port_list) == 1:
                    continue

                child_buf_list = [self.meta_fifo_dict.pop(port) for port in merge_port_list if port in self.meta_fifo_dict]

                #update the port map
                for merge_port in merge_port_list:
                    if new_start_port != merge_port:
                        self.port_map[new_start_port].extend(self.port_map.pop(merge_port))

                #update the read iterator in child fifo, because of the merge
                for child_buf in child_buf_list:
                    child_buf.recursive_update_read_iterator(stride_dim, len(merge_port_list) - 1)

                #merge the port iterator and update the range
                for merge_port in merge_port_list:
                    #pop all old merge_port
                    if merge_port != new_start_port:
                        self.port_access_iter.pop(merge_port)
                    #update the new start port
                    else:
                        self.port_access_iter[merge_port]._rng[stride_dim] += len(merge_port_list) - 1

                #create the row buffer stride, range, and size
                '''
                row_buf_stride = [st_origin // st_in_dim for st_origin, st_in_dim in
                                  zip(self.port_access_iter[new_start_port]._st.copy(), self._stride_in_dim)]
                row_buf_stride = [1 if st_dim == 0
                                  else reduce((lambda x,y : x*y),
                                              self.port_access_iter[new_start_port]._rng[:st_dim])
                                  for st_dim in len(self.port_access_iter._rng)]
                '''
                # use a virtual stride here
                row_buf_stride = []
                row_buf_range = self.port_access_iter[new_start_port]._rng.copy()

                row_buf_size = 1 if stride_dim == 0 \
                else reduce((lambda x,y : x*y), self.port_access_iter[new_start_port]._rng[:stride_dim])

                self.meta_fifo_dict.update(
                    {
                        new_start_port:
                        LineBufferNode(hw_input_port, hw_output_port,
                                       row_buf_range,
                                       row_buf_stride,
                                       self._capacity_dim[stride_dim],
                                       child_buf_list,
                                       stride_dim, len(merge_port_list)-1,
                                       row_buf_size)
                                       #stride // (self._stride_in_dim[stride_dim] ** (stride_dim + 1)))
                    }
                )
            #update the meta_fifo_dict and start address
            #self.meta_fifo_dict = new_meta_fifo_dict
            self.base_buf.read_iterator._start = list(root_dict.keys())

            # update the iterator range for the base buffer, it will keep the largest range
            # Further in the final it will be the reference to shift the start
            self.base_buf.read_iterator._rng[stride_dim] += longest_merge_port_list_size - 1

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
                    #print("port ", idx, data_from_port)
                else:
                    #there is no fifo, add the data from base buffer directly to output
                    data_dict[-start_addr_after_opt] = [data_from_base[idx]]
            else:
                valid = False

        for port in self.original_start:
            if port in data_dict:
                data.extend(data_dict[port])
        return valid, data

