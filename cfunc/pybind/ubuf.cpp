#include "access.h"
#include "virtualbuffer.h"
#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

namespace py = pybind11;


PYBIND11_MODULE(ubuf, m) {
    py::class_<AccessPattern>(m, "AccessPattern")
        .def(py::init<std::vector<int>, std::vector<int>, std::vector<int> >())
        .def_readwrite("range", &AccessPattern::range)
        .def_readwrite("stride", &AccessPattern::stride)
        .def_readwrite("start", &AccessPattern::stride);

    py::class_<AccessIter>(m, "AccessIter")
        .def(py::init<std::vector<int>, std::vector<int>, std::vector<int> > ())
        .def_property("done", &AccessIter::getDone, &AccessIter::forceDone)
        .def_property_readonly("addr", &AccessIter::getAddr)
        .def_readwrite("acc_pattern", &AccessIter::acc_pattern)
        .def("restart", &AccessIter::restart)
        .def("update", &AccessIter::update)
        .def("getPort", &AccessIter::getPort);

    py::class_<VirtualBuffer<int>>(m, "VirtualBuffer")
        .def(py::init<std::vector<int>, std::vector<int>, std::vector<int>,
            std::vector<int>, std::vector<int>, std::vector<int>,
            std::vector<int>, std::vector<int>, std::vector<int>, int>())
        .def("read", &VirtualBuffer<int>::read);
}

