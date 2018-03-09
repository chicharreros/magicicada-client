FROM ubuntu:16.04

RUN apt-get update && apt-get install -y make

WORKDIR /
ADD . /

RUN make clean
RUN make bootstrap
RUN make test
