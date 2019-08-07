#include "virtualbuffer.h"
#include <assert.h>
#include <numeric>
#include <iostream>
using namespace std;

template<typename Dtype>
VirtualBuffer<Dtype>::VirtualBuffer(vector<int> in_range, vector<int> in_stride, vector<int> in_start,
        vector<int> out_range, vector<int> out_stride, vector<int> out_start,
        vector<int> in_chunk, vector<int>out_stencil, vector<int> dimension,
        int stencil_acc_dim):
    dimensionality(dimension.size()),
    stencil_acc_dim(stencil_acc_dim),
    select(false),
    is_db(isEqual(in_chunk, out_stencil)),
    write_iterator(in_range, in_stride, in_start),
    read_iterator(out_range, out_stride, out_start)
{
    auto mul = [&](int a, int b){return a*b; };
    capacity = accumulate(dimension.begin(), dimension.end(), 1, mul);

    input_port = write_iterator.getPort();
    output_port = read_iterator.getPort();

    preload_bound = accumulate(in_chunk.begin(), in_chunk.end(), 1, mul) / input_port;
    preload_done = Counter(preload_bound);
    read_in_stencil_bound = accumulate(out_range.begin(), out_range.begin()+stencil_acc_dim, 1, mul);
    stencil_read_done = Counter(read_in_stencil_bound);

    if (is_db)
        read_iterator.forceDone();
    stencil_read_done.forceDone();
    // The data bank you have, 0 is for active working set, 1 for preload data
    // here we have an optimization for double buffer, do not move around, just change the pointer
    data = vector<vector<Dtype> >(2, vector<Dtype>(capacity, (Dtype)0));
    // the valid domain for active working set
    valid_domain = vector<bool> (capacity, false);
}

template<typename Dtype>
bool VirtualBuffer<Dtype>::getStencilValid() {
    bool valid = true;
    for (auto read_addr : read_iterator.getAddr()) {
        valid = valid && valid_domain[read_addr];
    }
    return valid;
}

template<typename Dtype>
RetDataWithVal<Dtype> VirtualBuffer<Dtype>::read() {
    assert((!read_iterator.getDone()) && "No more read allowed.\n");
    vector<Dtype> out_data;
    bool valid = true;

    for(auto read_addr : read_iterator.getAddr()) {
        out_data.push_back(data[select][read_addr]);
        valid = valid && valid_domain[read_addr];
    }
    if (valid){
        stencil_read_done.update();
        read_iterator.update();
        switch_check();
    }
    return RetDataWithVal<Dtype>(out_data, valid);
}

template<typename Dtype>
void VirtualBuffer<Dtype>::write(const vector<Dtype>& in_data) {
    assert((!write_iterator.getDone()) && "No more write allowed.\n");

    auto write_addr_array = write_iterator.getAddr();
    assert((write_addr_array.size() == in_data.size()) && "Input data width not equals to port width.\n");
    for (size_t i = 0; i < in_data.size(); i ++) {
        int write_addr = write_addr_array[i];
        copy_addr.push_back(write_addr);
        data[1 - select][write_addr] = in_data[i];
    }
    preload_done.update();
    write_iterator.update();
    switch_check();

}

template<typename Dtype>
void VirtualBuffer<Dtype>::copy2writebank() {
    if (is_db){
        //optimization for double buffer, do not copy data just switch bank
        select = select ^ 1;
    }
    else {
        for (auto addr : copy_addr) {
            data[select][addr] = data[1 - select][addr];
        }
    }
    for (auto addr: copy_addr)
        valid_domain[addr] = true;
    copy_addr.clear();
}

template<typename Dtype>
void VirtualBuffer<Dtype>::switch_check() {
    //switch between data tile, invalid data valid domain
    if (write_iterator.getDone() && read_iterator.getDone()) {
        read_iterator.restart();
        write_iterator.restart();
        for (auto&& valid : valid_domain) {
            valid = false;
        }
    }
    // Condition to copy data, either both input chunk stencil finished or stencil is not valid when we are feeding data
    if (preload_done.reachBound() && (stencil_read_done.reachBound() || !getStencilValid()) ) {
        copy2writebank();
        preload_done.restart();
        stencil_read_done.restart();
    }
}

template class VirtualBuffer<int>;

