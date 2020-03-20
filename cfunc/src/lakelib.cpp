#include "lakelib.h"
#include "coreir/libs/commonlib.h"

COREIR_GEN_C_API_DEFINITION_FOR_LIBRARY(lakelib);

using namespace std;
using namespace CoreIR;


///////////////////////
//helper functions////
//////////////////////

uint num_bits(uint N) {
  if (N==0) { return 1; }

  uint num_shifts = 0;
  uint temp_value = N;
  while (temp_value > 0) {
    temp_value  = temp_value >> 1;
    num_shifts++;
  }
  return num_shifts;
}

// returns vector starting with bitwidth
// array[bitwidth][dim1][dim2] -> {bitwidth,dim1,dim2
vector<uint> get_dims(Type* type) {
  vector<uint> lengths;
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

// returns number of arraytypes that are nested (not ignoring bitwidth)
uint num_dims(Type* type) {
  uint num_dims = 0;

  Type* cType = type;
  while(!cType->isBaseType()) {
    assert(cType->getKind() == Type::TypeKind::TK_Array);
    ArrayType* aType = static_cast<ArrayType*>(cType);
    cType = aType->getElemType();

    num_dims++;
  }
  return num_dims;
}

bool isPowerOfTwo(const uint n) {
  if (n == 0) {
    return 0;
  }

  return (n & (n - 1)) == 0;
}

uint inverted_index(uint outx, uint inx, uint i) {
  return (outx-1) - (inx-1 - i % inx) - (i / inx) * inx;
}

Namespace* CoreIRLoadLibrary_lakelib(Context* c) {

  Namespace* lakelib = c->newNamespace("lakelib");
  c->getNamespace("commonlib");

  Params MemGenParams = {{"width",c->Int()},{"depth",c->Int()}};
  //*** Linebuffer Memory. Use this for memory in linebuffer mode ***//
  lakelib->newTypeGen("LinebufferMemType",MemGenParams,[](Context* c, Values genargs) {
    uint width = genargs.at("width")->get<int>();
    return c->Record({
      {"clk", c->Named("coreir.clkIn")},
      {"wdata", c->BitIn()->Arr(width)},
      {"wen", c->BitIn()},
      {"rdata", c->Bit()->Arr(width)},
	// Is this just wen delayed by N?
      {"valid", c->Bit()},
    });
  });
  Generator* lbMem = lakelib->newGeneratorDecl("LinebufferMem",lakelib->getTypeGen("LinebufferMemType"),MemGenParams);
  lbMem->addDefaultGenArgs({{"width",Const::make(c,16)},{"depth",Const::make(c,1024)}});

  lbMem->setGeneratorDefFromFun([](Context* c, Values genargs, ModuleDef* def) {
    //uint width = genargs.at("width")->get<int>();
    uint depth = genargs.at("depth")->get<int>();
    uint awidth = (uint) ceil(log2(depth));

    def->addInstance("raddr","mantle.reg",{{"width",Const::make(c,awidth)},{"has_en",Const::make(c,true)}});
    def->addInstance("waddr","mantle.reg",{{"width",Const::make(c,awidth)},{"has_en",Const::make(c,true)}});

    def->addInstance("mem","coreir.mem",genargs);

    def->addInstance("add_r","coreir.add",{{"width",Const::make(c,awidth)}});
    def->addInstance("add_w","coreir.add",{{"width",Const::make(c,awidth)}});
    def->addInstance("c1","coreir.const",{{"width",Const::make(c,awidth)}},{{"value",Const::make(c,awidth,1)}});

    if (!isPowerOfTwo(depth)) {

      // Multiplexers to check max value
      def->addInstance("raddr_mux", "coreir.mux", {{"width", Const::make(c, awidth)}});
      def->addInstance("waddr_mux", "coreir.mux", {{"width", Const::make(c, awidth)}});

      // Equals to test if addresses are at the max
      def->addInstance("raddr_eq", "coreir.eq", {{"width", Const::make(c, awidth)}});
      def->addInstance("waddr_eq", "coreir.eq", {{"width", Const::make(c, awidth)}});

      // Reset constant
      def->addInstance("zero_const",
                       "coreir.const",
                       {{"width",Const::make(c,awidth)}},
                       {{"value", Const::make(c, awidth, 0)}});

      // Max constant
      def->addInstance("max_const",
                       "coreir.const",
                       {{"width",Const::make(c,awidth)}},
                       // Fix this for 64 bit constants!
                       {{"value", Const::make(c, awidth, depth)}}); //(1 << awidth) - 1)}});

      // Wire up the resets
      def->connect("raddr_eq.out", "raddr_mux.sel");
      def->connect("waddr_eq.out", "waddr_mux.sel");

      def->connect("zero_const.out", "raddr_mux.in1");
      def->connect("zero_const.out", "waddr_mux.in1");

      def->connect("add_r.out", "raddr_mux.in0");
      def->connect("add_w.out", "waddr_mux.in0");

      def->connect("waddr_mux.out", "waddr.in");
      def->connect("raddr_mux.out", "raddr.in");

      // Wire up equals inputs
      def->connect("add_r.out", "raddr_eq.in0");
      def->connect("max_const.out", "raddr_eq.in1");

      def->connect("add_w.out", "waddr_eq.in0");
      def->connect("max_const.out", "waddr_eq.in1");

    } else {
      def->connect("add_r.out","raddr.in");
      def->connect("add_w.out","waddr.in");
    }

    // Wire up the rest of the circuit
    def->connect("self.wdata","mem.wdata");

    def->connect("self.wen","mem.wen");
    def->connect("self.clk","mem.clk");

    def->connect("waddr.out","mem.waddr");
    def->connect("raddr.out","mem.raddr");
    def->connect("mem.rdata","self.rdata");


    def->connect("add_r.in0","raddr.out");
    def->connect("add_r.in1","c1.out");

    def->connect("waddr.en","self.wen");
    def->connect("waddr.clk","self.clk");

    def->connect("raddr.en","self.wen");
    def->connect("raddr.clk","self.clk");

    def->connect("add_w.in0","waddr.out");
    def->connect("add_w.in1","c1.out");

    def->addInstance("veq","coreir.neq",{{"width",Const::make(c,awidth)}});
    def->connect("veq.in0","raddr.out");
    def->connect("veq.in1","waddr.out");
    def->connect("veq.out","self.valid");
  });

//// reference verilog code for lbmem
//module #(parameter lbmem {
//  input clk,
//  input [W-1:0] wdata,
//  input wen,
//  output [W-1:0] rdata,
//  output valid
//}
//
//  reg [A-1] raddr
//  reg [A-1] waddr;
//
//  always @(posedge clk) begin
//    if (wen) waddr <= waddr + 1;
//  end
//  assign valid = waddr!=raddr;
//  always @(posedge clk) begin
//    if (valid) raddr <= raddr+1;
//  end
//
//  coreir_mem inst(
//    .clk(clk),
//    .wdata(wdata),
//    .waddr(wptr),
//    .wen(wen),
//    .rdata(rdata),
//    .raddr(rptr)
//  );
//
//endmodule



  //*** Fifo Memory. Use this for memory in Fifo mode ***//
  lakelib->newTypeGen("FifoMemType",MemGenParams,[](Context* c, Values genargs) {
    uint width = genargs.at("width")->get<int>();
    return c->Record({
      {"clk", c->Named("coreir.clkIn")},
      {"wdata", c->BitIn()->Arr(width)},
      {"wen", c->BitIn()},
      {"rdata", c->Bit()->Arr(width)},
      {"ren", c->BitIn()},
      {"almost_full", c->Bit()},
      {"valid", c->Bit()}
    });
  });
  Generator* fifoMem = lakelib->newGeneratorDecl("FifoMem",lakelib->getTypeGen("FifoMemType"),MemGenParams);
  fifoMem->addDefaultGenArgs({{"width",Const::make(c,16)},{"depth",Const::make(c,1024)}});
  fifoMem->setModParamsGen({{"almost_full_cnt",c->Int()}});

  lakelib->newTypeGen("RamType",MemGenParams,[](Context* c, Values genargs) {
    uint width = genargs.at("width")->get<int>();
    uint depth = genargs.at("depth")->get<int>();
    uint awidth = (uint) ceil(log2(depth));
    return c->Record({
      {"clk", c->Named("coreir.clkIn")},
      {"wdata", c->BitIn()->Arr(width)},
      {"waddr", c->BitIn()->Arr(awidth)},
      {"wen", c->BitIn()},
      {"rdata", c->Bit()->Arr(width)},
      {"raddr", c->BitIn()->Arr(awidth)},
      {"ren", c->BitIn()},
    });
  });
  Generator* ram = lakelib->newGeneratorDecl("Ram",lakelib->getTypeGen("RamType"),MemGenParams);
  ram->setGeneratorDefFromFun([](Context* c, Values genargs, ModuleDef* def) {
    def->addInstance("mem","coreir.mem",genargs);
    def->addInstance("readreg","coreir.reg",{{"width",genargs["width"]},{"has_en",Const::make(c,true)}});
    def->connect("self.clk","readreg.clk");
    def->connect("self.clk","mem.clk");
    def->connect("self.wdata","mem.wdata");
    def->connect("self.waddr","mem.waddr");
    def->connect("self.wen","mem.wen");
    def->connect("mem.rdata","readreg.in");
    def->connect("self.rdata","readreg.out");
    def->connect("self.raddr","mem.raddr");
    def->connect("self.ren","readreg.en");
  });


  //////////////////////////////////////////////////
  //*** generic recursively defined linebuffer ***//
  //////////////////////////////////////////////////

  // top-level linebuffer that should be used by the user
  Params lb_args =
    {{"input_type",CoreIRType::make(c)},
     {"output_type",CoreIRType::make(c)},
     {"image_type",CoreIRType::make(c)},
     {"has_valid",c->Bool()},
     {"has_stencil_valid",c->Bool()}
    };

  lakelib->newTypeGen(
    "lb_type", //name for the typegen
    lb_args,
    [](Context* c, Values genargs) { //Function to compute type
      bool has_valid = genargs.at("has_valid")->get<bool>();
      bool has_stencil_valid = genargs.at("has_stencil_valid")->get<bool>();
      Type* in_type  = genargs.at("input_type")->get<Type*>();
      Type* out_type  = genargs.at("output_type")->get<Type*>();
      Type* img_type = genargs.at("image_type")->get<Type*>();

      // can't have has_stencil_valid without a valid
      ASSERT(!(!has_valid && has_stencil_valid),
        "One must have a valid signal to utilize stencil valid");

      // process and check the input arguments
      vector<uint> in_dims = get_dims(in_type);
      vector<uint> out_dims = get_dims(out_type);
      vector<uint> img_dims = get_dims(img_type);

      uint bitwidth = in_dims[0]; // first array is bitwidth
      ASSERT(bitwidth > 0, "The first dimension for the input is interpretted "
             "as the bitwidth which was set to " + to_string(bitwidth));

      ASSERT(bitwidth == out_dims[0],
             to_string(bitwidth) + " != " + to_string(out_dims[0]) + \
             "all bitwidths must match (input doesn't match output)");
      ASSERT(bitwidth == img_dims[0],
             to_string(bitwidth) + " != " + to_string(img_dims[0]) + \
             "all bitwidths must match (input doesn't match image)");

      // erase the bitwidth size from vectors
      in_dims.erase(in_dims.begin());
      out_dims.erase(out_dims.begin());
      img_dims.erase(img_dims.begin());

      uint num_dims = in_dims.size();
      ASSERT(num_dims == out_dims.size(),
             "all must have same number of dimensions (input and output mismatch)");
      ASSERT(num_dims == img_dims.size(),
             "all must have same number of dimensions (input and image mismatch)");

      // we will check all dimensions for correct construction
      for (uint dim=0; dim<num_dims; ++dim) {
        uint out_dimx = out_dims[dim];
        uint img_dimx = img_dims[dim];
        uint in_dimx = in_dims[dim];

        ASSERT(img_dimx >= out_dimx,
               "image dimension length (" + to_string(img_dimx) + \
               ") must be larger than output (" + to_string(out_dimx) + \
               ") in dim " + to_string(dim));
        ASSERT(out_dimx >= in_dimx,
               "output stencil size (" + to_string(out_dimx) + \
               ") must be larger than input (" + to_string(in_dimx) + \
               ") in dim " + to_string(dim));
        ASSERT(img_dimx % in_dimx == 0,
               "img_dim=" + to_string(img_dimx) + " % in_dim=" + to_string(in_dimx) + \
               " != 0 in dim=" + to_string(dim) + \
               ", dimension length must be divisible, because we can't swizzle data");
        ASSERT(out_dimx % in_dimx == 0,
               "out_dim=" + to_string(out_dimx) + " % in_dim=" + to_string(in_dimx) + \
               " != 0 in dim=" + to_string(dim) + \
               ", dimension length must be divisible, because we can't swizzle data");

        if (img_dimx - out_dimx < 3 && (img_dimx != out_dimx)) {
          std::cout << "Image dimension " << dim << "  is " << img_dimx
                    << " and output stencil size is " << out_dimx
                    << ", which means the linebuffer mem is going to be very small"
                    << std::endl;

        }
      }

      // create the ports for the linebuffer
      RecordParams recordparams = {
          {"in", in_type},
          {"reset", c->BitIn()},
          {"wen",c->BitIn()},
          {"out", out_type}
      };

      if (has_valid) { recordparams.push_back({"valid",c->Bit()}); }
      return c->Record(recordparams);
    }
  );

  Generator* lb = lakelib->newGeneratorDecl(
    "linebuffer",
    lakelib->getTypeGen("lb_type"),
    lb_args
  );
  lb->addDefaultGenArgs({{"has_valid",Const::make(c,false)}});
  lb->addDefaultGenArgs({{"has_stencil_valid",Const::make(c,false)}});

  lb->setGeneratorDefFromFun([](Context* c, Values genargs, ModuleDef* def) {
      bool has_valid = genargs.at("has_valid")->get<bool>();
      bool has_stencil_valid = genargs.at("has_stencil_valid")->get<bool>();
      bool is_last_lb= true;
      Type* in_type  = genargs.at("input_type")->get<Type*>();
      Type* out_type = genargs.at("output_type")->get<Type*>();
      Type* img_type = genargs.at("image_type")->get<Type*>();

      // create a linebuffer
      Values lb_args = {
            {"input_type", Const::make(c, in_type)},
            {"image_type", Const::make(c, img_type)},
            {"output_type", Const::make(c, out_type)},
            {"has_valid", Const::make(c, has_valid)},
            {"has_stencil_valid", Const::make(c, has_stencil_valid)},
            {"is_last_lb", Const::make(c, is_last_lb)}
      };

      def->addInstance("lb_recurse",
                       "lakelib.linebuffer_recursive",
                       lb_args);

      // connect linebuffer to this generator's ports
      def->connect("self.in", "lb_recurse.in");
      def->connect("self.reset", "lb_recurse.reset");
      def->connect("self.wen", "lb_recurse.wen");
      if (has_valid) {
        def->connect("self.valid", "lb_recurse.valid");
      }

      // flip all of the outputs to the correct output port
      vector<uint> in_dims = get_dims(in_type);
      vector<uint> out_dims = get_dims(out_type);
      vector<uint> img_dims = get_dims(img_type);
      in_dims.erase(in_dims.begin());
      out_dims.erase(out_dims.begin());
      img_dims.erase(img_dims.begin());
      uint num_dims = in_dims.size();

      std::vector<std::pair<string,string>> out_pairs;
      out_pairs.push_back({"lb_recurse.out", "self.out"});
      for (int dim=num_dims-1; dim>=0; --dim) {
        uint  inx =  in_dims[dim];
        uint outx = out_dims[dim];

        std::vector<std::pair<string,string>> out_temp;
        out_temp.reserve(out_pairs.size() * outx);
        for (uint i=0; i<outx; ++i) {
          for (auto out_pair : out_pairs) {
            string source = out_pair.first;
            string sink = out_pair.second;
            uint iflip = inverted_index(outx, inx, i);
            out_temp.push_back({source + "." + to_string(i),
                    sink + "." + to_string(iflip)});

          }
        }
        out_pairs = out_temp;
      }

      //std::cout << "linebuffer connections:" << std::endl;
      for (auto out_pair : out_pairs) {
        //std::cout << "  connecting " << out_pair.first
        //          << " to " << out_pair.second
        //          << std::endl;
        def->connect(out_pair.first, out_pair.second);
      }
      //std::cout << std::endl;

    }
    );


  // recursive version for linebuffer
  Params lb_recursive_args =
      {{"input_type",CoreIRType::make(c)},
       {"output_type",CoreIRType::make(c)},
       {"image_type",CoreIRType::make(c)},
       {"has_valid",c->Bool()},
       {"has_stencil_valid",c->Bool()},
       {"is_last_lb",c->Bool()} // use this to denote when to create valid register chain
      };

  lakelib->newTypeGen(
      "lb_recursive_type", //name for the typegen
      lb_recursive_args,
      [](Context* c, Values genargs) { //Function to compute type
        bool has_valid = genargs.at("has_valid")->get<bool>();
        //bool is_last_lb = genargs.at("is_last_lb")->get<bool>();
        Type* in_type  = genargs.at("input_type")->get<Type*>();
        Type* out_type  = genargs.at("output_type")->get<Type*>();
        RecordParams recordparams = {
          {"in", in_type},
          {"reset", c->BitIn()},
          {"wen",c->BitIn()},
          {"out", out_type}
        };

        if (has_valid) { recordparams.push_back({"valid",c->Bit()}); }
        if (has_valid) { recordparams.push_back({"valid_chain",c->Bit()}); }
        return c->Record(recordparams);
      }
                        );

  Generator* lb_recursive = lakelib->newGeneratorDecl(
      "linebuffer_recursive",
      lakelib->getTypeGen("lb_recursive_type"),
      lb_recursive_args
    );

  lb_recursive->setGeneratorDefFromFun([](Context* c, Values genargs, ModuleDef* def) {
    //cout << "running linebuffer generator" << endl;
    bool has_valid = genargs.at("has_valid")->get<bool>();
    bool has_stencil_valid = genargs.at("has_stencil_valid")->get<bool>();
    bool is_last_lb= genargs.at("is_last_lb")->get<bool>();
    Type* in_type  = genargs.at("input_type")->get<Type*>();
    Type* out_type = genargs.at("output_type")->get<Type*>();
    Type* img_type = genargs.at("image_type")->get<Type*>();
    vector<uint> in_dims = get_dims(in_type);
    vector<uint> out_dims = get_dims(out_type);
    vector<uint> img_dims = get_dims(img_type);

    uint bitwidth = in_dims[0]; // first element in array is bitwidth
    ASSERT(bitwidth > 0, "The first dimension for the input is interpretted "
					 "as the bitwidth which was set to " + to_string(bitwidth));

    // erase the bitwidth size from vectors
    in_dims.erase(in_dims.begin());
    out_dims.erase(out_dims.begin());
    img_dims.erase(img_dims.begin());

    // last dimension most commonly used
    uint num_dims = in_dims.size();
    uint dim = num_dims-1;
    uint out_dim = out_dims[dim];
    uint img_dim = img_dims[dim];
    uint in_dim = in_dims[dim];

    if (!is_last_lb) {
      ASSERT(has_valid, "is_last_lb was set to false when !has_valid. This flag should not be used unless using valid output port");
    }

    //cout << "finished a bunch of asserts" << endl;

    string reg_prefix = "reg_";
    Const* aBitwidth = Const::make(c,bitwidth);
    assert(isa<ConstInt>(aBitwidth));

    // NOTE: registers and lbmems named such that they correspond to output connections

    ////////////////////////////////////////////
    ///// BASE CASE: DIM==1, all registers /////
    ////////////////////////////////////////////
    if (num_dims == 1) {
      //cout << "creating base case linebuffer" << endl;
      // connect based on input size
      for (uint i=0; i<out_dim; ++i) {
        // output goes to mirror position, except keeping order within a single clock cycle
        //uint iflip = (out_dim-1) - (in_dim - 1 - i % in_dim) - (i / in_dim) * in_dim;

        //uint iflip = (out_dim-1) - i;
        uint iflip = i;

        // connect to input
        if (i < in_dim) {
          def->connect({"self","in",to_string(i)}, {"self","out",to_string(iflip)});

        // create and connect to register; register connects input
        } else if ((i >= in_dim) && (i < 2*in_dim)) {
          uint in_idx = i - in_dim;
          string reg_name = reg_prefix + to_string(i);
          def->addInstance(reg_name, "coreir.reg", {{"width",aBitwidth}});
          def->connect({"self","in",to_string(in_idx)}, {reg_name, "in"});
          def->connect({reg_name, "out"}, {"self","out",to_string(iflip)});

        // create and connect to register; register connects to previous register
        } else {
          uint in_idx = i - in_dim;
          string reg_name = reg_prefix + to_string(i);
          string prev_reg_name = reg_prefix + to_string(in_idx);
          def->addInstance(reg_name, "coreir.reg", {{"width",aBitwidth}});
          def->connect({prev_reg_name, "out"}, {reg_name, "in"});
          def->connect({reg_name, "out"}, {"self","out",to_string(iflip)});

        }
      }


      // create and connect valid chain
      if (has_valid) {
        if (is_last_lb) {
          // this is a chain of valids
          string valid_prefix = "valreg_";

          uint last_idx = -1;
          for (uint i=0; i<out_dim-in_dim; i+=in_dim) {

            // connect to input wen
            if (i == 0) {
              string reg_name = valid_prefix + to_string(i);
              def->addInstance(reg_name, "corebit.reg");
              def->connect({"self","wen"}, {reg_name,"in"});

              // create and connect to register; register connects to previous register
            } else {
              uint in_idx = i - in_dim;
              string reg_name = valid_prefix + to_string(i);
              string prev_reg_name = valid_prefix + to_string(in_idx);
              def->addInstance(reg_name, "corebit.reg");
              def->connect({prev_reg_name, "out"}, {reg_name, "in"});

            }

            last_idx = i;
          }

          // connect last valid bit to self.valid
          string last_valid_name = valid_prefix + to_string(last_idx);
          def->connect({"self","valid"},{last_valid_name,"out"});
          def->connect({"self","valid_chain"},{last_valid_name,"out"});
        } else {
          def->connect({"self","wen"},{"self","valid"});
          def->connect({"self","wen"},{"self","valid_chain"});
        }
      }  // valid chain

      def->addInstance("reset_term", "corebit.term");
      def->connect("self.reset","reset_term.in");

    //////////////////////////
    ///// RECURSIVE CASE /////
    //////////////////////////
    } else {

      string lb_prefix = "lb" + to_string(dim) + "d_"; // use this for recursively smaller linebuffers
      Type* lb_input = cast<ArrayType>(in_type)->getElemType();
      Type* lb_image = cast<ArrayType>(img_type)->getElemType();
      Type* lb_output = cast<ArrayType>(out_type)->getElemType();

      // recursively create linebuffers
      for (uint i=0; i<out_dim; ++i) {
        string lb_name = lb_prefix + to_string(i);
        //cout << "creating linebuffer named " << lb_name << endl;
        Values args = {
            {"input_type", Const::make(c, lb_input)},
            {"image_type", Const::make(c, lb_image)},
            {"output_type", Const::make(c, lb_output)},
            {"has_valid", Const::make(c, has_valid)},
            {"has_stencil_valid", Const::make(c, has_stencil_valid)},
            {"is_last_lb", Const::make(c, !has_valid)}
          };
        // was used when is_last_lb was used recursively, now only lastlb makes valid counter chain
        //if (!has_valid || (is_last_lb && i == out_dim-1)) {

        def->addInstance(lb_name, "lakelib.linebuffer_recursive", args);
        def->connect({"self","reset"},{lb_name,"reset"});
      }

      // ALL CASES: stencil output connections
      // connect the stencil outupts
      for (uint i=0; i<out_dim; ++i) {
        // output goes to mirror position, except keeping order within a single clock cycle
        //uint iflip = (out_dim-1) - (in_dim-1 - i % in_dim) - (i / in_dim) * in_dim;
        //uint iflip = out_dim-1 - i;
        uint iflip = i;
        string lb_name = lb_prefix + to_string(i);

        def->connect({"self","out",to_string(iflip)}, {lb_name,"out"});
      }

      //cout << "created all linebuffers" << endl;

      // SPECIAL CASE: same sized stencil output as image, so no lbmems needed (all in regs)
      //if (out_dim == img_dim) {
      if (img_dim == 0) {
        ASSERT(false, "out_dim == img_dim isn't implemented yet");

      } else {
        //cout << "in the regular case of linebuffer" << endl;

        // REGULAR CASE: lbmems to store image lines

        // create lbmems to store data between linebuffers
        //   size_lbmems = prod((img[x] - (out[x]-in[x])) / in[x])
        //      except for x==1, img0 / in0
        uint size_lbmems = 1; //out_dim-1;
        for (uint dim_i=0; dim_i<num_dims-1; dim_i++) {
          if (dim_i == 0) {
            size_lbmems *= img_dims[dim_i] / in_dims[dim_i];
          } else {
            size_lbmems *= img_dims[dim_i] / in_dims[dim_i];
            //size_lbmems *= (img_dims[dim_i] - (out_dims[dim_i]-in_dims[dim_i])) / in_dims[dim_i];
          }
        }

        Const* aLbmemSize = Const::make(c, size_lbmems);

        //   num_lbmems = (prod(in[x]) * (out-in)
        string lbmem_prefix = "lbmem";
        for (uint out_i=0; out_i < out_dim-in_dim; ++out_i) {

          uint num_indices = num_dims - 1;
          //cout << "we have " << num_dims << " dims and " << num_indices << " input dims" << endl;
          uint indices[num_indices];

          memset( indices, 0, num_indices*sizeof(uint) );

          bool create_more_lbmems = true;
          while (create_more_lbmems) {
            ///// create lbmem //////

            // create lbmem name (lbmem_x_<in2>_<in1>_<in0>)
            uint lbmem_line = out_i + in_dim;
            string lbmem_name = lbmem_prefix + "_" + to_string(lbmem_line);

            for (int dim_i=num_indices-1; dim_i>=0; --dim_i) {
              lbmem_name += "_" + to_string(indices[dim_i]);
            }

            if (has_stencil_valid) {
              def->addInstance(lbmem_name, "memory.rowbuffer_stencil_valid",
                               {{"width",aBitwidth},{"depth",aLbmemSize},{"stencil_width",Const::make(c, 0)}});

            } else {
              def->addInstance(lbmem_name, "memory.rowbuffer",
                               {{"width",aBitwidth},{"depth",aLbmemSize}});
            }


            // hook up flush
            // FIXME: actually create flush signal using counters
            string lbmem_flush_name = lbmem_name + "_flush";
            def->addInstance(lbmem_flush_name, "corebit.const", {{"value",Const::make(c,false)}});
            def->connect({lbmem_name,"flush"},{lbmem_flush_name,"out"});

            ///// connect lbmem input and wen /////
            //cout << "connecting lbmem input for " << lbmem_name << endl;
            string input_name, input_suffix;
            string delim;
            if (num_dims == 2) { // special case with a 2D linebuffer
              // connect to input or end of last lbmem
              if (out_i < in_dim) {
                input_name = "self.in." + to_string(out_i);
                delim = ".";
                input_suffix = "";

              } else {
                // connect lbmem from previous line
                input_name = lbmem_prefix + "_" + to_string(lbmem_line-in_dim);
                delim = "_";
                input_suffix = ".rdata";
              }

              for (int dim_i=num_indices-1; dim_i>=0; --dim_i) {
                input_name += delim + to_string(indices[dim_i]);
              }

              def->connect(input_name + input_suffix, lbmem_name + ".wdata");

              // connect wen
              if (has_valid) {
                 if (out_i < in_dim) {
                   // use self wen; actually stall network for now
                   def->connect("self.wen", lbmem_name + ".wen");

                 } else {
                   // use valid from previous lbmem
                   def->connect(input_name + ".valid", lbmem_name + ".wen");
                 }
              } else {
                def->connect("self.wen", lbmem_name + ".wen");
              }

            } else {
              ///// connect lbmem inputs for non-2d case /////
              // connect to end of associated linebuffer, which is one of the stencil outputs
              input_name = lb_prefix + to_string(out_i) + ".out";
              for (int dim_i=num_indices-1; dim_i>=0; --dim_i) {
                if (dim_i == 0) {
                  // for last dimension, don't go to the end of register chain
                  uint index_i = inverted_index(out_dims[dim_i], in_dims[dim_i], indices[dim_i]);
                  input_name += "." + to_string(index_i);
                } else {
                  input_name += "." + to_string(in_dims[dim_i]-1 - indices[dim_i]);
                }
              }
              def->connect(lbmem_name + ".wdata", input_name);

              // connect wen if has_valid
              if (has_valid) {
                 if (out_i < in_dim) {
                   // use self wen; actually stall network for now
                   def->connect("self.wen", lbmem_name + ".wen");

                 } else {
                   // use valid from previous lbmem
                   def->connect(input_name + ".valid_chain", lbmem_name + ".wen");
                 }
              } else {
                def->connect("self.wen", lbmem_name + ".wen");
              }

            }

            //cout << "connecting lbmem output" << endl;
            ///// connect lbmem output /////
            // connect the lbmem output to linebuffer input in next layer
            string output_base = lb_prefix + to_string(out_i+in_dim);
            string output_name = output_base + ".in";
            for (int dim_i=num_indices-1; dim_i>=0; --dim_i) {
              output_name += "." + to_string(indices[dim_i]);
            }
            def->connect(lbmem_name + ".rdata", output_name);

            // increment lbmem indices
            indices[0] += 1;
            for (uint dim_i=0; dim_i<num_indices; dim_i++) {
              if (indices[dim_i] >= in_dims[dim_i]) {
                if ((uint)dim_i == num_dims-2) {
                  create_more_lbmems = false;
                } else {
                  indices[dim_i+1] += 1;
                  indices[dim_i] = 0;
                }
              }
            } // indices increment

          } // while create_more_lbmems
        } // for out_i

        //cout << "connecting linbuffer inputs" << endl;
        // connect linebuffer inputs to input (other already connected to lbmems)
        for (uint out_i=0; out_i<in_dim; ++out_i) {
          string lb_name = lb_prefix + to_string(out_i);
          def->connect({"self","in",to_string(out_i)}, {lb_name, "in"});
        }

        ///// connect linebuffer outputs /////
        if (has_valid) {
					// check if we create lbmems or not
					string valid_chain_str;
					if (out_dim - in_dim > 0) {
						// use the last lbmem for valid chaining (note this signal is duplicated among all in_dims)
						//  recall lbmem naming: lbmem_x_<in2>_<in1>_<in0>
						string last_lbmem_name = lbmem_prefix;
						for (int dim_i=num_dims-1; dim_i>=0; dim_i--) {
							if (dim_i == (int)(num_dims-1)) {
								last_lbmem_name += "_" + to_string(out_dim-1);
							} else {
								last_lbmem_name += "_" + to_string(in_dims[dim_i]-1);
							}
						}
						valid_chain_str = last_lbmem_name + ".valid";
					} else {
						valid_chain_str = "self.wen";
					}
					def->connect(valid_chain_str, "self.valid_chain");

          // create counters to create valid output (if top-level linebuffer)
          if (is_last_lb == false) {
            def->connect(valid_chain_str, "self.valid");
            def->addInstance("reset_term", "corebit.term");
            def->connect("self.reset","reset_term.in");
          } else if (is_last_lb && !has_stencil_valid) {

            std::vector<std::string> counter_outputs;
            counter_outputs.push_back("self.wen");

            // create a counter for every dimension
            for (uint dim_i=0; dim_i<num_dims; dim_i++) {
            //for (int dim_i=num_dims-1; dim_i>=0; dim_i--) {
              // comparator for valid (if stencil_size-1 <= count)
              int const_value = (out_dims[dim_i] / in_dims[dim_i]) - 1;
              //FIXME: not implemented, because overflow needed to trigger next counter
              //if (const_value == 0) continue;  // no counter needed if stencil_size is 1

              string const_name = "const_stencil" + to_string(dim_i);
              Values const_arg = {{"value",Const::make(c,BitVector(bitwidth,const_value))}};
              def->addInstance(const_name, "coreir.const", {{"width",aBitwidth}}, const_arg);

              string compare_name = "valcompare_" + to_string(dim_i);
              def->addInstance(compare_name,"coreir.ule",{{"width",aBitwidth}});

              // counter
              string counter_prefix = "valcounter_";
              string counter_name = counter_prefix + to_string(dim_i);
              Values counter_args = {
                {"width",Const::make(c,bitwidth)},
                {"min",Const::make(c,0)},
                {"max",Const::make(c,img_dims[dim_i] / in_dims[dim_i] - 1)},
                {"inc",Const::make(c,1)}
              };
              def->addInstance(counter_name,"commonlib.counter",counter_args);

              // connect reset to 0
              def->connect({counter_name, "reset"},{"self","reset"});

              // connections
              // counter en by wen or overflow bit
              //if (dim_i == 0 || counter_outputs.size() == 1) {
              if (dim_i == 0 || counter_outputs.size() == 1) {
                //def->connect({last_lbmem_name,"valid"},{counter_name,"en"});
                def->connect("self.wen",counter_name + ".en");
              } else {
                string last_compare_out_name = counter_outputs[counter_outputs.size()-1];
                string last_compare_name = last_compare_out_name.substr(0, last_compare_out_name.find(".out"));
                string last_compare_index = last_compare_name.substr(last_compare_name.find("_")+1);
                string last_counter_name = counter_prefix + last_compare_index;
                def->connect({last_counter_name,"overflow"},{counter_name,"en"});
              }

              // wire up comparator
              def->connect({const_name,"out"},{compare_name,"in0"});
              def->connect({counter_name,"out"},{compare_name,"in1"});
              counter_outputs.push_back(compare_name + ".out");
              //std::cout << "counter" << dim_i << " counts to " << const_value << std::endl;
              //def->connect({compare_name,"out"},{andr_name,"in",to_string(dim_i)});
            }

            if (counter_outputs.size() == 0) {
              def->connect("self.wen", "self.valid");
              def->addInstance("reset_term", "corebit.term");
              def->connect("self.reset","reset_term.in");

            } else {
              // andr all comparator outputs
              string andr_name = "valid_andr";
              Values andr_params = {{"N",Const::make(c,counter_outputs.size())},
                                    {"operator",Const::make(c,"corebit.and")}};
              def->addInstance(andr_name,"commonlib.bitopn",andr_params);
              def->connect({andr_name,"out"},{"self","valid"});
              //def->hasConnection({andr_name,"out"},{"self","valid"});

              for (uint dim_i=0; dim_i<counter_outputs.size(); ++dim_i) {
                def->connect(counter_outputs[dim_i], andr_name +".in."+to_string(dim_i));
              }
            }

          } else { //if (is_last_lb && has_stencil_valid) {
            ASSERT(is_last_lb && has_stencil_valid,
                   "This should be the only case left if these conditionals are correct");

            // By setting the stencil_width on the rowbuffer correctly, we don't need external counters.
            def->connect(valid_chain_str, "self.valid");
          }

        } else { // has_valid == 0
          // hook up wen for rest of linebuffers
          for (uint out_i=in_dim; out_i<out_dim; ++out_i) {
            //string lb_name = lb_prefix + to_string(out_i);
            //def->connect({"self","wen"}, {lb_name, "wen"}); // use stall network
          }
        }

        for (uint out_i=0; out_i<out_dim; ++out_i) {
          string lb_name = lb_prefix + to_string(out_i);
          def->connect({"self","wen"}, {lb_name, "wen"}); // use stall network
        }


      } // regular case

    }
    });


  /////////////////////////////////////////
  //*** new unified buffer definition ***//
  /////////////////////////////////////////
  // istream= input_stride, input_range, input_starting_addrs, input_chunk, input_block
  // ostream= output_stride, output_range, output_starting_addrs, output_stencil, output_block,
  //          num_stencil_acc_dim, stencil_width, iter_cnt
  Params new_ubparams = Params({
      {"width",c->Int()},
      {"logical_size",c->Json()},
      {"ostreams",c->Json()},
      {"istreams",c->Json()},
        //{"depth", c->Int()},    // remove: this is the product of all logical dims
      {"chain_en",c->Bool()}, // default: used only after hw mapping
      {"chain_idx",c->Int()}, // default: used only after hw mapping
      {"init",c->Json()}
    });

  // unified buffer type
  lakelib->newTypeGen(
    "new_unified_buffer_type", //name for the typegen
    new_ubparams, //generator parameters
    [](Context* c, Values genargs) { //Function to compute type
      uint width = genargs.at("width")->get<int>();
      Json istreams = genargs.at("istreams")->get<Json>();
      Json ostreams = genargs.at("ostreams")->get<Json>();
      uint num_inputs = 1;//genargs.at("num_input_ports")->get<int>();
      uint num_outputs = 1;//genargs.at("num_output_ports")->get<int>();

      RecordParams recordparams = {
        {"wen",c->BitIn()},
        {"ren",c->BitIn()},
        {"flush", c->BitIn()},
        {"reset", c->BitIn()},
        {"valid",c->Bit()}
      };

      // Add the dataports. The simulator needs them to be flattened
      bool simulation_compatible = true;
      bool multiple_streams = true;

      if (multiple_streams) {
        // Insert input ports for each input stream
        for (auto& stream : nlohmann::json::iterator_wrapper(istreams)) {
          //std::cout << "input: " << stream.value() << std::endl;
          for (size_t i=0; i < stream.value()["input_starting_addrs"].size(); ++i) {
            string stream_name = stream.key();
            recordparams.push_back({"datain_" + stream_name  + "_" + std::to_string(i),
                  c->BitIn()->Arr(width)});
          }
        }
        // Insert output ports for each output stream
        for (auto stream : nlohmann::json::iterator_wrapper(ostreams)) {
          //std::cout << "output: " << stream.value() << std::endl;
          for (size_t i=0; i < stream.value()["output_starting_addrs"].size(); ++i) {
            string stream_name = stream.key();
            recordparams.push_back({"dataout_" + stream_name + "_" + std::to_string(i),
                  c->Bit()->Arr(width)});
          }
        }
      } else if (simulation_compatible) {
        for (size_t i=0; i < num_inputs; ++i) {
          recordparams.push_back({"datain"+std::to_string(i), c->BitIn()->Arr(width)});
        }
        for (size_t i=0; i < num_outputs; ++i) {
          recordparams.push_back({"dataout"+std::to_string(i), c->Bit()->Arr(width)});
        }
      } else {
        recordparams.push_back({"datain",c->BitIn()->Arr(width)->Arr(num_inputs)});
        recordparams.push_back({"dataout",c->Bit()->Arr(width)->Arr(num_outputs)});
      }

      return c->Record(recordparams);
    }
  );

  auto new_unified_buffer_gen = lakelib->newGeneratorDecl("new_unified_buffer",lakelib->getTypeGen("new_unified_buffer_type"),new_ubparams);
  Json new_jdata;
  new_jdata["init"][0] = 0; // set default init to "0"
  new_unified_buffer_gen->addDefaultGenArgs({{"init",Const::make(c,new_jdata)}});

  // set some default inputs and outputs
  Json jistreams;
  jistreams["input0"]["input_stride"] = {0};
  jistreams["input0"]["input_range"] = {1};
  jistreams["input0"]["input_starting_addrs"] = {0};
  jistreams["input0"]["input_chunk"] = {1};
  jistreams["input0"]["input_block"] = {1};
  jistreams["input0"]["num_input_ports"] = {1};  // remove: this is the product of input block dims
  new_unified_buffer_gen->addDefaultGenArgs({{"istreams",Const::make(c,jistreams)}});

  Json jostreams;
  jostreams["output0"]["output_stride"] = {1};
  jostreams["output0"]["output_range"] = {1};
  jostreams["output0"]["output_starting_addrs"] = {0};
  jostreams["output0"]["output_stencil"] = {1};
  jostreams["output0"]["output_block"] = {1};
  // this parameter identifies how many dimensions of the access pattern range is inside the stencil
  jostreams["output0"]["num_stencil_acc_dim"] = {0};
  jostreams["output0"]["stencil_width"] = {1};    // default: used only after hw mapping
  jostreams["output0"]["iter_cnt"] = 1;           // remove: this is the product of all ranges
  jostreams["output0"]["num_loops"] = 1;          // remove: aka dimensionality, this can be inferred perhaps from the length of each ostream?
  jostreams["output0"]["num_output_ports"] = 1;   // remove: this is the product of output block dims
  new_unified_buffer_gen->addDefaultGenArgs({{"ostreams",Const::make(c,jostreams)}});

  /////////////////////////////////////
  //*** unified buffer definition ***//
  /////////////////////////////////////

  Params ubparams = Params({
      {"width",c->Int()},
      {"depth",c->Int()},
      {"rate_matched",c->Bool()},
      {"stencil_width",c->Int()},
      {"iter_cnt",c->Int()},
      {"num_input_ports",c->Int()},
      {"num_output_ports",c->Int()},
      {"dimensionality",c->Int()},
      {"stride_0",c->Int()},
      {"range_0",c->Int()},
      {"stride_1",c->Int()},
      {"range_1",c->Int()},
      {"stride_2",c->Int()},
      {"range_2",c->Int()},
      {"stride_3",c->Int()},
      {"range_3",c->Int()},
      {"stride_4",c->Int()},
      {"range_4",c->Int()},
      {"stride_5",c->Int()},
      {"range_5",c->Int()},
      {"input_stride_0",c->Int()},
      {"input_range_0",c->Int()},
      {"input_stride_1",c->Int()},
      {"input_range_1",c->Int()},
      {"input_stride_2",c->Int()},
      {"input_range_2",c->Int()},
      {"input_stride_3",c->Int()},
      {"input_range_3",c->Int()},
      {"input_stride_4",c->Int()},
      {"input_range_4",c->Int()},
      {"input_stride_5",c->Int()},
      {"input_range_5",c->Int()},
      {"chain_en",c->Bool()},
      {"chain_idx",c->Int()},
      {"input_starting_addrs",c->Json()},
      {"input_chunk",c->Json()},
      {"output_starting_addrs",c->Json()},
      {"output_stencil",c->Json()},
      {"logical_size",c->Json()},
      {"init",c->Json()},
      {"num_reduction_iter", c->Int()},
      //this parameter identify how many dimension of the access pattern range is inside stencil
      {"num_stencil_acc_dim", c->Int()}
    });

  // unified buffer type
  lakelib->newTypeGen(
    "unified_buffer_type", //name for the typegen
    ubparams, //generator parameters
    [](Context* c, Values genargs) { //Function to compute type
      uint width = genargs.at("width")->get<int>();
      uint num_inputs = genargs.at("num_input_ports")->get<int>();
      uint num_outputs = genargs.at("num_output_ports")->get<int>();

      RecordParams recordparams = {
        {"wen",c->BitIn()},
        {"ren",c->BitIn()},
        {"flush", c->BitIn()},
        {"reset", c->BitIn()},
        {"valid",c->Bit()}
      };

      // Add the dataports. The simulator needs them to be flattened
      bool simulation_compatible = true;
      if (simulation_compatible) {
        for (size_t i=0; i < num_inputs; ++i) {
          recordparams.push_back({"datain"+std::to_string(i), c->BitIn()->Arr(width)});
        }
        for (size_t i=0; i < num_outputs; ++i) {
          recordparams.push_back({"dataout"+std::to_string(i), c->Bit()->Arr(width)});
        }
      } else {
        recordparams.push_back({"datain",c->BitIn()->Arr(width)->Arr(num_inputs)});
        recordparams.push_back({"dataout",c->Bit()->Arr(width)->Arr(num_outputs)});
      }

      return c->Record(recordparams);
    }
  );

  auto unified_buffer_gen = lakelib->newGeneratorDecl("unified_buffer",lakelib->getTypeGen("unified_buffer_type"),ubparams);
  Json jdata;
  jdata["init"][0] = 0; // set default init to "0"
  unified_buffer_gen->addDefaultGenArgs({{"init",Const::make(c,jdata)}});
  unified_buffer_gen->addDefaultGenArgs({{"stride_0",Const::make(c,1)}});
  unified_buffer_gen->addDefaultGenArgs({{"range_0",Const::make(c,1)}});
  unified_buffer_gen->addDefaultGenArgs({{"stride_1",Const::make(c,0)}});
  unified_buffer_gen->addDefaultGenArgs({{"range_1",Const::make(c,0)}});
  unified_buffer_gen->addDefaultGenArgs({{"stride_2",Const::make(c,0)}});
  unified_buffer_gen->addDefaultGenArgs({{"range_2",Const::make(c,0)}});
  unified_buffer_gen->addDefaultGenArgs({{"stride_3",Const::make(c,0)}});
  unified_buffer_gen->addDefaultGenArgs({{"range_3",Const::make(c,0)}});
  unified_buffer_gen->addDefaultGenArgs({{"stride_4",Const::make(c,0)}});
  unified_buffer_gen->addDefaultGenArgs({{"range_4",Const::make(c,0)}});
  unified_buffer_gen->addDefaultGenArgs({{"stride_5",Const::make(c,0)}});
  unified_buffer_gen->addDefaultGenArgs({{"range_5",Const::make(c,0)}});

  unified_buffer_gen->addDefaultGenArgs({{"input_stride_0",Const::make(c,0)}});
  unified_buffer_gen->addDefaultGenArgs({{"input_range_0",Const::make(c,1)}});
  unified_buffer_gen->addDefaultGenArgs({{"input_stride_1",Const::make(c,0)}});
  unified_buffer_gen->addDefaultGenArgs({{"input_range_1",Const::make(c,0)}});
  unified_buffer_gen->addDefaultGenArgs({{"input_stride_2",Const::make(c,0)}});
  unified_buffer_gen->addDefaultGenArgs({{"input_range_2",Const::make(c,0)}});
  unified_buffer_gen->addDefaultGenArgs({{"input_stride_3",Const::make(c,0)}});
  unified_buffer_gen->addDefaultGenArgs({{"input_range_3",Const::make(c,0)}});
  unified_buffer_gen->addDefaultGenArgs({{"input_stride_4",Const::make(c,0)}});
  unified_buffer_gen->addDefaultGenArgs({{"input_range_4",Const::make(c,0)}});
  unified_buffer_gen->addDefaultGenArgs({{"input_stride_5",Const::make(c,0)}});
  unified_buffer_gen->addDefaultGenArgs({{"input_range_5",Const::make(c,0)}});

  // set default as a single input and output at index 0
  Json jinputs;
  Json joutputs;
  Json jinchunk;
  Json joutstencil;
  jinputs["input_start"][0] = 0;
  joutputs["output_start"][0] = 0;
  jinchunk["input_chunk"][0] = 1;
  joutputs["output_stencil"][0] = 1;
  unified_buffer_gen->addDefaultGenArgs({{"input_starting_addrs",Const::make(c,jinputs)}});
  unified_buffer_gen->addDefaultGenArgs({{"output_starting_addrs",Const::make(c,joutputs)}});
  unified_buffer_gen->addDefaultGenArgs({{"input_chunk",Const::make(c,jinchunk)}});
  unified_buffer_gen->addDefaultGenArgs({{"output_stencil",Const::make(c,joutstencil)}});
  unified_buffer_gen->addDefaultGenArgs({{"num_input_ports",Const::make(c,1)}});
  unified_buffer_gen->addDefaultGenArgs({{"num_output_ports",Const::make(c,1)}});
  unified_buffer_gen->addDefaultGenArgs({{"num_reduction_iter",Const::make(c,1)}});
  unified_buffer_gen->addDefaultGenArgs({{"num_stencil_acc_dim",Const::make(c,0)}});


  //////////////////////////////////////////////
  //*** abstract unified buffer definition ***//
  //////////////////////////////////////////////
  Params aubparams =
    {
     {"input_ports", CoreIRType::make(c)},
     {"output_ports", CoreIRType::make(c)},
     {"capacity", CoreIRType::make(c)},
     {"range", CoreIRType::make(c)},
     {"dim_ref", CoreIRType::make(c)},
     {"stride", CoreIRType::make(c)}
    };

    lakelib->newTypeGen(
      "abstract_unified_buffer_type",
      aubparams,
      [](Context* c, Values genargs) { //Function to compute type
      Type* input_port = genargs.at("input_ports")->get<Type*>();
      Type* output_port = genargs.at("output_ports")->get<Type*>();

      return c->Record({
        {"wen",c->BitIn()},
        {"ren",c->BitIn()},
        {"flush", c->BitIn()},
        {"reset", c->BitIn()},
        {"in",input_port},
        {"valid",c->Bit()},
        {"out",output_port}
      });
    }
  );

  Generator* aub = lakelib->newGeneratorDecl("abstract_unified_buffer",lakelib->getTypeGen("abstract_unified_buffer_type"),aubparams);
  aub->setGeneratorDefFromFun([](Context* c, Values genargs, ModuleDef* def) {
    });
return lakelib;
}

COREIR_GEN_EXTERNAL_API_FOR_LIBRARY(lakelib)
