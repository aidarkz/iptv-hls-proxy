#!/bin/bash

# Убедимся, что директория существует
mkdir -p /dev/shm/hls

# Запуск ffmpeg рестриминга
ffmpeg -re -i "https://m3u.ch/pl/f4cb98b64c59794f61effac58c5f57d2_7eeb72b1774fb97d1d7d662a7a519788.m3u" \
  -c copy \
  -f hls \
  -hls_time 3 \
  -hls_list_size 5 \
  -hls_flags delete_segments+program_date_time \
  -hls_segment_filename /dev/shm/hls/segment_%03d.ts \
  /dev/shm/hls/playlist.m3u8 &

# Запуск nginx
nginx -g "daemon off;"
