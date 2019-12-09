#ifndef ACCESS_H_
#define ACCESS_H_

#include <vector>
using namespace std;

class AccessPattern {
    public:
        AccessPattern() {};
        AccessPattern(vector<int> _range, vector<int> _stride, vector<int> _start);
        vector<int> range;
        vector<int> stride;
        vector<int> start;
        int dimension;
        int port;
        int total_iter;
};

class AccessIter {
    public:
        AccessIter() {};
        AccessIter(vector<int> _range, vector<int> _stride, vector<int> _start);
        AccessIter(vector<int> _range, vector<int> _stride, vector<int> _start, vector<int> _stencil_width);
        void restart();
        void update();
        bool getDone() {return done;}
        int getPort() {return acc_pattern.port;}
        int getTotalIteration() {return acc_pattern.total_iter;}
        void forceDone() {done = true;}
        vector<int> getAddr() {return addr;}
        AccessPattern acc_pattern;

        //stencil width is an optional parameter, it has the same dimensionality as the loop iterator and
        //will give create a stencil valid signal while iterator is large than stencil width at that dimension
        bool use_stencil_width;
        vector<int> stencil_width;
        bool getStencilValid();

    private:
        vector<int> iter_list;
        vector<int> addr;
        bool done;
};


#endif
