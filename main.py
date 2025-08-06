import os
import re
import sys
import asyncio
import requests

from aiohttp import ClientSession
from pyromod import listen
from pyromod.helpers import ikb

from pyrogram import Client, filters
from pyrogram.types import Message, CallbackQuery

import core as helper
from utils import hrb, hrt  # noqa: F401
from vars import API_ID, API_HASH, BOT_TOKEN

# In-memory user state store
user_state = {}

# Initialize the Pyrogram bot
bot = Client(
    "vj_txt_leech_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
)

# Default thumbnail URL
DEFAULT_THUMB_URL = "https://i.ibb.co/jkQJdwCj/th.png"


@bot.on_message(filters.command(["start"]))
async def start(bot: Client, m: Message):
    await m.reply_text(
        f"<b>Hello {m.from_user.mention}</b>\n\n"
        "I am a bot for downloading links from your .TXT file and then uploading "
        "those files on Telegram.  To use me, send /upload and follow the steps.\n\n"
        "Use /stop to stop any ongoing task.",
        disable_web_page_preview=True,
    )


@bot.on_message(filters.command("stop"))
async def stop(bot: Client, m: Message):
    await m.reply_text("**Stopped**", True)
    os.execl(sys.executable, sys.executable, *sys.argv)


@bot.on_message(filters.command(["upload"]))
async def upload(bot: Client, m: Message):
    # Step 1: ask for the .txt file
    user_state[m.chat.id] = {}
    prompt = await m.reply_text("📄 Please send me your .txt file containing the links.")
    input_msg: Message = await bot.listen(prompt.chat.id)

    caption_text = getattr(input_msg, "caption", None)
    txt_path = await input_msg.download()
    await input_msg.delete(True)

    os.makedirs(f"./downloads/{m.chat.id}", exist_ok=True)

    # Parse the text file into (name, url) pairs
    try:
        with open(txt_path, "r", encoding="utf-8") as f:
            lines = [line for line in f.read().strip().split("\n") if line.strip()]
        links = []
        for line in lines:
            parts = line.rsplit(" ", 1)
            name_part, url_full = (parts[0].strip(), parts[1].strip()) if len(parts) == 2 else ("", parts[0].strip())
            links.append([name_part, url_full])
        os.remove(txt_path)
    except Exception:
        await m.reply_text("❌ Invalid file input.")
        os.remove(txt_path)
        return

    user_state[m.chat.id]["links"] = links

    # Extract batch and subject from the caption
    parsed_batch = parsed_subject = None
    if caption_text:
        for line in caption_text.splitlines():
            cleaned = line.lstrip("📂📦📁📘📗📕📓📄🔗📝🗒️")
            parts = cleaned.split(":", 1)
            if len(parts) == 2:
                key, value = parts[0].strip().lower(), parts[1].strip()
                if "subject" in key and not parsed_subject:
                    parsed_subject = value
                elif "batch" in key and not parsed_batch:
                    parsed_batch = value
    user_state[m.chat.id]["parsed_batch"] = parsed_batch
    user_state[m.chat.id]["parsed_subject"] = parsed_subject

    # Step 2: ask for starting index (buttons: “1” and “custom”)
    start_keyboard = ikb([["1", "custom"]])
    msg_start = await m.reply_text(
        f"**Total links found:** <b>{len(links)}</b>\n\nSelect the starting index:",
        reply_markup=start_keyboard
    )
    # Remove the initial “send file” prompt for a cleaner UI
    try:
        await prompt.delete()
    except Exception:
        pass
    user_state[m.chat.id]["msg_start"] = msg_start


@bot.on_callback_query()
async def handle_buttons(bot: Client, cq: CallbackQuery):
    chat_id = cq.message.chat.id
    data = cq.data

    state = user_state.get(chat_id, {})
    links = state.get("links")
    if not links:
        await cq.answer("No upload session found.", show_alert=True)
        return

    # Stage 1: choosing starting index
    if "start_index" not in state:
        if data == "custom":
            await cq.message.delete()
            msg = await bot.send_message(chat_id, "📥 Please enter the starting index (1-based):")
            resp = await bot.listen(chat_id)
            try:
                start_index = int(resp.text.strip())
                if not 1 <= start_index <= len(links):
                    raise ValueError
            except Exception:
                start_index = 1
            await resp.delete(True)
            await msg.delete()
        else:
            start_index = int(data)
            await cq.message.delete()

        state["start_index"] = start_index

        parsed_batch = state.get("parsed_batch")
        if parsed_batch:
            batch_name = parsed_batch
        else:
            msg_batch = await bot.send_message(chat_id, "📦 Please enter the batch name (e.g. 'Batch 1')")
            input_batch = await bot.listen(chat_id)
            batch_name = input_batch.text.strip()
            await input_batch.delete(True)
            await msg_batch.delete()
        state["batch_name"] = batch_name

        # Stage 3: resolution selection
        quality_keyboard = ikb([
            ["144", "240", "360"],
            ["480", "720", "1080"]
        ])
        msg_res = await bot.send_message(chat_id, "Please choose a resolution:", reply_markup=quality_keyboard)
        state["msg_res"] = msg_res
    else:
        # Stage 3: resolution selected
        raw_res = data
        await cq.message.delete()
        res_map = {
            "144": "256x144", "240": "426x240", "360": "640x360",
            "480": "854x480", "720": "1280x720", "1080": "1920x1080",
        }
        quality = raw_res if raw_res in res_map else "UN"
        state["quality"] = quality
        state["quality_label"] = raw_res + "p"

        # Stage 4: subject name (use parsed if present)
        parsed_subject = state.get("parsed_subject")
        if parsed_subject:
            subject_name = parsed_subject
        else:
            msg_subject = await bot.send_message(chat_id, "📘 Please enter the subject name (e.g. 'Physics')")
            input_subject = await bot.listen(chat_id)
            subject_name = input_subject.text.strip()
            await input_subject.delete(True)
            await msg_subject.delete()
        state["subject_name"] = subject_name

        # Inform about the default thumbnail and delete that notification later
        thumb_msg = await cq.message.reply("📎 A default thumbnail will be used for all videos.")
        await process_links(bot, cq.message, state, thumb_msg)


async def process_links(bot: Client, m: Message, state: dict, info_msg: Message | None = None):
    # Delete the “default thumbnail” message right away for a clean UI
    if info_msg:
        try:
            await info_msg.delete()
        except Exception:
            pass

    links = state["links"]
    start_index = state["start_index"]
    batch_name = state["batch_name"]
    subject_name = state["subject_name"]
    quality_label = state["quality_label"]

    # Download default thumbnail once
    thumb_path = "thumb.jpg"
    try:
        async with ClientSession() as session:
            async with session.get(DEFAULT_THUMB_URL) as resp:
                data = await resp.read()
        with open(thumb_path, "wb") as f:
            f.write(data)
    except Exception:
        thumb_path = DEFAULT_THUMB_URL

    count = start_index
    total_links = len(links)

    for idx in range(start_index - 1, total_links):
        name_part, url = links[idx]
        display_name = re.sub(r"[\\/:*?\"<>|]", "", name_part).strip() or f"File_{count}"
        file_base = f"{str(count).zfill(3)}_{display_name}".replace(" ", "_")

        try:
            # Show the “verifying” progress message with name, quality, and URL
            show = (
                f"📥 <b>Verifying the Downloading… Source...</b>\n\n"
                f"📄 <b>Name:</b> <b>{display_name}</b>\n"
                f"🔰 <b>Quality:</b> <i>{quality_label}</i>\n\n"
                f"🌐 <b>URL:</b> <code>{url}</code>"
            )
            prog = await m.reply_text(show, disable_web_page_preview=True)
            # Download the file; helper.download_video will edit the message to show progress
            downloaded_file = await helper.download_video(
                url, "", file_base, prog, display_name, False
            )
            # Remove the progress message after download is complete
            await prog.delete(True)
            # Upload the video with proper caption
            await helper.send_vid(
                bot, m, downloaded_file, thumb_path,
                batch_name=batch_name, subject_name=subject_name,
                quality=quality_label, display_name=display_name, prog=prog
            )
            count += 1
            await asyncio.sleep(1)
        except Exception as e:
            await m.reply_text(
                f"❌ Downloading interrupted\n{str(e)}\nName: {display_name}\nLink: {url}"
            )
            continue

    # Final summary message
    await m.reply_text(
        f"✅ All downloads complete!\n\n"
        f"📦 Batch: <b>{batch_name}</b>\n"
        f"📘 Subject: <b>{subject_name}</b>\n"
        f"🔗 Total Links: <b>{total_links}</b>\n\n"
        "Hit /stop Then /start Again..",
        disable_web_page_preview=True
    )


if __name__ == "__main__":
    bot.run()
