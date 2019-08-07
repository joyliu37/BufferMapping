#ifndef UTIL_H_
#define UTIL_H_

#include <vector>
#include <assert.h>
#include <iostream>

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

template<typename Dtype>
struct RetDataWithVal {
    RetDataWithVal(vector<Dtype> _data, bool _valid):
    data(_data), valid(_valid){}

    std::vector<Dtype> data;
    bool valid;
};

template<typename T>
bool isEqual(std::vector<T> const &v1, std::vector<T> const &v2)
{
        return (v1.size() == v2.size() && std::equal(v1.begin(), v1.end(), v2.begin()));

}

#endif
