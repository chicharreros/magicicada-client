FROM ubuntu:16.04

RUN useradd -ms /bin/bash ubuntu

ADD . /home/ubuntu/magicicada-client
RUN chown -R ubuntu:ubuntu /home/ubuntu
COPY . /home/ubuntu/magicicada-client

USER ubuntu
ENV HOME /home/ubuntu

WORKDIR /home/ubuntu/magicicada-client

RUN make clean
RUN make bootstrap
RUN make test
