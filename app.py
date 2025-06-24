from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse, FileResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from pathvalidate import sanitize_filename
from yt_dlp import YoutubeDL
import os
import tempfile
import threading
import asyncio
import subprocess
import uuid
from typing import Dict

app = FastAPI()
templates = Jinja2Templates(directory="templates")

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Global variables to hold download progress and statuses
download_progress = 0
progress_lock = threading.Lock()

# Dictionary to track background downloads
download_tasks: Dict[str, dict] = {}
tasks_lock = threading.Lock()

@app.get("/")
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/video_info")
async def video_info(request: Request):
    data = await request.json()
    video_url = data.get('url')
    if not video_url:
        raise HTTPException(status_code=400, detail="No URL provided")

    ydl_opts = {
        'quiet': True,
        'skip_download': True,
        'format': 'bestaudio/best',
        'noplaylist': True,
    }

    try:
        with YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(video_url, download=False)
            if not info_dict:
                raise HTTPException(status_code=500, detail="Failed to extract video information")

            thumbnail = info_dict.get('thumbnail', '')
            formats = info_dict.get('formats', []) or []
            # Filter formats to include only MP4 extensions
            resolutions = []
            for f in formats:
                if f and isinstance(f, dict):
                    height = f.get('height')
                    ext = f.get('ext')
                    if height and ext == 'mp4' and height >= 144:
                        resolutions.append(height)
            resolutions = sorted(set(resolutions), reverse=True)
            return JSONResponse({
                "thumbnail": thumbnail,
                "resolutions": resolutions,
                "title": info_dict.get('title', 'Unknown Title')
            })
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/download")
async def download(url: str, resolution: int, title: str):
    """Legacy endpoint - redirects to new background processing"""
    # Create a background download task
    download_id = str(uuid.uuid4())

    with tasks_lock:
        download_tasks[download_id] = {
            "status": "processing",
            "progress": 0,
            "file_path": None,
            "error": None
        }

    # Start background download
    threading.Thread(target=background_video_download, args=(download_id, url, title, resolution)).start()

    # Wait for completion and serve file
    while True:
        await asyncio.sleep(1)
        with tasks_lock:
            task = download_tasks[download_id]
            if task["status"] == "ready":
                file_path = task["file_path"]
                break
            elif task["status"] == "error":
                raise HTTPException(status_code=500, detail=task["error"])

    return FileResponse(file_path, media_type="application/octet-stream", filename=os.path.basename(file_path))

def background_video_download(download_id: str, url: str, title: str, resolution: int):
    """Background video download function"""
    def progress_hook(d):
        if d['status'] == 'downloading':
            total_bytes = d.get('total_bytes') or d.get('total_bytes_estimate')
            downloaded_bytes = d.get('downloaded_bytes', 0)
            if total_bytes:
                progress = (downloaded_bytes / total_bytes) * 100
                with tasks_lock:
                    if download_id in download_tasks:
                        download_tasks[download_id]["progress"] = progress

    try:
        temp_dir = tempfile.mkdtemp()
        temp_file_path = os.path.join(temp_dir, 'temp_video.mp4')

        ydl_opts = {
            'outtmpl': temp_file_path,
            'format': f'bestvideo[ext=mp4][height={resolution}]+bestaudio/best[ext=mp4][height={resolution}]',
            'merge_output_format': 'mp4',
            'noplaylist': True,
            'progress_hooks': [progress_hook],
        }

        with YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

        final_file_path = os.path.join(temp_dir, f'{sanitize_filename(title)}_{resolution}p.mp4')
        os.rename(temp_file_path, final_file_path)

        with tasks_lock:
            if download_id in download_tasks:
                download_tasks[download_id].update({
                    "status": "ready",
                    "progress": 100,
                    "file_path": final_file_path
                })

    except Exception as e:
        with tasks_lock:
            if download_id in download_tasks:
                download_tasks[download_id].update({
                    "status": "error",
                    "error": str(e)
                })

def _get_ffmpeg_codec_args(format_type: str):
    """Helper function to get ffmpeg codec arguments"""
    codec_map = {
        'mp3': ['-codec:a', 'libmp3lame', '-b:a', '320k'],
        'ogg': ['-codec:a', 'libvorbis', '-q:a', '10'],
        'aac': ['-codec:a', 'aac', '-b:a', '320k'],
        'wav': ['-codec:a', 'pcm_s16le'],
        'flac': ['-codec:a', 'flac'],
        'm4a': ['-codec:a', 'aac', '-b:a', '320k']
    }
    return codec_map.get(format_type, [])

def background_audio_download(download_id: str, url: str, title: str, format_type: str):
    """Background audio download function"""
    def progress_hook(d):
        if d['status'] == 'downloading':
            total_bytes = d.get('total_bytes') or d.get('total_bytes_estimate')
            downloaded_bytes = d.get('downloaded_bytes', 0)
            if total_bytes:
                progress = (downloaded_bytes / total_bytes) * 50  # Download is 50% of total progress
                with tasks_lock:
                    if download_id in download_tasks:
                        download_tasks[download_id]["progress"] = progress

    try:
        temp_dir = tempfile.mkdtemp()
        temp_file_path = os.path.join(temp_dir, f'temp_audio.{format_type if format_type == "webm" else "webm"}')
        final_file_path = os.path.join(temp_dir, f'{sanitize_filename(title)}.{format_type}')

        ydl_opts = {
            'outtmpl': temp_file_path,
            'format': 'bestaudio/best',
            'noplaylist': True,
            'progress_hooks': [progress_hook],
        }

        with YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

        # Update progress to 50% after download
        with tasks_lock:
            if download_id in download_tasks:
                download_tasks[download_id]["progress"] = 50

        # If the requested format is webm, skip conversion
        if format_type == 'webm':
            os.rename(temp_file_path, final_file_path)
        else:
            # Convert to the desired format using ffmpeg
            ffmpeg_command = ['ffmpeg', '-i', temp_file_path]
            codec_args = _get_ffmpeg_codec_args(format_type)
            ffmpeg_command.extend(codec_args)
            ffmpeg_command.extend([final_file_path])
            subprocess.run(ffmpeg_command, check=True)
            os.remove(temp_file_path)

        with tasks_lock:
            if download_id in download_tasks:
                download_tasks[download_id].update({
                    "status": "ready",
                    "progress": 100,
                    "file_path": final_file_path
                })

    except Exception as e:
        with tasks_lock:
            if download_id in download_tasks:
                download_tasks[download_id].update({
                    "status": "error",
                    "error": str(e)
                })

@app.post("/prepare_download")
async def prepare_download(request: Request):
    data = await request.json()
    url = data.get('url')
    download_type = data.get('type')
    title = data.get('title')

    if not url or not download_type or not title:
        raise HTTPException(status_code=400, detail="Missing required parameters")

    download_id = str(uuid.uuid4())

    # Initialize download task
    with tasks_lock:
        download_tasks[download_id] = {
            "status": "processing",
            "progress": 0,
            "file_path": None,
            "error": None
        }

    # Start background download
    if download_type == "video":
        resolution = data.get('resolution')
        if not resolution:
            raise HTTPException(status_code=400, detail="Resolution required for video downloads")
        threading.Thread(target=background_video_download, args=(download_id, url, title, resolution)).start()
    elif download_type == "audio":
        format_type = data.get('format')
        if not format_type:
            raise HTTPException(status_code=400, detail="Format required for audio downloads")
        threading.Thread(target=background_audio_download, args=(download_id, url, title, format_type)).start()
    else:
        raise HTTPException(status_code=400, detail="Invalid download type")

    return JSONResponse({"download_id": download_id})

@app.get("/download_status/{download_id}")
async def download_status(download_id: str):
    with tasks_lock:
        if download_id not in download_tasks:
            raise HTTPException(status_code=404, detail="Download not found")

        task = download_tasks[download_id].copy()

    return JSONResponse({
        "status": task["status"],
        "progress": task["progress"],
        "error": task.get("error")
    })

@app.get("/get_download/{download_id}")
async def get_download(download_id: str):
    with tasks_lock:
        if download_id not in download_tasks:
            raise HTTPException(status_code=404, detail="Download not found")

        task = download_tasks[download_id]
        if task["status"] != "ready":
            raise HTTPException(status_code=400, detail="Download not ready")

        file_path = task["file_path"]

    if not file_path or not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")

    return FileResponse(file_path, media_type="application/octet-stream", filename=os.path.basename(file_path))

@app.get("/progress")
async def progress():
    """Legacy endpoint - returns progress from most recent download task"""
    with tasks_lock:
        if not download_tasks:
            return JSONResponse({"progress": 0})

        # Return progress from the most recent task
        latest_task = list(download_tasks.values())[-1]
        return JSONResponse({"progress": latest_task.get("progress", 0)})

@app.get("/download_audio")
async def download_audio(url: str, title: str, format: str):
    """Legacy endpoint - redirects to new background processing"""
    # Create a background download task
    download_id = str(uuid.uuid4())

    with tasks_lock:
        download_tasks[download_id] = {
            "status": "processing",
            "progress": 0,
            "file_path": None,
            "error": None
        }

    # Start background download
    threading.Thread(target=background_audio_download, args=(download_id, url, title, format)).start()

    # Wait for completion and serve file
    while True:
        await asyncio.sleep(1)
        with tasks_lock:
            task = download_tasks[download_id]
            if task["status"] == "ready":
                file_path = task["file_path"]
                break
            elif task["status"] == "error":
                raise HTTPException(status_code=500, detail=task["error"])

    return FileResponse(file_path, media_type="application/octet-stream", filename=os.path.basename(file_path))
