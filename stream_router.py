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
import requests

app = FastAPI()

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

PLAYLIST_PATH = "/opt/hlsp/playlist.m3u"
LOG_FOLDER = "/opt/hlsp"
PLAYLIST_URL = "https://m3u.ch/pl/f4cb98b64c59794f61effac58c5f57d2_7eeb72b1774fb97d1d7d662a7a519788.m3u"

stream_map = {}
last_access = {}

# Загрузка плейлиста с URL
def download_playlist_from_url():
    try:
        r = requests.get(PLAYLIST_URL, timeout=10)
        if r.status_code == 200:
            with open(PLAYLIST_PATH, "w", encoding="utf-8") as f:
                f.write(r.text)
            print("[✓] Плейлист обновлён")
            return True
        else:
            print(f"[!] Ошибка загрузки: HTTP {r.status_code}")
    except Exception as e:
        print(f"[!] Ошибка запроса плейлиста: {e}")
    return False

# Автозагрузка каждые 10 минут
def auto_reload_loop():
    while True:
        if download_playlist_from_url():
            load_stream_map()
        time.sleep(600)

# Загрузка stream_map из файла
def load_stream_map():
    global stream_map
    stream_map = {}
    try:
        with open(PLAYLIST_PATH, "r", encoding="utf-8") as f:
            lines = f.read().splitlines()

        for i in range(0, len(lines), 2):
            if lines[i].startswith("#EXTINF") and i+1 < len(lines):
                url = lines[i+1]
                if "stream=" in url:
                    try:
                        stream_id = url.split("stream=")[1].split("&")[0]
                        name = lines[i].split(",")[-1]
                        stream_map[stream_id] = {
                            "url": url,
                            "name": name
                        }
                    except:
                        continue
    except FileNotFoundError:
        print("[!] playlist.m3u не найден")

# Прокси по ID
@app.get("/stream/{stream_id}.m3u8")
def stream_proxy(stream_id: str):
    if stream_id not in stream_map:
        return Response("Stream not found", status_code=404)

    stream_url = stream_map[stream_id]["url"]

    session_id = stream_id  # сохраняем с ID
    stream_folder = f"/dev/shm/{session_id}"
    os.makedirs(stream_folder, exist_ok=True)

    output_path = f"{stream_folder}/playlist.m3u8"
    log_path = f"{LOG_FOLDER}/log_{session_id}.txt"

    if os.path.exists(output_path):
        last_access[stream_id] = time.time()
        return HTMLResponse(f"/streams/{session_id}/playlist.m3u8")

    cmd = [
        "ffmpeg",
        "-hide_banner", "-loglevel", "error",
        "-i", stream_url,
        "-c", "copy",
        "-f", "hls",
        "-hls_time", "4",
        "-hls_list_size", "5",
        "-hls_flags", "delete_segments",
        output_path
    ]

    def run_ffmpeg():
        with open(log_path, "w") as log_file:
            subprocess.run(cmd, stdout=log_file, stderr=log_file)

    threading.Thread(target=run_ffmpeg, daemon=True).start()
    last_access[stream_id] = time.time()

    return HTMLResponse(f"/streams/{session_id}/playlist.m3u8")

# Скачать плейлист с заменой ссылок на прокси
@app.get("/playlist/download")
def download_playlist():
    result = ["#EXTM3U"]
    for sid, data in stream_map.items():
        name = data["name"]
        result.append(f'#EXTINF:-1 tvg-id="{sid}" group-title="Proxy",{name}')
        result.append(f"http://ldnjeccd.deploy.cx/stream/{sid}.m3u8")
    return Response("\n".join(result), media_type="application/x-mpegURL")

# Отображение админки
@app.get("/admin", response_class=HTMLResponse)
def admin_page(request: Request):
    status = []
    now = time.time()
    for sid, data in stream_map.items():
        last = last_access.get(sid)
        status.append({
            "id": sid,
            "name": data["name"],
            "active": os.path.exists(f"/dev/shm/{sid}/playlist.m3u8"),
            "last": int(now - last) if last else "–"
        })

    return templates.TemplateResponse("admin.html", {"request": request, "status": status})

# Просмотр логов
@app.get("/log/{stream_id}")
def view_log(stream_id: str):
    path = f"{LOG_FOLDER}/log_{stream_id}.txt"
    if os.path.exists(path):
        return FileResponse(path, media_type="text/plain")
    return Response("Log not found", status_code=404)

# Остановка потока
@app.post("/stop/{stream_id}")
def stop_stream(stream_id: str):
    folder = f"/dev/shm/{stream_id}"
    try:
        shutil.rmtree(folder)
    except FileNotFoundError:
        pass
    return Response("Stopped")

# Запускаем
download_playlist_from_url()
load_stream_map()
threading.Thread(target=auto_reload_loop, daemon=True).start()

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=7000)
