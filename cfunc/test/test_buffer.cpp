#include "virtualbuffer.h"
#include <iostream>
#include <cstdlib>
#include <assert.h>

using namespace std;

void GenAddrReadStream(vector<vector<int> > & );
void GenAddrWriteStream(vector<vector<int> > & );
void GenRandomBufferData(vector<int> &);
void WriteBlock(const vector<int> & data, const vector<vector<int> > & write_stream, shared_ptr<VirtualBuffer<int> > & buffer);
void ReadBlockCheck(const vector<int> & data, const vector<vector<int> > & read_stream, shared_ptr<VirtualBuffer<int> > & buffer);

int main(int argc, char* argv[]) {
    //define a access iterator for double buffer with
    //8 channels, 3x3 conv window , with 32x32 spatial dimension, 4 port at channel dimension
    shared_ptr<VirtualBuffer<int> > db(new VirtualBuffer<int>({9248}, {1}, {0},
                {6, 3, 32, 32}, {4, 272, 8, 272}, {0, 1, 2, 3}, 9248));

    vector<int> random_data_cube(73728, 0);
    GenRandomBufferData(random_data_cube);

    vector<vector<int> > read_stream(18432, vector<int>(4));
    vector<vector<int> > write_stream(9248, vector<int>(1));
    GenAddrReadStream(read_stream);
    GenAddrWriteStream(write_stream);

    int block_num = 4;
    WriteBlock(random_data_cube, write_stream, db);
    for (int data_block_cnt = 0; data_block_cnt < block_num; data_block_cnt ++) {
        ReadBlockCheck(random_data_cube, read_stream, db);
        cout << "Read block No " << data_block_cnt <<endl;
        GenRandomBufferData(random_data_cube);
        WriteBlock(random_data_cube, write_stream, db);
        cout << "Write block No " << data_block_cnt <<endl;
    }

    cout << "Test passed for VirtualBuffer!\n";

}

void GenRandomBufferData(vector<int> & random_data) {
    for (auto & data: random_data)
        data = rand();
}

void GenAddrReadStream(vector<vector<int> >& gold_stream) {
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

void GenAddrWriteStream(vector<vector<int> > & gold_stream) {
    for (int i = 0; i < 9248; i ++) {
        for (int port = 0; port < 1; port ++) {
            gold_stream[i][port] = i;
        }
    }
}

void WriteBlock(const vector<int> & data, const vector<vector<int> > & write_stream, shared_ptr<VirtualBuffer<int> > & buffer) {
    for (int i = 0; i < buffer->getWriteIteration(); i ++) {
        vector<int> in_data(buffer->getInPort(), 0);
        for (int port = 0; port < buffer->getInPort(); port ++){
            in_data[port] = data[write_stream[i][port]];
            buffer->write(in_data);
        }
    }
}

void ReadBlockCheck(const vector<int> & data, const vector<vector<int> > & read_stream, shared_ptr<VirtualBuffer<int> > & buffer) {
    for (int i = 0; i < buffer->getReadIteration(); i ++) {
        vector<int> out_data = buffer->read();
        for (int port = 0; port < buffer->getOutPort(); port ++){
            assert(out_data[port] == data[read_stream[i][port]] && "read data does not match");
        }
    }
}
