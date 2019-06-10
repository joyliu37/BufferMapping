#include "virtualbuffer.h"
#include <assert.h>

template<typename Dtype>
VirtualBuffer<Dtype>::VirtualBuffer(vector<int> in_range, vector<int> in_stride, vector<int> in_start,
        vector<int> out_range, vector<int> out_stride, vector<int> out_start, int _capacity):
    capacity(_capacity),
    select(false),
    write_iterator(in_range, in_stride, in_start),
    read_iterator(out_range, out_stride, out_start)
{
    input_port = write_iterator.getPort();
    output_port = read_iterator.getPort();
    read_iterator.forceDone();
    data = vector<vector<Dtype> >(2, vector<Dtype>(capacity, (Dtype)0));
}

template<typename Dtype>
vector<Dtype> VirtualBuffer<Dtype>::read() {
    assert((!read_iterator.getDone()) && "No more read allowed.\n");
    vector<Dtype> out_data;

    for(auto read_addr : read_iterator.getAddr()) {
        out_data.push_back(data[select][read_addr]);
    }

    read_iterator.update();
    switch_check();
    return out_data;
}

template<typename Dtype>
void VirtualBuffer<Dtype>::write(const vector<Dtype>& in_data) {
    assert((!write_iterator.getDone()) && "No more write allowed.\n");

    auto write_addr_array = write_iterator.getAddr();
    assert((write_addr_array.size() == in_data.size()) && "Input data width not equals to port width.\n");
    for (size_t i = 0; i < in_data.size(); i ++) {
        int write_addr = write_addr_array[i];
        data[1 - select][write_addr] = in_data[i];
    }
    write_iterator.update();
    switch_check();
}

template<typename Dtype>
void VirtualBuffer<Dtype>::switch_check() {
    if (write_iterator.getDone() && read_iterator.getDone()) {
        select = select ^ 1;
        read_iterator.restart();
        write_iterator.restart();
    }
}

template class VirtualBuffer<int>;

