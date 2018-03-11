FROM ubuntu:16.04

ADD . /home/ubuntu/magicicada-client
COPY . /home/ubuntu/magicicada-client
WORKDIR /home/ubuntu/magicicada-client

RUN apt-get update && apt-get install make -y
RUN make clean

RUN useradd -ms /bin/bash ubuntu
RUN chown -R ubuntu:ubuntu /home/ubuntu

USER ubuntu
ENV HOME /home/ubuntu

RUN make bootstrap
RUN make test
