#define CATCH_CONFIG_MAIN
#include "catch.hpp"

#include "coreir.h"
#include "coreir/passes/transform/rungenerators.h"
#include "coreir/simulator/interpreter.h"
//#include "coreir/libs/commonlib.h"
#include "coreir/libs/float.h"
#include "ubuf_coreirsim.h"
#include "lakelib.h"

#include <iostream>
#include <numeric>

using namespace CoreIR;
using namespace CoreIR::Passes;
using namespace std;

namespace CoreIR {

    string quote(string s) {
        return "\""+s+"\"";
    }


  // Define unified buffer generator simulation class
  class UnifiedBufferStub : public SimulatorPlugin {
    BitVector lastVal;

    int width;

  public:

    void initialize(vdisc vd, SimulatorState& simState) {
      auto wd = simState.getCircuitGraph().getNode(vd);
      Wireable* w = wd.getWire();

      assert(isInstance(w));

      Instance* inst = toInstance(w);
      width = inst->getModuleRef()->getGenArgs().at("width")->get<int>();
      lastVal = BitVector(width, 0);

    }

    void exeSequential(vdisc vd, SimulatorState& simState) {
      auto wd = simState.getCircuitGraph().getNode(vd);

      simState.updateInputs(vd);

      assert(isInstance(wd.getWire()));

      Instance* inst = toInstance(wd.getWire());

      auto inSels = getInputSelects(inst);

      Select* arg1 = toSelect(CoreIR::findSelect("in", inSels));
      assert(arg1 != nullptr);

      lastVal = simState.getBitVec(arg1);
    }

    void exeCombinational(vdisc vd, SimulatorState& simState) {
      auto wd = simState.getCircuitGraph().getNode(vd);

      Instance* inst = toInstance(wd.getWire());

      simState.setValue(toSelect(inst->sel("out")), lastVal);

    }

  };

  TEST_CASE("Unified buffer simulation stub") {
    std::cout << "unified buffer sim stub running...\n";
    Context* c = newContext();
    Namespace* g = c->newNamespace("bufferLib");

    // Define (dummy) unified buffer generator
    Params params = {{"width", c->Int()}, {"depth", c->Int()}};
    auto ubufstubTg = g->newTypeGen(
                  "ubufstub_type",
                  params,
                  [](Context* c, Values genargs) {
                    uint width = genargs.at("width")->get<int>();
                    uint depth = genargs.at("depth")->get<int>();

                    return c->Record({
                        {"clk",c->Named("coreir.clkIn")},
                          {"in", c->BitIn()->Arr(width)},
                            {"out", c->Bit()->Arr(width)}});
                  }
                  );

    g->newGeneratorDecl("ubufstub", ubufstubTg, params);

    // Build container module
    Namespace* global = c->getNamespace("global");
    int width = 16;
    Type* bufWrapperType =
        c->Record({
            {"clk",c->Named("coreir.clkIn")},
            {"in",c->BitIn()->Arr(width)},
            {"out",c->Bit()->Arr(width)}
          });

    Module* wrapperMod =
      c->getGlobal()->newModuleDecl("bufWrapper", bufWrapperType);
    ModuleDef* def = wrapperMod->newModuleDef();

    def->addInstance("buf0",
                       "bufferLib.ubufstub",
                       {{"width", Const::make(c, width)},
                           {"depth", Const::make(c, 64)}});

    def->connect("buf0.out", "self.out");
    def->connect("buf0.in", "self.in");
    def->connect("buf0.clk", "self.clk");

    wrapperMod->setDef(def);
    c->runPasses({"rungenerators", "flatten", "flattentypes", "wireclocks-coreir"});

    // Build the simulator with the new model
    auto modBuilder = [](WireNode& wd) {
      UnifiedBufferStub* simModel = new UnifiedBufferStub();
      return simModel;
    };

    map<std::string, SimModelBuilder> qualifiedNamesToSimPlugins{{string("bufferLib.ubufstub"), modBuilder}};

    SimulatorState state(wrapperMod, qualifiedNamesToSimPlugins);

    state.setValue("self.in", BitVector(width, 89));
    state.setClock("self.clk", 0, 1);

    state.resetCircuit();

    state.execute();

    REQUIRE(state.getBitVec("self.out") == BitVector(width, 89));

    state.setValue("self.in", BitVector(width, 7));

    state.execute();

    REQUIRE(state.getBitVec("self.out") == BitVector(width, 7));

    deleteContext(c);
    std::cout << "PASSED: unified buffer stub simulation!\n";
  }


  TEST_CASE("Unified buffer address generator simulation") {
    std::cout << "unified buffer address generator sim running...\n";
    Context* c = newContext();
    Namespace* g = c->newNamespace("bufferLib");

    // Define unified buffer address generator
    Params params =
      {{"width", c->Int()},
       {"range_type", CoreIRType::make(c)},
       {"stride_type", CoreIRType::make(c)},
       {"start_type", CoreIRType::make(c)}
      };
    auto uBufAddrTg = g->newTypeGen(
                  "ubufaddrgen_type",
                  params,
                  [](Context* c, Values genargs) {
                    uint width = genargs.at("width")->get<int>();

                    return c->Record({
                        {"clk",c->Named("coreir.clkIn")},
                        {"reset", c->BitIn()},
                        {"out", c->Bit()->Arr(width)}});
                  }
                  );

    g->newGeneratorDecl("ubufaddr", uBufAddrTg, params);

    // Build container module
    Namespace* global = c->getNamespace("global");
    int width = 16;
    Type* bufaddrWrapperType =
        c->Record({
            {"clk",c->Named("coreir.clkIn")},
            {"reset",c->BitIn()},
            {"out",c->Bit()->Arr(width)}
          });

    Module* wrapperMod =
      c->getGlobal()->newModuleDecl("bufaddrWrapper", bufaddrWrapperType);
    ModuleDef* def = wrapperMod->newModuleDef();

    def->addInstance("bufaddr0",
                       "bufferLib.ubufaddr",
                       {{"width",       Const::make(c, width)},
                        {"range_type",  Const::make(c, c->Bit()->Arr(6)->Arr(3)->Arr(32)->Arr(32))},
                        {"stride_type", Const::make(c, c->Bit()->Arr(4)->Arr(272)->Arr(8)->Arr(272))},
                        {"start_type",  Const::make(c, c->Bit()->Arr(0)->Arr(2)->Arr(3)->Arr(4))}
                     });

    def->connect("bufaddr0.out", "self.out");
    def->connect("bufaddr0.reset", "self.reset");
    def->connect("bufaddr0.clk", "self.clk");

    wrapperMod->setDef(def);
    c->runPasses({"rungenerators", "flatten", "flattentypes", "wireclocks-coreir"});

    // Build the simulator with the new model
    auto modBuilder = [](WireNode& wd) {
      UnifiedBufferAddressGenerator* simModel = new UnifiedBufferAddressGenerator();
      return simModel;
    };

    map<std::string, SimModelBuilder> qualifiedNamesToSimPlugins{{string("bufferLib.ubufaddr"), modBuilder}};

    SimulatorState state(wrapperMod, qualifiedNamesToSimPlugins);

    state.setValue("self.reset", BitVector(1, 1));
    state.setClock("self.clk", 0, 1);

    state.resetCircuit();

    state.execute();

    REQUIRE(state.getBitVec("self.out") == BitVector(width, 0));

    state.setValue("self.reset", BitVector(1, 0));

    state.execute();

    REQUIRE(state.getBitVec("self.out") == BitVector(width, 4));

    deleteContext(c);
    std::cout << "PASSED: unified buffer address generator simulation!\n";
  }


  TEST_CASE("Unified buffer basic simulation") {
    std::cout << "unified buffer sim running...\n";
    Context* c = newContext();
    Namespace* g = c->newNamespace("bufferLib");
    CoreIRLoadLibrary_commonlib(c);
    CoreIRLoadLibrary_lakelib(c);

    // Define unified buffer generator
    /*
    Params params =
      {{"width", c->Int()},
       {"range_type", CoreIRType::make(c)},
       {"stride_type", CoreIRType::make(c)},
       {"start_type", CoreIRType::make(c)}
      };
    auto uBufTg = g->newTypeGen(
                  "ubufgen_type",
                  params,
                  [](Context* c, Values genargs) {
                    uint width = genargs.at("width")->get<int>();

                    return c->Record({
                        {"clk",c->Named("coreir.clkIn")},
                        {"reset", c->BitIn()},
                        {"dataout", c->Bit()->Arr(width)},
                        {"valid", c->BitIn()},
                        {"datain", c->Bit()->Arr(width)}});
                  }
                  );

    g->newGeneratorDecl("ubuf", uBufTg, params);
    */

    // Build container module
    Namespace* global = c->getNamespace("global");
    int width = 16;
    Type* bufWrapperType =
        c->Record({
            {"clk",c->Named("coreir.clkIn")},
            {"reset",c->BitIn()},
            {"out",c->Bit()->Arr(width)},
            {"valid",c->Bit()},
            {"in",c->BitIn()->Arr(width)},
            {"ren",c->BitIn()},
            {"wen",c->BitIn()}
          });

    Module* wrapperMod =
      c->getGlobal()->newModuleDecl("bufWrapper", bufWrapperType);
    ModuleDef* def = wrapperMod->newModuleDef();

    /*
    Json jinputs;
    Json joutputs;
    jinputs["input_start"][0] = 0;
    joutputs["output_start"][0] = 0;
    */
    Json logical_size;
    logical_size["capacity"][0] = 16;
    Json in_chunk;
    in_chunk["input_chunk"][0] = 1;
    Json out_stencil;
    out_stencil["output_stencil"][0] = 1;
    //using default input/output start
    def->addInstance("buf0",
                       "lakelib.unified_buffer",
                       {{"width",       Const::make(c, width)},
                        {"stencil_width", Const::make(c, 0)},
                        {"depth", Const::make(c, 16)},
                        {"chain_idx", Const::make(c, 0)},
                        {"rate_matched", Const::make(c, false)},
                        {"chain_en", Const::make(c, false)},
                        {"dimensionality", Const::make(c, 1)},
                        {"iter_cnt", Const::make(c, 16)},
                        {"logical_size", Const::make(c, logical_size)},
                        {"input_chunk", Const::make(c, in_chunk)},
                        {"output_stencil", Const::make(c, out_stencil)},
                        {"num_stencil_acc_dim", Const::make(c, 0)},
                        {"input_range_0",  Const::make(c, 16)},
                        {"input_stride_0", Const::make(c, 1)},
                        {"range_0",  Const::make(c, 16)},
                        {"stride_0", Const::make(c, 1)}
                     });

    def->connect("buf0.datain0", "self.in");
    def->connect("buf0.dataout0", "self.out");
    def->connect("buf0.ren", "self.ren");
    def->connect("buf0.wen", "self.wen");
    def->connect("buf0.valid", "self.valid");
    def->connect("buf0.reset", "self.reset");

    std::cout << "finish connect" << std::endl;

    wrapperMod->setDef(def);
    c->runPasses({"rungenerators", "flatten", "flattentypes", "wireclocks-coreir"});

    // Build the simulator with the new model
    auto modBuilder = [](WireNode& wd) {
      UnifiedBuffer_new* simModel = new UnifiedBuffer_new();
      return simModel;
    };

    map<std::string, SimModelBuilder> qualifiedNamesToSimPlugins{{string("lakelib.unified_buffer"), modBuilder}};

    SimulatorState state(wrapperMod, qualifiedNamesToSimPlugins);

    std::cout << "finish create SimulatorState" << std::endl;
    state.setValue("self.reset", BitVector(1, 1));
    state.setValue("self.wen", BitVector(1, 0));
    state.setValue("self.ren", BitVector(1, 1));
    state.setValue("self.in", BitVector(width, 0));
    state.setClock("self.clk", 0, 1);

    std::cout << "finish set value" << std::endl;
    state.resetCircuit();

    //state.execute();

    //REQUIRE(state.getBitVec("self.out") == BitVector(width, 0));

    //cycle for initialize

    std::cout << "start running" << std::endl;
    for (int i = 0; i < 16; i ++) {
        state.setValue("self.reset", BitVector(1, 0));
        state.setValue("self.wen", BitVector(1, 1));
        state.setValue("self.ren", BitVector(1, 1));
        state.setValue("self.in", BitVector(width, i));

        state.execute();

        REQUIRE(state.getBitVec("self.out") == BitVector(width, i));
    }
    /*
    for (int i = 0; i < 16; i ++) {
        state.setValue("self.reset", BitVector(1, 0));
        state.setValue("self.wen", BitVector(1, 1));
        state.setValue("self.ren", BitVector(1, 1));
        state.setValue("self.in", BitVector(width, i));
        REQUIRE(state.getBitVec("self.out") == BitVector(width, i));

        state.execute();

    }*/

    //REQUIRE(state.getBitVec("self.out") == BitVector(width, 4));

    deleteContext(c);
    std::cout << "PASSED: unified buffer basic simulation!\n";
  }

  TEST_CASE("New Unified buffer basic simulation") {
    std::cout << "New unified buffer sim running...\n";
    Context* c = newContext();
    Namespace* g = c->newNamespace("bufferLib");
    CoreIRLoadLibrary_commonlib(c);
    CoreIRLoadLibrary_lakelib(c);

    // Build container module
    Namespace* global = c->getNamespace("global");
    int width = 16;
    Type* bufWrapperType =
        c->Record({
            {"clk",c->Named("coreir.clkIn")},
            {"reset",c->BitIn()},
            {"out",c->Bit()->Arr(width)},
            {"valid",c->Bit()},
            {"in",c->BitIn()->Arr(width)},
            {"ren",c->BitIn()},
            {"wen",c->BitIn()}
          });

    Module* wrapperMod =
      c->getGlobal()->newModuleDecl("bufWrapper", bufWrapperType);
    ModuleDef* def = wrapperMod->newModuleDef();

    /*
    Json jinputs;
    Json joutputs;
    jinputs["input_start"][0] = 0;
    joutputs["output_start"][0] = 0;
    */
    Json logical_size;
    logical_size["capacity"][0] = 16;
    // set some default inputs and outputs
    Json jistreams;
    jistreams["input0"]["input_stride"] = {1};
    jistreams["input0"]["input_range"] = {16};
    jistreams["input0"]["input_starting_addrs"] = {0};
    jistreams["input0"]["input_chunk"] = {1};
    jistreams["input0"]["input_block"] = {1};
    jistreams["input0"]["num_input_ports"] = 1;

    Json jostreams;
    jostreams["output0"]["output_stride"] = {1};
    jostreams["output0"]["output_range"] = {16};
    jostreams["output0"]["output_starting_addrs"] = {0};
    jostreams["output0"]["output_stencil"] = {1};
    jostreams["output0"]["output_block"] = {1};
    jostreams["output0"]["num_output_ports"] = 1;
    jostreams["output0"]["num_stencil_acc_dim"] = 0;
    jostreams["output0"]["stencil_width"] = {0};

    //using default input/output start
    def->addInstance("buf0",
                       "lakelib.new_unified_buffer",
                       {{"width",       Const::make(c, width)},
                        {"chain_idx", Const::make(c, 0)},
                        {"chain_en", Const::make(c, false)},
                        {"logical_size", Const::make(c, logical_size)},
                        {"istreams", Const::make(c, jistreams)},
                        {"ostreams", Const::make(c, jostreams)}
                     });

    def->connect("buf0.datain_input0_0", "self.in");
    def->connect("buf0.dataout_output0_0", "self.out");
    def->connect("buf0.ren", "self.ren");
    def->connect("buf0.wen", "self.wen");
    def->connect("buf0.valid", "self.valid");
    def->connect("buf0.reset", "self.reset");

    std::cout << "finish connect" << std::endl;

    wrapperMod->setDef(def);
    c->runPasses({"rungenerators", "flatten", "flattentypes", "wireclocks-coreir"});

    // Build the simulator with the new model
    auto modBuilder = [](WireNode& wd) {
      UnifiedBuffer_new* simModel = new UnifiedBuffer_new();
      return simModel;
    };

    map<std::string, SimModelBuilder> qualifiedNamesToSimPlugins{{string("lakelib.new_unified_buffer"), modBuilder}};

    SimulatorState state(wrapperMod, qualifiedNamesToSimPlugins);

    std::cout << "finish create SimulatorState" << std::endl;
    state.setValue("self.reset", BitVector(1, 1));
    state.setValue("self.wen", BitVector(1, 0));
    state.setValue("self.ren", BitVector(1, 1));
    state.setValue("self.in", BitVector(width, 0));
    state.setClock("self.clk", 0, 1);

    std::cout << "finish set value" << std::endl;
    state.resetCircuit();

    //state.execute();

    //REQUIRE(state.getBitVec("self.out") == BitVector(width, 0));

    //cycle for initialize

    std::cout << "start running" << std::endl;
    for (int i = 0; i < 16; i ++) {
        state.setValue("self.reset", BitVector(1, 0));
        state.setValue("self.wen", BitVector(1, 1));
        state.setValue("self.ren", BitVector(1, 1));
        state.setValue("self.in", BitVector(width, i));

        state.execute();

        REQUIRE(state.getBitVec("self.out") == BitVector(width, i));
    }

    deleteContext(c);
    std::cout << "PASSED: new unified buffer basic simulation!\n";
  }


   TEST_CASE("Unified buffer 3x3 Conv simulation") {
    std::cout << "unified buffer 3x3 conv sim running...\n";
    Context* c = newContext();
    Namespace* g = c->newNamespace("bufferLib");
    CoreIRLoadLibrary_commonlib(c);
    CoreIRLoadLibrary_lakelib(c);


    // Build container module
    Namespace* global = c->getNamespace("global");
    int width = 16;
    int num_input_port = 1;
    int num_output_port = 9;
    Type* bufWrapperType =
        c->Record({
            {"clk",c->Named("coreir.clkIn")},
            {"reset",c->BitIn()},
            {"out0",c->Bit()->Arr(width)},
            {"out1",c->Bit()->Arr(width)},
            {"out2",c->Bit()->Arr(width)},
            {"out3",c->Bit()->Arr(width)},
            {"out4",c->Bit()->Arr(width)},
            {"out5",c->Bit()->Arr(width)},
            {"out6",c->Bit()->Arr(width)},
            {"out7",c->Bit()->Arr(width)},
            {"out8",c->Bit()->Arr(width)},
            {"valid",c->Bit()},
            {"in",c->BitIn()->Arr(width)},
            {"ren",c->BitIn()},
            {"wen",c->BitIn()}
          });

    Module* wrapperMod =
      c->getGlobal()->newModuleDecl("bufWrapper", bufWrapperType);
    ModuleDef* def = wrapperMod->newModuleDef();

    //define the unified buffer parameter
    Json logical_size;
    logical_size["capacity"][0] = 16;
    logical_size["capacity"][1] = 16;
    Json in_chunk;
    in_chunk["input_chunk"][0] = 1;
    in_chunk["input_chunk"][1] = 1;
    Json out_stencil;
    out_stencil["output_stencil"][0] = 3;
    out_stencil["output_stencil"][1] = 3;

    Json out_start;
    for (int x = 0 ; x < 3; x ++) {
      for (int y = 0 ; y < 3; y ++) {
        out_start["output_start"][x+y*3] = x+y*16;
      }
    }
    //using default input/output start
    def->addInstance("buf0",
                       "lakelib.unified_buffer",
                       {{"width", Const::make(c, width)},
                       {"num_input_ports", Const::make(c, num_input_port)},
                       {"num_output_ports", Const::make(c, num_output_port)},
                        {"stencil_width", Const::make(c, 0)},
                        {"depth", Const::make(c, 256)},
                        {"chain_idx", Const::make(c, 0)},
                        {"rate_matched", Const::make(c, false)},
                        {"chain_en", Const::make(c, false)},
                        {"dimensionality", Const::make(c, 2)},
                        {"iter_cnt", Const::make(c, 256)},
                        {"logical_size", Const::make(c, logical_size)},
                        {"input_chunk", Const::make(c, in_chunk)},
                        {"output_stencil", Const::make(c, out_stencil)},
                        {"num_stencil_acc_dim", Const::make(c, 0)},
                        {"input_range_0",  Const::make(c, 16)},
                        {"input_stride_0", Const::make(c, 1)},
                        {"input_range_1",  Const::make(c, 16)},
                        {"input_stride_1", Const::make(c, 16)},
                        {"range_0",  Const::make(c, 14)},
                        {"stride_0", Const::make(c, 1)},
                        {"range_1",  Const::make(c, 14)},
                        {"stride_1", Const::make(c, 16)},
                        {"output_starting_addrs", Const::make(c, out_start)}
                     });

    def->connect("buf0.datain0", "self.in");
    def->connect("buf0.dataout0", "self.out0");
    def->connect("buf0.dataout1", "self.out1");
    def->connect("buf0.dataout2", "self.out2");
    def->connect("buf0.dataout3", "self.out3");
    def->connect("buf0.dataout4", "self.out4");
    def->connect("buf0.dataout5", "self.out5");
    def->connect("buf0.dataout6", "self.out6");
    def->connect("buf0.dataout7", "self.out7");
    def->connect("buf0.dataout8", "self.out8");
    def->connect("buf0.ren", "self.ren");
    def->connect("buf0.wen", "self.wen");
    def->connect("buf0.valid", "self.valid");
    def->connect("buf0.reset", "self.reset");
    //def->connect("buf0.clk", "self.clk");

    std::cout << "finish connect" << std::endl;

    wrapperMod->setDef(def);
    c->runPasses({"rungenerators", "flatten", "flattentypes", "wireclocks-coreir"});

    // Build the simulator with the new model
    auto modBuilder = [](WireNode& wd) {
      UnifiedBuffer_new* simModel = new UnifiedBuffer_new();
      return simModel;
    };

    map<std::string, SimModelBuilder> qualifiedNamesToSimPlugins{{string("lakelib.unified_buffer"), modBuilder}};

    SimulatorState state(wrapperMod, qualifiedNamesToSimPlugins);

    std::cout << "finish create SimulatorState" << std::endl;
    state.setValue("self.reset", BitVector(1, 1));
    state.setValue("self.wen", BitVector(1, 0));
    state.setValue("self.ren", BitVector(1, 1));
    state.setValue("self.in", BitVector(width, 0));
    state.setClock("self.clk", 0, 1);

    std::cout << "finish set value" << std::endl;
    state.resetCircuit();

    //state.execute();

    //REQUIRE(state.getBitVec("self.out") == BitVector(width, 0));

    //cycle for initialize

    std::cout << "start running" << std::endl;

    //simulation start
    for (int tile = 0; tile < 4; tile ++){
    cout << "Consume tile: " << tile << endl;
    for (int i = 0; i < 256; i ++) {
        state.setValue("self.reset", BitVector(1, 0));
        state.setValue("self.wen", BitVector(1, 1));
        state.setValue("self.ren", BitVector(1, 1));
        state.setValue("self.in", BitVector(width, i));

        state.execute();

        if (state.getBitVec("self.valid") == BitVector(1, 1)){
          //output valid
          for (int x = 0; x < 3; x ++) {
            for (int y = 0; y < 3; y ++) {
              REQUIRE(state.getBitVec("self.out"+to_string(x+y*3)) == BitVector(width, i-2-32+x+y*16));
            }
          }
          //update valid counter
        }
    }
    }


    deleteContext(c);
    std::cout << "PASSED: unified buffer 3x3 conv simulation!\n";
  }

   TEST_CASE("New unified buffer 3x3 Conv simulation") {
    std::cout << "New unified buffer 3x3 conv sim running...\n";
    Context* c = newContext();
    Namespace* g = c->newNamespace("bufferLib");
    CoreIRLoadLibrary_commonlib(c);
    CoreIRLoadLibrary_lakelib(c);


    // Build container module
    Namespace* global = c->getNamespace("global");
    int width = 16;
    int num_input_port = 1;
    int num_output_port = 9;
    Type* bufWrapperType =
        c->Record({
            {"clk",c->Named("coreir.clkIn")},
            {"reset",c->BitIn()},
            {"out0",c->Bit()->Arr(width)},
            {"out1",c->Bit()->Arr(width)},
            {"out2",c->Bit()->Arr(width)},
            {"out3",c->Bit()->Arr(width)},
            {"out4",c->Bit()->Arr(width)},
            {"out5",c->Bit()->Arr(width)},
            {"out6",c->Bit()->Arr(width)},
            {"out7",c->Bit()->Arr(width)},
            {"out8",c->Bit()->Arr(width)},
            {"valid",c->Bit()},
            {"in",c->BitIn()->Arr(width)},
            {"ren",c->BitIn()},
            {"wen",c->BitIn()}
          });

    Module* wrapperMod =
      c->getGlobal()->newModuleDecl("bufWrapper", bufWrapperType);
    ModuleDef* def = wrapperMod->newModuleDef();

    //define the unified buffer parameter
    Json logical_size;
    logical_size["capacity"][0] = 16;
    logical_size["capacity"][1] = 16;

    Json jistreams;
    jistreams["input0"]["input_stride"] = {1};
    jistreams["input0"]["input_range"] = {256};
    jistreams["input0"]["input_starting_addrs"] = {0};
    jistreams["input0"]["input_chunk"] = {1};
    jistreams["input0"]["input_block"] = {1};
    jistreams["input0"]["num_input_ports"] = 1;

    Json jostreams;
    jostreams["output0"]["output_stride"] = {1, 16};
    jostreams["output0"]["output_range"] = {14, 14};
    jostreams["output0"]["output_stencil"] = {3,3};
    jostreams["output0"]["output_block"] = {3,3};
    jostreams["output0"]["num_output_ports"] = 9;
    jostreams["output0"]["num_stencil_acc_dim"] = 0;
    jostreams["output0"]["stencil_width"] = {0};
    for (int x = 0 ; x < 3; x ++) {
      for (int y = 0 ; y < 3; y ++) {
        jostreams["output0"]["output_starting_addrs"][x+y*3] = x+y*16;
      }
    }

    //using default input/output start
    def->addInstance("buf0",
                       "lakelib.new_unified_buffer",
                       {{"width",       Const::make(c, width)},
                        {"chain_idx", Const::make(c, 0)},
                        {"chain_en", Const::make(c, false)},
                        {"logical_size", Const::make(c, logical_size)},
                        {"istreams", Const::make(c, jistreams)},
                        {"ostreams", Const::make(c, jostreams)}
                     });
    //using default input/output start

    def->connect("buf0.datain_input0_0", "self.in");
    for (int i = 0; i < 9; i ++)
        def->connect("buf0.dataout_output0_"+to_string(i), "self.out"+to_string(i));
    def->connect("buf0.ren", "self.ren");
    def->connect("buf0.wen", "self.wen");
    def->connect("buf0.valid", "self.valid");
    def->connect("buf0.reset", "self.reset");
    //def->connect("buf0.clk", "self.clk");

    std::cout << "finish connect" << std::endl;

    wrapperMod->setDef(def);
    c->runPasses({"rungenerators", "flatten", "flattentypes", "wireclocks-coreir"});

    // Build the simulator with the new model
    auto modBuilder = [](WireNode& wd) {
      UnifiedBuffer_new* simModel = new UnifiedBuffer_new();
      return simModel;
    };

    map<std::string, SimModelBuilder> qualifiedNamesToSimPlugins{{string("lakelib.new_unified_buffer"), modBuilder}};

    SimulatorState state(wrapperMod, qualifiedNamesToSimPlugins);

    std::cout << "finish create SimulatorState" << std::endl;
    state.setValue("self.reset", BitVector(1, 1));
    state.setValue("self.wen", BitVector(1, 0));
    state.setValue("self.ren", BitVector(1, 1));
    state.setValue("self.in", BitVector(width, 0));
    state.setClock("self.clk", 0, 1);

    std::cout << "finish set value" << std::endl;
    state.resetCircuit();

    //state.execute();

    //REQUIRE(state.getBitVec("self.out") == BitVector(width, 0));

    //cycle for initialize

    std::cout << "start running" << std::endl;

    //simulation start
    for (int tile = 0; tile < 4; tile ++){
    cout << "Consume tile: " << tile << endl;
    for (int i = 0; i < 256; i ++) {
        state.setValue("self.reset", BitVector(1, 0));
        state.setValue("self.wen", BitVector(1, 1));
        state.setValue("self.ren", BitVector(1, 1));
        state.setValue("self.in", BitVector(width, i));

        state.execute();

        if (state.getBitVec("self.valid") == BitVector(1, 1)){
          //output valid
          for (int x = 0; x < 3; x ++) {
            for (int y = 0; y < 3; y ++) {
              REQUIRE(state.getBitVec("self.out"+to_string(x+y*3)) == BitVector(width, i-2-32+x+y*16));
            }
          }
          //update valid counter
        }
    }
    }


    deleteContext(c);
    std::cout << "PASSED: new unified buffer 3x3 conv simulation!\n";
  }

     TEST_CASE("Unified buffer DB simulation") {
    std::cout << "unified buffer DB sim running...\n";
    Context* c = newContext();
    Namespace* g = c->newNamespace("bufferLib");
    CoreIRLoadLibrary_commonlib(c);
    CoreIRLoadLibrary_lakelib(c);


    // Build container module
    Namespace* global = c->getNamespace("global");
    int width = 16;
    int num_input_port = 4;
    int num_output_port = 4;
    Type* bufWrapperType =
        c->Record({
            {"clk",c->Named("coreir.clkIn")},
            {"reset",c->BitIn()},
            {"out0",c->Bit()->Arr(width)},
            {"out1",c->Bit()->Arr(width)},
            {"out2",c->Bit()->Arr(width)},
            {"out3",c->Bit()->Arr(width)},
            {"valid",c->Bit()},
            {"in0",c->BitIn()->Arr(width)},
            {"in1",c->BitIn()->Arr(width)},
            {"in2",c->BitIn()->Arr(width)},
            {"in3",c->BitIn()->Arr(width)},
            {"ren",c->BitIn()},
            {"wen",c->BitIn()}
          });

    Module* wrapperMod =
      c->getGlobal()->newModuleDecl("bufWrapper", bufWrapperType);
    ModuleDef* def = wrapperMod->newModuleDef();

    //define the unified buffer parameter
    Json logical_size;
    logical_size["capacity"][0] = 16;
    logical_size["capacity"][1] = 16;
    logical_size["capacity"][2] = 16;
    Json in_chunk;
    in_chunk["input_chunk"][0] = 16;
    in_chunk["input_chunk"][1] = 16;
    in_chunk["input_chunk"][2] = 16;
    Json out_stencil;
    out_stencil["output_stencil"][0] = 16;
    out_stencil["output_stencil"][1] = 16;
    out_stencil["output_stencil"][2] = 16;

    Json out_start;
    for (int x = 0 ; x < 4; x ++) {
      out_start["output_start"][x] = x;
    }
    Json in_start;
    for (int x = 0 ; x < 4; x ++) {
      in_start["input_start"][x] = x;
    }
    //using default input/output start
    def->addInstance("buf0",
                       "lakelib.unified_buffer",
                       {{"width", Const::make(c, width)},
                       {"num_input_ports", Const::make(c, num_input_port)},
                       {"num_output_ports", Const::make(c, num_output_port)},
                        {"stencil_width", Const::make(c, 0)},
                        {"depth", Const::make(c, 1024)},
                        {"chain_idx", Const::make(c, 0)},
                        {"rate_matched", Const::make(c, false)},
                        {"chain_en", Const::make(c, false)},
                        {"dimensionality", Const::make(c, 4)},
                        {"iter_cnt", Const::make(c, 9216)},
                        {"logical_size", Const::make(c, logical_size)},
                        {"input_chunk", Const::make(c, in_chunk)},
                        {"output_stencil", Const::make(c, out_stencil)},
                        {"num_stencil_acc_dim", Const::make(c, 4)},
                        {"input_range_0",  Const::make(c, 4)},
                        {"input_stride_0", Const::make(c, 4)},
                        {"input_range_1",  Const::make(c, 16)},
                        {"input_stride_1", Const::make(c, 16)},
                        {"input_range_2",  Const::make(c, 16)},
                        {"input_stride_2", Const::make(c, 256)},
                        {"range_0",  Const::make(c, 12)},
                        {"stride_0", Const::make(c, 4)},
                        {"range_1",  Const::make(c, 3)},
                        {"stride_1", Const::make(c, 256)},
                        {"range_2",  Const::make(c, 14)},
                        {"stride_2", Const::make(c, 16)},
                        {"range_3",  Const::make(c, 14)},
                        {"stride_3", Const::make(c, 256)},
                        {"input_starting_addrs", Const::make(c, in_start)},
                        {"output_starting_addrs", Const::make(c, out_start)}
                     });

    def->connect("buf0.datain0", "self.in0");
    def->connect("buf0.datain1", "self.in1");
    def->connect("buf0.datain2", "self.in2");
    def->connect("buf0.datain3", "self.in3");
    def->connect("buf0.dataout0", "self.out0");
    def->connect("buf0.dataout1", "self.out1");
    def->connect("buf0.dataout2", "self.out2");
    def->connect("buf0.dataout3", "self.out3");
    def->connect("buf0.ren", "self.ren");
    def->connect("buf0.wen", "self.wen");
    def->connect("buf0.valid", "self.valid");
    def->connect("buf0.reset", "self.reset");
    //def->connect("buf0.clk", "self.clk");

    std::cout << "finish connect" << std::endl;

    wrapperMod->setDef(def);
    c->runPasses({"rungenerators", "flatten", "flattentypes", "wireclocks-coreir"});

    // Build the simulator with the new model
    auto modBuilder = [](WireNode& wd) {
      UnifiedBuffer_new* simModel = new UnifiedBuffer_new();
      return simModel;
    };

    map<std::string, SimModelBuilder> qualifiedNamesToSimPlugins{{string("lakelib.unified_buffer"), modBuilder}};

    SimulatorState state(wrapperMod, qualifiedNamesToSimPlugins);

    std::cout << "finish create SimulatorState" << std::endl;
    state.setValue("self.reset", BitVector(1, 1));
    state.setValue("self.wen", BitVector(1, 0));
    state.setValue("self.ren", BitVector(1, 1));
    for (int ii = 0; ii < 4; ii ++)
        state.setValue("self.in"+to_string(ii), BitVector(width, ii));
    state.setClock("self.clk", 0, 1);

    std::cout << "finish set value" << std::endl;
    state.resetCircuit();

    //state.execute();

    //REQUIRE(state.getBitVec("self.out") == BitVector(width, 0));

    //cycle for initialize

    std::cout << "start running" << std::endl;

    int initial_cnt = 4096;
    int steady_cnt = 4*3*3*14*14;

    //simulation start
    for (int i = 0; i < initial_cnt / 4; i ++) {
      state.setValue("self.reset", BitVector(1, 0));
      state.setValue("self.wen", BitVector(1, 1));
      state.setValue("self.ren", BitVector(1, 0));
      for (int ii = 0; ii < 4; ii ++)
        state.setValue("self.in"+to_string(ii), BitVector(width, 4*i + ii));

      state.execute();
      REQUIRE(state.getBitVec("self.valid") == BitVector(1, 0));
    }

    //finish inital enter data load
    for (int tile = 0; tile < 4; tile ++){
      cout << "Consume tile: " << tile << endl;

      int iter = 0;
      for (int y = 0; y < 14; y ++)
      for (int x = 0; x < 14; x ++)
      for (int ky = 0; ky < 3; ky ++)
      for (int kx = 0; kx < 3; kx ++)
      for (int c = 0; c < 4; c ++) {
        if (iter < initial_cnt/4)
          state.setValue("self.wen", BitVector(1, 1));
        else
          state.setValue("self.wen", BitVector(1, 0));
        state.setValue("self.reset", BitVector(1, 0));
        state.setValue("self.ren", BitVector(1, 1));
        for (int ii = 0; ii < 4; ii ++)
          state.setValue("self.in"+to_string(ii), BitVector(width, 4*iter + ii));

        state.execute();

        if (state.getBitVec("self.valid") == BitVector(1, 1)){
          //output valid
          for (int port = 0; port < 4; port ++) {
            REQUIRE(state.getBitVec("self.out"+to_string(port)) == BitVector(width, port+c*4+(x+kx)*16+(y+ky)*256));
          }
          //update valid counter
        }
        iter ++;
      }
    }


    deleteContext(c);
    std::cout << "PASSED: unified buffer DB simulation!\n";
  }

}
