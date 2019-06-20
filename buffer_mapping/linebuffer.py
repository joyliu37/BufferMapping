from buffer_mapping.virtualbuffer import VirtualBuffer, VirtualRowBuffer
from functools import reduce
from collections import defaultdict

class LineBufferNode:

    def __init__(self, input_port, output_port, read_iterator, counter_bound, buf_list=[], stride_dim=0, fifo_depth=0, fifo_size = 0):

        #fifo size and fifo depth
        self._fifo_depth = fifo_depth
        self._fifo_size = fifo_size

        #a list of VirtualRowBuffer that save data
        self.row_buffer_chain = [ VirtualRowBuffer(input_port,
                                                   output_port,
                                                   fifo_size,
                                                   # python transfer reference for any non unary object
                                                   read_iterator._rng.copy(),
                                                   read_iterator._st.copy(),
                                                   [0] * output_port,
                                                   fifo_depth * fifo_size,
                                                   counter_bound)
                                 for _ in range(self._fifo_depth)]

        #changing range of address pattern to adapt to the fifo input
        for depth, row_buffer in enumerate(reversed(self.row_buffer_chain)):
            row_buffer.read_iterator._rng[stride_dim] += self._fifo_depth

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

    def recursive_update_write_iterator(self, incremental_delay=0):
        '''
        Helper function when we finish create line buffer tree
        We need to update write iterator,
        because not all node has same amount of write iteration
        '''
        for idx, row_buffer in enumerate(self.row_buffer_chain):
            deduct = incremental_delay + idx * self._fifo_size
            row_buffer.write_iterator._rng[0] = reduce((lambda x, y: x * y),
                                                       row_buffer.read_iterator._rng) - deduct
        for idx, child in enumerate(self.child_fifo):
            child.recursive_update_write_iterator(incremental_delay + idx*self._fifo_size)


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

    def __init__(self, v_lb: VirtualBuffer, hw_input_port, hw_output_port, capacity_dim):
        '''
        Initialized from a VirtualBuffer Class
        '''
        #get a copy of the original virtual buffer
        self.base_buf = VirtualBuffer(v_lb._input_port, v_lb._output_port, v_lb._capacity,
                         v_lb.read_iterator._rng.copy(), v_lb.read_iterator._st.copy(),
                         v_lb.read_iterator._start.copy(),
                         v_lb._manual_switch, v_lb._arbitrary_addr)

        #the entry to root of line buffer tree
        self.meta_fifo_dict = {}

        #get the incremental dimension for this high dimensional buffer
        self._capacity_dim = [reduce((lambda x, y: x*y), capacity_dim[:dim+1]) for dim in range(len(capacity_dim))]
        self.fifo_optimize(hw_input_port, hw_output_port)

    def fifo_optimize(self, hw_input_port, hw_output_port):

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

            # mutate the buffer tree
            new_meta_fifo_dict = {}
            for new_start_port, merge_port_list in root_dict.items():
                #the first time to merge port, leaf node in the tree
                if(self.meta_fifo_dict == {}):
                    new_meta_fifo_dict.update(
                        {
                            new_start_port:
                            LineBufferNode(hw_input_port, hw_output_port, self.base_buf.read_iterator,
                                           self._capacity_dim[stride_dim], [],
                                           stride_dim, len(merge_port_list)-1, stride)
                        }
                    )
                #merge row or plane, aka subtree
                else:
                    child_buf_list = [self.meta_fifo_dict[port] for port in merge_port_list]
                    for child_buf in child_buf_list:
                        child_buf.recursive_update_read_iterator(stride_dim, len(merge_port_list) - 1)
                    new_meta_fifo_dict.update(
                        {
                            new_start_port:
                            LineBufferNode(hw_input_port, hw_output_port, self.base_buf.read_iterator,
                                           self._capacity_dim[stride_dim],
                                           child_buf_list,
                                           stride_dim, len(merge_port_list)-1, stride)
                        }
                    )
            #update the meta_fifo_dict and start address
            self.meta_fifo_dict = new_meta_fifo_dict
            self.base_buf.read_iterator._start = list(root_dict.keys())

            # update the iterator range
            self.base_buf.read_iterator._rng[stride_dim] += len(merge_port_list) - 1

        #update the write iterator because of the delay
        for _, root in self.meta_fifo_dict.items():
            root.recursive_update_write_iterator()

    def read_write(self, data_in):
        '''
        The only method for line buffer, will write a data and read out a data,
        also associate with a valid signal
        '''
        valid = False
        data = []
        for _, entry in self.meta_fifo_dict.items():
            valid, data = entry.read_write(data_in)
        return valid, data

