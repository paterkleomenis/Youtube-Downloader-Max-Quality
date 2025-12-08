from typing import List, Optional, Dict, Literal
from pydantic import BaseModel, HttpUrl, validator, Field
import re
from urllib.parse import urlparse
from config import settings

class VideoInfoRequest(BaseModel):
    url: HttpUrl

    @validator('url')
    def validate_url_domain(cls, v):
        parsed = urlparse(str(v))
        domain = parsed.netloc.lower()

        # Remove www. prefix for comparison
        if domain.startswith('www.'):
            domain = domain[4:]

        allowed_domains = [d.replace('www.', '') for d in settings.allowed_domains]

        if not any(domain == allowed_domain or domain.endswith('.' + allowed_domain)
                  for allowed_domain in allowed_domains):
            raise ValueError(f'Domain not allowed. Allowed domains: {settings.allowed_domains}')
        return v

class DownloadRequest(BaseModel):
    url: HttpUrl
    type: Literal["video", "audio"]
    title: str = Field(..., min_length=1, max_length=settings.max_title_length)
    resolution: Optional[int] = None
    format: Optional[str] = None

    @validator('url')
    def validate_url_domain(cls, v):
        parsed = urlparse(str(v))
        domain = parsed.netloc.lower()

        if domain.startswith('www.'):
            domain = domain[4:]

        allowed_domains = [d.replace('www.', '') for d in settings.allowed_domains]

        if not any(domain == allowed_domain or domain.endswith('.' + allowed_domain)
                  for allowed_domain in allowed_domains):
            raise ValueError(f'Domain not allowed. Allowed domains: {settings.allowed_domains}')
        return v

    @validator('title')
    def validate_title(cls, v):
        # Remove potentially dangerous characters
        v = re.sub(r'[<>:"/\\|?*]', '_', v)
        # Remove control characters
        v = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', v)
        if not v.strip():
            raise ValueError('Title cannot be empty after sanitization')
        return v.strip()

    @validator('resolution')
    def validate_resolution(cls, v, values):
        if values.get('type') == 'video':
            if v is None:
                raise ValueError('Resolution is required for video downloads')
            # Removed strict list check to allow non-standard resolutions (like 816p)
        return v

    @validator('format')
    def validate_format(cls, v, values):
        if values.get('type') == 'audio':
            if v is None:
                raise ValueError('Format is required for audio downloads')
            if v not in settings.allowed_audio_formats:
                raise ValueError(f'Invalid format. Allowed: {settings.allowed_audio_formats}')
        elif values.get('type') == 'video':
            if v and v not in settings.allowed_video_formats:
                raise ValueError(f'Invalid video format. Allowed: {settings.allowed_video_formats}')
        return v

class DownloadStatusResponse(BaseModel):
    status: Literal["processing", "ready", "error", "expired"]
    progress: float = Field(..., ge=0, le=100)
    error: Optional[str] = None
    estimated_time_remaining: Optional[int] = None  # seconds
    download_speed: Optional[str] = None  # e.g., "1.2 MB/s"
    file_size: Optional[str] = None  # e.g., "45.6 MB"

class ResolutionOption(BaseModel):
    label: str
    value: int

class VideoInfoResponse(BaseModel):
    title: str
    thumbnail: str
    resolutions: List[ResolutionOption]
    duration: Optional[int] = None
    uploader: Optional[str] = None
    view_count: Optional[int] = None
    estimated_size: Optional[Dict[int, float]] = None

class DownloadPrepareResponse(BaseModel):
    download_id: str
    estimated_size_mb: Optional[float] = None
    estimated_duration_seconds: Optional[int] = None

class DownloadResponse(BaseModel):
    status: str
    message: str
    file_path: Optional[str] = None
    download_id: Optional[str] = None  # Added for frontend tracking

class ErrorResponse(BaseModel):
    error: str
    error_code: Optional[str] = None
    details: Optional[dict] = None
