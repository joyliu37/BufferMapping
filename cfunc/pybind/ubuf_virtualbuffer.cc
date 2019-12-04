#include "virtualbuffer.h"
#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

namespace py = pybind11;

void init_virtualbuffer(py::module &m) {
    auto VirtualBuffer= py::class_<VirtualBuffer>(m, "VirtualBuffer");
    VirtualBuffer.def(py::init<std::vector, std::vector, std::vector,
            std::vector, std::vector, std::vector,
            std::vector, std::vector, std::vector, int>())
        .def("read", &VirtualBuffer::read);
}
