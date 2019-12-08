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
    is_db(isEqual(in_chunk, dimension)),
    stencil_valid_to_be_read(false),
    write_iterator(in_range, in_stride, in_start),
    read_iterator(out_range, out_stride, out_start)
{
    auto mul = [&](int a, int b){return a*b; };
    capacity = accumulate(dimension.begin(), dimension.end(), 1, mul);

    //create acc_iter for read_stencil_iterator
    vector<int> stencil_range, stencil_stride, stencil_start;
    assignValIfEmpty<int>(stencil_range, out_range, stencil_acc_dim, 1);
    assignValIfEmpty<int>(stencil_stride, out_stride, stencil_acc_dim, 1);
    vector<int> acc_dim;
    for (int i = 0; i < dimensionality; i ++) {
        acc_dim.push_back(accumulate(dimension.begin(), dimension.begin()+i, 1, mul));
    }
    int stencil_size= accumulate(out_stencil.begin(), out_stencil.end(), 1, mul);
    AddrGen(stencil_start, out_stencil, acc_dim, stencil_size);
    stencil_iterator = AccessIter(stencil_range, stencil_stride, stencil_start);

    input_port = write_iterator.getPort();
    output_port = read_iterator.getPort();

    preload_bound = accumulate(in_chunk.begin(), in_chunk.end(), 1, mul) / input_port;
    preload_done = Counter(preload_bound);
    read_in_stencil_bound = accumulate(out_range.begin(), out_range.begin()+stencil_acc_dim, 1, mul);
    stencil_read_done = Counter(read_in_stencil_bound);

    //for double buffer initialization
    if (is_db)
        read_iterator.forceDone();

    // The data bank you have, 0 is for active working set, 1 for preload data
    // here we have an optimization for double buffer, do not move around, just change the pointer
    data = vector<vector<Dtype> >(2, vector<Dtype>(capacity, (Dtype)0));
    // the valid domain for active working set
    valid_domain = vector<bool> (capacity, false);
}

template<typename Dtype>
bool VirtualBuffer<Dtype>::getStencilValid() {
    bool valid = true;
    for (auto read_addr : stencil_iterator.getAddr()) {
        valid = valid && valid_domain[read_addr%capacity];
        //std::cout << "valid_domain: " << read_addr << ", " << valid_domain[read_addr%capacity] << endl;
    }
    return valid;
}

template<typename Dtype>
std::tuple<vector<Dtype>, bool> VirtualBuffer<Dtype>::read() {

    //assert((!read_iterator.getDone()) && "No more read allowed.\n");
    //if reach the end you could read but never get valid
    vector<Dtype> out_data;
    bool valid = !read_iterator.getDone();
    if( stencil_valid_to_be_read == false) {
        stencil_valid_to_be_read = getStencilValid();
    }
    valid = stencil_valid_to_be_read;
    valid &= !stencil_read_done.reachBound();

    for(auto read_addr : read_iterator.getAddr()) {
        read_addr %= capacity;
        out_data.push_back(data[select][read_addr]);
        //valid = valid && valid_domain[read_addr];
    }


    if (valid){
        stencil_read_done.update();
        read_iterator.update();
        switch_check();
    }
    return std::make_tuple(out_data, valid);
}

template<typename Dtype>
void VirtualBuffer<Dtype>::write(const vector<Dtype>& in_data) {
    assert((!write_iterator.getDone()) && "No more write allowed.\n");

    auto write_addr_array = write_iterator.getAddr();
    assert((write_addr_array.size() == in_data.size()) && "Input data width not equals to port width.\n");
    for (size_t i = 0; i < in_data.size(); i ++) {
        int write_addr = write_addr_array[i] % capacity;
        //std::cout << "write_addr = " << write_addr << std::endl;
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
    for (auto addr: copy_addr) {
        valid_domain[addr] = true;
    }
    copy_addr.clear();
}

template<typename Dtype>
void VirtualBuffer<Dtype>::switch_check() {
    // Condition to copy data, either both input chunk stencil finished or stencil is not valid when we are feeding data
    if (stencil_valid_to_be_read == false) {
        if (preload_done.reachBound()){
            copy2writebank();
            preload_done.restart();
        }
    }
    //copy the data in steady state
    else if (preload_done.reachBound() && (stencil_read_done.reachBound()  )) {
        //update the stencil iterator if we finish read all the data from output stencil

        stencil_iterator.update();
        stencil_valid_to_be_read = false;
        //TODO: double check this part may be improved
        if (stencil_iterator.getDone()){
            stencil_iterator.restart();
        }

        copy2writebank();
        preload_done.restart();
        stencil_read_done.restart();
    }


    //switch between data tile, invalid data valid domain
    if (write_iterator.getDone() && read_iterator.getDone()) {
        read_iterator.restart();
        write_iterator.restart();
        for (size_t i = 0; i < valid_domain.size(); i++) {
          valid_domain[i] = false;
        }
        //for (auto& valid : valid_domain) {
            //valid = false;
        //}
    }
}

template class VirtualBuffer<int>;

