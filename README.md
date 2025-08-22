# YouTube Video/Audio Downloader

A FastAPI application that enables you to download both videos and audio from YouTube (and other sites supported by [yt-dlp]) in various resolutions and formats

## Table of Contents
1. [Features](#features)
2. [Installation](#installation)
3. [Usage](#usage)
4. [Project Structure](#project-structure)

---

## Features
- Download YouTube videos in multiple resolutions (MP4).
- Download audio in various formats (WEBM, MP3, OGG, AAC, WAV, FLAC, M4A).
- Real-time download progress updates.
- Simple UI built with FastAPI templates, JavaScript, and CSS.

## Installation

1. Clone the repository or download the project files:
   ```bash
   git clone https://github.com/paterkleomenis/Youtube-Downloader-Max-Quality
   ```
2. Navigate to the project directory:
   ```bash
   cd Youtube-Downloader-Max-Quality
   ```
3. Create and activate a virtual environment (recommended):
   ```bash
   python -m venv venv
   ```
   ```bash
   source venv/bin/activate   # Linux/macOS
   ```
   ```bash
   venv\Scripts\activate      # Windows
   ```
4. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

   Or individually:
   ```bash
   pip install fastapi uvicorn yt-dlp pathvalidate jinja2 python-multipart
   ```

## Usage

1. Make sure you have [FFmpeg](https://ffmpeg.org/) installed and available in your system's PATH. FFmpeg is required for audio conversion to certain formats (e.g., MP3, AAC, etc.).
2. Start the FastAPI server using the following command:
   ```bash
   uvicorn app:app --host 0.0.0.0 --port 5000 --reload
   ```
3. Open your browser and navigate to:
   ```
   http://localhost:5000
   ```
4. Enter the YouTube (or other supported site) URL in the text field and click "Search".
5. The app will display the available resolutions and a button to download audio in multiple formats.

## Project Structure

- `app.py`:
  The main FastAPI application, containing routes and logic for fetching video information, downloading files, and handling conversion.

- `templates/`:
  Contains the Jinja2 templates that define the frontend interface (index.html).

- `static/`:
  Holds static files including CSS (`styles.css`), JavaScript (`script.js`), and image assets (in `/images`).
