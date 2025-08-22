from pydantic_settings import BaseSettings
from typing import List
import os

class Settings(BaseSettings):
    # Server settings
    host: str = "0.0.0.0"
    port: int = 5000
    debug: bool = False

    # Download settings
    temp_dir: str = "/tmp/youtube_downloader"
    max_concurrent_downloads: int = 5
    task_expiry_hours: int = 2
    max_file_size_mb: int = 10000
    download_timeout_minutes: int = 30000

    # Supported formats
    allowed_video_formats: List[str] = ["mp4"]
    allowed_audio_formats: List[str] = ["mp3", "wav", "flac", "aac", "ogg", "m4a", "webm"]
    allowed_resolutions: List[int] = [144, 240, 360, 480, 720, 1080, 1440, 2160]

    # External tools
    ffmpeg_path: str = "ffmpeg"

    # Rate limiting
    rate_limit_per_minute: int = 10
    rate_limit_per_hour: int = 50

    # Security
    max_title_length: int = 200
    allowed_domains: List[str] = [
        "youtube.com", "youtu.be", "m.youtube.com",
        "music.youtube.com", "www.youtube.com"
    ]

    # Cleanup settings
    cleanup_interval_minutes: int = 60
    max_temp_file_age_hours: int = 24

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

# Global settings instance
settings = Settings()

# Ensure temp directory exists
os.makedirs(settings.temp_dir, exist_ok=True)
