#!/bin/bash
set -eux

mkdir -p /dev/shm
python3 /opt/hlsp/stream_router.py &
nginx -g "daemon off;"
