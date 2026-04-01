ARG TARGETPLATFORM=linux/amd64

FROM --platform=$TARGETPLATFORM debian:bookworm-slim AS builder

ARG MTPROXY_REPO=https://github.com/TelegramMessenger/MTProxy
ARG MTPROXY_REF=master

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        ca-certificates \
        git \
        libssl-dev \
        zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /src

RUN git clone --depth 1 --branch "${MTPROXY_REF}" "${MTPROXY_REPO}" mtproxy

WORKDIR /src/mtproxy

RUN make

FROM --platform=$TARGETPLATFORM debian:bookworm-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        iproute2 \
        libssl3 \
        openssl \
        python3 \
        python3-pip \
        zlib1g \
    && python3 -m pip install --break-system-packages --no-cache-dir tdjson \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/mtproxy

COPY --from=builder /src/mtproxy/objs/bin/mtproto-proxy /usr/local/bin/mtproto-proxy
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
COPY stats-ui-server.py /usr/local/bin/stats-ui-server.py
COPY tdlib-proxy-check.py /usr/local/bin/tdlib-proxy-check.py
COPY stats-ui /opt/mtproxy/stats-ui

RUN chmod +x /usr/local/bin/docker-entrypoint.sh /usr/local/bin/stats-ui-server.py /usr/local/bin/tdlib-proxy-check.py

VOLUME ["/data"]

EXPOSE 443 8888 8080

ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
