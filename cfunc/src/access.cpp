#include "access.h"
#include <assert.h>

using namespace std;

AccessPattern::AccessPattern(vector<int> _range, vector<int> _stride, vector<int> _start) {
    assert(_range.size() == _stride.size() && "range and stride must has same dimension in Access Pattern definition.\n");
    dimension = _range.size();
    port = _start.size();
    total_iter = 1;

    for (auto _rng: _range) {
        this->range.push_back(_rng);
        total_iter *= _rng;
    }

    for (auto _st: _stride) {
        this->stride.push_back(_st);
    }

    for (auto start_pos: _start) {
        this->start.push_back(start_pos);
    }
}

AccessIter::AccessIter(vector<int> _range, vector<int> _stride, vector<int> _start, vector<int> _stencil_width) :
    done(false), use_stencil_width(true){
    acc_pattern = AccessPattern(_range, _stride, _start);

    for (int stencil_width_dim : _stencil_width) {
        stencil_width.push_back(stencil_width_dim);
    }

    for (int i = 0; i < acc_pattern.dimension; i ++) {
        iter_list.push_back(0);
    }

    for (int start_pos: acc_pattern.start) {
        addr.push_back(start_pos);
    }
}

bool AccessIter::getStencilValid() {
    if (use_stencil_width){
        bool valid = true;
        for (auto itr = 0; itr < iter_list.size(); itr ++) {
            valid &= iter_list[itr] >= stencil_width[itr];
        }
        return valid;
    }
    else {
        return true;
    }
}

AccessIter::AccessIter(vector<int> _range, vector<int> _stride, vector<int> _start) :
    done(false), use_stencil_width(false){
    acc_pattern = AccessPattern(_range, _stride, _start);

    for (int i = 0; i < acc_pattern.dimension; i ++) {
        iter_list.push_back(0);
    }

    for (int start_pos: acc_pattern.start) {
        addr.push_back(start_pos);
    }
}

void AccessIter::restart() {
    for (int & iter : iter_list) {
        iter = 0;
    }

    for (size_t i = 0; i < acc_pattern.start.size(); i ++) {
        addr[i] = acc_pattern.start[i];
    }

    done = false;
}

void AccessIter::update() {
    assert(!done && "Error: no more access can make because it's done!\n");

    //logic to update the internal iterator
    for (int dim = 0; dim < acc_pattern.dimension; dim ++) {
        iter_list[dim] += 1;

        //return to zero for the previous dim if we enter the next dim
        if (dim > 0)
            iter_list[dim - 1] = 0;

        //not the last dimension
        if (dim < acc_pattern.dimension - 1) {
            if (iter_list[dim] < acc_pattern.range[dim])
                break;
        }
        else {
            if (iter_list[dim] == acc_pattern.range[dim]){
                done = true;
                break;
            }
        }
    }


    int addr_offset = 0;
    for (int i = 0; i < acc_pattern.dimension; i ++) {
        addr_offset += iter_list[i] * acc_pattern.stride[i];
    }

    for (int port_num = 0; port_num < acc_pattern.port; port_num ++) {
        addr[port_num] = addr_offset + acc_pattern.start[port_num];
    }
}

