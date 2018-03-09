FROM ubuntu:16.04

WORKDIR /
ADD . /

RUN make clean
RUN make bootstrap
RUN make test
