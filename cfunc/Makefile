CC = g++

INCLUDE_DIR = include
BUILD_DIR = bin

CFLAGS = -Wall -std=c++11 
LDFLGAS = 
FLAGS = $(foreach includedir,$(INCLUDE_DIR),-I$(includedir))

SRCS := $(shell find src -name "*.cpp")
TEST_SRCS := $(shell find test -name "*.cpp")

#TEST_BINS = $(addprefix $(BUILD_DIR)/,${TEST_SRCS:.cpp=})
TEST_BINS = $(patsubst test/%.cpp, $(BUILD_DIR)/test/%, $(TEST_SRCS))
#OBJS = $(addprefix $(BUILD_DIR)/,${SRCS:.cpp=.o})
OBJS = $(patsubst src/%.cpp, $(BUILD_DIR)/%.o, $(SRCS))

TARGET = demo

all:$(TEST_BINS)

$(TEST_BINS): $(BUILD_DIR)/% : %.cpp $(OBJS)
	@mkdir -p $(BUILD_DIR)/test
	$(CC) $^ $(CFLAGS) $(FLAGS)  -o $@ $(LDFLGAS)

$(OBJS): $(BUILD_DIR)/%.o : src/%.cpp include/*.h
	@mkdir -p $(BUILD_DIR)
	$(CC) $(CFLAGS) $(FLAGS) -c $< -o $@ $(LDFLGAS)

.PHONY: clean

clean:
	@rm -rf $(BUILD_DIR) core

