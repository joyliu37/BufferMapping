TEST_FILE=./bin/test/test_*
for file in $TEST_FILE ;do
    echo "Run test $file ..."
    ./$file
done
