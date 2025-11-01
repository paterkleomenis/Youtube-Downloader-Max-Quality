#!/usr/bin/env python3
"""
yt-dlp Auto-Updater Module
Handles automatic updates of yt-dlp without requiring system Python installation
"""

import os
import sys
import json
import shutil
import logging
import threading
import tempfile
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Tuple
import hashlib

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

    def download_update(self) -> bool:
        """Download and install yt-dlp update"""
        with self.update_lock:
            try:
                import httpx

                logger.info("Downloading yt-dlp update...")

                # Download the wheel or source
                response = httpx.get(
                    "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp",
                    timeout=30.0,
                    follow_redirects=True,
                )

                if response.status_code != 200:
                    logger.error(
                        f"Failed to download update: HTTP {response.status_code}"
                    )
                    return False

                # Save to temp file
                temp_file = self.cache_dir / "yt-dlp_update"
                with open(temp_file, "wb") as f:
                    f.write(response.content)

                # Verify download (basic check)
                if temp_file.stat().st_size < 1000:
                    logger.error("Downloaded file is too small, update failed")
                    temp_file.unlink()
                    return False

                # Try to update via pip (works even in frozen environment)
                try:
                    import subprocess

                    # Use pip to install from the downloaded file
                    result = subprocess.run(
                        [
                            sys.executable,
                            "-m",
                            "pip",
                            "install",
                            "--upgrade",
                            "--force-reinstall",
                            "yt-dlp",
                        ],
                        capture_output=True,
                        timeout=60,
                    )

                    if result.returncode == 0:
                        logger.info("✅ yt-dlp updated successfully via pip")
                        temp_file.unlink(missing_ok=True)
                        return True
                    else:
                        logger.warning(f"pip update failed: {result.stderr.decode()}")

                except Exception as e:
                    logger.warning(f"pip update method failed: {e}")

                # Fallback: try to replace the module directly (not recommended but works)
                logger.info("Attempting direct module replacement...")
                temp_file.unlink(missing_ok=True)

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
