import asyncio
import os
import tempfile
import shutil
import subprocess
import threading
import time
import uuid
import atexit
import logging
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import Dict, Optional, Union, cast
from pathvalidate import sanitize_filename
from yt_dlp import YoutubeDL

from config import settings
from models import DownloadStatusResponse, VideoInfoResponse, DownloadPrepareResponse

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global fast progress tracking
global_progress = 0
progress_lock = threading.Lock()

class DownloadTask:
    def __init__(self, download_id: str, url: str, title: str, download_type: str):
        self.download_id = download_id
        self.url = url
        self.title = title
        self.type = download_type
        self.status = "processing"
        self.progress = 0.0
        self.error: Optional[str] = None
        self.file_path: Optional[str] = None
        self.created_at = datetime.now()
        self.estimated_time_remaining: Optional[int] = None
        self.download_speed: Optional[str] = None
        self.file_size: Optional[str] = None
        self.temp_dir: Optional[str] = None

    def update_global_progress(self, progress: float):
        """Update global progress for fast tracking"""
        global global_progress
        with progress_lock:
            global_progress = progress
        self.progress = progress

    def update_progress(self, progress: float, speed: Optional[str] = None, eta: Optional[int] = None, file_size: Optional[str] = None):
        self.progress = progress
        self.download_speed = speed
        self.estimated_time_remaining = eta
        self.file_size = file_size

    def set_ready(self, file_path: str):
        self.status = "ready"
        self.progress = 100.0
        self.file_path = file_path
        self.estimated_time_remaining = 0

    def set_error(self, error: str):
        self.status = "error"
        self.error = error

    def is_expired(self) -> bool:
        return datetime.now() - self.created_at > timedelta(hours=settings.task_expiry_hours)

class DownloadService(ABC):
    @abstractmethod
    async def get_video_info(self, url: str) -> VideoInfoResponse:
        pass

    @abstractmethod
    async def prepare_download(self, url: str, title: str, download_type: str,
                             resolution: Optional[int] = None, format_type: Optional[str] = None) -> DownloadPrepareResponse:
        pass

    @abstractmethod
    def get_download_status(self, download_id: str) -> Optional[DownloadStatusResponse]:
        pass

    @abstractmethod
    def get_file_path(self, download_id: str) -> Optional[str]:
        pass

class YoutubeDLService(DownloadService):
    def __init__(self):
        self.download_tasks: Dict[str, DownloadTask] = {}
        self.tasks_lock = threading.Lock()
        self.cleanup_registry = []
        self.executor = None

        # Start cleanup scheduler
        self._start_cleanup_scheduler()

        # Register cleanup on exit
        atexit.register(self.cleanup_all)

    def _start_cleanup_scheduler(self):
        """Start background cleanup scheduler"""
        def cleanup_worker():
            while True:
                try:
                    self.cleanup_expired_tasks()
                    self.cleanup_old_temp_files()
                    time.sleep(settings.cleanup_interval_minutes * 60)
                except Exception as e:
                    logger.error(f"Cleanup error: {e}")

        cleanup_thread = threading.Thread(target=cleanup_worker, daemon=True)
        cleanup_thread.start()

    def cleanup_expired_tasks(self):
        """Remove expired tasks and their files"""
        with self.tasks_lock:
            expired_tasks = [
                task_id for task_id, task in self.download_tasks.items()
                if task.is_expired()
            ]

            for task_id in expired_tasks:
                task = self.download_tasks[task_id]
                if task.temp_dir and os.path.exists(task.temp_dir):
                    try:
                        shutil.rmtree(task.temp_dir)
                    except Exception as e:
                        logger.error(f"Error removing temp dir {task.temp_dir}: {e}")

                del self.download_tasks[task_id]
                logger.info(f"Cleaned up expired task: {task_id}")

    def cleanup_old_temp_files(self):
        """Clean up old temporary files"""
        try:
            cutoff_time = time.time() - (settings.max_temp_file_age_hours * 3600)
            for root, dirs, files in os.walk(settings.temp_dir):
                for file in files:
                    file_path = os.path.join(root, file)
                    if os.path.getmtime(file_path) < cutoff_time:
                        try:
                            os.remove(file_path)
                        except Exception as e:
                            logger.error(f"Error removing old file {file_path}: {e}")
        except Exception as e:
            logger.error(f"Error during temp file cleanup: {e}")

    def cleanup_all(self):
        """Clean up all temporary files on shutdown"""
        logger.info("Cleaning up all temporary files...")
        with self.tasks_lock:
            for task in self.download_tasks.values():
                if task.temp_dir and os.path.exists(task.temp_dir):
                    try:
                        shutil.rmtree(task.temp_dir)
                    except Exception as e:
                        logger.error(f"Error cleaning up {task.temp_dir}: {e}")

    async def get_video_info(self, url: str) -> VideoInfoResponse:
        """Extract video information without downloading"""
        ydl_opts = {
            'quiet': True,
            'skip_download': True,
            'format': 'bestaudio/best',
            'noplaylist': True,
            'socket_timeout': 30,
            'retries': 3,
            'fragment_retries': 3,
            'extractor_retries': 3,
            'file_access_retries': 3,
            'force_ipv4': True,
        }

        def extract_info():
            max_retries = 3
            retry_delay = 2

            for attempt in range(max_retries):
                try:
                    with YoutubeDL(ydl_opts) as ydl:
                        return ydl.extract_info(url, download=False)
                except Exception as e:
                    error_msg = str(e).lower()
                    if "temporary failure in name resolution" in error_msg or "transport error" in error_msg:
                        if attempt < max_retries - 1:
                            logger.warning(f"Network error on attempt {attempt + 1}, retrying in {retry_delay}s: {e}")
                            time.sleep(retry_delay)
                            retry_delay *= 2  # Exponential backoff
                            continue
                    raise ValueError(f"Failed to extract video information: {str(e)}")

            raise ValueError("Failed to extract video information after multiple attempts")

        # Run in thread pool to avoid blocking
        loop = asyncio.get_event_loop()
        info_dict = await loop.run_in_executor(None, extract_info)

        if not info_dict:
            raise ValueError("Failed to extract video information")

        # Extract available resolutions
        formats = info_dict.get('formats', []) or []
        resolutions = []
        estimated_sizes = {}

        for f in formats:
            if f and isinstance(f, dict):
                height = f.get('height')
                ext = f.get('ext')
                filesize = f.get('filesize') or f.get('filesize_approx')

                if height and ext == 'mp4' and height >= 144:
                    resolutions.append(height)
                    if filesize:
                        estimated_sizes[height] = round(filesize / (1024 * 1024), 1)  # MB

        resolutions = sorted(set(resolutions), reverse=True)

        return VideoInfoResponse(
            title=info_dict.get('title') or 'Unknown Title',
            thumbnail=info_dict.get('thumbnail') or '',
            resolutions=resolutions,
            duration=info_dict.get('duration'),
            uploader=info_dict.get('uploader'),
            view_count=info_dict.get('view_count'),
            estimated_size=estimated_sizes
        )

    async def prepare_download(self, url: str, title: str, download_type: str,
                             resolution: Optional[int] = None, format_type: Optional[str] = None) -> DownloadPrepareResponse:
        """Prepare a download task"""
        download_id = str(uuid.uuid4())

        # Create download task
        task = DownloadTask(download_id, url, title, download_type)

        with self.tasks_lock:
            self.download_tasks[download_id] = task

        # Start background download
        if download_type == "video":
            threading.Thread(
                target=self._background_video_download,
                args=(download_id, url, title, resolution),
                daemon=True
            ).start()
        elif download_type == "audio":
            threading.Thread(
                target=self._background_audio_download,
                args=(download_id, url, title, format_type),
                daemon=True
            ).start()

        # Estimate download parameters
        estimated_size = None
        estimated_duration = None

        try:
            # Quick info extraction for estimates
            info = await self.get_video_info(url)
            if download_type == "video" and info.estimated_size:
                estimated_size = info.estimated_size.get(resolution)
            estimated_duration = info.duration
        except Exception as e:
            logger.warning(f"Could not get estimates: {e}")

        return DownloadPrepareResponse(
            download_id=download_id,
            estimated_size_mb=estimated_size,
            estimated_duration_seconds=estimated_duration
        )

    def get_download_status(self, download_id: str) -> Optional[DownloadStatusResponse]:
        """Get the status of a download task"""
        with self.tasks_lock:
            task = self.download_tasks.get(download_id)
            if not task:
                return None

            if task.is_expired():
                task.status = "expired"

            return DownloadStatusResponse(
                status=cast(str, task.status),
                progress=task.progress,
                error=task.error,
                estimated_time_remaining=task.estimated_time_remaining,
                download_speed=task.download_speed,
                file_size=task.file_size
            )

    def get_file_path(self, download_id: str) -> Optional[str]:
        """Get the file path for a completed download"""
        with self.tasks_lock:
            task = self.download_tasks.get(download_id)
            if task and task.status == "ready" and task.file_path:
                return task.file_path
            return None

    def _create_progress_hook(self, download_id: str, is_audio: bool = False):
        """Create a progress hook for yt-dlp"""
        def progress_hook(d):
            if d['status'] == 'downloading':
                total_bytes = d.get('total_bytes') or d.get('total_bytes_estimate')
                downloaded_bytes = d.get('downloaded_bytes', 0)
                speed = d.get('speed')
                eta = d.get('eta')

                if total_bytes:
                    # For audio, downloading is 50% of total progress due to conversion
                    progress_multiplier = 0.5 if is_audio else 1.0
                    progress = (downloaded_bytes / total_bytes) * 100 * progress_multiplier

                    speed_str = None
                    if speed:
                        if speed > 1024 * 1024:
                            speed_str = f"{speed / (1024 * 1024):.1f} MB/s"
                        else:
                            speed_str = f"{speed / 1024:.1f} KB/s"

                    file_size_str = None
                    if total_bytes:
                        if total_bytes > 1024 * 1024:
                            file_size_str = f"{total_bytes / (1024 * 1024):.1f} MB"
                        else:
                            file_size_str = f"{total_bytes / 1024:.1f} KB"

                    with self.tasks_lock:
                        if download_id in self.download_tasks:
                            self.download_tasks[download_id].update_progress(
                                progress, speed_str, eta, file_size_str
                            )
                            # Update global progress for fast access
                            self.download_tasks[download_id].update_global_progress(progress)

        return progress_hook

    def _background_video_download(self, download_id: str, url: str, title: str, resolution: int):
        """Background video download function"""
        try:
            task = self.download_tasks[download_id]
            temp_dir = tempfile.mkdtemp(prefix="yt_dl_", dir=settings.temp_dir)
            task.temp_dir = temp_dir

            temp_file_path = os.path.join(temp_dir, 'temp_video.mp4')

            ydl_opts = {
                'outtmpl': temp_file_path,
                'format': f'bestvideo[ext=mp4][height={resolution}]+bestaudio/best[ext=mp4][height={resolution}]',
                'merge_output_format': 'mp4',
                'noplaylist': True,
                'progress_hooks': [self._create_progress_hook(download_id)],
                'quiet': True,
                'socket_timeout': 30,
                'retries': 3,
                'fragment_retries': 3,
                'extractor_retries': 3,
                'file_access_retries': 3,
                'force_ipv4': True,
            }

            # Add retry logic for downloads
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    with YoutubeDL(ydl_opts) as ydl:
                        ydl.download([url])
                    break  # Success, exit retry loop
                except Exception as e:
                    error_msg = str(e).lower()
                    if ("temporary failure" in error_msg or "transport error" in error_msg) and attempt < max_retries - 1:
                        logger.warning(f"Video download attempt {attempt + 1} failed, retrying: {e}")
                        time.sleep(2 * (attempt + 1))  # Progressive delay
                        continue
                    else:
                        raise  # Re-raise if not a network error or max retries exceeded

            # Find the downloaded file
            downloaded_files = [f for f in os.listdir(temp_dir) if f.endswith('.mp4')]
            if not downloaded_files:
                raise Exception("No video file found after download")

            temp_file = os.path.join(temp_dir, downloaded_files[0])
            final_file_path = os.path.join(temp_dir, f'{sanitize_filename(title)}_{resolution}p.mp4')
            os.rename(temp_file, final_file_path)

            with self.tasks_lock:
                if download_id in self.download_tasks:
                    self.download_tasks[download_id].set_ready(final_file_path)

        except Exception as e:
            logger.error(f"Video download failed for {download_id}: {e}")
            with self.tasks_lock:
                if download_id in self.download_tasks:
                    self.download_tasks[download_id].set_error(str(e))

    def _background_audio_download(self, download_id: str, url: str, title: str, format_type: str):
        """Background audio download function"""
        try:
            task = self.download_tasks[download_id]
            temp_dir = tempfile.mkdtemp(prefix="yt_dl_", dir=settings.temp_dir)
            task.temp_dir = temp_dir

            temp_file_path = os.path.join(temp_dir, 'temp_audio.webm')
            final_file_path = os.path.join(temp_dir, f'{sanitize_filename(title)}.{format_type}')

            ydl_opts = {
                'outtmpl': temp_file_path,
                'format': 'bestaudio/best',
                'noplaylist': True,
                'progress_hooks': [self._create_progress_hook(download_id, is_audio=True)],
                'quiet': True,
                'socket_timeout': 30,
                'retries': 3,
                'fragment_retries': 3,
                'extractor_retries': 3,
                'file_access_retries': 3,
                'force_ipv4': True,
            }

            # Add retry logic for audio downloads
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    with YoutubeDL(ydl_opts) as ydl:
                        ydl.download([url])
                    break  # Success, exit retry loop
                except Exception as e:
                    error_msg = str(e).lower()
                    if ("temporary failure" in error_msg or "transport error" in error_msg) and attempt < max_retries - 1:
                        logger.warning(f"Audio download attempt {attempt + 1} failed, retrying: {e}")
                        time.sleep(2 * (attempt + 1))  # Progressive delay
                        continue
                    else:
                        raise  # Re-raise if not a network error or max retries exceeded

            # Use the downloaded file
            if not os.path.exists(temp_file_path):
                # Find any downloaded file
                downloaded_files = [f for f in os.listdir(temp_dir) if not f.endswith('.part')]
                if not downloaded_files:
                    raise Exception("No audio file found after download")
                temp_file = os.path.join(temp_dir, downloaded_files[0])
            else:
                temp_file = temp_file_path

            # Update progress to 50% after download
            with self.tasks_lock:
                if download_id in self.download_tasks:
                    self.download_tasks[download_id].update_progress(50.0)
                    self.download_tasks[download_id].update_global_progress(50.0)

            # Convert to desired format if needed
            if format_type == 'webm' or temp_file.endswith(f'.{format_type}'):
                os.rename(temp_file, final_file_path)
            else:
                # Convert using ffmpeg
                ffmpeg_command = [settings.ffmpeg_path, '-i', temp_file]
                codec_args = self._get_ffmpeg_codec_args(format_type)
                ffmpeg_command.extend(codec_args)
                ffmpeg_command.extend(['-y', final_file_path])  # -y to overwrite

                subprocess.run(ffmpeg_command, check=True, capture_output=True)
                os.remove(temp_file)

            with self.tasks_lock:
                if download_id in self.download_tasks:
                    self.download_tasks[download_id].set_ready(final_file_path)

        except Exception as e:
            logger.error(f"Audio download failed for {download_id}: {e}")
            with self.tasks_lock:
                if download_id in self.download_tasks:
                    self.download_tasks[download_id].set_error(str(e))

    def _get_ffmpeg_codec_args(self, format_type: str):
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

# Global service instance
_download_service = None

def get_download_service() -> DownloadService:
    """Dependency injection function for FastAPI"""
    global _download_service
    if _download_service is None:
        _download_service = YoutubeDLService()
    return _download_service

def get_global_progress() -> float:
    """Get the current global progress"""
    global global_progress
    with progress_lock:
        return global_progress
