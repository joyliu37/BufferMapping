from ctypes import cdll

lib = cdll.LoadLibrary('../cfunc/bin/libfuncubuf.so')

class AccessPattern(object):
    def __init__(self, _range, _stride, _start):
        self.obj = lib.AccessPattern(_range, _stride, _start)

obj = AccessPattern([16], [1], [0])
