from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.responses import JSONResponse, FileResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
# Rate limiting imports - optional
try:
    from slowapi import Limiter, _rate_limit_exceeded_handler
    from slowapi.util import get_remote_address
    from slowapi.errors import RateLimitExceeded
    RATE_LIMITING_AVAILABLE = True
except ImportError:
    RATE_LIMITING_AVAILABLE = False
import os
import logging
import asyncio
import threading
import uuid
from typing import Optional, Union

from config import settings
from models import (
    VideoInfoRequest, DownloadRequest, DownloadStatusResponse,
    VideoInfoResponse, DownloadPrepareResponse, ErrorResponse
)
from services import DownloadService, get_download_service

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="YouTube Video/Audio Downloader",
    description="Download videos and audio from YouTube with progress tracking",
    version="2.0.0"
)

# Initialize rate limiter if available
if RATE_LIMITING_AVAILABLE:
    limiter = Limiter(key_func=get_remote_address)
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
else:
    limiter = None

# Initialize templates
templates = Jinja2Templates(directory="templates")

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.on_event("startup")
async def startup_event():
    """Initialize application on startup"""
    logger.info("Starting YouTube Downloader application")
    logger.info(f"Temp directory: {settings.temp_dir}")
    logger.info(f"Max concurrent downloads: {settings.max_concurrent_downloads}")

@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on application shutdown"""
    logger.info("Shutting down YouTube Downloader application")

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Custom HTTP exception handler"""
    return JSONResponse(
        status_code=exc.status_code,
        content=ErrorResponse(
            error=exc.detail,
            error_code=f"HTTP_{exc.status_code}"
        ).dict()
    )

@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """General exception handler"""
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content=ErrorResponse(
            error="Internal server error",
            error_code="INTERNAL_ERROR",
            details={"message": str(exc)} if settings.debug else None
        ).dict()
    )

@app.get("/")
async def index(request: Request):
    """Serve the main page"""
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/api/video_info", response_model=VideoInfoResponse)
async def get_video_info(
    request: Request,
    video_request: VideoInfoRequest,
    download_service: DownloadService = Depends(get_download_service)
):
    """Get video information including available resolutions and formats"""
    try:
        logger.info(f"Getting video info for: {video_request.url}")

        video_info = await download_service.get_video_info(str(video_request.url))

        logger.info(f"Successfully extracted info for: {video_info.title}")
        return video_info

    except Exception as e:
        logger.error(f"Error getting video info: {e}")
        raise HTTPException(
            status_code=400,
            detail=f"Failed to extract video information: {str(e)}"
        )

@app.post("/api/prepare_download", response_model=DownloadPrepareResponse)
async def prepare_download(
    request: Request,
    download_request: DownloadRequest,
    download_service: DownloadService = Depends(get_download_service)
):
    """Prepare a download task (video or audio)"""
    try:
        logger.info(
            f"Preparing {download_request.type} download: {download_request.title} "
            f"from {download_request.url}"
        )

        # Validate file size if we can estimate it
        if download_request.type == "video" and download_request.resolution:
            # Check if resolution is reasonable for file size limits
            if download_request.resolution > 1080 and settings.max_file_size_mb < 500:
                logger.warning(f"High resolution {download_request.resolution}p requested")

        response = await download_service.prepare_download(
            url=str(download_request.url),
            title=download_request.title,
            download_type=download_request.type,
            resolution=download_request.resolution or 720,
            format_type=download_request.format or "webm"
        )

        logger.info(f"Download prepared with ID: {response.download_id}")
        return response

    except Exception as e:
        logger.error(f"Error preparing download: {e}")
        raise HTTPException(
            status_code=400,
            detail=f"Failed to prepare download: {str(e)}"
        )

@app.get("/download")
async def download(url: str, resolution: int, title: str):
    """Fast direct download endpoint - original implementation"""
    download_service = get_download_service()

    # Start the download immediately
    download_id = str(uuid.uuid4())

    # Create download task
    from services import DownloadTask
    with download_service.tasks_lock:
        download_service.download_tasks[download_id] = DownloadTask(
            download_id, url, title, "video"
        )

    # Start background download
    threading.Thread(
        target=download_service._background_video_download,
        args=(download_id, url, title, resolution),
        daemon=True
    ).start()

    # Wait for completion and serve file
    while True:
        await asyncio.sleep(0.5)  # Much faster polling
        with download_service.tasks_lock:
            task = download_service.download_tasks.get(download_id)
            if not task:
                break
            if task.status == "ready":
                file_path = task.file_path
                break
            elif task.status == "error":
                raise HTTPException(status_code=500, detail=task.error)

    return FileResponse(file_path, media_type="application/octet-stream", filename=os.path.basename(file_path))

@app.get("/download_audio")
async def download_audio(url: str, title: str, format: str):
    """Fast direct audio download endpoint - original implementation"""
    download_service = get_download_service()

    # Start the download immediately
    download_id = str(uuid.uuid4())

    # Create download task
    from services import DownloadTask
    with download_service.tasks_lock:
        download_service.download_tasks[download_id] = DownloadTask(
            download_id, url, title, "audio"
        )

    # Start background download
    threading.Thread(
        target=download_service._background_audio_download,
        args=(download_id, url, title, format),
        daemon=True
    ).start()

    # Wait for completion and serve file
    while True:
        await asyncio.sleep(0.5)  # Much faster polling
        with download_service.tasks_lock:
            task = download_service.download_tasks.get(download_id)
            if not task:
                break
            if task.status == "ready":
                file_path = task.file_path
                break
            elif task.status == "error":
                raise HTTPException(status_code=500, detail=task.error)

    return FileResponse(file_path, media_type="application/octet-stream", filename=os.path.basename(file_path))

@app.get("/progress")
async def progress():
    """Fast progress endpoint - original implementation"""
    from services import get_global_progress

    # Use global progress for super fast updates
    current_progress = get_global_progress()
    return JSONResponse({"progress": current_progress})

@app.get("/api/download_status/{download_id}", response_model=DownloadStatusResponse)
async def get_download_status(
    download_id: str,
    download_service: DownloadService = Depends(get_download_service)
):
    """Get the status of a download task"""
    try:
        status = download_service.get_download_status(download_id)

        if not status:
            raise HTTPException(
                status_code=404,
                detail="Download task not found or expired"
            )

        return status

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting download status: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get download status: {str(e)}"
        )

@app.get("/api/download/{download_id}")
async def download_file(
    download_id: str,
    download_service: DownloadService = Depends(get_download_service)
):
    """Download the completed file"""
    try:
        file_path = download_service.get_file_path(download_id)

        if not file_path:
            raise HTTPException(
                status_code=404,
                detail="File not found or download not ready"
            )

        if not os.path.exists(file_path):
            logger.error(f"File not found on disk: {file_path}")
            raise HTTPException(
                status_code=404,
                detail="File not found on server"
            )

        filename = os.path.basename(file_path)
        logger.info(f"Serving file: {filename}")

        return FileResponse(
            path=file_path,
            media_type="application/octet-stream",
            filename=filename,
            headers={
                "Cache-Control": "no-cache",
                "Content-Disposition": f"attachment; filename*=UTF-8''{filename}"
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error serving file: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to serve file: {str(e)}"
        )

@app.get("/api/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "temp_dir_exists": os.path.exists(settings.temp_dir),
        "ffmpeg_available": await check_ffmpeg_available()
    }

async def check_ffmpeg_available() -> bool:
    """Check if FFmpeg is available"""
    try:
        process = await asyncio.create_subprocess_exec(
            settings.ffmpeg_path, "-version",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        await process.communicate()
        return process.returncode == 0
    except Exception:
        return False

@app.get("/api/config")
async def get_config():
    """Get public configuration for frontend"""
    return {
        "max_file_size_mb": settings.max_file_size_mb,
        "allowed_audio_formats": settings.allowed_audio_formats,
        "allowed_video_formats": settings.allowed_video_formats,
        "allowed_resolutions": settings.allowed_resolutions,
        "rate_limit_per_minute": settings.rate_limit_per_minute,
        "max_title_length": settings.max_title_length
    }

# Error handlers for specific exceptions
@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError):
    """Handle validation errors"""
    return JSONResponse(
        status_code=400,
        content=ErrorResponse(
            error=str(exc),
            error_code="VALIDATION_ERROR"
        ).dict()
    )

# Development endpoints (only available in debug mode)
if settings.debug:
    @app.get("/api/debug/tasks")
    async def debug_get_tasks(
        download_service: DownloadService = Depends(get_download_service)
    ):
        """Debug endpoint to view active tasks"""
        if hasattr(download_service, 'download_tasks') and hasattr(download_service, 'tasks_lock'):
            tasks = {}
            with download_service.tasks_lock:
                for task_id, task in download_service.download_tasks.items():
                    tasks[task_id] = {
                        "status": task.status,
                        "progress": task.progress,
                        "type": task.type,
                        "title": task.title,
                        "created_at": task.created_at.isoformat(),
                        "is_expired": task.is_expired()
                    }
            return {"tasks": tasks}
        return {"tasks": {}}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        log_level="info"
    )
