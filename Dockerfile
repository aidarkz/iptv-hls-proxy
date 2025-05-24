FROM ubuntu:20.04

EXPOSE 80

ENV DEBIAN_FRONTEND=noninteractive

RUN apt update && apt install -y wget unzip ffmpeg nginx curl python3 python3-pip
RUN pip3 install fastapi uvicorn

RUN mkdir -p /opt/hlsp

# Обновление файлов с отключением кеша
RUN rm -f /etc/nginx/nginx.conf \
 && wget "https://raw.githubusercontent.com/aidarkz/iptv-hls-proxy/main/start.sh?nocache=forced" -O /opt/hlsp/start.sh \
 && wget "https://raw.githubusercontent.com/aidarkz/iptv-hls-proxy/main/nginx.conf?nocache=forced" -O /etc/nginx/nginx.conf \
 && wget "https://raw.githubusercontent.com/aidarkz/iptv-hls-proxy/main/stream_router.py?nocache=forced" -O /opt/hlsp/stream_router.py \
 && wget "https://raw.githubusercontent.com/aidarkz/iptv-hls-proxy/main/playlist.m3u?nocache=forced" -O /opt/hlsp/playlist.m3u \
 && chmod +x /opt/hlsp/start.sh

WORKDIR /opt/hlsp
ENTRYPOINT ["/opt/hlsp/start.sh"]
