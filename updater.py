#!/usr/bin/env python3
"""
yt-dlp Auto-Updater Module
Handles automatic updates of yt-dlp without requiring system Python installation
"""

import hashlib
import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


class YtDlpUpdater:
    """Manages yt-dlp updates for standalone executables"""

    def __init__(self):
        self.cache_dir = self._get_cache_dir()
        self.version_file = self.cache_dir / "version.json"
        self.update_lock = threading.Lock()
        self.last_check_file = self.cache_dir / "last_check.txt"

        # Create cache directory
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _get_cache_dir(self) -> Path:
        """Get platform-specific cache directory"""
        if sys.platform == "win32":
            base = os.environ.get("LOCALAPPDATA", os.path.expanduser("~"))
            cache_path = Path(base) / "youtube-downloader" / "yt-dlp"
        elif sys.platform == "darwin":
            cache_path = (
                Path.home() / "Library" / "Caches" / "youtube-downloader" / "yt-dlp"
            )
        else:  # Linux and others
            base = os.environ.get("XDG_CACHE_HOME", os.path.expanduser("~/.cache"))
            cache_path = Path(base) / "youtube-downloader" / "yt-dlp"

        return cache_path

    def get_lib_dir(self) -> Path:
        """Get directory where custom library updates are stored"""
        return self.cache_dir / "lib"

    def _should_check_update(self) -> bool:
        """Check if we should check for updates (once per day)"""
        if not self.last_check_file.exists():
            return True

        try:
            with open(self.last_check_file, "r") as f:
                last_check_str = f.read().strip()
                last_check = datetime.fromisoformat(last_check_str)

            # Check if more than 24 hours have passed
            return datetime.now() - last_check > timedelta(hours=24)
        except Exception as e:
            logger.error(f"Error reading last check time: {e}")
            return True

    def _update_last_check(self):
        """Update the last check timestamp"""
        try:
            with open(self.last_check_file, "w") as f:
                f.write(datetime.now().isoformat())
        except Exception as e:
            logger.error(f"Error updating last check time: {e}")

    def get_current_version(self) -> Optional[str]:
        """Get currently installed yt-dlp version"""
        try:
            import yt_dlp

            return yt_dlp.version.__version__
        except Exception as e:
            logger.error(f"Error getting yt-dlp version: {e}")
            return None

    def get_latest_version(self) -> Optional[str]:
        """Get latest yt-dlp version from GitHub API"""
        try:
            import httpx

            response = httpx.get(
                "https://api.github.com/repos/yt-dlp/yt-dlp/releases/latest",
                timeout=5.0,
                follow_redirects=True,
            )

            if response.status_code == 200:
                data = response.json()
                return data.get("tag_name", "").lstrip("v")

            return None
        except Exception as e:
            logger.error(f"Error fetching latest version: {e}")
            return None

    def check_for_updates(
        self, force: bool = False
    ) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Check if updates are available

        Returns:
            Tuple of (update_available, current_version, latest_version)
        """
        if not force and not self._should_check_update():
            logger.info("Skipping update check (checked recently)")
            return (False, self.get_current_version(), None)

        current_version = self.get_current_version()
        latest_version = self.get_latest_version()

        self._update_last_check()

        if not current_version or not latest_version:
            return (False, current_version, latest_version)

        # Compare versions
        update_available = self._compare_versions(current_version, latest_version)

        if update_available:
            logger.info(
                f"yt-dlp update available: {current_version} -> {latest_version}"
            )
        else:
            logger.info(f"yt-dlp is up to date: {current_version}")

        return (update_available, current_version, latest_version)

    def _compare_versions(self, current: str, latest: str) -> bool:
        """Compare version strings"""
        try:
            # Remove any non-numeric prefixes
            current = current.lstrip("v")
            latest = latest.lstrip("v")

            # Split by dots and compare
            current_parts = [int(x) for x in current.split(".")]
            latest_parts = [int(x) for x in latest.split(".")]

            # Pad shorter version with zeros
            max_len = max(len(current_parts), len(latest_parts))
            current_parts.extend([0] * (max_len - len(current_parts)))
            latest_parts.extend([0] * (max_len - len(latest_parts)))

            return latest_parts > current_parts
        except Exception as e:
            logger.error(f"Error comparing versions: {e}")
            return False

    def _install_from_wheel(self, url: str) -> bool:
        """Download and install yt-dlp from wheel"""
        try:
            import io
            import zipfile

            import httpx

            logger.info(f"Downloading yt-dlp wheel from {url}")

            response = httpx.get(url, follow_redirects=True, timeout=60.0)
            if response.status_code != 200:
                logger.error(f"Failed to download wheel: {response.status_code}")
                return False

            # Extract to lib dir
            lib_dir = self.get_lib_dir()

            # Create a temp directory for extraction
            with tempfile.TemporaryDirectory() as temp_extract_dir:
                with zipfile.ZipFile(io.BytesIO(response.content)) as zip_ref:
                    zip_ref.extractall(temp_extract_dir)

                # Move yt_dlp folder to lib_dir
                source_yt_dlp = Path(temp_extract_dir) / "yt_dlp"
                dest_yt_dlp = lib_dir / "yt_dlp"

                if source_yt_dlp.exists():
                    if dest_yt_dlp.exists():
                        shutil.rmtree(dest_yt_dlp)
                    lib_dir.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(source_yt_dlp), str(dest_yt_dlp))

                    # Also copy .dist-info if possible to preserve version info,
                    # but just the package is enough for functionality

                    logger.info(f"Successfully installed yt-dlp to {lib_dir}")
                    return True
                else:
                    logger.error("yt_dlp package not found in wheel")
                    return False

        except Exception as e:
            logger.error(f"Error installing from wheel: {e}")
            return False

    def download_update(self) -> bool:
        """Download and install yt-dlp update"""
        with self.update_lock:
            try:
                import httpx

                is_frozen = getattr(sys, "frozen", False)
                logger.info("Downloading yt-dlp update...")

                # Get release info to find wheel
                response = httpx.get(
                    "https://api.github.com/repos/yt-dlp/yt-dlp/releases/latest",
                    timeout=30.0,
                    follow_redirects=True,
                )

                if response.status_code != 200:
                    logger.error(
                        f"Failed to fetch release info: {response.status_code}"
                    )
                    return False

                data = response.json()
                assets = data.get("assets", [])
                wheel_asset = next(
                    (a for a in assets if a["name"].endswith(".whl")), None
                )

                # If frozen, we MUST use the wheel/custom path method
                if is_frozen:
                    if wheel_asset:
                        logger.info(
                            "Frozen environment detected: Installing from wheel..."
                        )
                        return self._install_from_wheel(
                            wheel_asset["browser_download_url"]
                        )
                    else:
                        logger.error("No wheel asset found for frozen update")
                        return False

                # If not frozen, try pip first (standard behavior)
                # But we need the binary URL for the old method?
                # Actually the old method downloaded the binary 'yt-dlp' file and then tried to pip install 'yt-dlp' from PyPI.
                # That was weird. 'pip install yt-dlp' installs from PyPI, ignoring the downloaded file.
                # Let's clean this up. If not frozen, just run pip install yt-dlp.

                try:
                    import subprocess

                    logger.info("Attempting update via pip...")
                    result = subprocess.run(
                        [
                            sys.executable,
                            "-m",
                            "pip",
                            "install",
                            "--upgrade",
                            "yt-dlp",
                        ],
                        capture_output=True,
                        timeout=60,
                    )

                    if result.returncode == 0:
                        logger.info("✅ yt-dlp updated successfully via pip")
                        return True
                    else:
                        logger.warning(f"pip update failed: {result.stderr.decode()}")
                except Exception as e:
                    logger.warning(f"pip update method failed: {e}")

                # Fallback to wheel installation even for non-frozen if pip fails
                if wheel_asset:
                    logger.info("Attempting direct module replacement from wheel...")
                    return self._install_from_wheel(wheel_asset["browser_download_url"])

                return False

            except Exception as e:
                logger.error(f"Error downloading update: {e}")
                return False

    def update_if_needed(self, force: bool = False) -> bool:
        """Check and update yt-dlp if needed"""
        update_available, current, latest = self.check_for_updates(force=force)

        if update_available:
            logger.info(f"Updating yt-dlp from {current} to {latest}...")
            return self.download_update()

        return False

    def update_in_background(self):
        """Run update check in background thread"""

        def _update():
            try:
                self.update_if_needed()
            except Exception as e:
                logger.error(f"Background update failed: {e}")

        thread = threading.Thread(target=_update, daemon=True)
        thread.start()

    def try_update_on_error(self, error_message: str) -> bool:
        """
        Try to update yt-dlp if error suggests it's outdated

        Returns:
            True if update was attempted, False otherwise
        """
        # Error patterns that suggest yt-dlp is outdated
        outdated_patterns = [
            "unable to extract",
            "unsupported url",
            "no suitable extractor",
            "signature extraction failed",
            "unable to download webpage",
            "requested format not available",
        ]

        error_lower = error_message.lower()

        # Check if error matches outdated patterns
        if any(pattern in error_lower for pattern in outdated_patterns):
            logger.warning(
                "Download error suggests outdated yt-dlp, attempting update..."
            )
            return self.download_update()

        return False


class AppUpdater:
    """Manages full application updates via GitHub Releases"""

    REPO_OWNER = "paterkleomenis"
    REPO_NAME = "Youtube-Downloader-Max-Quality"

    def __init__(self, current_version: str):
        self.current_version = current_version
        self.cache_dir = self._get_cache_dir()
        self.update_lock = threading.Lock()
        self.last_check_file = self.cache_dir / "app_last_check.txt"
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _get_cache_dir(self) -> Path:
        """Get platform-specific cache directory"""
        if sys.platform == "win32":
            base = os.environ.get("LOCALAPPDATA", os.path.expanduser("~"))
            cache_path = Path(base) / "youtube-downloader" / "app-update"
        elif sys.platform == "darwin":
            cache_path = (
                Path.home() / "Library" / "Caches" / "youtube-downloader" / "app-update"
            )
        else:
            base = os.environ.get("XDG_CACHE_HOME", os.path.expanduser("~/.cache"))
            cache_path = Path(base) / "youtube-downloader" / "app-update"
        return cache_path

    def check_for_updates(self) -> Tuple[bool, Optional[str], Optional[str]]:
        """Check if app update is available"""
        try:
            import httpx

            # 1. Fetch latest release from GitHub
            url = f"https://api.github.com/repos/{self.REPO_OWNER}/{self.REPO_NAME}/releases/latest"
            response = httpx.get(url, timeout=5.0, follow_redirects=True)

            if response.status_code != 200:
                logger.warning(f"Failed to check app updates: {response.status_code}")
                return False, self.current_version, None

            data = response.json()
            latest_tag = data.get("tag_name", "").lstrip("v")

            # 2. Compare versions
            if self._compare_versions(self.current_version, latest_tag):
                return True, self.current_version, latest_tag

            return False, self.current_version, latest_tag

        except Exception as e:
            logger.error(f"Error checking app update: {e}")
            return False, self.current_version, None

    def _compare_versions(self, current: str, latest: str) -> bool:
        """Simple semantic version comparison"""
        try:
            c_parts = [int(x) for x in current.split(".")]
            l_parts = [int(x) for x in latest.split(".")]

            # Pad with zeros
            max_len = max(len(c_parts), len(l_parts))
            c_parts.extend([0] * (max_len - len(c_parts)))
            l_parts.extend([0] * (max_len - len(l_parts)))

            return l_parts > c_parts
        except Exception:
            return False

    def download_and_apply_update(self) -> bool:
        """Download new binary and trigger swap process"""
        try:
            import httpx

            # 1. Identify correct asset for current platform
            url = f"https://api.github.com/repos/{self.REPO_OWNER}/{self.REPO_NAME}/releases/latest"
            data = httpx.get(url).json()

            assets = data.get("assets", [])
            target_asset = None

            if sys.platform == "win32":
                target_name = "youtube-downloader-windows-x64.exe"
            elif sys.platform == "linux":
                target_name = "youtube-downloader-linux-x64"
            else:
                return False  # Unsupported for auto-update

            for asset in assets:
                if asset["name"] == target_name:
                    target_asset = asset
                    break

            if not target_asset:
                logger.error("No matching asset found for this platform")
                return False

            # 2. Download new binary
            download_url = target_asset["browser_download_url"]
            logger.info(f"Downloading update from {download_url}...")

            # Determine where the current executable is
            if getattr(sys, "frozen", False):
                current_exe = Path(sys.executable)
            else:
                # Development mode - cannot self-update
                logger.info("Running in development mode, cannot self-update binary")
                return False

            new_exe = current_exe.with_suffix(".new")

            with httpx.stream("GET", download_url, follow_redirects=True) as r:
                with open(new_exe, "wb") as f:
                    for chunk in r.iter_bytes():
                        f.write(chunk)

            # Make executable (Linux)
            if sys.platform != "win32":
                new_exe.chmod(0o755)

            # 3. Create Updater Script
            self._trigger_swap(current_exe, new_exe)
            return True

        except Exception as e:
            logger.error(f"Update failed: {e}")
            return False

    def _trigger_swap(self, current_exe: Path, new_exe: Path):
        """Launch separate script to swap files and restart"""

        # Platform specific updater script
        if sys.platform == "win32":
            # Windows batch script with retry loop
            script_content = f"""
@echo off
set "RETRIES=0"
:loop
timeout /t 1 /nobreak > NUL
move /y "{new_exe}" "{current_exe}" > NUL 2>&1
if errorlevel 1 (
    set /a "RETRIES+=1"
    if %RETRIES% LSS 30 goto loop
)
start "" "{current_exe}"
del "%~f0"
"""
            script_file = current_exe.parent / "update.bat"
            with open(script_file, "w") as f:
                f.write(script_content)

            subprocess.Popen(
                [str(script_file)],
                shell=True,
                creationflags=subprocess.CREATE_NEW_CONSOLE,
            )

        else:  # Linux
            # Linux shell script with retry loop
            sh_content = f"""#!/bin/sh
# Wait for the main process to exit
sleep 2

# Retry loop for moving the file
RETRIES=0
while [ $RETRIES -lt 30 ]; do
    mv -f "{new_exe}" "{current_exe}" > /dev/null 2>&1
    if [ $? -eq 0 ]; then
        break
    fi
    sleep 1
    RETRIES=$((RETRIES+1))
done

chmod +x "{current_exe}"
unset LD_LIBRARY_PATH
"{current_exe}" &
rm -- "$0"
"""
            script_file = current_exe.parent / "update.sh"
            with open(script_file, "w") as f:
                f.write(sh_content)

            os.chmod(script_file, 0o755)

            # Prepare clean environment to avoid library conflicts with PyInstaller
            env = os.environ.copy()
            env.pop("LD_LIBRARY_PATH", None)

            # Use setsid to detach completely if possible, otherwise standard background
            subprocess.Popen(
                ["/bin/sh", str(script_file)], env=env, start_new_session=True
            )

        # Schedule exit in a separate thread to allow API response to return
        def delayed_exit():
            time.sleep(1.0)
            logger.info("Update started, exiting...")
            os._exit(0)

        threading.Thread(target=delayed_exit, daemon=True).start()


# Global updater instance
_updater_instance = None


def get_updater() -> YtDlpUpdater:
    """Get global updater instance"""
    global _updater_instance
    if _updater_instance is None:
        _updater_instance = YtDlpUpdater()
    return _updater_instance


def check_updates_on_startup():
    """Run update check on application startup"""
    updater = get_updater()
    updater.update_in_background()
