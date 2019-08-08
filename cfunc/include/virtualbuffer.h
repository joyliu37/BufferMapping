#ifndef VIRTUALBUFFER_H_
#define VIRTUALBUFFER_H_

#include <vector>
#include "access.h"
#include "util.h"


template <typename Dtype>
class VirtualBuffer {
    public:
        VirtualBuffer() {};
        VirtualBuffer(std::vector<int> in_range, std::vector<int> in_stride, std::vector<int> in_start,
                std::vector<int> out_range, std::vector<int> out_stride, std::vector<int> out_start,
                std::vector<int> in_chunk, std::vector<int> out_stencil, std::vector<int> dimension,
                int stencil_acc_dim);
        RetDataWithVal<Dtype> read();
        void write(const std::vector<Dtype>& write_data);
        void switch_check();
        void copy2writebank();
        bool getStencilValid();
        int getReadIteration() {return read_iterator.getTotalIteration();}
        int getWriteIteration() {return write_iterator.getTotalIteration();}
        int getInPort() {return input_port;}
        int getOutPort() {return output_port;}

    private:

        int input_port, output_port, capacity, dimensionality, stencil_acc_dim;
        int preload_bound, read_in_stencil_bound;
        bool select, is_db;
        AccessIter write_iterator, read_iterator, stencil_iterator;
        Counter preload_done, stencil_read_done;
        std::vector<vector<Dtype> > data;
        std::vector<bool> valid_domain;
        std::vector<int> copy_addr;
};


#endif
