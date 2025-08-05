"""
Entry point for the Telegram bot.

This module sets up a Pyrogram client and defines handlers for the /start,
/stop and /upload commands.  It orchestrates reading a .txt file of
links, prompting the user for additional metadata (start index, batch
name, resolution and subject), downloading each item using yt‑dlp via
``core.download_video``, trimming the video, and finally uploading it to
Telegram with a rich caption.

NOTE: Do not remove credit.  Telegram: @VJ_Botz, YouTube: https://youtube.com/@Tech_VJ
"""

import os
import re
import sys
import time
import asyncio
import requests
from subprocess import getstatusoutput

from aiohttp import ClientSession
from pyromod import listen

from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.errors import FloodWait

import core as helper
from utils import hrb, hrt  # noqa: F401: imported for side effects
from vars import API_ID, API_HASH, BOT_TOKEN


# Initialize the Pyrogram bot
bot = Client(
    "vj_txt_leech_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
)

# Default thumbnail URL.  This is used automatically for all videos; the
# user is not prompted to provide their own thumbnail.  If you wish to
# change the default thumbnail, simply modify this constant.
DEFAULT_THUMB_URL = "https://i.ibb.co/jkQJdwCj/th.png"


@bot.on_message(filters.command(["start"]))
async def start(bot: Client, m: Message):
    """Send a welcome message with usage instructions."""
    await m.reply_text(
        f"<b>Hello {m.from_user.mention}</b>\n\n"
        "I am a bot for downloading links from your .TXT file and then uploading "
        "those files on Telegram.  To use me, send /upload and follow the steps.\n\n"
        "Use /stop to stop any ongoing task.",
        disable_web_page_preview=True,
    )


@bot.on_message(filters.command("stop"))
async def restart_handler(_, m: Message):
    """Restart the bot when /stop is issued."""
    await m.reply_text("**Stopped**", True)
    os.execl(sys.executable, sys.executable, *sys.argv)


@bot.on_message(filters.command(["upload"]))
async def upload(bot: Client, m: Message):
    """
    Handle the /upload command.

    This handler asks the user for a .txt file, reads the links, prompts
    for metadata (start index, batch name, resolution and subject), and
    then iterates over each link to download and upload it with a rich
    caption and trimmed video.
    """
    # Prompt for the .txt file
    editable = await m.reply_text("📄 Please send me your .txt file containing the links.")
    input_msg: Message = await bot.listen(editable.chat.id)
    txt_path = await input_msg.download()
    await input_msg.delete(True)

    # Prepare a downloads directory (not strictly necessary but good practice)
    path = f"./downloads/{m.chat.id}"
    os.makedirs(path, exist_ok=True)

    # Parse the text file
    try:
        with open(txt_path, "r", encoding="utf-8") as f:
            content = f.read().strip()
        lines = [line for line in content.split("\n") if line.strip()]
        links: list[list[str]] = []
        for line in lines:
            # Split only at the first occurrence of '://'.  The part before
            # contains the name, the part after is the URL without scheme.
            parts = line.split("://", 1)
            if len(parts) == 2:
                links.append(parts)
            else:
                # If no scheme found, treat entire line as URL with empty name
                links.append(["", parts[0]])
        os.remove(txt_path)
    except Exception:
        await m.reply_text("❌ Invalid file input.")
        os.remove(txt_path)
        return

    # Ask user from which index to start downloading
    await editable.edit(
        f"**Tᴏᴛᴀʟ ʟɪɴᴋs ғᴏᴜɴᴅ:** <b>{len(links)}</b>\n\n"
        "**Sᴇɴᴅ ᴛʜᴇ sᴛᴀʀᴛɪɴɢ ɪɴᴅᴇx** (1-based)",
        disable_web_page_preview=True,
    )
    input_start: Message = await bot.listen(editable.chat.id)
    raw_start = input_start.text.strip()
    await input_start.delete(True)
    # Validate starting index
    try:
        start_index = int(raw_start)
        if start_index < 1 or start_index > len(links):
            raise ValueError
    except Exception:
        start_index = 1

    # Ask for batch name
    await editable.edit("📦 Please enter the batch name (e.g. 'Batch 1')")
    input_batch: Message = await bot.listen(editable.chat.id)
    batch_name = input_batch.text.strip()
    await input_batch.delete(True)

    # Ask for resolution
    await editable.edit(
        "Please choose a resolution (144, 240, 360, 480, 720, 1080):"
    )
    input_res: Message = await bot.listen(editable.chat.id)
    raw_res = input_res.text.strip()
    await input_res.delete(True)
    res_map = {
        "144": "256x144",
        "240": "426x240",
        "360": "640x360",
        "480": "854x480",
        "720": "1280x720",
        "1080": "1920x1080",
    }
    # quality_label is used for display and caption (append 'p' for human‑readable)
    # If the user enters an unsupported resolution, fall back to "UN"
    if raw_res in res_map:
        quality = raw_res
        quality_label = raw_res + "p"
    else:
        quality = "UN"
        quality_label = raw_res

    # Ask for subject name
    await editable.edit("📘 Please enter the subject name (e.g. 'Physics')")
    input_subject: Message = await bot.listen(editable.chat.id)
    subject_name = input_subject.text.strip()
    await input_subject.delete(True)

    # Use a fixed default thumbnail for all uploads.  The user is not prompted
    # to provide a custom thumbnail.  Download the thumbnail to a local file
    # once per upload command.  If you wish to change the default, modify
    # ``DEFAULT_THUMB_URL`` defined near the top of this file.
    await editable.edit(
        "📎 A default thumbnail will be used for all videos.",
        disable_web_page_preview=True,
    )
    # Remove the informational message
    await editable.delete()
    # Download the default thumbnail to a local file asynchronously.  We use
    # aiohttp to fetch the image without blocking the event loop.  If
    # downloading fails (e.g. network error), ``thumb_path`` falls back to
    # the remote URL so that Telegram can try to fetch the image itself.
    thumb_path = "thumb.jpg"
    try:
        async with ClientSession() as session:
            async with session.get(DEFAULT_THUMB_URL) as resp:
                data = await resp.read()
        # Write the downloaded bytes to the local file synchronously.  The file
        # size is small (thumbnail), so this write will not noticeably block.
        with open(thumb_path, "wb") as f:
            f.write(data)
    except Exception:
        thumb_path = DEFAULT_THUMB_URL

    # Process each link starting from the specified index
    count = start_index
    total_links = len(links)
    for idx in range(start_index - 1, total_links):
        # Extract name and URL without scheme
        name_part, url_part = links[idx]
        # Construct the full URL
        url = "https://" + url_part.strip()
        # Special cases for VisionIAS, Classplus and .mpd to .m3u8 conversion
        if "visionias" in url:
            async with ClientSession() as session:
                async with session.get(
                    url,
                    headers={
                        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9",
                        "Accept-Language": "en-US,en;q=0.9",
                        "Cache-Control": "no-cache",
                        "Connection": "keep-alive",
                        "Pragma": "no-cache",
                        "Referer": "http://www.visionias.in/",
                        "Sec-Fetch-Dest": "iframe",
                        "Sec-Fetch-Mode": "navigate",
                        "Sec-Fetch-Site": "cross-site",
                        "Upgrade-Insecure-Requests": "1",
                        "User-Agent": (
                            "Mozilla/5.0 (Linux; Android 12; RMX2121) "
                            "AppleWebKit/537.36 (KHTML, like Gecko) "
                            "Chrome/107.0.0.0 Mobile Safari/537.36"
                        ),
                        "sec-ch-ua": '"Chromium";v="107", "Not=A?Brand";v="24"',
                        "sec-ch-ua-mobile": "?1",
                        "sec-ch-ua-platform": '"Android"',
                    },
                ) as resp:
                    text = await resp.text()
                    try:
                        url = re.search(r"(https://.*?playlist.m3u8.*?)\"", text).group(1)
                    except Exception:
                        pass
        elif "videos.classplusapp" in url:
            try:
                api_resp = requests.get(
                    f"https://api.classplusapp.com/cams/uploader/video/jw-signed-url?url={url}",
                    headers={
                        "x-access-token": (
                            "eyJhbGciOiJIUzM4NCIsInR5cCI6IkpXVCJ9."
                            "eyJpZCI6MzgzNjkyMTIsIm9yZ0lkIjoyNjA1LCJ0eXBlIjoxLCJtb2JpbGUiOiI5MTcwODI3"
                            "NzQyODkiLCJuYW1lIjoiQWNlIiwiZW1haWwiOm51bGwsImlzRmlyc3RMb2dpbiI6dHJ1ZSwi"
                            "ZGVmYXVsdExhbmd1YWdlIjpudWxsLCJjb3VudHJ5Q29kZSI6IklOIiwiaXNJbnRlcm5hdGlv"
                            "bmFsIjowLCJpYXQiOjE2NDMyODE4NzcsImV4cCI6MTY0Mzg4NjY3N30.hM33P2ai6ivdzxP"
                            "Pfm01LAd4JWv-vnrSxGXqvCirCSpUfhhofpeqyeHPxtstXwe0"
                        ),
                    },
                ).json()
                url = api_resp["url"]
            except Exception:
                pass
        elif "/master.mpd" in url:
            id_ = url.split("/")[-2]
            url = f"https://d26g5bnklkwsh4.cloudfront.net/{id_}/master.m3u8"

        # Build a safe file name from name_part; strip scheme fragments if present
        name1 = (
            name_part
            .replace("\t", "")
            .replace(":", "")
            .replace("/", "")
            .replace("+", "")
            .replace("#", "")
            .replace("|", "")
            .replace("@", "")
            .replace("*", "")
            .replace(".", "")
            .replace("https", "")
            .replace("http", "")
            .strip()
        )
        # Derive a display name for the user without any index.  If name1 is
        # empty (e.g. when a line only contains a URL), use a generic name
        # based on the current count.
        display_name = name1[:60] if name1 else f"File_{count}"
        # Create a file base for storing the downloaded file on disk.  We
        # prefix the display name with a zero‑padded index to avoid filename
        # collisions and to preserve ordering, but this prefix is not shown to
        # the user.  Do not include any parentheses.
        # Replace spaces in the file base with underscores to avoid issues with shell commands
        file_base = f"{str(count).zfill(3)}_{display_name}".replace(" ", "_")

        # Format selection for yt‑dlp
        if "youtu" in url:
            ytf = (
                f'b[height<={quality}][ext=mp4]/'
                f'bv[height<={quality}][ext=mp4]+ba[ext=m4a]/'
                f'b[ext=mp4]'
            )
        else:
            ytf = (
                f'b[height<={quality}]/'
                f'bv[height<={quality}]+ba/'
                f'b/bv+ba'
            )
        # Determine if this is a JW player link; if so, we will not pass a format
        is_jw = "jw-prod" in url

        try:
            # Display an initial message about the download.  Use the display
            # name rather than the internal file_base so the user does not
            # see numbering prefixes.  The dynamic progress bar will edit
            # this message throughout the download.
            show = (
                f"📥 <b>Verifying the Downloading… Source...</b>\n\n"
                f"📄 <b>Name:</b> <b>{display_name}</b>\n"
                f"🔰 <b>Quality:</b> <i>{quality_label}</i>\n\n"
                f"🌐 <b>URL:</b> <code>{url}</code>"
            )
            prog = await m.reply_text(show, disable_web_page_preview=True)
            # Download the video using the dynamic download function.  It
            # accepts the format string (ytf), file base, reply message, and display name.
            downloaded_file = await helper.download_video(
                url,
                ytf if not is_jw else "",
                file_base,
                prog,
                display_name,
                is_jw,
            )
            # Once download is finished, remove the progress message.  It will
            # be replaced by the upload progress message in send_vid.
            await prog.delete(True)
            # Upload the trimmed video with caption.  Provide the display name
            # so the caption and progress bar omit numbering.  Use the
            # quality_label with 'p' suffix for the caption.
            await helper.send_vid(
                bot,
                m,
                downloaded_file,
                thumb_path,
                batch_name=batch_name,
                subject_name=subject_name,
                quality=quality_label,
                display_name=display_name,
                prog=prog,
            )
            count += 1
            # Yield control briefly between uploads so the event loop can handle
            # other tasks.  Replacing time.sleep with asyncio.sleep prevents
            # blocking the loop and improves responsiveness.
            await asyncio.sleep(1)
        except Exception as e:
            await m.reply_text(
                f"❌ Downloading interrupted\n{str(e)}\n"
                f"**Name:** {display_name}\n"
                f"**Link:** `{url}`"
            )
            continue

    await m.reply_text("✅ All downloads complete!\n\nHit /stop \nThen /start Again.. ", disable_web_page_preview=True)


if __name__ == "__main__":
    bot.run()
