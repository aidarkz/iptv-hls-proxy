#!/usr/bin/env python3
import os, time, subprocess, threading, requests
from fastapi import FastAPI, Request, Response
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
import uvicorn

app = FastAPI()
templates = Jinja2Templates(directory="/opt/hlsp/templates")

PLAYLIST_PATH = "/opt/hlsp/playlist.m3u"
PLAYLIST_SOURCE_URL = "https://m3u.ch/pl/f4cb98b64c59794f61effac58c5f57d2_7eeb72b1774fb97d1d7d662a7a519788.m3u"
UPDATE_INTERVAL = 600  # 10 минут

playlist, channel_map = [], {}
processes, last_access = {}, {}
timeout_seconds = 60

def download_playlist():
    try:
        r = requests.get(PLAYLIST_SOURCE_URL, timeout=10)
        if r.status_code == 200:
            with open(PLAYLIST_PATH, "w", encoding="utf-8") as f:
                f.write(r.text)
            print("✔️ Playlist updated successfully.")
        else:
            print(f"⚠️ Playlist download failed: status {r.status_code}")
    except Exception as e:
        print(f"❌ Playlist update error: {e}")

def load_playlist_and_channels():
    global playlist, channel_map
    playlist, channel_map = [], {}
    name = None
    try:
        with open(PLAYLIST_PATH, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("#EXTINF"):
                    name = line.split('tvg-name="')[1].split('"')[0] if 'tvg-name="' in line else line.split(",")[-1].strip()
                    name = name.lower().replace(" ", "_").replace("/", "_").replace("&", "and")
                elif line.startswith("http"):
                    playlist.append(line)
                    if name:
                        channel_map[name] = len(playlist) - 1
                    name = None
        print(f"📺 Loaded {len(channel_map)} channels.")
    except Exception as e:
        print(f"❌ Failed to load playlist: {e}")

def update_loop():
    while True:
        download_playlist()
        load_playlist_and_channels()
        time.sleep(UPDATE_INTERVAL)

def ffmpeg_running(channel_id):
    return channel_id in processes and processes[channel_id].poll() is None

def start_ffmpeg(channel_id):
    os.makedirs(f"/dev/shm/{channel_id}", exist_ok=True)
    log_path = f"/opt/hlsp/log_{channel_id}.txt"
    log_file = open(log_path, "w")
    stream_url = playlist[channel_id]
    cmd = [
        "ffmpeg", "-re", "-user_agent", "VLC/3.0.18 LibVLC/3.0.18", "-i", stream_url,
        "-c", "copy", "-f", "hls", "-hls_time", "4", "-hls_list_size", "5",
        "-hls_flags", "delete_segments+program_date_time",
        "-hls_segment_filename", f"/dev/shm/{channel_id}/segment_%03d.ts",
        f"/dev/shm/{channel_id}/playlist.m3u8"
    ]
    try:
        proc = subprocess.Popen(cmd, stdout=log_file, stderr=log_file)
        processes[channel_id] = proc
        last_access[channel_id] = time.time()
        print(f"▶️ Started FFmpeg for channel {channel_id}")
    except Exception as e:
        log_file.write(f"❌ Failed to start ffmpeg: {e}\n")
        log_file.close()

def stop_ffmpeg(channel_id):
    proc = processes.get(channel_id)
    if proc and proc.poll() is None:
        proc.terminate()
        proc.wait()
    processes.pop(channel_id, None)
    last_access.pop(channel_id, None)
    os.system(f"rm -rf /dev/shm/{channel_id}")
    print(f"⏹️ Stopped FFmpeg for channel {channel_id}")

def monitor_processes():
    while True:
        time.sleep(10)
        now = time.time()
        for cid in list(last_access.keys()):
            if now - last_access[cid] > timeout_seconds:
                stop_ffmpeg(cid)

@app.get("/stream/{channel}.m3u8")
async def stream(channel: str):
    channel_id = int(channel) if channel.isdigit() else channel_map.get(channel)
    if channel_id is None or channel_id >= len(playlist):
        return Response("❌ Channel not found", status_code=404)
    if not ffmpeg_running(channel_id):
        start_ffmpeg(channel_id)
    last_access[channel_id] = time.time()
    return RedirectResponse(url=f"/streams/{channel_id}/playlist.m3u8")

@app.get("/log/{channel_id}")
async def get_log(channel_id: int):
    path = f"/opt/hlsp/log_{channel_id}.txt"
    if os.path.exists(path):
        with open(path) as f:
            return Response(f.read(), media_type="text/plain")
    return Response("❌ Log not found", status_code=404)

@app.get("/admin")
async def admin(request: Request):
    status = []
    for name, cid in channel_map.items():
        active = ffmpeg_running(cid)
        last = int(time.time() - last_access.get(cid, 0)) if active else "-"
        status.append({"name": name, "id": cid, "active": active, "last": last})
    return templates.TemplateResponse("admin.html", {"request": request, "status": status})

@app.post("/stop/{channel_id}")
async def stop_channel(channel_id: int):
    stop_ffmpeg(channel_id)
    return RedirectResponse("/admin", status_code=303)

if __name__ == "__main__":
    download_playlist()
    load_playlist_and_channels()
    threading.Thread(target=update_loop, daemon=True).start()
    threading.Thread(target=monitor_processes, daemon=True).start()
    uvicorn.run(app, host="0.0.0.0", port=7000)
