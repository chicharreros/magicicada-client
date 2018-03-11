FROM ubuntu:16.04

RUN useradd -ms /bin/bash ubuntu

ADD . /home/ubuntu/magicicada-client
RUN chown -R ubuntu:ubuntu /home/ubuntu
COPY . /home/ubuntu/magicicada-client
WORKDIR /home/ubuntu/magicicada-client

RUN apt install make -y
RUN make clean

USER ubuntu
ENV HOME /home/ubuntu

RUN make bootstrap
RUN make test
