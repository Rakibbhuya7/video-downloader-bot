"""
yt-dlp download helpers with async support.
"""
import asyncio
import os
import re
from pathlib import Path

import yt_dlp

from config import DOWNLOAD_DIR

os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# ── Quality format strings ─────────────────────────────────────────────────────
FORMATS = {
    "360p": (
        "bestvideo[height<=360][ext=mp4]+bestaudio[ext=m4a]"
        "/bestvideo[height<=360]+bestaudio"
        "/best[height<=360][ext=mp4]/best[height<=360]"
    ),
    "720p": (
        "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]"
        "/bestvideo[height<=720]+bestaudio"
        "/best[height<=720][ext=mp4]/best[height<=720]"
    ),
    "1080p": (
        "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]"
        "/bestvideo[height<=1080]+bestaudio"
        "/best[height<=1080][ext=mp4]/best[height<=1080]"
    ),
    "mp3": "bestaudio/best",
}


def _sanitize(name: str, max_len: int = 60) -> str:
    name = re.sub(r'[\\/*?:"<>|]', "", name)
    return name[:max_len].strip()


def get_info(url: str) -> dict | None:
    opts = {"quiet": True, "no_warnings": True, "skip_download": True}
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            return ydl.extract_info(url, download=False)
    except Exception:
        return None


def _build_opts(quality: str, out_template: str) -> dict:
    fmt = FORMATS[quality]
    opts: dict = {
        "format": fmt,
        "outtmpl": out_template,
        "quiet": True,
        "no_warnings": True,
        "concurrent_fragment_downloads": 4,
        "retries": 5,
        "fragment_retries": 5,
    }
    if quality == "mp3":
        opts["postprocessors"] = [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "320",
            }
        ]
        opts["writethumbnail"] = True
    else:
        opts["merge_output_format"] = "mp4"
        opts["writethumbnail"] = True
        opts["postprocessors"] = [
            {"key": "FFmpegThumbnailsConvertor", "format": "jpg"}
        ]
    return opts


async def download(url: str, quality: str, job_id: str) -> dict:
    """
    Download *url* in *quality* into a job-specific subfolder.
    Returns {path, thumb_path, title, ext}.
    """
    job_dir = os.path.join(DOWNLOAD_DIR, job_id)
    os.makedirs(job_dir, exist_ok=True)

    out_template = os.path.join(job_dir, "%(title)s.%(ext)s")
    opts = _build_opts(quality, out_template)

    loop = asyncio.get_event_loop()

    def _dl():
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            return info

    info = await loop.run_in_executor(None, _dl)

    # Find the main media file
    files = list(Path(job_dir).iterdir())
    media_file = None
    thumb_file = None

    # yt-dlp writes thumbnail as .jpg / .webp alongside the media
    for f in files:
        if f.suffix.lower() in (".mp4", ".mkv", ".webm", ".mp3", ".m4a", ".ogg"):
            media_file = f
        elif f.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp"):
            thumb_file = f

    if media_file is None:
        # fallback: pick largest file that isn't a thumbnail
        candidates = [
            f for f in files
            if f.suffix.lower() not in (".jpg", ".jpeg", ".png", ".webp")
        ]
        if candidates:
            media_file = max(candidates, key=lambda f: f.stat().st_size)

    if media_file is None:
        raise FileNotFoundError("yt-dlp did not produce a media file.")

    return {
        "path": str(media_file),
        "thumb_path": str(thumb_file) if thumb_file else None,
        "title": info.get("title", "video"),
        "ext": media_file.suffix.lstrip("."),
        "duration": info.get("duration", 0),
    }
