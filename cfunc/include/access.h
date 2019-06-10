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
};

class AccessIter {
    public:
        AccessIter() {};
        AccessIter(vector<int> _range, vector<int> _stride, vector<int> _start);
        void restart();
        void update();
        bool getDone() {return done;}
        vector<int> getAddr() {return addr;}

    private:
        AccessPattern acc_pattern;
        vector<int> iter_list;
        vector<int> addr;
        bool done;
};
#endif
