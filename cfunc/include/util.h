#ifndef UTIL_H_
#define UTIL_H_

#include <vector>
#include <assert.h>
#include <iostream>

//helper class and helper functions

class Counter {
    public:
        Counter(){}
        Counter(int _bound): bound(_bound), cnt(0){}
        void update() {
            if (cnt < bound)
                cnt ++;
            else
                assert(false && "Counter has already reach bound, cannot increment!\n");
        }
        bool reachBound() {return cnt == bound;};
        void forceDone() {cnt = bound; }
        void restart() {cnt = 0;}
    private:
        int bound;
        int cnt;
};
/*
template<typename Dtype>
struct RetDataWithVal {
    RetDataWithVal(vector<Dtype> _data, bool _valid):
    data(_data), valid(_valid){}

    std::vector<Dtype> data;
    bool valid;
};

template<typename Dtype>
void init_RetDataWithVal<Dtype>(py::module &m);
*/
template<typename T>
bool isEqual(std::vector<T> const &v1, std::vector<T> const &v2)
{
        return (v1.size() == v2.size() && std::equal(v1.begin(), v1.end(), v2.begin()));

}

template<typename T>
void assignValIfEmpty(std:: vector<T> & v1, std::vector<T> const &v_assign, int start_dim, T default_val) {
    //function to assign the vector element from start_dim to end,
    //if it's empty assign default_val
    assert(start_dim <= v_assign.size() &&
            "assign dimension should not exceed the target vector dimension!\n");
    v1.assign(v_assign.begin()+start_dim, v_assign.end());
    if (v1.empty())
        v1.push_back(default_val);
}

inline void AddrGen(std::vector<int> & gen_addr,
        const std::vector<int> & rng,
        const std::vector<int>& st,
        const int stencil_size) {
    //helper function generate the starting address for stencil iterator
    int dim = rng.size();
    std::vector<int> idx(3, 0);

    for (int i = 0; i < stencil_size; i ++) {
        int addr = 0;
        for (int dimension = 0; dimension < dim; dimension ++) {
            addr += idx[dimension] * st[dimension];
        }
        gen_addr.push_back(addr);

        for (int dimension  = 0; dimension < dim; dimension ++) {
            idx[dimension] ++;
            if (idx[dimension] ==  rng[dimension])
                idx[dimension] = 0;
            else
                break;
        }
    }
}



#endif
