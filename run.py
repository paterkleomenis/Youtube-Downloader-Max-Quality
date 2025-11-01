#!/usr/bin/env python3
"""
YouTube Downloader - Startup Script
Run this script to start the application with proper configuration.
"""

import os
import sys
import subprocess
import logging
import socket
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
        "ffmpeg": "FFmpeg is required for audio conversion",
    }

    missing_deps = []

    for dep, description in dependencies.items():
        try:
            subprocess.run(
                [dep, "-version"], capture_output=True, check=True, timeout=5
            )
        except (
            subprocess.CalledProcessError,
            FileNotFoundError,
            subprocess.TimeoutExpired,
        ):
            missing_deps.append((dep, description))

    if missing_deps:
        print("⚠️  Warning: Missing optional dependencies:")
        for dep, desc in missing_deps:
            print(f"   - {dep}: {desc}")
        print("   Audio conversion may not work properly.")
        print("   Install FFmpeg: https://ffmpeg.org/download.html")
        print()

    return len(missing_deps) == 0


def get_local_ip():
    """Get local IP address"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
        return local_ip
    except Exception:
        return "Unable to detect"


def is_port_available(port):
    """Check if a port is available"""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        result = sock.connect_ex(("127.0.0.1", port))
        sock.close()
        return result != 0
    except Exception:
        return False


def get_available_port(start_port=5000):
    """Find an available port starting from start_port"""
    port = start_port
    while port < 65535:
        if is_port_available(port):
            return port
        port += 1
    return None


def setup_logging():
    """Setup logging configuration"""
    log_level = "DEBUG" if settings.debug else "INFO"
    logging.basicConfig(
        level=getattr(logging, log_level),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler("youtube_downloader.log"),
        ],
    )


def main():
    """Main startup function"""
    print("🚀 Starting YouTube Downloader...")
    print(f"📁 Project directory: {project_dir}")
    print(f"🗂️  Temp directory: {settings.temp_dir}")
    print()

    # Setup logging
    setup_logging()

    # Check dependencies
    check_dependencies()

    # Ensure temp directory exists
    os.makedirs(settings.temp_dir, exist_ok=True)

    # Check if port is available
    port = settings.port
    if not is_port_available(port):
        print(f"⚠️  Port {port} is already in use!")
        print()
        print("Choose an option:")
        print(f"  1. Use next available port")
        print(f"  2. Enter a different port")
        print(f"  3. Exit")
        print()

        choice = input("Enter your choice (1-3): ").strip()

        if choice == "1":
            new_port = get_available_port(port + 1)
            if new_port:
                port = new_port
                print(f"✅ Using port {port}")
            else:
                print("❌ No available ports found!")
                sys.exit(1)
        elif choice == "2":
            while True:
                try:
                    user_port = int(input("Enter port number (1024-65535): ").strip())
                    if 1024 <= user_port <= 65535:
                        if is_port_available(user_port):
                            port = user_port
                            print(f"✅ Using port {port}")
                            break
                        else:
                            print(f"❌ Port {user_port} is also in use. Try another.")
                    else:
                        print("❌ Port must be between 1024 and 65535")
                except ValueError:
                    print("❌ Invalid input. Please enter a number.")
        else:
            print("👋 Exiting...")
            sys.exit(0)
        print()

    # Get local IP
    local_ip = get_local_ip()

    # Print server URLs
    print("🌐 Server URLs:")
    print(f"   - Local:   http://127.0.0.1:{port}")
    if local_ip != "Unable to detect":
        print(f"   - Network: http://{local_ip}:{port}")
    print()

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
            port=port,
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
