
CC := $(if $(CXX),$(CXX), g++)

INCLUDE_DIR = include
BUILD_DIR = bin
#COREIR_DIR := $(if $(COREIR_DIR),$(COREIR_DIR),/nobackup/joeyliu/aha/coreir)
COREIR_DIR ?= ../../coreir

#COREIR_DIR = /nobackup/joeyliu/aha/coreir
INCLUDE_DIR += $(COREIR_DIR)/include
COREIR_LD_FLAGS = -L$(COREIR_DIR)/lib -Wl,-rpath,$(COREIR_DIR)/lib -lcoreir -lcoreirsim -lcoreir-commonlib

CFLAGS = -Wall -std=c++17 -fpic 
PYCFLAGS = -undefined dynamic_lookup
LDFLGAS = -shared
LDFLGAS += $(COREIR_LD_FLAGS)
FLAGS = $(foreach includedir,$(INCLUDE_DIR),-I$(includedir)) -static-libgcc -static-libstdc++

#pybind flags
PYFLAGS = `python3 -m pybind11 --includes`
PY_LDFLAGS = -L$(BUILD_DIR) -lfuncubuf

SRCS := $(shell find src -name "*.cpp")
TEST_SRCS := $(shell find test -name "*.cpp")
PY_SRCS := $(shell find pybind -name "*.cpp")

#TEST_BINS = $(addprefix $(BUILD_DIR)/,${TEST_SRCS:.cpp=})
TEST_BINS = $(patsubst test/%.cpp, $(BUILD_DIR)/test/%, $(TEST_SRCS))
#OBJS = $(addprefix $(BUILD_DIR)/,${SRCS:.cpp=.o})
OBJS = $(patsubst src/%.cpp, $(BUILD_DIR)/%.o, $(SRCS))

TARGET = $(BUILD_DIR)/libcoreir-lakelib.so
PY_MODULE = $(BUILD_DIR)/ubuf`python3-config\ --extension-suffix`

all:$(TEST_BINS)

$(TEST_BINS): $(BUILD_DIR)/% : %.cpp $(OBJS) $(TARGET)
	@echo $(CXX)
	@mkdir -p $(BUILD_DIR)/test
	$(CC) $^ $(CFLAGS) $(FLAGS) $(COREIR_LD_FLAGS) -o $@ 

$(OBJS): $(BUILD_DIR)/%.o : src/%.cpp include/*.h
	@mkdir -p $(BUILD_DIR)
	$(CC) $(CFLAGS) $(FLAGS) -c $< $(COREIR_LD_FLAGS) -o $@

lib:$(TARGET)

$(TARGET): $(OBJS)
	$(CC) $(FLAGS) $(CFLAGS) $(COREIR_LD_FLAGS) -o $@ $^ $(LDFLGAS)

pybind: $(PY_MODULE)

$(PY_MODULE): $(PY_SRCS) $(TARGET)
	$(CC) -shared $^ $(PYCFLAGS) $(CFLAGS) $(FLAGS) $(PYFLAGS) $(PY_LDFLAGS) -o $@

.PHONY: clean

clean:
	@rm -rf $(BUILD_DIR) core

