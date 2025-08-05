"""
Utility functions for the Telegram bot.

This module contains a human‑readable file size converter, a human
time converter, and a progress bar function used to update messages
during downloads or uploads.  It also implements a simple timer to
prevent flooding Telegram with too frequent edits.

NOTE: Do not remove credit.  Telegram: @VJ_Botz, YouTube: https://youtube.com/@Tech_VJ
"""

import time
from datetime import timedelta
from typing import Optional

from pyrogram.errors import FloodWait
import psutil  # Added for system statistics


class Timer:
    """A simple timer to control message update frequency."""

    def __init__(self, time_between: int = 5) -> None:
        self.start_time = time.time()
        self.time_between = time_between

    def can_send(self) -> bool:
        """Return True if enough time has passed since last send."""
        if time.time() > (self.start_time + self.time_between):
            self.start_time = time.time()
            return True
        return False


def hrb(value: float, digits: int = 2, delim: str = "", postfix: str = "") -> str:
    """Return a human‑readable file size from bytes."""
    if value is None:
        return "0B"
    chosen_unit = "B"
    for unit in ("KiB", "MiB", "GiB", "TiB"):
        if value > 1000:
            value /= 1024
            chosen_unit = unit
        else:
            break
    return f"{value:.{digits}f}" + delim + chosen_unit + postfix


def hrt(seconds: float, precision: int = 0) -> str:
    """Return a human‑readable time delta as a string."""
    pieces = []
    value = timedelta(seconds=seconds)
    if value.days:
        pieces.append(f"{value.days}d")
    seconds = value.seconds
    if seconds >= 3600:
        hours = seconds // 3600
        pieces.append(f"{hours}h")
        seconds -= hours * 3600
    if seconds >= 60:
        minutes = seconds // 60
        pieces.append(f"{minutes}m")
        seconds -= minutes * 60
    if seconds > 0 or not pieces:
        pieces.append(f"{seconds}s")
    if not precision:
        return "".join(pieces)
    return "".join(pieces[:precision])


# utils.py
timer = Timer(time_between=3)


async def progress_bar(
    current: int,
    total: int,
    reply,
    start: float,
    display_name: str = "",
    mode: str = "Downloading",
) -> None:
    """
    Edit a Telegram message with an updated progress bar.

    This function supports both downloading and uploading progress.  The
    ``mode`` parameter should be either ``"Downloading"`` or
    ``"Uploading"``.  ``display_name`` is used to show the file name
    alongside the progress bar.  To avoid spamming Telegram with edits,
    the message is updated only once every few seconds.
    """
    # Don't update too frequently
    if not timer.can_send():
        return
    now = time.time()
    diff = now - start
    if diff < 1:
        return

    # Compute progress metrics.  Guard against division by zero when the total
    # size is unknown (total == 0).  If ``total`` is zero, treat the
    # percentage as 0 and leave the bar empty, with ETA unknown.
    elapsed_time = round(diff)
    speed = current / elapsed_time if elapsed_time > 0 else 0
    if total > 0:
        percent = current * 100 / total
        remaining_bytes = total - current
        eta_seconds = remaining_bytes / speed if speed > 0 else -1
        total_str = hrb(total)
        bar_length = 12
        completed_len = int(current * bar_length / total)
        remain_len = bar_length - completed_len
    else:
        percent = 0.0
        remaining_bytes = 0
        eta_seconds = -1
        total_str = "?B"
        bar_length = 12
        completed_len = 0
        remain_len = bar_length
    eta_str = hrt(eta_seconds, precision=2) if eta_seconds > 0 else "-"
    speed_str = f"{hrb(speed)}/s"
    current_str = hrb(current)
    filled_char = "⬢"
    empty_char = "⬡"
    bar = filled_char * completed_len + empty_char * remain_len

    # Gather system stats
    cpu = psutil.cpu_percent()
    memory = psutil.virtual_memory()
    disk = psutil.disk_usage("/")

    # Convert memory and disk usage to used/total GiB
    def to_gib(v: float) -> str:
        return f"{v / 1024**3:.1f} GiB"
    ram_usage = f"{to_gib(memory.used)} / {to_gib(memory.total)}"
    disk_usage = f"{to_gib(disk.used)} / {to_gib(disk.total)}"

    # Build header based on mode and display name
    header = f"📥 {mode}"
    if display_name:
        header = f"📥 {mode}: \n\n📁 {display_name}"

    bytes_label = "Uploaded" if mode.lower().startswith("up") else "Downloaded"

    # Compose the message with spacing and separators
    text = (
        f"<b>{header}</b>\n"
        f"[{bar}] {percent:.2f}%\n"
        f"──────────────────────────\n\n"
        f"⏱️ <b>Elapsed:</b> {hrt(diff, precision=2)} | ⏳ <b>ETA:</b> {eta_str}\n"
        f"📦 <b>{bytes_label}:</b> {current_str} / {total_str}\n"
        f"🚀 <b>Speed:</b> {speed_str}\n\n"
        f"──────────────────────────\n"
        f"🖥️ <b>CPU:</b> {cpu:.1f}%\n"
        f"💾 <b>Disk:</b> {disk_usage}\n"
        f"🧠 <b>RAM:</b> {ram_usage}"
    )

    try:
        await reply.edit(text, disable_web_page_preview=True)
    except FloodWait as e:
        time.sleep(e.x)
