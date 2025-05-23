#!/bin/bash

# Убедимся, что директория существует
mkdir -p /dev/shm/hls

# Запуск ffmpeg рестриминга
ffmpeg -re -i "http://SOURCE_URL" \
  -c copy \
  -f hls \
  -hls_time 3 \
  -hls_list_size 5 \
  -hls_flags delete_segments+program_date_time \
  -hls_segment_filename /dev/shm/hls/segment_%03d.ts \
  /dev/shm/hls/playlist.m3u8 &

# Запуск nginx
nginx -g "daemon off;"
