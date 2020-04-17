#include "coreir.h"
#include "coreir/passes/transform/rungenerators.h"
#include "coreir/simulator/interpreter.h"
#include "coreir/libs/commonlib.h"
#include "coreir/libs/float.h"
#include "access.h"
#include "util.h"
#include "virtualbuffer.h"

//#include "fuzzing.hpp"

#include <iostream>
#include <numeric>


namespace CoreIR {


// Define address generator simulation class
  class UnifiedBufferAddressGenerator : public SimulatorPlugin {
    int width;
    std::vector<int> iter_list;

    std::vector<int> output_range;
    std::vector<int> output_stride;
    std::vector<int> output_start;

    size_t dimension;
    size_t port;
    int total_iter;
    bool is_done;

    std::vector<int> get_dims(Type* type) {
      std::vector<int> lengths;
      uint bitwidth = 1;
      Type* cType = type;
      while(!cType->isBaseType()) {
        if (auto aType = dyn_cast<ArrayType>(cType)) {

          uint length = aType->getLen();

          cType = aType->getElemType();
          if (cType->isBaseType()) {
            bitwidth = length;
          } else {
            lengths.insert(lengths.begin(), length);
            //lengths.push_back(length);
          }
        }
      }

      lengths.insert(lengths.begin(), bitwidth);
      return lengths;
    }

  public:
    UnifiedBufferAddressGenerator() {
      is_done = false;
    }

    UnifiedBufferAddressGenerator(std::vector<int> range, std::vector<int> stride, std::vector<int> start, int myWidth) :
      is_done(false) {
      init_parameters(myWidth, range, stride, start);
    }

    bool isDone() {
      return is_done;
    }

    void restart() {
      is_done = false;
      for (auto &iter : iter_list) {
        iter = 0;
      }
    }

    void setDone() {
        is_done = true;
    }

    void updateIterator(BitVector resetVal) {
      if (resetVal == BitVector(1, 1)) {
        restart();
        return;
      }

      // logic to update the internal iterator
      for (size_t dim = 0; dim < dimension; dim++) {
        iter_list[dim] += 1;

        //return to zero for the previous dim if we enter the next dim
        if (dim > 0)
          iter_list[dim - 1] = 0;

        //not the last dimension
        if (dim < dimension - 1) {
          if (iter_list[dim] < output_range[dim]) {
            is_done = false;
            break;
          }
        } else {
          if (iter_list[dim] == output_range[dim]){
            is_done = true;
            break;
          }
        }
      }
    }

    int calcBaseAddress() {
#if VERBOSE==1
      std::cout << "dims=" << dimension << std::endl;
#endif
      int addr_offset = 0;
      assert(iter_list.size() <= dimension);
      assert(output_stride.size() <= dimension);
      for (size_t i = 0; i < dimension; i++) {
        addr_offset += iter_list.at(i) * output_stride.at(i);
      }
      return addr_offset;
    }

    std::vector<int> getAddresses() {
      std::vector<int> addresses = std::vector<int>(output_start.size());
      auto baseAddr = calcBaseAddress();

      for (size_t i=0; i<addresses.size(); ++i) {
        addresses.at(i) = baseAddr + output_start.at(i);
      }

      return addresses;
    }


    void init_parameters(int _width, std::vector<int> _output_range, std::vector<int> _output_stride, std::vector<int> _output_start) {
      width = _width;
      output_range = _output_range;
      output_stride = _output_stride;
      output_start = _output_start;

      // start values all need to decrement 1
      //for (auto& start_num : output_start) {
      //  start_num -= 1;
      //}

      // deduce from other parameters
      assert(output_range.size() == output_stride.size());
      dimension = output_range.size();
      std::cout << "buffer has " << dimension << " dims\n";
      port = output_start.size();
      total_iter = 1;

      for (size_t i = 0; i < dimension; ++i) {
        total_iter *= output_range.at(i) / output_stride.at(i);
      }

      // initialize parameters
      iter_list = std::vector<int>(dimension);
      assert(iter_list.size() == dimension);
      restart();
    }


    void initialize(vdisc vd, SimulatorState& simState) {
      auto wd = simState.getCircuitGraph().getNode(vd);
      Wireable* w = wd.getWire();

      assert(isInstance(w));

      // extract parameters
      Instance* inst = toInstance(w);
      auto myWidth = inst->getModuleRef()->getGenArgs().at("width")->get<int>();
      auto rangeType = inst->getModuleRef()->getGenArgs().at("range_type")->get<Type*>();
      auto strideType = inst->getModuleRef()->getGenArgs().at("stride_type")->get<Type*>();
      auto startType = inst->getModuleRef()->getGenArgs().at("start_type")->get<Type*>();

      init_parameters(myWidth, get_dims(rangeType), get_dims(strideType), get_dims(startType));
    }

    void exeSequential(vdisc vd, SimulatorState& simState) {
      auto wd = simState.getCircuitGraph().getNode(vd);

      simState.updateInputs(vd);

      assert(isInstance(wd.getWire()));

      Instance* inst = toInstance(wd.getWire());

      auto inSels = getInputSelects(inst);

      Select* arg1 = toSelect(CoreIR::findSelect("reset", inSels));
      assert(arg1 != nullptr);
      BitVector resetVal = simState.getBitVec(arg1);

      updateIterator(resetVal);
    }

    void exeCombinational(vdisc vd, SimulatorState& simState) {
#if VERBOSE==1
      std::cout << "execomb..\n";
#endif
      auto wd = simState.getCircuitGraph().getNode(vd);

      Instance* inst = toInstance(wd.getWire());

      int addr_offset = calcBaseAddress();
      simState.setValue(toSelect(inst->sel("out")), BitVector(width, addr_offset));
    }

  };

/*****new funcitonal simulation****/

//helper function
/*
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
    RetDataWithVal(std::vector<Dtype> _data, bool _valid):
    data(_data), valid(_valid){}

    std::vector<Dtype> data;
    bool valid;
};

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


//access pattern access iteration class
class AccessPattern {
    public:
        AccessPattern() {};
        AccessPattern(std::vector<int> _range, std::vector<int> _stride, std::vector<int> _start);
        std::vector<int> range;
        std::vector<int> stride;
        std::vector<int> start;
        int dimension;
        int port;
        int total_iter;
};

class AccessIter {
    public:
        AccessIter() {};
        AccessIter(std::vector<int> _range, std::vector<int> _stride, std::vector<int> _start);
        void restart();
        void update();
        bool getDone() {return done;}
        int getPort() {return acc_pattern.port;}
        int getTotalIteration() {return acc_pattern.total_iter;}
        void forceDone() {done = true;}
        std::vector<int> getAddr() {return addr;}

    private:
        AccessPattern acc_pattern;
        std::vector<int> iter_list;
        std::vector<int> addr;
        bool done;
};


//virtual buffer helper class
template <typename Dtype>
class VirtualBuffer {
    public:
        VirtualBuffer() {};
        VirtualBuffer(std::vector<int> in_range, std::vector<int> in_stride, std::vector<int> in_start,
                std::vector<int> out_range, std::vector<int> out_stride, std::vector<int> out_start,
                std::vector<int> in_chunk, std::vector<int> out_stencil, std::vector<int> dimension,
                int stencil_acc_dim);
        RetDataWithVal<Dtype> read();
        void write(const std::vector<Dtype>& write_data);
        void switch_check();
        void copy2writebank();
        bool getStencilValid();
        int getReadIteration() {return read_iterator.getTotalIteration();}
        int getWriteIteration() {return write_iterator.getTotalIteration();}
        int getInPort() {return input_port;}
        int getOutPort() {return output_port;}

    private:

        int input_port, output_port, capacity, dimensionality, stencil_acc_dim;
        int preload_bound, read_in_stencil_bound;
        bool select, is_db;
        AccessIter write_iterator, read_iterator, stencil_iterator;
        Counter preload_done, stencil_read_done;
        std::vector<std::vector<Dtype> > data;
        std::vector<bool> valid_domain;
        std::vector<int> copy_addr;
};
*/

//functional model
  class UnifiedBuffer_new : public SimulatorPlugin {
  private:
    map<string, VirtualBuffer<int>> func_kernel;
    bool valid_wire = false;
    bool wenVal = false, renVal=false;
    bool use_input_access_pattern, rate_matched = false;//, wen_wire, ren_wire;
    int width, dimensionality;
    std::vector<int> in_data_wire;
    map<string, vector<int>> out_data_wire;
    std::vector<string> istream_name;
    std::vector<string> ostream_name;

  public:
    UnifiedBuffer_new (bool use = false) {
        use_input_access_pattern = use;
    }
    vector<int> to_vec(const Json data) {
        vector<int> tmp;
        for (auto const & item: data)
            tmp.push_back(item);
        return tmp;
    }

    void initialize(vdisc vd, SimulatorState& simState) {
      auto wd = simState.getCircuitGraph().getNode(vd);
      Wireable* w = wd.getWire();

      assert(isInstance(w));

      std::cout << "start initialization" << std::endl;
      std::vector<int> input_stride, output_stride, input_range, output_range,  input_start, output_start, input_chunk, output_stencil, dimension;
      vector<int> stencil_width;
      int stencil_acc_dim;

      // extract parameters
      Instance* inst = toInstance(w);
      std::cout << inst->getModuleRef()->getRefName() << std::endl;
      string module_name = inst->getModuleRef()->getRefName();

      //initial the value

      auto inSels = getInputSelects(inst);
      Select* arg_wen= toSelect(CoreIR::findSelect("wen", inSels));
      Select* arg_ren= toSelect(CoreIR::findSelect("ren", inSels));
      //simState.setValue(toSelect(inst->sel("valid")), BitVector(1, false));
      assert(arg_wen != nullptr);
      assert(arg_ren != nullptr);
      cout << "Setting arg_wen" << endl;
      simState.setValue(arg_wen, BitVector(1, false));
      cout << "Setting arg_ren" << endl;
      simState.setValue(arg_ren, BitVector(1, false));

      cout << "finish set value" << endl;

      if (module_name == "lakelib.unified_buffer") {
        rate_matched = inst->getModuleRef()->getGenArgs().at("rate_matched")->get<bool>();
        width = inst->getModuleRef()->getGenArgs().at("width")->get<int>();
        dimensionality = inst->getModuleRef()->getGenArgs().at("dimensionality")->get<int>();
        stencil_width.push_back( inst->getModuleRef()->getGenArgs().at("stencil_width")->get<int>());
        stencil_acc_dim = inst->getModuleRef()->getGenArgs().at("num_stencil_acc_dim")->get<int>();

        //output range
        for (int i = 0; i < dimensionality; i ++) {
          if (inst->getModuleRef()->getGenArgs().at("input_range_"+std::to_string(i))->get<int>() == 0)
            break;
          input_stride.push_back(inst->getModuleRef()->getGenArgs().at("input_stride_"+std::to_string(i))->get<int>());
          input_range.push_back(inst->getModuleRef()->getGenArgs().at("input_range_"+std::to_string(i))->get<int>());
        }

        for (int i = 0; i < dimensionality; i ++) {
            output_stride.push_back(inst->getModuleRef()->getGenArgs().at("stride_"+std::to_string(i))->get<int>());
            output_range.push_back(inst->getModuleRef()->getGenArgs().at("range_"+std::to_string(i))->get<int>());
        }

        auto output_start_json = inst->getModuleRef()->getGenArgs().at("output_starting_addrs")->get<json>();
        for (auto const & start_val: output_start_json["output_start"]) {
          output_start.push_back(start_val);
        }

        auto input_start_json = inst->getModuleRef()->getGenArgs().at("input_starting_addrs")->get<json>();
        for (auto const & start_val: input_start_json["input_start"]) {
          input_start.push_back(start_val);
        }

        auto in_chunk_json = inst->getModuleRef()->getGenArgs().at("input_chunk")->get<json>();
        for (auto const & dim_val: in_chunk_json["input_chunk"]) {
          input_chunk.push_back(dim_val);
        }

        auto out_stencil_json = inst->getModuleRef()->getGenArgs().at("output_stencil")->get<json>();
        for (auto const & dim_val: out_stencil_json["output_stencil"]) {
          output_stencil.push_back(dim_val);
        }

        auto dimension_json = inst->getModuleRef()->getGenArgs().at("logical_size")->get<json>();
        for (auto const & dim_val: dimension_json["capacity"]) {
          dimension.push_back(dim_val);
        }

        //fill in the wire with 0 after definition
        std::fill_n(std::back_inserter(in_data_wire), input_start.size(), 0);
        std::fill_n(std::back_inserter(out_data_wire["def"]), output_start.size(), 0);

        std::cout << "Start Initialize the Func Kernel" << std::endl;

        func_kernel["def"] = VirtualBuffer<int>(input_range, input_stride, input_start,
          output_range, output_stride, output_start,
          input_chunk, output_stencil, dimension, stencil_width, stencil_acc_dim);

        std::cout << "Finish Initialize the Func Kernel" << std::endl;
      }
      else if (module_name == "lakelib.new_unified_buffer") {
          cout << "Parse Parameter for New Unified Buffer.\n";
        auto genargs = inst->getModuleRef()->getGenArgs();
        width = genargs.at("width")->get<int>();
        Json istreams = genargs.at("istreams")->get<Json>();
        Json ostreams = genargs.at("ostreams")->get<Json>();
        dimension = to_vec(genargs.at("logical_size")->get<Json>()["capacity"]);
        for (auto& stream : nlohmann::json::iterator_wrapper(istreams)) {
            istream_name.push_back(stream.key());
            if (use_input_access_pattern){
                input_start = to_vec(stream.value()["input_starting_addrs"]);
                input_range = to_vec(stream.value()["input_range"]);
                input_stride = to_vec(stream.value()["input_stride"]);

            }
            input_chunk = to_vec(stream.value()["input_chunk"]);
            //TODO: update the ubuffer functional model to support multistream, right now just support single stream
            break;
            }

        if (use_input_access_pattern)
           std::fill_n(std::back_inserter(in_data_wire), input_start.size(), 0);
        else
           std::fill_n(std::back_inserter(in_data_wire), 1, 0);
        for (auto& stream : nlohmann::json::iterator_wrapper(ostreams)) {
            ostream_name.push_back(stream.key());
            output_start = to_vec(stream.value()["output_starting_addrs"]);
            output_range = to_vec(stream.value()["output_range"]);
            output_stride = to_vec(stream.value()["output_stride"]);
            output_stencil = to_vec(stream.value()["output_stencil"]);
            stencil_width = to_vec(stream.value()["stencil_width"]);
            stencil_acc_dim = stream.value()["num_stencil_acc_dim"];
            dimensionality = output_range.size();


            if (use_input_access_pattern){
                std::fill_n(std::back_inserter(out_data_wire[stream.key()]), output_start.size(), 0);
                func_kernel[stream.key()] =
                VirtualBuffer<int>(input_range, input_stride, input_start,
                  output_range, output_stride, output_start,
                  input_chunk, output_stencil, dimension, stencil_width, stencil_acc_dim);

            }
            else {
                std::fill_n(std::back_inserter(out_data_wire[stream.key()]), output_start.size(), 0);
                func_kernel[stream.key()] = VirtualBuffer<int>(output_range, output_stride, output_start,
                  input_chunk, output_stencil, dimension, stencil_width, stencil_acc_dim);
            }
        }

        //fill in the wire with 0 after definition

        for (auto func_kernel_stream: func_kernel) {
            cout << "Virtual buffer for stream: " << func_kernel_stream.first << endl;
        }
        std::cout << "Finish Initialize the Func Kernel" << std::endl;

      }
    /*
      auto outputRangeType = inst->getModuleRef()->getGenArgs().at("output_range_type")->get<Type*>();
      auto outputStrideType = inst->getModuleRef()->getGenArgs().at("output_stride_type")->get<Type*>();
      auto outputStartType = inst->getModuleRef()->getGenArgs().at("output_start_type")->get<Type*>();

      auto inputRangeType = inst->getModuleRef()->getGenArgs().at("input_range_type")->get<Type*>();
      auto inputStrideType = inst->getModuleRef()->getGenArgs().at("input_stride_type")->get<Type*>();
      auto inputStartType = inst->getModuleRef()->getGenArgs().at("input_start_type")->get<Type*>();

      auto output_range = get_dims(outputRangeType);
      auto output_stride = get_dims(outputStrideType);
      auto output_start = get_dims(outputStartType);
*/
      //write_iterator = UnifiedBufferAddressGenerator(input_range, input_stride, input_start, width);
      //read_iterator = UnifiedBufferAddressGenerator(output_range, output_stride, output_start, width);

      //read_iterator.setDone();

      // deduce capacity from other output iterator
      /*
      auto mul = [&](int a, int b){return a*b; };
      capacity = accumulate(input_range.begin(), input_range.end(), 1, mul);

      size_t dimension = output_range.size();

      for (size_t i = 0; i < dimension; ++i) {
        capacity += (output_range.at(i) - 1) * max(output_stride.at(i), 0);
      }

      int max_start = 0;
      for (const auto &start_value : output_start) {
        max_start = max(max_start, start_value);
      }
      capacity += max_start;
      */


      // initialize data and select
      //data = std::vector< std::vector<int> >(2, std::vector<int>(capacity, 0));
      //select = 0;

    }

    void exeSequential(vdisc vd, SimulatorState& simState) {
      auto wd = simState.getCircuitGraph().getNode(vd);

      simState.updateInputs(vd);

      assert(isInstance(wd.getWire()));

      Instance* inst = toInstance(wd.getWire());

#if VERBOSE == 1
      std::cout <<"Ubuf->{" << inst->getInstname() << "} exeseq.." <<std::endl;
      std::cout << "ren: " << renVal << ", wen: " << wenVal<<endl;
#endif

      auto inSels = getInputSelects(inst);

      //FIXME: change this into sequential, and add a reset method for functional model.
      Select* arg1 = toSelect(CoreIR::findSelect("reset", inSels));
      assert(arg1 != nullptr);
      BitVector resetVal = simState.getBitVec(arg1);

      //get the wen value

      /*Select* arg_wen= toSelect(CoreIR::findSelect("wen", inSels));
      assert(arg_wen != nullptr);
      BitVector wenVal = simState.getBitVec(arg_wen);
      //get ren value
      Select* arg_ren= toSelect(CoreIR::findSelect("ren", inSels));
      assert(arg_ren != nullptr);
      BitVector renVal = simState.getBitVec(arg_ren);
      if (rate_matched)
          renVal = wenVal;
*/

      //only update the internal state(write to buffer) if wen
      //if (wenVal == BitVector(1, 1)) {
      if (wenVal) {


        //assert((write_addr_array.size() == in_data.size()) && "Input data width not equals to port width.\n");
        //FIXME: move this to execomb
        for (size_t i = 0; i < in_data_wire.size(); i++) {
            string stream_suffix = "";
            if (istream_name.size())
                stream_suffix = "_"+istream_name[0]+"_";
            Select* arg_data = toSelect(CoreIR::findSelect("datain" + stream_suffix + std::to_string(i), inSels));
            auto in_data = simState.getBitVec(arg_data);
            in_data_wire[i] = in_data.to_type<int>();
#if VERBOSE==1
            if (i == 0)
                std::cout << "---------------write data---------------" << std::endl;
            std::cout << "wrote data[" << i << "] = " << in_data.to_type<int>() << std::endl;
            if (i == in_data_wire.size()-1)
                std::cout << "---------------------------------------" << std::endl;
#endif
        }
        for (auto & func_kernel_stream : func_kernel)
            func_kernel_stream.second.write(in_data_wire);
      }

      //if (renVal == BitVector(1, 1)){
      if (renVal){
        for (auto & itr : func_kernel) {
          auto& func_kernel_stream = itr.second;
          auto stream_name = itr.first;
          auto dataout_pack = func_kernel_stream.read();
          valid_wire = std::get<1>(dataout_pack);
          auto read_data= std::get<0>(dataout_pack);

#if VERBOSE==1
          std::cout << "valid signal = " << valid_wire << std::endl;
#endif
          auto & out_wire_stream = out_data_wire.at(stream_name);
          for (size_t i = 0; i < out_wire_stream.size(); i++ ) {
            out_wire_stream[i] = read_data[i];
#if VERBOSE==1
            if (i == 0)
              std::cout << "---------------read data---------------" << std::endl;
            std::cout << "Stream: "<< stream_name <<", Read data[" << i << "] = " << out_wire_stream[i] << std::endl;
            if (i == in_data_wire.size()-1)
                std::cout << "---------------------------------------" << std::endl;
#endif
          }
        }
      }


    }
    /*
    Select* recursive_find_pred(Select* sel) {
        auto wd = sel->getConnectedWireables();
        assert(wd.size() == 1);

    }*/

    void exeCombinational(vdisc vd, SimulatorState& simState) {
      simState.updateInputs(vd);
      auto wd = simState.getCircuitGraph().getNode(vd);

      Instance* inst = toInstance(wd.getWire());
      auto inSels = getInputSelects(inst);
      Select* arg_wen= toSelect(CoreIR::findSelect("wen", inSels));
      Select* arg_ren= toSelect(CoreIR::findSelect("ren", inSels));
      //bool wenVal = false, renVal = false;
      wenVal = simState.getBitVec(arg_wen).to_type<bool>();
      if (rate_matched)
          renVal = wenVal;
      else
          renVal = simState.getBitVec(arg_ren).to_type<bool>();

      //And valid with ren
      bool valid_for_this_cycle;
      valid_for_this_cycle = renVal && valid_wire;

      /*Select* arg_wen= toSelect(CoreIR::findSelect("wen", inSels));
      assert(arg_wen != nullptr);
      auto wen = arg_wen->getConnectedWireables();
      assert(wen.size() == 1);
      wenVal = simState.getBitVec(toSelect(*(wen.begin()))).to_type<bool>();

    if (rate_matched) {
        renVal = wenVal;
    }
    else {

        //get ren value
        Select* arg_ren= toSelect(CoreIR::findSelect("ren", inSels));
        assert(arg_ren != nullptr);
        auto ren = arg_ren->getConnectedWireables();
        assert(ren.size() == 1);
        renVal = simState.getBitVec(toSelect(*(ren.begin()))).to_type<bool>();
    }
    valid_wire &= renVal;*/

#if VERBOSE==1
      std::cout << "Ubuf->{" << inst->getInstname() << "} execomb.." <<std::endl;
      std::cout << "ren: " << renVal << ", wen: " << wenVal;
      std::cout << ", valid: " << valid_for_this_cycle << std::endl;
#endif

      //assert((!read_iterator.isDone()) && "No more read allowed.\n");
      //output signal propagate
      simState.setValue(toSelect(inst->sel("valid")), BitVector(1, valid_for_this_cycle));

      string stream_suffix = "";

      for (auto itr: out_data_wire) {
        auto out_data_wire_stream = itr.second;
        if (ostream_name.size())
          stream_suffix = "_"+itr.first+"_";
        for (size_t i=0; i<out_data_wire_stream.size(); ++i) {
          simState.setValue(toSelect(inst->sel("dataout" + stream_suffix + std::to_string(i))), BitVector(width, out_data_wire_stream.at(i)));
        }
      }


      //input signal propagate



    }

  };

// Define address generator simulation class
  class UnifiedBuffer : public SimulatorPlugin {
    //int input_port;
    //int output_port;
    int capacity;
    int select;
    int width;
    int dimensionality;

    UnifiedBufferAddressGenerator write_iterator;
    UnifiedBufferAddressGenerator read_iterator;
    std::vector< std::vector<int> > data;

    std::vector<int> get_dims(Type* type) {
      std::vector<int> lengths;
      uint bitwidth = 1;
      Type* cType = type;
      while(!cType->isBaseType()) {
        if (auto aType = dyn_cast<ArrayType>(cType)) {

          uint length = aType->getLen();

          cType = aType->getElemType();
          if (cType->isBaseType()) {
            bitwidth = length;
          } else {
            lengths.insert(lengths.begin(), length);
            //lengths.push_back(length);
          }
        }
      }

      lengths.insert(lengths.begin(), bitwidth);
      return lengths;
    }

  public:

    void initialize(vdisc vd, SimulatorState& simState) {
      auto wd = simState.getCircuitGraph().getNode(vd);
      Wireable* w = wd.getWire();

      assert(isInstance(w));

      // extract parameters
      Instance* inst = toInstance(w);
      width = inst->getModuleRef()->getGenArgs().at("width")->get<int>();
      dimensionality = inst->getModuleRef()->getGenArgs().at("dimensionality")->get<int>();

      //output range
      std::vector<int> input_stride, output_stride, input_range, output_range,  input_start, output_start;
      for (int i = 0; i < dimensionality; i ++) {
          input_stride.push_back(inst->getModuleRef()->getGenArgs().at("input_stride_"+std::to_string(i))->get<int>());
          input_range.push_back(inst->getModuleRef()->getGenArgs().at("input_range_"+std::to_string(i))->get<int>());
          output_stride.push_back(inst->getModuleRef()->getGenArgs().at("stride_"+std::to_string(i))->get<int>());
          output_range.push_back(inst->getModuleRef()->getGenArgs().at("range_"+std::to_string(i))->get<int>());
      }
    /*
      auto outputRangeType = inst->getModuleRef()->getGenArgs().at("output_range_type")->get<Type*>();
      auto outputStrideType = inst->getModuleRef()->getGenArgs().at("output_stride_type")->get<Type*>();
      auto outputStartType = inst->getModuleRef()->getGenArgs().at("output_start_type")->get<Type*>();

      auto inputRangeType = inst->getModuleRef()->getGenArgs().at("input_range_type")->get<Type*>();
      auto inputStrideType = inst->getModuleRef()->getGenArgs().at("input_stride_type")->get<Type*>();
      auto inputStartType = inst->getModuleRef()->getGenArgs().at("input_start_type")->get<Type*>();

      auto output_range = get_dims(outputRangeType);
      auto output_stride = get_dims(outputStrideType);
      auto output_start = get_dims(outputStartType);
*/
      auto output_start_json = inst->getModuleRef()->getGenArgs().at("output_starting_addrs")->get<json>();
      for (auto const & start_val: output_start_json["output_start"]) {
        output_start.push_back(start_val);
      }

      auto input_start_json = inst->getModuleRef()->getGenArgs().at("input_starting_addrs")->get<json>();
      for (auto const & start_val: input_start_json["input_start"]) {
        input_start.push_back(start_val);
      }

      write_iterator = UnifiedBufferAddressGenerator(input_range, input_stride, input_start, width);
      read_iterator = UnifiedBufferAddressGenerator(output_range, output_stride, output_start, width);

      read_iterator.setDone();

      // deduce capacity from other output iterator
      auto mul = [&](int a, int b){return a*b; };
      capacity = accumulate(input_range.begin(), input_range.end(), 1, mul);

      /*
      size_t dimension = output_range.size();

      for (size_t i = 0; i < dimension; ++i) {
        capacity += (output_range.at(i) - 1) * max(output_stride.at(i), 0);
      }

      int max_start = 0;
      for (const auto &start_value : output_start) {
        max_start = max(max_start, start_value);
      }
      capacity += max_start;
      */


      // initialize data and select
      data = std::vector< std::vector<int> >(2, std::vector<int>(capacity, 0));
      select = 0;

    }

    void switch_check() {
      if (write_iterator.isDone() && read_iterator.isDone()) {
        select = select ^ 1;
        read_iterator.restart();
        write_iterator.restart();
      }
    }


    void exeSequential(vdisc vd, SimulatorState& simState) {
      auto wd = simState.getCircuitGraph().getNode(vd);

      simState.updateInputs(vd);

      assert(isInstance(wd.getWire()));

      Instance* inst = toInstance(wd.getWire());

      auto inSels = getInputSelects(inst);

      Select* arg1 = toSelect(CoreIR::findSelect("reset", inSels));
      assert(arg1 != nullptr);
      BitVector resetVal = simState.getBitVec(arg1);
      //auto in_data = simState.getBitVec(arg2);
      //get the wen value
      Select* arg_wen= toSelect(CoreIR::findSelect("wen", inSels));
      assert(arg_wen != nullptr);
      BitVector wenVal = simState.getBitVec(arg_wen);

      assert((!write_iterator.isDone()) && "No more write allowed.\n");

      //get ren value
      Select* arg_ren= toSelect(CoreIR::findSelect("ren", inSels));
      assert(arg_ren != nullptr);
      BitVector renVal = simState.getBitVec(arg_ren);
      if (renVal == BitVector(1, 1)){
        read_iterator.updateIterator(BitVector(1, 0));

      }
      //only update the internal state(write to buffer) if wen
      if (wenVal == BitVector(1, 1)) {

          auto write_addr_array = write_iterator.getAddresses();
        //assert((write_addr_array.size() == in_data.size()) && "Input data width not equals to port width.\n");
        for (size_t i = 0; i < write_addr_array.size(); i++) {
            int write_addr = write_addr_array[i];

            Select* arg_data = toSelect(CoreIR::findSelect("datain" + std::to_string(i), inSels));
            auto in_data = simState.getBitVec(arg_data);
            data[0x1 ^ select][write_addr] = in_data.to_type<int>();
            std::cout << "wrote data[" << write_addr << "] = " << in_data.to_type<int>();

            //update iterator after write all data
            write_iterator.updateIterator(resetVal);
        }
        std::cout << "\n";

        switch_check();
    }
    }

    void exeCombinational(vdisc vd, SimulatorState& simState) {
      auto wd = simState.getCircuitGraph().getNode(vd);

      std::cout << "execomb.." <<std::endl;

      Instance* inst = toInstance(wd.getWire());
      auto inSels = getInputSelects(inst);


      //assert((!read_iterator.isDone()) && "No more read allowed.\n");

      //FIXME: hard code the valid signal
     simState.setValue(toSelect(inst->sel("valid")), BitVector(1, 0));


      std::vector<int> out_data;
      for (auto read_addr : read_iterator.getAddresses()) {
        out_data.push_back(data[select][read_addr]);
        std::cout << "Read data[" << read_addr << "] = " << out_data.back() << std::endl;
      }

      switch_check();

      for (size_t i=0; i<out_data.size(); ++i) {
        simState.setValue(toSelect(inst->sel("dataout"+std::to_string(i))), BitVector(width, out_data.at(i)));
      }

      //hardcode valid to be True all the time
      simState.setValue(toSelect(inst->sel("valid")), BitVector(1, 1));
    }
  };
}
