"""
Core functionality for the Telegram bot.

This module implements various helpers such as video downloading via yt-dlp
with concurrent fragment fetching, PDF downloading with aiohttp, duration
calculation via ffprobe, and Telegram upload routines for documents and
videos.  It also defines a constant for controlling fragment concurrency.

NOTE: Do not remove credit.  Telegram: @VJ_Botz, YouTube: https://youtube.com/@Tech_VJ
"""

from __future__ import annotations

import os
import time
import datetime
import aiohttp
import aiofiles
import asyncio
import logging
import requests
import subprocess
import concurrent.futures

from typing import Optional

from utils import progress_bar, hrb, hrt  # noqa: F401: imported for type hints
from pyrogram import Client
from pyrogram.types import Message

# Number of HLS fragments to download concurrently.  You can set
# CONCURRENT_FRAGMENTS in the environment to override the default.
CONCURRENT_FRAGMENTS = int(os.environ.get("CONCURRENT_FRAGMENTS", "10"))


def duration(filename: str) -> float:
    """Return the duration of a media file using ffprobe.

    If ffprobe is not installed on the system, log a warning and return 0.
    """
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
    except FileNotFoundError:
        logging.warning(
            f"ffprobe not found. Returning 0 duration for file {filename}. "
            "Install the ffmpeg package to enable accurate duration."
        )
        return 0.0
    except (TypeError, ValueError):
        return 0.0


def exec(cmd: list[str]) -> str:
    """Execute a shell command synchronously and return its output."""
    process = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    output = process.stdout.decode(errors="ignore")
    print(output)
    return output


def pull_run(work: int, cmds: list[list[str]]):
    """Run multiple shell commands concurrently using a thread pool."""
    with concurrent.futures.ThreadPoolExecutor(max_workers=work) as executor:
        print("Waiting for tasks to complete")
        list(executor.map(exec, cmds))


async def aio(url: str, name: str) -> str:
    """Download a URL to a PDF file asynchronously using aiohttp."""
    k = f"{name}.pdf"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            if resp.status == 200:
                f = await aiofiles.open(k, mode="wb")
                await f.write(await resp.read())
                await f.close()
    return k


async def download(url: str, name: str) -> str:
    """Download a URL to a PDF file asynchronously using aiohttp."""
    ka = f"{name}.pdf"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            if resp.status == 200:
                f = await aiofiles.open(ka, mode="wb")
                await f.write(await resp.read())
                await f.close()
    return ka


async def run(cmd: str) -> Optional[str]:
    """Run a shell command asynchronously and return output or None."""
    proc = await asyncio.create_subprocess_shell(
        cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    print(f"[{cmd!r} exited with {proc.returncode}]")
    if proc.returncode != 0:
        return None
    if stdout:
        return stdout.decode(errors="ignore")
    if stderr:
        return stderr.decode(errors="ignore")
    return None


def human_readable_size(size: int, decimal_places: int = 2) -> str:
    """Return a human‑readable file size string."""
    for unit in ["B", "KB", "MB", "GB", "TB", "PB"]:
        if size < 1024.0 or unit == "PB":
            break
        size /= 1024.0
    return f"{size:.{decimal_places}f} {unit}"


def time_name() -> str:
    """Generate a timestamped file name for temporary video files."""
    date = datetime.date.today()
    now = datetime.datetime.now()
    current_time = now.strftime("%H%M%S")
    return f"{date} {current_time}.mp4"


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

    Instead of invoking ``yt-dlp`` via the command line and parsing stdout,
    this function uses the Python API and a progress hook to provide
    real‑time feedback to the user.  The progress bar is updated on
    ``reply`` using the shared ``progress_bar`` helper.  The ``fmt``
    parameter controls the format string passed to yt‑dlp; if ``is_jw`` is
    True the default format is used.  The file is saved with base name
    ``name`` and an appropriate extension determined by yt‑dlp.  Returns
    the full path to the downloaded file.
    """
    import yt_dlp  # Imported here to avoid overhead when not downloading

    loop = asyncio.get_event_loop()
    start_time = time.time()

    # Define a progress hook for yt‑dlp.  This hook will be called
    # frequently by yt‑dlp as fragments are downloaded.  We schedule
    # execution of ``progress_bar`` in the main event loop thread.
    def hook(d: dict):
        if d.get("status") == "downloading":
            current = d.get("downloaded_bytes") or 0
            # For HLS streams, total_bytes may be missing; use total_bytes_estimate
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            # Schedule an asynchronous call to progress_bar safely across threads
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
            # Once finished, force a final update with all bytes downloaded
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

    # Build yt‑dlp options
    ytdl_opts: dict = {
        "outtmpl": f"{name}.%(ext)s",
        "noplaylist": True,
        "progress_hooks": [hook],
        # Retrying settings
        "retries": 25,
        "fragment_retries": 25,
        # Concurrency settings for HLS
        "concurrent_fragment_downloads": CONCURRENT_FRAGMENTS,
        "hls_prefer_native": True,
        # External downloader settings for non‑HLS
        "external_downloader": "aria2c",
        "external_downloader_args": {
            "aria2c": ["-c", "-x", "16", "-s", "16", "-k", "1M"],
        },
        # Silence yt‑dlp output; progress is managed via hooks
        "quiet": True,
        "no_warnings": True,
    }
    # Set format string if provided and not JW
    if fmt and not is_jw:
        ytdl_opts["format"] = fmt
    # Perform the download in a background thread to avoid blocking the
    # event loop.  yt‑dlp is synchronous, so this call will block.  We
    # capture any exceptions and re‑raise them in the async context.
    def blocking_download():
        with yt_dlp.YoutubeDL(ytdl_opts) as ydl:
            return ydl.download([url])

    await loop.run_in_executor(None, blocking_download)
    # After download completes, determine the actual file path.  yt‑dlp
    # chooses the extension based on container format.  Search common
    # extensions to find the file.  Use the first match.
    possible_extensions = [".mp4", ".webm", ".mkv", ".mp4.webm"]
    for ext in possible_extensions:
        candidate = f"{name}{ext}"
        if os.path.isfile(candidate):
            return candidate
    # As a fallback, assume an mp4 extension if none of the above exists
    fallback = f"{name}.mp4"
    return fallback


async def send_doc(
    bot: Client,
    m: Message,
    file_path: str,
    caption: str,
) -> None:
    """Send a document to Telegram and delete the temporary file."""
    reply = await m.reply_text(f"Uploading » `{os.path.basename(file_path)}`")
    start_time = time.time()
    try:
        await m.reply_document(file_path, caption=caption)
    finally:
        await reply.delete(True)
        # Remove local file after sending
        os.remove(file_path)
        time.sleep(1)


async def send_vid(
    bot: Client,
    m: Message,
    filename: str,
    thumb: str,
    batch_name: str,
    subject_name: str,
    quality: str,
    display_name: str,
    prog,
) -> None:
    """
    Send a video to Telegram with a rich caption and trimming the first 15 seconds.

    This function generates a thumbnail, attempts to trim the first 15 seconds off
    the video, then renames the file to a user-friendly name (without numbering),
    and uploads either the trimmed file (if successful) or the original.  After
    upload the temporary files are removed.
    """
    # Generate thumbnail at 12 seconds for preview
    thumb_path = f"{filename}.jpg"
    subprocess.run(
        f'ffmpeg -y -i "{filename}" -ss 00:00:12 -vframes 1 "{thumb_path}"',
        shell=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    # Attempt to trim the first 15 seconds
    trimmed_path = f"{os.path.splitext(filename)[0]}.trim.mp4"
    subprocess.run(
        f'ffmpeg -y -i "{filename}" -ss 00:00:15 -c copy "{trimmed_path}"',
        shell=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    # Choose which file to upload: trimmed if exists, else original
    if os.path.exists(trimmed_path):
        file_to_upload = trimmed_path
        # Remove original if trimming succeeded
        try:
            os.remove(filename)
        except FileNotFoundError:
            pass
    else:
        file_to_upload = filename

    # Rename the file to a clean display name (without index) for upload
    upload_path = f"{display_name}.mp4"
    # Avoid overwriting if the file already exists
    if file_to_upload != upload_path:
        if os.path.exists(upload_path):
            os.remove(upload_path)
        os.rename(file_to_upload, upload_path)
        file_to_upload = upload_path

    # Inform the user that upload has started
    reply = await m.reply_text(
        f"<b>Uploading…</b>\n\n━━━━━━━━━━━━━━━\n<b>{display_name}\n━━━━━━━━━━━━━━━</b>",
        disable_web_page_preview=True,
    )

    # Compute size and duration based on the file that will be uploaded
    file_size = os.path.getsize(file_to_upload)
    size_readable = hrb(file_size)
    dur_seconds = int(duration(file_to_upload))
    dur_readable = hrt(dur_seconds)

    # Build the caption
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

    # Choose thumbnail: if user provided a thumbnail, use it; else use generated
    final_thumb = thumb_path if thumb == "no" else thumb
    start_time = time.time()

    try:
        # Only provide duration if it is greater than zero; otherwise omit it
        if dur_seconds > 0:
            await m.reply_video(
                file_to_upload,
                caption=caption,
                supports_streaming=True,
                height=720,
                width=1280,
                thumb=final_thumb,
                duration=dur_seconds,
                progress=progress_bar,
                progress_args=(reply, start_time, display_name, "Uploading"),
            )
        else:
            await m.reply_video(
                file_to_upload,
                caption=caption,
                supports_streaming=True,
                height=720,
                width=1280,
                thumb=final_thumb,
                progress=progress_bar,
                progress_args=(reply, start_time, display_name, "Uploading"),
            )
    except Exception:
        # If video upload fails for any reason, fall back to document upload
        await m.reply_document(
            file_to_upload,
            caption=caption,
            progress=progress_bar,
            progress_args=(reply, start_time, display_name, "Uploading"),
        )

    # Remove whichever file was uploaded
    try:
        os.remove(file_to_upload)
    except FileNotFoundError:
        pass
    # Remove generated thumbnail if no custom thumb was supplied
    if thumb == "no" and os.path.exists(thumb_path):
        os.remove(thumb_path)
    await reply.delete(True)
