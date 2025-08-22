#!/usr/bin/env python3
"""
YouTube Downloader - Startup Script
Run this script to start the application with proper configuration.
"""

import os
import sys
import subprocess
import logging
from pathlib import Path

# Add the project directory to Python path
project_dir = Path(__file__).parent
sys.path.insert(0, str(project_dir))

try:
    import uvicorn
    from config import settings
    from app import app
except ImportError as e:
    print(f"Error importing dependencies: {e}")
    print("Please install requirements: pip install -r requirements.txt")
    sys.exit(1)

def check_dependencies():
    """Check if required external dependencies are available"""
    dependencies = {
        'ffmpeg': 'FFmpeg is required for audio conversion',
    }

    missing_deps = []

    for dep, description in dependencies.items():
        try:
            subprocess.run([dep, '-version'],
                         capture_output=True,
                         check=True,
                         timeout=5)
        except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
            missing_deps.append((dep, description))

    if missing_deps:
        print("⚠️  Warning: Missing optional dependencies:")
        for dep, desc in missing_deps:
            print(f"   - {dep}: {desc}")
        print("   Audio conversion may not work properly.")
        print("   Install FFmpeg: https://ffmpeg.org/download.html")
        print()

    return len(missing_deps) == 0

def setup_logging():
    """Setup logging configuration"""
    log_level = "DEBUG" if settings.debug else "INFO"
    logging.basicConfig(
        level=getattr(logging, log_level),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler('youtube_downloader.log')
        ]
    )

def main():
    """Main startup function"""
    print("🚀 Starting YouTube Downloader...")
    print(f"📁 Project directory: {project_dir}")
    print(f"🗂️  Temp directory: {settings.temp_dir}")
    print(f"🌐 Server URL: http://{settings.host}:{settings.port}")
    print()

    # Setup logging
    setup_logging()

    # Check dependencies
    check_dependencies()

    # Ensure temp directory exists
    os.makedirs(settings.temp_dir, exist_ok=True)

    # Print configuration
    print("⚙️  Configuration:")
    print(f"   - Debug mode: {settings.debug}")
    print(f"   - Max file size: {settings.max_file_size_mb}MB")
    print(f"   - Max concurrent downloads: {settings.max_concurrent_downloads}")
    print(f"   - Rate limit: {settings.rate_limit_per_minute}/minute")
    print(f"   - Task expiry: {settings.task_expiry_hours} hours")
    print()

    # Start the server
    print("✅ Starting server...")
    try:
        uvicorn.run(
            "app:app",
            host=settings.host,
            port=settings.port,
            reload=settings.debug,
            log_level="info" if not settings.debug else "debug",
            access_log=True,
            server_header=False,
            date_header=False,
        )
    except KeyboardInterrupt:
        print("\n🛑 Server stopped by user")
    except Exception as e:
        print(f"❌ Error starting server: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
