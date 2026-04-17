# syntax=docker/dockerfile:1

FROM nvidia/cuda:12.6.3-cudnn-devel-ubuntu24.04

ARG USERNAME=vscode
ARG USER_UID=1000
ARG USER_GID=1000

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
    bash-completion \
    build-essential \
    ca-certificates \
    curl \
    fish \
    git \
    make \
    pkg-config \
    python3.12 \
    python3.12-dev \
    python3.12-venv \
    python3-pip \
    sudo \
    unzip \
    && rm -rf /var/lib/apt/lists/*

RUN update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.12 1

RUN if ! getent group ${USER_GID} >/dev/null 2>&1; then \
        groupadd --gid ${USER_GID} ${USERNAME}; \
    fi \
    && if ! id -u ${USERNAME} >/dev/null 2>&1; then \
        useradd --uid ${USER_UID} --gid ${USER_GID} -m -o ${USERNAME}; \
    fi \
    && echo "${USERNAME} ALL=(root) NOPASSWD:ALL" > /etc/sudoers.d/${USERNAME} \
    && chmod 0440 /etc/sudoers.d/${USERNAME}

WORKDIR /workspaces
