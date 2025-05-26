# stream_router.py
from fastapi import FastAPI, Request, Response
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.responses import HTMLResponse
import subprocess
import os
import shutil
import uvicorn
import threading
import time
import uuid

app = FastAPI()

app.mount("/static", StaticFiles(directory="static"), name="static")

# Путь к плейлисту и логам
PLAYLIST_PATH = "/opt/hlsp/playlist.m3u"
LOG_FOLDER = "/opt/hlsp"

# Оригинальные URL по stream_id (можно заменить на загрузку из базы)
stream_map = {}

# Загрузка и парсинг плейлиста в stream_map (при запуске)
def load_stream_map():
    with open(PLAYLIST_PATH, "r", encoding="utf-8") as f:
        lines = f.read().splitlines()

    for i in range(0, len(lines), 2):
        if lines[i].startswith("#EXTINF") and i+1 < len(lines):
            url = lines[i+1]
            if "stream=" in url:
                try:
                    stream_id = url.split("stream=")[1].split("&")[0]
                    stream_map[stream_id] = url
                except IndexError:
                    continue

# Прокси по ID
@app.get("/stream/{stream_id}.m3u8")
def stream_proxy(stream_id: str):
    if stream_id not in stream_map:
        return Response("Stream not found", status_code=404)

    stream_url = stream_map[stream_id]

    session_id = str(uuid.uuid4())[:8]
    stream_folder = f"/dev/shm/{session_id}"
    os.makedirs(stream_folder, exist_ok=True)

    output_path = f"{stream_folder}/playlist.m3u8"
    log_path = f"{LOG_FOLDER}/log_{session_id}.txt"

    cmd = [
        "ffmpeg",
        "-hide_banner", "-loglevel", "error",
        "-i", stream_url,
        "-c", "copy",
        "-f", "hls",
        "-hls_time", "4",
        "-hls_list_size", "5",
        "-hls_flags", "delete_segments",
        f"{output_path}"
    ]

    def run_ffmpeg():
        with open(log_path, "w") as log_file:
            subprocess.run(cmd, stdout=log_file, stderr=log_file)

    threading.Thread(target=run_ffmpeg, daemon=True).start()

    return HTMLResponse(f"<h2>Stream started. HLS path: /streams/{session_id}/playlist.m3u8</h2>")

# Скачать плейлист с заменой на /stream/{id}.m3u8
@app.get("/playlist/download")
def download_playlist():
    if not os.path.exists(PLAYLIST_PATH):
        return Response("Playlist not found", status_code=404)

    result = []
    with open(PLAYLIST_PATH, "r", encoding="utf-8") as f:
        lines = f.read().splitlines()

    for i in range(0, len(lines), 2):
        extinf = lines[i]
        if i+1 < len(lines):
            url = lines[i+1]
            stream_id = ""
            if "stream=" in url:
                try:
                    stream_id = url.split("stream=")[1].split("&")[0]
                    proxy_url = f"http://ldnjeccd.deploy.cx/stream/{stream_id}.m3u8"
                except:
                    proxy_url = url
            else:
                proxy_url = url
            result.append(extinf)
            result.append(proxy_url)

    return Response("\n".join(result), media_type="application/x-mpegURL")

# Запускаем при старте
load_stream_map()

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=7000)
