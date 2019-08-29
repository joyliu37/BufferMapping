#include "access.h"
#include <iostream>
#include <assert.h>
#include <memory>

using namespace std;

void GenAddrStream(vector<vector<int> > & );

int main(int argc, char* argv[]) {
    //define a access iterator for double buffer with
    //8 channels, 3x3 conv window , with 32x32 spatial dimension, 4 port at channel dimension
    shared_ptr<AccessIter> db_iter(new AccessIter(
                {6, 3, 32, 32},
                {4, 272, 8, 272},
                {0, 1, 2, 3}));

    vector<vector<int>> gold_stream(18432, vector<int>(4));
    GenAddrStream(gold_stream);
    db_iter->restart();
    for (int itr = 0; itr < 18432; itr ++) {
        vector<int> addr = db_iter->getAddr();
        vector<int> ref_addr = gold_stream[itr];
        for (size_t i = 0; i < addr.size(); i ++) {
            //cout << addr[i] << "," << ref_addr[i] <<endl;
            assert(addr[i] == ref_addr[i] && "Generated address did not match");
        }
        //cout << "produce result for pos" << itr << ".\n";
        db_iter->update();
    }
    cout << "Test passed for AccessIter!\n";

}

void GenAddrStream(vector<vector<int> >& gold_stream) {
    int cnt = 0;
    for (int y = 0; y < 32; y ++) {
        for (int x = 0; x < 32; x ++) {
            for (int ky = 0; ky < 3; ky ++) {
                for (int kx = 0; kx < 3; kx ++) {
                    for (int c = 0; c < 2; c ++) {
                        for (int port = 0; port < 4; port ++) {
                            int addr = (y+ky) * 34 * 8 + (x+kx) * 8 + c * 4 + port;
                            gold_stream[cnt][port] = addr;
                        }
                        cnt ++;
                    }
                }
            }
        }
    }
}
