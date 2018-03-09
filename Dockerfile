FROM ubuntu:xenial

RUN apt-get update
RUN make clean
RUN make bootstrap
RUN make test
