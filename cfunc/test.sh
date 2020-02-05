#!/bin/sh
for file in bin/test/test_*; do
    echo "Run test $file ..."
    ./$file
done
