
    #!/usr/bin/env python3
    import os
    import time
    import subprocess
    import threading
    from fastapi import FastAPI, Response
    from fastapi.responses import RedirectResponse
    import uvicorn

    app = FastAPI()
    playlist_path = "/opt/hlsp/playlist.m3u"

    with open(playlist_path, "r") as f:
        playlist = [line.strip() for line in f if line.strip().startswith("http")]

    channel_map = {
    "now_hk_sports_4k_1_uhd": 0,
    "fox_uhd_(event_only)": 1,
    "fs_1_4k_uhd_(event_only)": 2,
    "nbc_sports_chicago_4k_uhd_(event_only)": 3,
    "nesn_uhd": 4,
}


    processes = {}
    last_access = {}
    timeout_seconds = 60

    def ffmpeg_running(channel_id: int) -> bool:
        return channel_id in processes and processes[channel_id].poll() is None

    def start_ffmpeg(channel_id: int):
        os.makedirs(f"/dev/shm/{channel_id}", exist_ok=True)
        log_file = open(f"/opt/hlsp/log_{channel_id}.txt", "w")
        cmd = [
            "ffmpeg", "-re", "-i", playlist[channel_id],
            "-c", "copy", "-f", "hls",
            "-hls_time", "3", "-hls_list_size", "5",
            "-hls_flags", "delete_segments+program_date_time",
            "-hls_segment_filename", f"/dev/shm/{channel_id}/segment_%03d.ts",
            f"/dev/shm/{channel_id}/playlist.m3u8"
        ]
        proc = subprocess.Popen(cmd, stdout=log_file, stderr=log_file)
        processes[channel_id] = proc
        last_access[channel_id] = time.time()

    def stop_ffmpeg(channel_id: int):
        proc = processes.get(channel_id)
        if proc and proc.poll() is None:
            proc.terminate()
            proc.wait()
        processes.pop(channel_id, None)
        last_access.pop(channel_id, None)
        os.system(f"rm -rf /dev/shm/{channel_id}")

    def monitor_processes():
        while True:
            time.sleep(10)
            now = time.time()
            for channel_id in list(last_access.keys()):
                if now - last_access[channel_id] > timeout_seconds:
                    stop_ffmpeg(channel_id)

    threading.Thread(target=monitor_processes, daemon=True).start()

    @app.get("/stream/{channel_name}.m3u8")
    async def stream(channel_name: str):
        channel_id = None
        if channel_name.isdigit():
            channel_id = int(channel_name)
        elif channel_name in channel_map:
            channel_id = channel_map[channel_name]
        else:
            return Response("Channel not found", status_code=404)

        if not ffmpeg_running(channel_id):
            start_ffmpeg(channel_id)
        last_access[channel_id] = time.time()
        return RedirectResponse(url=f"/streams/{channel_id}/playlist.m3u8")

    @app.get("/log/{channel_id}")
    async def get_log(channel_id: int):
        path = f"/opt/hlsp/log_{channel_id}.txt"
        if not os.path.exists(path):
            return Response("Log not found", status_code=404)
        with open(path) as f:
            return Response(f.read(), media_type="text/plain")

    if __name__ == "__main__":
        uvicorn.run(app, host="0.0.0.0", port=7000)
