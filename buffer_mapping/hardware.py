from buffer_mapping.virtualbuffer import VirtualRowBuffer, VirtualBuffer, VirtualDoubleBuffer, AccessIter
from buffer_mapping.util import Counter, AccessPattern
from buffer_mapping.pretty_print import NoIndent
import copy
from functools import reduce
from collections import defaultdict

class HardwarePort:
    '''
    class for the connection wire and save its value
    '''
    def __init__(self, key, val):
        self.key = key
        self.val = val
        self.val_type = type(val)
        self.pred = None
        self.succ = []

    def makePred(self, pred):
        self.pred = pred

    def removePred(self):
        self.pred = None

    def addSucc(self, succ):
        self.succ.append(succ)

    def removeSucc(self, succ):
        self.succ.remove(succ)

class DummyNode:
    def __init__(self, name):
        self.name = name
        self.contain_node = False

class FlushNode(DummyNode):
    def __init__(self, name):
        super().__init__(name)

    def dump_json(self):
        mem_tile = {}
        mem_tile["modref"] = "corebit.const"
        mem_tile["modargs"] = {"value": ["Bool", False]}

        return mem_tile

    def connectNode(self, node):
        connection_dict = {}
        if type(node) == BufferNode:
            connection_dict[(self.name+".out", node.name+".flush")] = \
                DummyWire(self.name+".out", node.name+".flush")

        else:
            assert True, "Connection between flush node to"+ str(type(node))+" node is not implemented"
        return connection_dict

class HardwareNode:
    '''
    class wrapper for functional model check
    has I/O port, with connection information of predecessor and successorvalid
    '''
    def __init__(self, name, input_list, output_list):
        '''
        input/output is a list of name, type tuple
        '''
        self.contain_node = False
        self.name = name
        self.kernel = None
        self.input_port = {port.key.split(".",1)[-1]: port  for port in input_list}
        self.output_port = {port.key.split(".",1)[-1]: port for port in output_list}
        self.pred = None
        self.succ = defaultdict(list)

    def makePred(self, pred):
        self.pred = pred

    def removePred(self):
        self.pred = None

    def addSucc(self, succ, port_id=0):
        self.succ[port_id].append(succ)

    def removeSucc(self, succ, port_id=0):
        self.succ[port_id].remove(succ)


    def removeConnection(self):
        #no need to remove the succ's pred because pred update is always overwrite
        self.pred.removeSucc(self)
        remove_wire_list = []
        for key, in_port in self.input_port.items():
            #remove the predessor's succ information
            in_port.pred.removeSucc(in_port)
            #remove the connection
            remove_wire_list.append((in_port.key, in_port.pred.key))
        for key, out_port in self.output_port.items():
            for succ in out_port.succ:
                remove_wire_list.append((succ.key, out_port.key))

        #remove dummy reset wire if it's buffernode
        if type(self) == BufferNode:
            remove_wire_list.append(("self.reset", self.name+".reset"))

        return remove_wire_list
    def update(self):
        '''
        virtual api
        define the node update method, update the internal state from input
        '''

class InputNode(HardwareNode):

    def __init__(self, name, data_port_name, valid_port_name, ren_port_name, size=1):
        self.data_port_name = data_port_name
        self.valid_port_name = valid_port_name
        self.ren_port_name = ren_port_name
        super().__init__(name, [], [HardwarePort(name+"."+"datain", [0]*size),
                                    HardwarePort(name+".in_en", False),
                                    HardwarePort(name+".ren", False)])
        self.output_port["datain"].key = self.data_port_name
        self.output_port["in_en"].key = self.valid_port_name
        self.output_port["ren"].key = self.ren_port_name

    def update(self, datain_val, in_en_val):
        self.output_port["datain"].val = datain_val
        self.output_port["in_en"].val = in_en_val

class OutputValidNode(HardwareNode):
    def __init__(self, node_name, port_name, size=1):
        self.port_name = port_name
        super().__init__(node_name, [HardwarePort(node_name+"."+port_name, [False]*size)], [])

    def getval(self):
        return self.input_port

    def connectNode(self, node):
        connection_dict = {}
        if type(node) == BufferNode:
            self.input_port[self.port_name].makePred(node.output_port["valid"])
            node.output_port["valid"].addSucc(self.input_port[self.port_name])
            connection_dict[(self.input_port[self.port_name].key, node.output_port["valid"].key)] = \
                HardwareWire(self.input_port[self.port_name], node.output_port["valid"])
            #FIXME: name is repeated so, do not add node connection for output va;ld
        elif type(node) == ValidGenNode:
            #connect with the ult out port
            self.input_port[self.port_name].makePred(node.output_port["out"])
            connection_dict[(self.input_port[self.port_name].key, node.output_port["out"].key)] = \
                HardwareWire(self.input_port[self.port_name], node.output_port["out"])
        return connection_dict

class OutputNode(HardwareNode):

    def __init__(self, node_name, port_name, size=1):
        self.port_name = port_name
        super().__init__(node_name, [HardwarePort(node_name+"."+port_name, [0]*size)], [])

    def getval(self):
        return self.input_port

    def connectNode(self, node, port_id=0):
        connection_dict = {}
        if type(node) == BufferNode:
            self.input_port[self.port_name].makePred(node.output_port["dataout0"])
            node.output_port["dataout0"].addSucc(self.input_port[self.port_name])
            connection_dict[(self.input_port[self.port_name].key, node.output_port["dataout0"].key)] = \
                HardwareWire(self.input_port[self.port_name], node.output_port["dataout0"])
            self.makePred( node)
            node.addSucc(self, port_id)
        elif type(node) == InputNode:
            self.input_port[self.port_name].makePred(node.output_port["datain"])
            node.output_port["datain"].addSucc(self.input_port[self.port_name])
            connection_dict[(self.input_port[self.port_name].key, node.data_port_name)] = \
                HardwareWire(self.input_port[self.port_name], node.output_port["datain"])
            self.makePred( node)
            node.addSucc(self)
        return connection_dict


class ValidGenNode(HardwareNode):
    def __init__(self, name, stencil_width, iter_cnt):
        self.stencil_width = stencil_width
        self.iter_cnt = iter_cnt
        input_list = []
        output_list = []
        input_list.append(HardwarePort(name+"_counter.en", 0))
        output_list.append(HardwarePort(name+"_ult.out", 0))
        super().__init__(name, input_list, output_list)
        self.contain_node = True

    def update(self):
        pass

    def connectNode(self, node_pred):
        connection_dict = {}
        if type(node_pred) == BufferNode:
            connection_dict[self.input_port["en"].key, node_pred.output_port["valid"].key] = \
                HardwareWire(self.input_port["en"].key, node_pred.output_port["valid"])
        elif type(node_pred) == InputNode:
            connection_dict[self.input_port["en"].key, node_pred.output_port["in_en"].key] = \
                HardwareWire(self.input_port["en"].key, node_pred.output_port["in_en"])
        else:
            assert False, "can only connect to buffernode"
        return connection_dict

    def dump_json(self):
        node = {}
        dummy_connection = []
        input_counter = {}
        input_counter["genref"] = "commonlib.counter"
        input_counter["genargs"] = {"width": ["Int", 16], "min": ["Int", 0], "max": ["Int", self.iter_cnt], "inc": ["Int", 1]}
        node[self.name+"_counter"] = input_counter

        ult_cmp = {}
        ult_cmp["genref"] = "coreir.ult"
        ult_cmp["genargs"] = {"width": ["Int", 16]}
        node[self.name+"_ult"] = ult_cmp

        value = {}
        value["genref"] = "coreir.const"
        value["genargs"] = {"width": ["Int", 16]}
        #TODO: not work with large stencil width, but may be ok for reg
        value["modargs"] = {"value":[["BitVector", 16], "16'h000"+str(self.stencil_width)]}
        node[self.name+"_value_"+str(self.stencil_width)] = value

        dummy_connection.append([self.name+"_value_"+str(self.stencil_width)+".out", self.name+"_ult"+".in1"])
        dummy_connection.append([self.name+"_counter.out", self.name+"_ult"+".in0"])
        dummy_connection.append([self.name+"_counter.reset", "self.reset"])

        return node, dummy_connection

class NAndNode(HardwareNode):
    def __init__(self, name, num_input):
        input_list =[]
        output_list = []
        for i in num_input:
            input_list.append(HardwarePort(name+".in"+str(i), 0))
        output_list.append(HardwarePort(name+".out", 0))
        super().__init__(name, input_list, output_list)

    def update(self):
        pass

    def connectInput(self, node_list):
        for node in node_list:
            node.addSucc(self)



class SelectorNode(HardwareNode):
    def __init__(self, name, total_bank, bank_per_dim, capacity_per_dim):
        #TODO kernel of bank selector not implemented
        self.bank_num = total_bank
        self.bank_per_dim = bank_per_dim
        self.capacity_per_dim = capacity_per_dim
        input_list = []
        output_list = []
        input_list.append(HardwarePort(name+"_counter.en", 0))
        #input_list.append(HardwarePort(name+"_mux.in1", 0))
        for bank in range(total_bank):
            output_list.append(HardwarePort(name+"_mux_"+str(bank)+".out."+str(bank), 0))
        super().__init__(name, input_list, output_list)
        #TODO: hack to add port
        for bank in range(total_bank):
            self.input_port["mux_in"+str(bank)] = HardwarePort(name+"_mux_" +str(bank)+".in1", 0)
        self.contain_node = True

    def update(self):
        pass

    def connectNode(self, node):
        if type(node) != InputNode:
            assert True ,"can only connect to input enable!"
        connection_dict = {}
        for bank in range(self.bank_num):
            connection_dict[(self.input_port["mux_in"+str(bank)].key, node.output_port["in_en"].key)] = \
                HardwareWire(self.input_port["mux_in"+str(bank)], node.output_port["in_en"])
        connection_dict[(self.input_port["en"].key, node.output_port["in_en"].key)] = \
            HardwareWire(self.input_port["en"], node.output_port["in_en"])
        return connection_dict

    def connectOutput(self, output_node_list):
        connection_dict = {}
        for bank_id, output_node in enumerate(output_node_list):
            out_port = output_node.input_port["wen"]
            connection_dict[(out_port.key, self.output_port["out."+str(bank_id)].key.rsplit(".",1)[0])] = \
                HardwareWire(out_port, self.output_port["out."+str(bank_id)])
        return connection_dict


    def dump_json(self):
        node = {}
        dummy_connection = []

        invalid_bit = {}
        invalid_bit["modref"] = "corebit.const"
        invalid_bit["modargs"] = {"value": ["Bool", False]}
        node[self.name+"_invalidbit"] = invalid_bit
        bank_dim = 0

        for idx, (bank_in_dim, capacity_in_dim) in enumerate(zip(self.bank_per_dim, self.capacity_per_dim)):
            bank_dim += 1
            if bank_in_dim == 1 :
                continue

            input_counter = {}
            input_counter["genref"] = "commonlib.counter"
            input_counter["genargs"] = {"width": ["Int", 16], "min": ["Int", 0], "max": ["Int", bank_in_dim], "inc":["Int", 1]}
            node[self.name+"_counter_"+str(idx)] = input_counter

            if idx > 0:
                #add base counter
                input_counter = {}
                input_counter["genref"] = "commonlib.counter"
                input_counter["genargs"] = {"width": ["Int", 16], "min": ["Int", 0], "max": ["Int", self.capacity_per_dim[idx-1]], "inc":["Int", 1]}
                node[self.name+"_counter_base_"+str(idx)] = input_counter

                #add another input port
                self.input_port["base_en"] = HardwarePort(self.name+"_counter_base_"+str(idx)+".en", 0)

                #add reset to the previous counter
                dummy_connection.append([self.name+"_counter_"+str(idx-1)+".reset",
                                         self.name+"_counter_base_"+str(idx)+".overflow"])
                dummy_connection.append([self.name+"_counter_"+str(idx)+".en",
                                         self.name+"_counterbase_"+str(idx)+".overflow"])

            for i in range(bank_in_dim):
                eq = {}
                eq["genref"] = "coreir.eq"
                eq["genargs"] = {"width": ["Int", 16]}
                node[self.name+"_eq_"+str(idx)+"_"+str(i)] = eq


                value = {}
                value["genref"] = "coreir.const"
                value["genargs"] = {"width": ["Int", 16]}
                value["modargs"] = {"value":[["BitVector", 16], "16'h000"+str(i)]}
                node[self.name+"_value_"+str(idx) + "_" + str(i)] = value
                dummy_connection.append([self.name+"_value_"+str(idx)+"_"+str(i)+".out",
                                         self.name+"_eq_"+str(idx)+"_"+str(i)+".in1"])
                dummy_connection.append([self.name+"_counter"+str(idx)+".out",
                                         self.name+"_eq_"+str(idx)+"_"+str(i)+".in0"])

        cur_port = 0
        for dim, bank_in_dim in enumerate(self.bank_per_dim):
            for i in range(bank_in_dim):
                mux = {}
                mux["modref"] = "corebit.mux"
                node[self.name+"_mux_" + str(dim) + "_" + str(i)] = mux

                if bank_dim > 1:
                    _and = {}
                    _and["modref"] = "corebit.and"
                    node[self.name+"_and_" + str(dim) + "_" + str(i)] = _and
                    index = [i, dim]
                    for idx in range(len(self.bank_per_dim)):
                        dummy_connection.append([self.name+"_and_"+str(dim)+"_"+str(i)+".in"+str(idx),
                                                  self.name+"_eq_"+str(idx)+"_"+str(index[idx])+".out"])
                    dummy_connection.append([self.name+"_and_"+str(dim)+"_"+str(i)+".out",
                                             self.name+"_mux_"+str(cur_port)+".sel"])
                    dummy_connection.append([self.name+"_invalidbit.out", self.name+"_mux_"+str(cur_port)+".in0"])
                    cur_port+=1


                else:
                    dummy_connection.append([self.name+"_invalidbit.out", self.name+"_mux_"+str(i)+".in0"])
                    dummy_connection.append([self.name+"_eq_"+str(cur_port)+".out", self.name+"_mux_"+str(i)+".sel"])


        return node, dummy_connection




class RegNode(HardwareNode):
    def __init__(self, name, virtualbuffer: VirtualBuffer):
        input_list = []
        output_list = []
        input_list.append(HardwarePort(name+".in", [0]*virtualbuffer._input_port))
        output_list.append(HardwarePort(name+".out", [0]*virtualbuffer._output_port))
        super().__init__(name, input_list, output_list)
        self.kernel = virtualbuffer

    def update(self):
        stencil_valid, read_valid, dataout = self.kernel.read()
        self.output_port["out"].val = dataout
        write_valid = True
        data = self.input_port["in"].val
        self.kernel.write(write_valid, data)

    def dump_json(self):
        mem_tile = {}
        mem_tile["genref"] = "coreir.reg"
        args = {"width": ["Int", 16]}
        mem_tile["genargs"] = args
        mem_tile["modargs"] = {"clk_posedge": ["Bool", True], "init": [["BitVector", 16], "16'hxxxx"]}

        #TODO: add dummy node clk

        return mem_tile

    def connect(self, substitue_node, connection_dict):
        #FIXME: hack for stencil valid
        self.stencil_delay = substitue_node.stencil_delay
        self.counter_bound = substitue_node.counter_bound
        '''
        Get input connected from original node
        '''
        #update the node connection
        pred_node = substitue_node.pred
        if pred_node:
            self.makePred(pred_node)
            self.pred.removeSucc(substitue_node)
            self.pred.addSucc(self)
        for succ in substitue_node.succ[0]:
            self.addSucc(succ)
            succ.makePred(self)

        #remove the flush connection, reset, add clk signal
        connection_dict.pop(("self.reset", substitue_node.name + ".reset"))
        #connection_dict[(self.name+".clk", "self.clk")] = DummyWire("self.clk", self.name+".clk")

        #update the output path connection
        predecesor = substitue_node.input_port["datain0"].pred
        self.input_port["in"].makePred(predecesor)
        predecesor.removeSucc(substitue_node.input_port["datain0"])
        connection_dict[(self.input_port["in"].key, predecesor.key)] = HardwareWire(self.input_port["in"], predecesor)
        connection_dict.pop((substitue_node.input_port["datain0"].key, predecesor.key))

        #delete the control path connection
        predecesor = substitue_node.input_port["wen"].pred
        #chances are predecesor has already been removed
        if predecesor:
            predecesor.removeSucc(substitue_node.input_port["wen"])
            connection_dict.pop((substitue_node.input_port["wen"].key, predecesor.key))
        predecesor = substitue_node.input_port["ren"].pred
        if predecesor:
            predecesor.removeSucc(substitue_node.input_port["ren"])
            connection_dict.pop((substitue_node.input_port["ren"].key, predecesor.key))

        #update the out data path connection
        for succ in substitue_node.output_port["dataout0"].succ:
            self.output_port["out"].addSucc(succ)
            succ.makePred(self.output_port["out"])
            connection_dict.pop((succ.key, substitue_node.output_port["dataout0"].key))
            connection_dict[(succ.key, self.output_port["out"].key)] = HardwareWire(succ, self.output_port["out"])

        for succ in substitue_node.output_port["valid"].succ:
            succ.removePred()
            connection_dict.pop((succ.key, substitue_node.output_port["valid"].key))

class BufferNode(HardwareNode):
    def __init__(self, name, virtualbuffer: VirtualBuffer, child_read_delay=0, num_bank = 1, bank_id = 0):
        #self.input_bank_select = [False, num_bank, bank_id]
        #self.output_bank_select = [False, num_bank, bank_id]
        #if num_bank > 1:
        #    virtualbuffer = self.initBanking(name, virtualbuffer, num_bank)
        self.last_in_chain = False

        #a temporary solution for different memory tile definition
        self.child_read_delay = child_read_delay

        input_list = []
        output_list = []
        input_list.append(HardwarePort(name+".datain0", [0]*virtualbuffer._input_port))
        input_list.append(HardwarePort(name+".wen", False))
        input_list.append(HardwarePort(name+".ren", False))
        output_list.append(HardwarePort(name+".dataout0", [0]*virtualbuffer._output_port))
        output_list.append(HardwarePort(name+".valid", False))
        output_list.append(HardwarePort(name+".stencil_valid", False))
        super().__init__(name, input_list, output_list)
        self.kernel = virtualbuffer
        self.stencil_delay = 0

    def setStencilConfig(self, counter_bound, fifo_depth):
        self.stencil_delay = fifo_depth
        self.counter_bound = counter_bound

    def assertLastOfChain(self):
        self.last_in_chain = True

    def initBanking(self, name, virtualbuffer, num_bank, ):
        kernel_for_bank = copy.deepcopy(virtualbuffer)

        def sliceAccessIter(access_pattern: AccessIter, num_bank, num_port, bank_id):
            '''
            method that recreate a new access pattern for banked buffer
            '''

            if num_port >= num_bank:
                #normal situation
                bank_per_dim = [0]*len(access_pattern._st)
                bank_stride = []
                bank_assign = 1
                bank_remain = num_bank
                #TODO: only support 2D down sample
                for idx, st_in_dim in enumerate(access_pattern._st):
                    if st_in_dim >= num_bank:
                        #assert st_in_dim % num_bank == 0, "stride is not divisible by number of bank"
                        bank_stride.append(st_in_dim // num_bank)
                        bank_assign = num_bank
                        bank_per_dim[idx] =  bank_remain
                        bank_remain = 1
                    else:
                        bank_stride.append(1)
                        bank_assign =  bank_assign * st_in_dim
                        bank_remain = bank_remain // st_in_dim
                        bank_per_dim[idx] = st_in_dim


                bank_start = [access_pattern._start[bank_id]]
                bank_range = [rng for rng in access_pattern._rng]
                return False, bank_per_dim, AccessIter(bank_range, bank_stride, bank_start)
            else:
                #need add bank selector
                bank_stride = []
                for st_in_dim in access_pattern._st:
                    if st_in_dim >= num_bank:
                        assert st_in_dim % num_bank == 0, "stride is not divisible by number of bank"
                        bank_stride.append(st_in_dim // num_bank)
                    else:
                        bank_stride.append(st_in_dim)
                bank_start = access_pattern._start[0:num_port]
                bank_range = [rng for rng in access_pattern._rng]
                bank_range[0] = bank_range[0] // num_bank
                return True, [], AccessIter(bank_range, bank_stride, bank_start)


        #update the read write iterator
        need_read_select, bank_per_dim, kernel_for_bank.read_iterator = sliceAccessIter(virtualbuffer.read_iterator, num_bank, kernel_for_bank._output_port, self.output_bank_select[2])
        need_write_select, _, kernel_for_bank.write_iterator = sliceAccessIter(virtualbuffer.write_iterator, num_bank, kernel_for_bank._input_port, self.input_bank_select[2])
        self.input_bank_select[0] = need_write_select
        self.output_bank_select[0] = need_read_select
        self.bank_in_dim = bank_per_dim

        #update port and capacity
        #FIXME: possible bug, ohter line buffer hyper parameter may need changing
        kernel_for_bank._capacity = virtualbuffer._capacity // num_bank
        if need_write_select == False:
            kernel_for_bank._input_port = virtualbuffer._input_port // num_bank
        if need_read_select == False:
            kernel_for_bank._output_port = virtualbuffer._output_port // num_bank

        return kernel_for_bank


    def update(self):
        stencil_valid, read_valid, dataout = self.kernel.read()
        self.output_port["dataout0"].val = dataout
        self.output_port["valid"].val = read_valid
        self.output_port["stencil_valid"].val = stencil_valid
        write_valid = self.input_port["wen"].val
        data = self.input_port["datain0"].val
        self.kernel.write(write_valid, data)

    def dump_json(self):
        '''
        create the json file instance dictionary for CoreIR and return
        '''
        mem_tile = {}
        mem_tile["genref"] = "lakelib.unified_buffer"
        args = {}
        args["width"] = ["Int", 16]
        args["depth"] = ["Int", self.kernel._capacity]
        args["logical_size"] = ["Json", {"capacity": [self.kernel._capacity]}]
        args["rate_matched"] = ["Bool", type(self.kernel) == VirtualRowBuffer]
        dimension = len(self.kernel.read_iterator._rng)
        args["dimensionality"] = ["Int", dimension]
        if type(self.kernel) == VirtualRowBuffer:
            args["iter_cnt"] = ["Int", self.kernel._capacity]
        else:
            total_iter_cnt = reduce(lambda x, y: x*y, self.kernel.read_iterator._rng)
            args["iter_cnt"] = ["Int", total_iter_cnt]
        if self.last_in_chain == False or type(self.kernel) != VirtualRowBuffer:
            args["stencil_width"] = ["Int", 0]
        else:
            args["stencil_width"] = ["Int", self.child_read_delay+1]

        for idx in range(len(self.kernel.read_iterator._st)):
            args["stride_" + str(idx)] = ["Int", self.kernel.read_iterator._st[idx]]
            if type(self.kernel) == VirtualRowBuffer:
                args["range_" + str(idx)] = ["Int", self.kernel._capacity]
            else:
                args["range_" + str(idx)] = ["Int", self.kernel.read_iterator._rng[idx]]
        for idx in range(len(self.kernel.write_iterator._st)):
            args["input_stride_" + str(idx)] = ["Int", self.kernel.write_iterator._st[idx]]
            if type(self.kernel) == VirtualRowBuffer:
                args["input_range_" + str(idx)] = ["Int", self.kernel._capacity]
            else:
                args["input_range_" + str(idx)] = ["Int", self.kernel.write_iterator._rng[idx]]
        #TODO: add chainning
        args["chain_en"] = ["Bool", self.kernel._chain_en]
        args["chain_idx"] = ["Int", self.kernel._chain_id]
        args["output_starting_addrs"] = ["Json", {"output_start": self.kernel.read_iterator._start}]
        mem_tile["genargs"] = args

        #TODO: add dummy node flush

        return mem_tile

    def connectInput(self, data_in, valid, ren, data_key, valid_key, ren_key, data_only):
        '''
        connecting method to wire input with buffer
        '''
        connection_dict = {}
        if data_only == False:
            self.input_port["wen"].makePred(valid)
            self.input_port["ren"].makePred(ren)
            valid.addSucc(self.input_port["wen"])
            ren.addSucc(self.input_port["ren"])
            connection_dict[(self.input_port["wen"].key, valid_key)] = \
                HardwareWire(self.input_port["wen"], valid)
            connection_dict[(self.input_port["ren"].key, ren_key)] = \
                HardwareWire(self.input_port["ren"], ren)
        self.input_port["datain0"].makePred(data_in)
        data_in.addSucc(self.input_port["datain0"])
        connection_dict[(self.input_port["datain0"].key, data_key)] = \
            HardwareWire(self.input_port["datain0"], data_in)
        return connection_dict

    def connectNode(self, node, bank_idx = 0, data_only = False):
        '''
        method connect buffer with predecessor buffer
        data_only flag is added for banked buffer need bank selector
        '''
        if type(node) == BufferNode:
            connection_dict = {}
            self.input_port["wen"].makePred(node.output_port["valid"])
            self.input_port["ren"].makePred(node.output_port["valid"])
            self.input_port["datain0"].makePred(node.output_port["dataout0"])
            node.output_port["valid"].addSucc(self.input_port["wen"])
            node.output_port["valid"].addSucc(self.input_port["ren"])
            node.output_port["dataout0"].addSucc(self.input_port["datain0"])
            connection_dict[(self.input_port["wen"].key, node.output_port["valid"].key)] = \
                HardwareWire(self.input_port["wen"], node.output_port["valid"])
            connection_dict[(self.input_port["ren"].key, node.output_port["valid"].key)] = \
                HardwareWire(self.input_port["ren"], node.output_port["valid"])
            connection_dict[(self.input_port["datain0"].key, node.output_port["dataout0"].key)] = \
                HardwareWire(self.input_port["datain0"], node.output_port["dataout0"])

        elif type(node) == InputNode:
            connection_dict = self.connectInput(node.output_port["datain"], node.output_port["in_en"], node.output_port["ren"], node.data_port_name, node.valid_port_name, node.ren_port_name, data_only)

        #dummy connection not in data path
        connection_dict[("self.reset", self.name+".reset")] = \
            DummyWire("self.reset", self.name+".reset")
        self.makePred(node)
        node.addSucc(self, bank_idx)
        return connection_dict



class HardwareWire:
    '''
    class for funcitonal model connection
    '''
    def __init__(self, _pred, _succ):
        #pred and succ is a tuple with key and value
        self.pred = _pred
        self.succ = _succ

    def propagate(self):
        self.succ.val = self.pred.val

    def isLinkedTo(self, name):
        return (name == self.pred.key.split(".")[0]) or (name == self.succ.key.split(".")[0])

class DummyWire(HardwareWire):
    '''
    class for the non datapath propagrate wire, like clk flush
    '''
    def __init__(self, _pred_name:str, _succ_name: str):
        self.pred = _pred_name
        self.succ = _succ_name

    def propageate(self):
        #do nothing
        pass

    def isLinkedTo(self, name):
        #only check the succ node name
        return (name == self.succ.split(".")[0])


class BankedChainedMemoryTile:
    '''
    class wrap on Chained Memory Tile, use multiple parallel bank to increase the bandwidth
    '''
    def __init__(self, chained_mem_tile, num_bank, in_port, out_port):
        #create a list to save all the chained memory_tile
        self.banked_mem_tile = []
        for _ in range(num_bank):
            self.banked_mem_tile.append(copy.deepcopy(chained_mem_tile))
        self._num_bank = num_bank
        self._in_port_per_bank = chained_mem_tile._input_port
        self._out_port_per_bank = chained_mem_tile._output_port
        self._in_port = in_port
        self._out_port = out_port

        self.write_counter = Counter(self._num_bank // self._in_port)
        self.read_counter = Counter(self._num_bank // self._out_port)

    def dump_json(self)->dict:
        mem_bank = {}
        for idx, mem_chain in enumerate(self.banked_mem_tile):
            mem_bank["mem_bankid_"+str(idx)] = mem_chain.dump_json()
        return mem_bank

    def read(self):
        out_data_chain = []
        start_bank = self.read_counter.read() * self._out_port
        end_bank = (self.read_counter.read() + 1 ) * self._out_port
        for bank in self.banked_mem_tile[start_bank: end_bank]:
            out_data_chain.extend(bank.read())
        self.read_counter.update()
        return out_data_chain


    def write(self, data):
        start_bank = self.write_counter.read() * self._in_port
        end_bank = (self.write_counter.read() + 1 ) * self._in_port
        for bank_id, bank in enumerate(self.banked_mem_tile[start_bank: end_bank]):
            #TODO: currently only support contigous write pattern
            start = bank_id * self._in_port_per_bank
            end = (bank_id + 1) * self._in_port_per_bank
            bank.write(data[start: end])
        self.write_counter.update()

    def write_bank(self, data, bank_no):
        '''
        helper function to write a portion of bank in case of virtual in port is not equal to out port
        '''
        assert  bank_no < self._num_bank, "write bank exceeded the total bank amount!\n"
        self.banked_mem_tile[bank_no].write(data)

    def write_partial(self, data):
        '''
        Write function if in port less than out port
        '''
        pass

    def read_bank(self, bank_no):
        '''
        helper function for reading a portion of banks
        '''
        assert bank_no < self._num_bank, "read bank exceeded the total bank amount!\n"
        data = self.banked_mem_tile[bank_no].read()
        return data

class ChainedMemoryTile:
    '''
    class wrap on memory tile, chain for larger capacity
    '''
    def __init__(self, mem_tile_list):
        self._mem_tile_chain = mem_tile_list
        self._input_port = mem_tile_list[0]._input_port
        self._output_port = mem_tile_list[0]._output_port

    def dump_json(self)->dict:
        mem_chain = {}
        for idx, mem_tile in enumerate(self._mem_tile_chain):
            mem_tile_config = mem_tile.dump_json()
            mem_tile_config.update({'chain_idx':  NoIndent(['int', idx])})
            mem_chain["mem_chainid" + str(idx)] = mem_tile_config

        return mem_chain

    def read(self):
        '''
        This should be a mux in the CGRA with valid signal from memory tile as control
        '''
        valid_tile_id = -1
        out_data = 0
        for idx, mem_tile in enumerate(self._mem_tile_chain):
            #read all memory tile, to update the iterator
            read_valid, out_data_tmp = mem_tile.read()
            if read_valid:
                out_data = out_data_tmp
                assert valid_tile_id == -1, \
                    "Multiple valid tile in the chain available, check chaining mapping algorithm!\n"
                valid_tile_id = idx
        return out_data

    def write(self, data):
        '''
        data will be broad cast to different tile,
        only the bank with write valid can be written
        '''
        valid_tile_id = -1
        for idx, mem_tile in enumerate(self._mem_tile_chain):
            write_success= mem_tile.write(data)

            #debug: to see if there is multiple valid tile to write
            if write_success:
                assert valid_tile_id == -1,\
                    "Multiple valid tile in the chain available, check chaining mapping algorithm!\n"
                valid_tile_id = idx
                #print ("valide id = ", idx)
        assert valid_tile_id != -1, "No valid tile to write."


class MemoryTile(VirtualDoubleBuffer):
    '''
    memory tile functional model
    has the valid signal for chaining
    '''
    #FIXME mem_tile_config should be only one, not share by all mem_tile
    def __init__(self, mem_tile_config, read_access_pattern, start_addr, end_addr, chain_capacity, manual_switch=0):
        super().__init__(mem_tile_config._input_port,
                         mem_tile_config._output_port,
                         mem_tile_config._capacity,
                         read_access_pattern._rng,
                         read_access_pattern._st,
                         read_access_pattern._start,
                         manual_switch)
        #overwrite the write iterator
        #FIXME Possible bug if input port not equals output_port
        self.write_iterator = AccessIter([int(chain_capacity / self._input_port)],
                                         [1],
                                         list(range(self._input_port)),
                                         manual_switch)

        #control signal tell if we read the valid signal
        self.addr_domain = [start_addr, end_addr]
        self.read_val = 0
        self.write_val = 0

    def dump_json(self)->dict:
        '''
        Method to dump a diction into json
        '''
        mem_tile = {}
        dimension = len(self.read_iterator._rng)
        mem_tile['dimensionality'] = NoIndent(['int', dimension])
        for idx in range(dimension):
            mem_tile['stride_'+str(idx)] = NoIndent(['int', self.read_iterator._st[idx]])
            mem_tile['range_'+str(idx)] = NoIndent(['int', self.read_iterator._rng[idx]])
        #TODO: not hardcode if we are going to support line buffer
        mem_tile['depth'] = NoIndent(['int', 0])
        mem_tile['mode'] = NoIndent(['int', 3]) # DB is mode = 3
        mem_tile['tile_en'] = NoIndent(['bool', 1])
        mem_tile['rate_matched'] = NoIndent(['bool', 0])
        mem_tile['stencil_width'] = NoIndent(['int', 0])
        mem_tile['iter_cnt'] = NoIndent(['int', reduce((lambda x, y: x * y), self.read_iterator._rng)])
        return mem_tile

    def read(self):
        '''
        return the read data with valid signal
        wrapper the super class read method
        return type: valid, data_out
        '''
        if self.read_iterator._addr[0] >= self.addr_domain[0] and\
                self.read_iterator._addr[-1] < self.addr_domain[1]:
            self.read_val = 1
        else:
            self.read_val = 0

        if self.read_val:
            data_out = super().read(self.addr_domain[0])
        else:
            self.read_iterator.update()
            self.check_switch()
            data_out = None

        return self.read_val, data_out

    def write(self, data_in):
        '''
        write the data if signal is valid
        wrap the super class write method
        return type: if write is valid
        '''
        if self.write_iterator._addr[0] >= self.addr_domain[0] and\
                self.write_iterator._addr[-1] < self.addr_domain[1]:
            self.write_val = 1
        else:
            self.write_val = 0

        if self.write_val:
            super().write(data_in, self.addr_domain[0])
        else:
            self.write_iterator.update()
            self.check_switch()


        return self.write_val




