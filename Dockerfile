FROM frolvlad/alpine-glibc

RUN apk add wget &&  mkdir -p /opt/channel && wget  https://github.com/sjqzhang/ops_channel/releases/download/v1.0.4/CliServer  -O /opt/channel/CliServer && cd /opt/channel/ && chmod +x CliServer 

WORKDIR /opt/channel

ENTRYPOINT ["./CliServer"]

