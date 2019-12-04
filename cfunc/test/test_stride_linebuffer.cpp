#include "virtualbuffer.h"
#include <iostream>
#include <cstdlib>
#include <assert.h>
#include <memory>

using namespace std;

void GenAddrReadStream(vector<vector<int> > & );
void GenAddrWriteStream(vector<vector<int> > & );
void GenRandomBufferData(vector<int> &);
//void WriteBlock(const vector<int> & data, const vector<vector<int> > & write_stream, shared_ptr<VirtualBuffer<int> > & buffer);
//void ReadBlockCheck(const vector<int> & data, const vector<vector<int> > & read_stream, shared_ptr<VirtualBuffer<int> > & buffer);
void ReadWriteBlockCheck(const vector<int> & data,
        const vector<vector<int> > & read_stream,
        const vector<vector<int> > & write_stream,
        shared_ptr<VirtualBuffer<int> > & buffer);

int main(int argc, char* argv[]) {
    //define a access iterator for double buffer with
    //8 channels, 3x3 conv window , with 32x32 spatial dimension, 4 port at channel dimension
    shared_ptr<VirtualBuffer<int> > db(new VirtualBuffer<int>({64, 64}, {1, 64}, {0},
                {31, 31}, {2, 128}, {0, 1, 2, 64, 65, 66, 128, 129, 130},
                {2, 2}, {3, 3}, {64, 64}, 0));
    vector<int> random_data_cube(16384, 0);
    GenRandomBufferData(random_data_cube);

    vector<vector<int> > read_stream(3844, vector<int>(9));
    vector<vector<int> > write_stream(4096, vector<int>(1));
    GenAddrReadStream(read_stream);
    GenAddrWriteStream(write_stream);

    int block_num = 4;
    for (int data_block_cnt = 0; data_block_cnt < block_num; data_block_cnt ++) {
        GenRandomBufferData(random_data_cube);
        ReadWriteBlockCheck(random_data_cube, read_stream,write_stream, db);
        cout << "Test data block No " << data_block_cnt <<endl;
    }

    cout << "Test passed for Virtual Stride Line Buffer!\n";

}

void GenRandomBufferData(vector<int> & random_data) {
    for (auto & data: random_data)
        data = rand();
}

void GenAddrReadStream(vector<vector<int> >& gold_stream) {
    int cnt = 0;
    for (int y = 0; y < 31; y ++) {
        for (int x = 0; x < 31; x ++) {
            for (int ky = 0; ky < 3; ky ++) {
                for (int kx = 0; kx < 3; kx ++) {
                    int addr = (2*y + ky)* 64 + 2*x + kx;
                        gold_stream[cnt][kx + ky*3] = addr;
                }
            }
            cnt ++;
        }
    }
}

void GenAddrWriteStream(vector<vector<int> > & gold_stream) {
    for (int i = 0; i < 4096; i ++) {
        for (int port = 0; port < 1; port ++) {
            gold_stream[i][port] = i;
        }
    }
}

void ReadWriteBlockCheck(const vector<int> & data,
        const vector<vector<int> > & read_stream,
        const vector<vector<int> > & write_stream,
        shared_ptr<VirtualBuffer<int> > & buffer) {
    int output_cnt = 0;
    for (int i = 0; i < buffer->getWriteIteration(); i ++) {
        vector<int> in_data(buffer->getInPort(), 0);
        for (int port = 0; port < buffer->getInPort(); port ++){
            in_data[port] = data[write_stream[i][port]];
        }
        buffer->write(in_data);
        //std::cout << "Write data in location " << i << std::endl;

        //if (output_cnt < 31*31){
        //extra check for strided conv
        auto out_data_pack = buffer->read();
        auto out_data = std::get<0>(out_data_pack);
        bool out_valid = std::get<1>(out_data_pack);
        //std::cout << "Read data in location " << i <<", valid = " << out_valid << std::endl;
        if (out_valid){
            for (int port = 0; port < buffer->getOutPort(); port ++){
                assert(out_data[port] == data[read_stream[output_cnt][port]] && "read data does not match");
            }
        output_cnt ++;

        }

    }
}
