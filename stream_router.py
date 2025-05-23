#!/usr/bin/env python3
import os
import subprocess
from fastapi import FastAPI, Response
from fastapi.responses import RedirectResponse
import uvicorn

app = FastAPI()

# Загрузка потоков из плейлиста
with open("/opt/hlsp/playlist.m3u", "r") as f:
    playlist = [line.strip() for line in f if line.strip().startswith("http")]

def ffmpeg_running(channel_id: int) -> bool:
    return os.path.exists(f"/dev/shm/{channel_id}/playlist.m3u8")

def start_ffmpeg(channel_id: int):
    os.makedirs(f"/dev/shm/{channel_id}", exist_ok=True)
    cmd = [
        "ffmpeg", "-re", "-i", playlist[channel_id],
        "-c", "copy", "-f", "hls",
        "-hls_time", "3", "-hls_list_size", "5",
        "-hls_flags", "delete_segments+program_date_time",
        "-hls_segment_filename", f"/dev/shm/{channel_id}/segment_%03d.ts",
        f"/dev/shm/{channel_id}/playlist.m3u8"
    ]
    subprocess.Popen(cmd)

@app.get("/stream/{channel_id}.m3u8")
async def stream(channel_id: int):
    if channel_id < 0 or channel_id >= len(playlist):
        return Response("Channel not found", status_code=404)
    if not ffmpeg_running(channel_id):
        start_ffmpeg(channel_id)
    return RedirectResponse(url=f"/streams/{channel_id}/playlist.m3u8")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=7000)
