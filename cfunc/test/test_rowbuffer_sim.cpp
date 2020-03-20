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
    //define a access iterator for row buffer with
    //8x8 spatial dimension, 1 port and 8 cycle initial delay with capacity of 8
    //this is the version that implemented storage folding
    shared_ptr<VirtualBuffer<int> > db(new VirtualBuffer<int>({8}, {1}, {0},
                {8}, {1}, {0},
                {8}, {8}, {8}, {2}, 1));
    vector<int> random_data_cube(256, 0);
    GenRandomBufferData(random_data_cube);

    vector<vector<int> > read_stream(256, vector<int>(1));
    vector<vector<int> > write_stream(256, vector<int>(1));
    GenAddrReadStream(read_stream);
    GenAddrWriteStream(write_stream);

    GenRandomBufferData(random_data_cube);
    ReadWriteBlockCheck(random_data_cube, read_stream,write_stream, db);

    cout << "Test passed for Virtual Row Buffer!\n";

}

void GenRandomBufferData(vector<int> & random_data) {
    for (auto & data: random_data)
        data = rand();
}

void GenAddrReadStream(vector<vector<int> >& gold_stream) {
    for (int y = 0; y < 64; y ++) {
        gold_stream[y][0] = y;
    }
}

void GenAddrWriteStream(vector<vector<int> > & gold_stream) {
    for (int i = 0; i < 64; i ++) {
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
    for (int row = 0; row < 8; row ++) {
    for (int i = 0; i < buffer->getWriteIteration(); i ++) {
        vector<int> in_data(buffer->getInPort(), 0);
        for (int port = 0; port < buffer->getInPort(); port ++){
            in_data[port] = data[write_stream[row*8 + i][port]];
        }

        auto out_data_pack = buffer->read();
        auto out_data = std::get<0>(out_data_pack);
        bool out_valid = std::get<1>(out_data_pack);
        //cout << "no." << i << ", valid = " << out_valid << std::endl;
        if (row > 0){
            if (i > 1) {
                assert(out_valid == true && "Valid signal not match for valid signal");
            }
            else {
                assert(out_valid == false && "Valid signal not match for the initial halo");
            }
            for (int port = 0; port < buffer->getOutPort(); port ++){
                //cout << "read data: " << out_data[port] <<", expected data: " << data[read_stream[output_cnt][port]] <<" at location: " << read_stream[output_cnt][port] << endl;
                assert(out_data[port] == data[read_stream[output_cnt][port]] && "read data does not match");
            }
            output_cnt ++;
        }
        else {
            assert(out_valid == false && "Valid signal not match for the first delay row");
        }

        buffer->write(in_data);
        //std::cout << "No. " << i << " write data: " << in_data[0] << std::endl;
    }
    }
}
