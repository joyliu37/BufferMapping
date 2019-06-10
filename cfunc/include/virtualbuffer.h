#ifndef VIRTUALBUFFER_H_
#define VIRTUALBUFFER_H_

#include <vector>
#include "access.h"

using namespace std;

template <typename Dtype>
class VirtualBuffer {
    public:
        VirtualBuffer() {};
        VirtualBuffer(vector<int> in_range, vector<int> in_stride, vector<int> in_start,
                vector<int> out_range, vector<int> out_stride, vector<int> out_start, int capacity);
        vector<Dtype> read();
        void write(const vector<Dtype>& write_data);
        void switch_check();
        int getReadIteration() {return read_iterator.getTotalIteration();}
        int getWriteIteration() {return write_iterator.getTotalIteration();}
        int getInPort() {return input_port;}
        int getOutPort() {return output_port;}

    private:
        int input_port, output_port, capacity;
        bool select;
        AccessIter write_iterator, read_iterator;
        vector<vector<Dtype> > data;
};


#endif
