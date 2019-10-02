CC = g++

INCLUDE_DIR = include
BUILD_DIR = bin
COREIR_DIR = /nobackup/joeyliu/aha/coreir
INCLUDE_DIR += $(COREIR_DIR)/include
COREIR_LD_FLAGS = -L$(COREIR_DIR)/lib -Wl,-rpath,$(COREIR_DIR)/lib -lcoreir-commonlib -lcoreir -lcoreirsim -lcoreir-float

CFLAGS = -Wall -std=c++11 -fpic
LDFLGAS = -shared
LDFLGAS += $(COREIR_LD_FLAGS)
FLAGS = $(foreach includedir,$(INCLUDE_DIR),-I$(includedir))

SRCS := $(shell find src -name "*.cpp")
TEST_SRCS := $(shell find test -name "*.cpp")

#TEST_BINS = $(addprefix $(BUILD_DIR)/,${TEST_SRCS:.cpp=})
TEST_BINS = $(patsubst test/%.cpp, $(BUILD_DIR)/test/%, $(TEST_SRCS))
#OBJS = $(addprefix $(BUILD_DIR)/,${SRCS:.cpp=.o})
OBJS = $(patsubst src/%.cpp, $(BUILD_DIR)/%.o, $(SRCS))

TARGET = $(BUILD_DIR)/libfuncubuf.so

all:$(TEST_BINS)

$(TEST_BINS): $(BUILD_DIR)/% : %.cpp $(OBJS)
	@mkdir -p $(BUILD_DIR)/test
	$(CC) $^ $(CFLAGS) $(FLAGS) $(COREIR_LD_FLAGS) -o $@ 

$(OBJS): $(BUILD_DIR)/%.o : src/%.cpp include/*.h
	@mkdir -p $(BUILD_DIR)
	$(CC) $(CFLAGS) $(FLAGS) -c $< $(COREIR_LD_FLAGS) -o $@ 

lib:$(TARGET)

$(TARGET): $(BUILD_DIR)/% : $(OBJS)
	$(CC) $(FLAGS) $(CFLAGS) $(COREIR_LD_FLAGS) -o $@ $^ $(LDFLGAS)

.PHONY: clean

clean:
	@rm -rf $(BUILD_DIR) core

