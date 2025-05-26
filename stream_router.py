# stream_router.py

from fastapi import FastAPI, Request, Response
from fastapi.responses import StreamingResponse, FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import subprocess
import os
import shutil
import uvicorn
import threading
import time
import uuid

app = FastAPI()

# Папка с HTML-шаблонами
templates = Jinja2Templates(directory="/opt/hlsp/templates")

# Пути
PLAYLIST_PATH = "/opt/hlsp/playlist.m3u"
LOG_FOLDER = "/opt/hlsp"

# Хранилище ссылок и состояний
stream_map = {}
stream_status = {}

# Загрузка плейлиста в stream_map
def load_stream_map():
    if not os.path.exists(PLAYLIST_PATH):
        return
    with open(PLAYLIST_PATH, "r", encoding="utf-8") as f:
        lines = f.read().splitlines()
    for i in range(0, len(lines), 2):
        if lines[i].startswith("#EXTINF") and i + 1 < len(lines):
            url = lines[i + 1]
            if "stream=" in url:
                try:
                    stream_id = url.split("stream=")[1].split("&")[0]
                    name = lines[i].split(",")[-1].strip()
                    stream_map[stream_id] = url
                    if stream_id not in stream_status:
                        stream_status[stream_id] = {
                            "name": name,
                            "active": False,
                            "last": None
                        }
                except:
                    continue

# Прокси HLS по stream_id
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
        stream_status[stream_id]["active"] = True
        stream_status[stream_id]["last"] = 0
        with open(log_path, "w") as log_file:
            subprocess.run(cmd, stdout=log_file, stderr=log_file)
        stream_status[stream_id]["active"] = False

    threading.Thread(target=run_ffmpeg, daemon=True).start()

    return HTMLResponse(f"<h2>Stream started. HLS path: /streams/{session_id}/playlist.m3u8</h2>")

# Админка
@app.get("/admin", response_class=HTMLResponse)
def admin(request: Request):
    # обновим last
    for stream_id, info in stream_status.items():
        if info["active"]:
            if info["last"] is None:
                info["last"] = 0
            else:
                info["last"] += 1
    status_list = [
        {"id": sid, "name": s["name"], "active": s["active"], "last": s["last"] or 0}
        for sid, s in stream_status.items()
    ]
    return templates.TemplateResponse("admin.html", {"request": request, "status": status_list})

# Просмотр логов
@app.get("/log/{stream_id}")
def get_log(stream_id: str):
    for fname in os.listdir(LOG_FOLDER):
        if fname.startswith("log_") and fname.endswith(".txt"):
            full_path = os.path.join(LOG_FOLDER, fname)
            with open(full_path, "r") as f:
                if stream_id in f.read():
                    return FileResponse(full_path)
    return Response("Log not found", status_code=404)

# Остановка
@app.post("/stop/{stream_id}")
def stop_stream(stream_id: str):
    # Удаляем сегменты и помечаем как неактивный
    for folder in os.listdir("/dev/shm"):
        if os.path.exists(f"/dev/shm/{folder}/playlist.m3u8"):
            shutil.rmtree(f"/dev/shm/{folder}", ignore_errors=True)
    stream_status[stream_id]["active"] = False
    return Response("Stopped", status_code=200)

# Скачать изменённый плейлист
@app.get("/playlist/download")
def download_playlist():
    if not os.path.exists(PLAYLIST_PATH):
        return Response("Playlist not found", status_code=404)

    result = []
    with open(PLAYLIST_PATH, "r", encoding="utf-8") as f:
        lines = f.read().splitlines()

    for i in range(0, len(lines), 2):
        extinf = lines[i]
        if i + 1 < len(lines):
            url = lines[i + 1]
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

# Запуск
load_stream_map()

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=7000)
