# -*- mode: python ; coding: utf-8 -*-
import sys
import os
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None

# Collect all data files from templates and static directories
datas = [
    ('templates', 'templates'),
    ('static', 'static'),
]

# Add FFmpeg binaries if they exist
import os
if os.path.exists('ffmpeg_bin'):
    if sys.platform == 'win32':
        datas.append(('ffmpeg_bin/ffmpeg.exe', 'ffmpeg_bin'))
        datas.append(('ffmpeg_bin/ffprobe.exe', 'ffmpeg_bin'))
    else:
        datas.append(('ffmpeg_bin/ffmpeg', 'ffmpeg_bin'))
        datas.append(('ffmpeg_bin/ffprobe', 'ffmpeg_bin'))

# Collect hidden imports for yt-dlp and other dependencies
hiddenimports = [
    'uvicorn.logging',
    'uvicorn.loops',
    'uvicorn.loops.auto',
    'uvicorn.protocols',
    'uvicorn.protocols.http',
    'uvicorn.protocols.http.auto',
    'uvicorn.protocols.websockets',
    'uvicorn.protocols.websockets.auto',
    'uvicorn.lifespan',
    'uvicorn.lifespan.on',
    'yt_dlp',
    'yt_dlp.extractor',
    'yt_dlp.downloader',
    'fastapi',
    'jinja2',
    'pydantic',
    'pydantic_settings',
    'slowapi',
    'starlette',
    'pathvalidate',
    'aiofiles',
    'httpx',
    'structlog',
    # Hardening deps
    'Cryptodome',  # pycryptodomex
    'websockets',
    'mutagen',
    'brotli',
]

# Collect all yt-dlp extractors
hiddenimports.extend(collect_submodules('yt_dlp.extractor'))

# Create runtime hook to fix paths
runtime_hook_content = """
import sys
import os

# Get the path where PyInstaller extracts files
if getattr(sys, 'frozen', False):
    # Running as compiled executable
    bundle_dir = sys._MEIPASS
    # Change to the bundle directory so relative paths work
    os.chdir(bundle_dir)

    # Add FFmpeg to PATH
    ffmpeg_path = os.path.join(bundle_dir, 'ffmpeg_bin')
    if os.path.exists(ffmpeg_path):
        os.environ['PATH'] = ffmpeg_path + os.pathsep + os.environ.get('PATH', '')
"""

# Write runtime hook file
with open('pyi_runtime_hook.py', 'w') as f:
    f.write(runtime_hook_content)

a = Analysis(
    ['run.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=['pyi_runtime_hook.py'],
    excludes=[
        'matplotlib',
        'tkinter',
        'pygame',
        'PyQt5',
        'numpy',
        'scipy',
        'pandas',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='youtube-downloader',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)
