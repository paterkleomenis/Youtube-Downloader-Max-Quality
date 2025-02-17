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
import shutil

app = FastAPI()
templates = Jinja2Templates(directory="templates")

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Global variable to hold download progress
download_progress = 0
progress_lock = threading.Lock()

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
            thumbnail = info_dict.get('thumbnail', '')
            formats = info_dict.get('formats', [])
            # Filter formats to include only MP4 extensions
            resolutions = sorted(set(
                f['height'] for f in formats
                if f.get('height') and f.get('ext') == 'mp4' and f['height'] >= 144
            ), reverse=True)
            return JSONResponse({
                "thumbnail": thumbnail,
                "resolutions": resolutions,
                "title": info_dict.get('title', 'Unknown Title')
            })
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Hook function to update download progress
def hook(d):
    global download_progress
    if d['status'] == 'downloading':
        total_bytes = d.get('total_bytes') or d.get('total_bytes_estimate')
        downloaded_bytes = d.get('downloaded_bytes', 0)
        if total_bytes:
            with progress_lock:
                download_progress = (downloaded_bytes / total_bytes) * 100

@app.get("/download")
async def download(url: str, resolution: int, title: str):
    if not url or not resolution or not title:
        raise HTTPException(status_code=400, detail="URL, resolution, or title not provided")

    global download_progress
    download_progress = 0  # Reset progress for new download

    temp_dir = tempfile.mkdtemp()
    temp_file_path = os.path.join(temp_dir, 'temp_video.mp4')

    ydl_opts = {
        'outtmpl': temp_file_path,
        'format': f'bestvideo[ext=mp4][height={resolution}]+bestaudio[ext=m4a]/best[ext=mp4][height={resolution}]',
        'merge_output_format': 'mp4',
        'noplaylist': True,
        'progress_hooks': [hook],  # Hook added for progress tracking
    }

    def download_video():
        try:
            with YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
                final_file_path = os.path.join(temp_dir, f'{sanitize_filename(title)}_{resolution}p.mp4')
                os.rename(temp_file_path, final_file_path)
                return final_file_path
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    loop = asyncio.get_event_loop()
    final_file_path = await loop.run_in_executor(None, download_video)

    return FileResponse(final_file_path, media_type="application/octet-stream", filename=os.path.basename(final_file_path))

@app.get("/progress")
async def progress():
    with progress_lock:
        return JSONResponse({"progress": download_progress})

@app.get("/download_audio")
async def download_audio(url: str, title: str, format: str):
    if not url or not title or not format:
        raise HTTPException(status_code=400, detail="URL, title, or format not provided")

    global download_progress
    download_progress = 0  # Reset progress for new download

    temp_dir = tempfile.mkdtemp()
    temp_file_path = os.path.join(temp_dir, f'temp_audio.{format if format == "webm" else "webm"}')
    final_file_path = os.path.join(temp_dir, f'{sanitize_filename(title)}.{format}')

    ydl_opts = {
        'outtmpl': temp_file_path,
        'format': 'bestaudio/best',
        'noplaylist': True,
        'progress_hooks': [hook],  # Hook added for progress tracking
    }

    def download_and_convert_audio():
        try:
            with YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])

            # If the requested format is the default format, skip conversion
            if format == 'webm':
                return temp_file_path

            # Convert to the desired format using ffmpeg
            ffmpeg_command = ['ffmpeg', '-i', temp_file_path]

            if format == 'mp3':
                ffmpeg_command.extend(['-codec:a', 'libmp3lame', '-b:a', '320k'])
            elif format == 'ogg':
                ffmpeg_command.extend(['-codec:a', 'libvorbis', '-q:a', '10'])
                #ffmpeg_command.extend(['-codec:a', 'libopus', '-b:a', '512k'])
            elif format == 'aac':
                ffmpeg_command.extend(['-codec:a', 'aac', '-b:a', '320k'])
            elif format == 'wav':
                ffmpeg_command.extend(['-codec:a', 'pcm_s16le'])
            elif format == 'flac':
                ffmpeg_command.extend(['-codec:a', 'flac'])
            elif format == 'm4a':
                ffmpeg_command.extend(['-codec:a', 'aac', '-b:a', '320k'])
            ffmpeg_command.extend([final_file_path])

            subprocess.run(ffmpeg_command, check=True)
            os.remove(temp_file_path)  # Clean up the temporary file
            return final_file_path
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    loop = asyncio.get_event_loop()
    final_file_path = await loop.run_in_executor(None, download_and_convert_audio)

    return FileResponse(final_file_path, media_type="application/octet-stream", filename=os.path.basename(final_file_path))

