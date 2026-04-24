# To build directly: docker build --build-arg BASE_IMAGE=ubuntu:24.04 --build-arg CONTAINER_WORKDIR=/mydockerspace .
ARG BASE_IMAGE
FROM $BASE_IMAGE

ARG CONTAINER_WORKDIR
WORKDIR $CONTAINER_WORKDIR

CMD ["bash"]
