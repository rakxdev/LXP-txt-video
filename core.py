"""
Core functionality for the Telegram bot.

This module implements various helpers such as video downloading via yt‑dLP,
duration calculation via ffprobe, and Telegram upload routines for videos.

NOTE: Do not remove credit.  Telegram: @VJ_Botz, YouTube: https://youtube.com/@Tech_VJ
"""

from __future__ import annotations

import os
import time
import datetime
import asyncio
import logging
import subprocess
from typing import Optional

from pyrogram import Client
from pyrogram.types import Message
from utils import progress_bar, hrb, hrt

# Number of HLS fragments to download concurrently.
CONCURRENT_FRAGMENTS = int(os.environ.get("CONCURRENT_FRAGMENTS", "10"))


def duration(filename: str) -> float:
    """Return the duration of a media file using ffprobe (returns 0 if missing)."""
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                filename,
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        return float(result.stdout)
    except Exception:
        return 0.0


async def download_video(
    url: str,
    fmt: str,
    name: str,
    reply: Message,
    display_name: str,
    is_jw: bool = False,
) -> str:
    """
    Download a video using the Python ``yt_dlp`` API with a dynamic progress bar.

    It uses yt‑dLP’s Python API and updates ``reply`` with a progress bar.  The file
    is saved with base name ``name`` and an extension chosen by yt‑dLP.
    """
    import yt_dlp  # Import inside to avoid overhead when unused

    loop = asyncio.get_event_loop()
    start_time = time.time()

    def hook(d: dict):
        if d.get("status") == "downloading":
            current = d.get("downloaded_bytes") or 0
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            loop.call_soon_threadsafe(
                asyncio.create_task,
                progress_bar(
                    current,
                    total,
                    reply,
                    start_time,
                    display_name,
                    "Downloading",
                ),
            )
        elif d.get("status") == "finished":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            loop.call_soon_threadsafe(
                asyncio.create_task,
                progress_bar(
                    total,
                    total,
                    reply,
                    start_time,
                    display_name,
                    "Downloading",
                ),
            )

    ytdl_opts: dict = {
        "outtmpl": f"{name}.%(ext)s",
        "noplaylist": True,
        "progress_hooks": [hook],
        "retries": 25,
        "fragment_retries": 25,
        "concurrent_fragment_downloads": CONCURRENT_FRAGMENTS,
        "hls_prefer_native": True,
        "external_downloader": "aria2c",
        "external_downloader_args": {
            "aria2c": ["-c", "-x", "16", "-s", "16", "-k", "1M"],
        },
        "quiet": True,
        "no_warnings": True,
    }
    if fmt and not is_jw:
        ytdl_opts["format"] = fmt

    def blocking_download():
        with yt_dlp.YoutubeDL(ytdl_opts) as ydl:
            return ydl.download([url])

    await loop.run_in_executor(None, blocking_download)
    for ext in [".mp4", ".webm", ".mkv", ".mp4.webm"]:
        candidate = f"{name}{ext}"
        if os.path.isfile(candidate):
            return candidate
    return f"{name}.mp4"


async def send_vid(
    bot: Client,
    m: Message,
    filename: str,
    thumb: str,
    batch_name: str,
    subject_name: str,
    quality: str,
    display_name: str,
    progress_msg: Optional[Message] = None,
) -> None:
    """
    Send a video to Telegram with a rich caption and trimming the first 15 seconds.

    Thumbnail behaviour:
      • If ``thumb`` is not "no" and the file exists, it is used as the video’s thumbnail.
      • If ``thumb`` is "no" or the file does not exist, no thumbnail is attached.
      • This function does NOT generate a thumbnail from the video itself.
    """
    # Attempt to trim the first 15 seconds
    trimmed_path = f"{os.path.splitext(filename)[0]}.trim.mp4"
    subprocess.run(
        f'ffmpeg -y -i "{filename}" -ss 00:00:15 -c copy "{trimmed_path}"',
        shell=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    # Choose trimmed file if available
    if os.path.exists(trimmed_path):
        file_to_upload = trimmed_path
        try:
            os.remove(filename)
        except FileNotFoundError:
            pass
    else:
        file_to_upload = filename

    # Rename to clean display name
    upload_path = f"{display_name}.mp4"
    if file_to_upload != upload_path:
        if os.path.exists(upload_path):
            os.remove(upload_path)
        os.rename(file_to_upload, upload_path)
        file_to_upload = upload_path

    file_size = os.path.getsize(file_to_upload)
    size_readable = hrb(file_size)
    dur_seconds = int(duration(file_to_upload))
    dur_readable = hrt(dur_seconds)

    caption = (
        f"📦 <b>Batch:</b> <b>{batch_name}</b>\n"
        f"📘 <b>Subject:</b> <b>{subject_name}</b>\n"
        f"──────────────────────────\n"
        f"🎬 <b>File:</b> <b>{display_name}</b>\n"
        f"──────────────────────────\n"
        f"📁 <b>Size:</b> <i>{size_readable}</i>\n"
        f"⏱️ <b>Duration:</b> <i>{dur_readable}</i>\n"
        f"📽️ <b>Quality:</b> <i>{quality}</i>\n"
        f"──────────────────────────\n\n"
        f"🧑‍💻 <b>Uploaded by:</b> <a href='https://t.me/Itz_lumino'>๏ ʟᴜᴍɪɴᴏ ⇗ ˣᵖ</a>\n"
        f"📢 <b>Join Updates:</b> <spoiler>@luminoxpp</spoiler>"
    )

    # Only use a thumbnail if a file path was provided AND it exists
    use_thumb = thumb != "no" and os.path.exists(thumb)
    start_time = time.time()

    try:
        if dur_seconds > 0:
            if use_thumb:
                await m.reply_video(
                    file_to_upload,
                    caption=caption,
                    supports_streaming=True,
                    height=720,
                    width=1280,
                    thumb=thumb,
                    duration=dur_seconds,
                    progress=progress_bar,
                    progress_args=(progress_msg, start_time, display_name, "Uploading"),
                )
            else:
                await m.reply_video(
                    file_to_upload,
                    caption=caption,
                    supports_streaming=True,
                    height=720,
                    width=1280,
                    duration=dur_seconds,
                    progress=progress_bar,
                    progress_args=(progress_msg, start_time, display_name, "Uploading"),
                )
        else:
            if use_thumb:
                await m.reply_video(
                    file_to_upload,
                    caption=caption,
                    supports_streaming=True,
                    height=720,
                    width=1280,
                    thumb=thumb,
                    progress=progress_bar,
                    progress_args=(progress_msg, start_time, display_name, "Uploading"),
                )
            else:
                await m.reply_video(
                    file_to_upload,
                    caption=caption,
                    supports_streaming=True,
                    height=720,
                    width=1280,
                    progress=progress_bar,
                    progress_args=(progress_msg, start_time, display_name, "Uploading"),
                )
    except Exception:
        # Fallback to document upload if video upload fails
        await m.reply_document(
            file_to_upload,
            caption=caption,
            progress=progress_bar,
            progress_args=(progress_msg, start_time, display_name, "Uploading"),
        )

    # Clean up uploaded file
    try:
        os.remove(file_to_upload)
    except FileNotFoundError:
        pass
