FROM ubuntu:latest

RUN apt update && \
    apt install sudo \
                clang \
                libclang-dev \
                python3-clang \
                python3-pip \
                python3-jinja2 \
                -y
