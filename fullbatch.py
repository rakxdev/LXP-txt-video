#!/usr/bin/env python3
"""
Unified bot with per‑subject start index (skipping earlier links),
subject‑completion messages, default thumbnail, and fully functional /stop.
"""

import os
import sys  # <--- Add this at the top (right after 'import os')
import re
import html
import json
import logging
import asyncio
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Tuple, Optional

import aiohttp
import aiofiles
from pyrogram import Client, filters
from pyrogram.types import Message, CallbackQuery
from pyromod.helpers import ikb
from pyromod import listen

# import from your LXP repository
from core import download_video, send_vid

# -------------------------------------------------------------------------
# Configuration
# API_ID = int(os.environ.get("API_ID", "24986604"))
# API_HASH = os.environ.get("API_HASH", "afda6f8e5493b9a5bc87656974f3c82e")
# BOT_TOKEN = os.environ.get("BOT_TOKEN", "7734371947:AAEu32ysTCsJJh0vExhS1dyakId-qT1aOGg")
# AUTH_STR  = os.environ.get("AUTHORIZED_USERS", "7875474866")
# AUTHORIZED_USERS: Optional[set[int]] = (
#     {int(u) for u in AUTH_STR.split(",") if u.strip().isdigit()} if AUTH_STR else None
# )

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)
for lib in ["httpx", "pyrogram", "pyrogram.client", "pyrogram.connection"]:
    logging.getLogger(lib).setLevel(logging.WARNING)
    logging.getLogger(lib).propagate = False

# -------------------------------------------------------------------------
# Thumbnail
DEFAULT_THUMB_URL = "https://i.ibb.co/jkQJdwCj/th.png"

async def get_default_thumb(path: str = "/tmp/default_thumb.jpg") -> str:
    if os.path.exists(path):
        return path
    async with aiohttp.ClientSession() as session:
        async with session.get(DEFAULT_THUMB_URL) as resp:
            if resp.status == 200:
                async with aiofiles.open(path, "wb") as f:
                    await f.write(await resp.read())
    return path

# -------------------------------------------------------------------------
# Parsing functions

def remove_ansi(line: str) -> str:
    return re.sub(r"!ESC!\[[0-9;]+m", "", line)

def parse_file(path: Path) -> Dict[str, Dict[str, Dict[str, List[Tuple[str, str]]]]]:
    text = path.read_text(errors="ignore")
    data = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
    current_subject = None
    current_chapter = None
    last_lecture = None
    last_dpp_video = None
    subj_pat = re.compile(r"\[SUBJECT\]\s*(.+)")
    chap_pat = re.compile(r"\[CHAPTER\]\s*(.+)")
    var_pat  = re.compile(r'set\s+"([^=]+)=([^"\n]+)"')
    m3u8_pat = re.compile(r'N_m3u8DL-RE\s+"(https?://[^"\s]+)"')
    for raw_line in text.splitlines():
        line = remove_ansi(raw_line)
        if (m := subj_pat.search(line)):
            current_subject = m.group(1).strip()
            current_chapter = None
            continue
        if (m := chap_pat.search(line)):
            current_chapter = m.group(1).strip()
            continue
        if (m := var_pat.match(line)):
            var_name = m.group(1).strip().lower()
            var_val  = m.group(2).strip()
            if var_name.startswith("lecture"):
                last_lecture = var_val
            elif var_name.startswith("dpp_video"):
                last_dpp_video = var_val
            continue
        if (m := m3u8_pat.search(raw_line)):
            url = m.group(1).strip()
            if last_lecture and current_subject and current_chapter:
                data[current_subject][current_chapter]["Lectures"].append((last_lecture, url))
                last_lecture = None
            elif last_dpp_video and current_subject and current_chapter:
                data[current_subject][current_chapter]["DPP Videos"].append((last_dpp_video, url))
                last_dpp_video = None
    return data

def parse_notes(path: Path) -> Dict[str, Dict[str, Dict[str, List[Tuple[str, str]]]]]:
    text = path.read_text(errors="ignore")
    data = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
    current_subject = None
    current_chapter = None
    last_note = None
    last_dpp_note = None
    subj_pat = re.compile(r"\[SUBJECT\]\s*(.+)")
    chap_pat = re.compile(r"\[CHAPTER\]\s*(.+)")
    var_pat  = re.compile(r'set\s+"([^=]+)=([^"\n]+)')
    pdf_pat  = re.compile(r'https?://[^"\s]+\.pdf')
    for raw_line in text.splitlines():
        line = remove_ansi(raw_line)
        if (m := subj_pat.search(line)):
            current_subject = m.group(1).strip()
            current_chapter = None
            continue
        if (m := chap_pat.search(line)):
            current_chapter = m.group(1).strip()
            continue
        if (m := var_pat.match(line)):
            var_name = m.group(1).strip().lower()
            var_val  = m.group(2).strip()
            if var_name.startswith("note") and not var_name.startswith("note_name"):
                last_note = var_val
            elif var_name.startswith("dpp_note"):
                last_dpp_note = var_val
            continue
        if (m := pdf_pat.search(raw_line)):
            url = m.group(0).strip()
            if current_subject and current_chapter:
                if last_note:
                    data[current_subject][current_chapter]["Notes"].append((last_note, url))
                    last_note = None
                elif last_dpp_note:
                    data[current_subject][current_chapter]["DPP Notes"].append((last_dpp_note, url))
                    last_dpp_note = None
    return data

def sanitize_name(name: str) -> str:
    return name.replace("/", "-").replace(":", "-").strip()

def generate_notes_html(data, output_path, batch_title):
    notes_json = {
        subj: {
            chap: {
                key: [{"name": n, "url": u} for n, u in sorted(contents.get(key, []))]
                for key in ["Notes", "DPP Notes"] if contents.get(key)
            }
            for chap, contents in chapters.items()
        }
        for subj, chapters in data.items()
    }
    notes_js = json.dumps(notes_json)
    # (HTML omitted here for brevity—same as previous versions)
    # ...
    # For brevity, you can reuse the notes HTML generation from the previous script.
    pass

# -------------------------------------------------------------------------
# In-memory state & tasks
user_state: dict[int, dict] = {}
download_tasks: dict[int, asyncio.Task] = {}

def build_subject_keyboard(subjects: List[str], selected: set) -> List[List[Tuple[str, str]]]:
    """Construct the inline keyboard for subject selection."""
    keyboard: List[List[Tuple[str, str]]] = []
    for idx, name in enumerate(subjects):
        prefix = "✅ " if name in selected else ""
        keyboard.append([(prefix + name, f"toggle_{idx}")])
    all_selected = len(selected) == len(subjects) and bool(subjects)
    keyboard.append([(("❌ Unselect All" if all_selected else "✅ Select All"), "toggle_all")])
    keyboard.append([("➡️ Proceed", "proceed")])
    return keyboard

def count_links(data, subject):
    return sum(
        len(contents.get("Lectures", [])) + len(contents.get("DPP Videos", []))
        for contents in data[subject].values()
    )

async def ensure_authorized(msg: Message) -> bool:
    if AUTHORIZED_USERS is None:
        return True
    uid = msg.from_user.id if msg.from_user else 0
    if uid not in AUTHORIZED_USERS:
        await msg.reply_text("❌ Sorry, you are not authorised to use this bot.")
        return False
    return True

# -------------------------------------------------------------------------
# Pyrogram Client
bot = Client("custom_index_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# -------------------------------------------------------------------------
# Start & Stop commands

@bot.on_message(filters.command("start"))
async def start_cmd(_, m: Message):
    if not await ensure_authorized(m):
        return
    await m.reply_text(
        "👋 Send me a .bat or .txt script, select subjects, then choose starting indexes "
        "and resolution. I will skip earlier links according to the index. Use /stop to cancel."
    )

@bot.on_message(filters.command("stop"))
async def stop_cmd(_, m: Message):
    await m.reply_text("⛔️ Bot is restarting. All ongoing downloads will be aborted instantly!")
    os.execl(sys.executable, sys.executable, *sys.argv)

# -------------------------------------------------------------------------
# Handle script upload

@bot.on_message(filters.document)
async def handle_script(_, m: Message):
    if m.edit_date:
        return
    if not await ensure_authorized(m):
        return
    doc = m.document
    filename = doc.file_name or "unknown"
    if not filename.lower().endswith((".bat", ".txt")):
        await m.reply_text("⚠️ Only .bat or .txt files are supported.")
        return
    tmp_path = os.path.join("/tmp", filename)
    state = {}
    user_state[m.chat.id] = state
    state["batch_name"] = filename
    state["stage"] = "inspect"
    state["cancel"] = False
    try:
        note = await m.reply_text("🔍 Inspecting…")
        await bot.download_media(doc, file_name=tmp_path)
        data = parse_file(Path(tmp_path))
        if not data:
            await note.delete()
            await m.reply_text("⚠️ No valid subjects found.")
            return
        state["data"] = data
        state["subject_list"] = list(data.keys())
        state["selected_subjects"] = set()
        state["batch_path"] = tmp_path
        kb = build_subject_keyboard(state["subject_list"], set())
        await note.delete()
        msg = await m.reply_text("📚 Choose subjects:", reply_markup=ikb(kb))
        state["stage"] = "select_subjects"
    except Exception as exc:
        logger.exception("Error while reading file")
        await m.reply_text(f"❌ Error: {exc}")
        try:
            os.remove(tmp_path)
        except Exception:
            pass

# -------------------------------------------------------------------------
# Handle inline buttons

@bot.on_callback_query()
async def handle_button(_, cq: CallbackQuery):
    chat_id = cq.message.chat.id
    state = user_state.get(chat_id)
    if not state:
        await cq.answer("No active session.", show_alert=True)
        return
    if AUTHORIZED_USERS is not None and cq.from_user.id not in AUTHORIZED_USERS:
        await cq.answer("❌ Not authorised.", show_alert=True)
        return
    data = cq.data

    # Subject selection
    if state.get("stage") == "select_subjects":
        if data.startswith("toggle_") and data != "toggle_all":
            idx = int(data.split("_")[1])
            subject = state["subject_list"][idx]
            if subject in state["selected_subjects"]:
                state["selected_subjects"].remove(subject)
            else:
                state["selected_subjects"].add(subject)
            kb = build_subject_keyboard(state["subject_list"], state["selected_subjects"])
            await cq.message.edit_reply_markup(reply_markup=ikb(kb))
            await cq.answer()
            return
        if data == "toggle_all":
            subs = state["subject_list"]
            sel = state["selected_subjects"]
            if len(sel) == len(subs) and bool(subs):
                sel.clear()
            else:
                sel.clear()
                sel.update(subs)
            kb = build_subject_keyboard(state["subject_list"], state["selected_subjects"])
            await cq.message.edit_reply_markup(reply_markup=ikb(kb))
            await cq.answer()
            return
        if data == "proceed":
            subjects = (
                list(state["selected_subjects"])
                if state["selected_subjects"]
                else state["subject_list"]
            )
            state["selected_subjects"] = set(subjects)
            await cq.message.delete()
            state["stage"] = "await_start_index_subject"
            state["subjects_iter"] = subjects.copy()
            state["start_indexes"] = {}
            # Ask the first subject's starting index with link count
            if subjects:
                first_subj = subjects[0]
                total = count_links(state["data"], first_subj)
                kb = [[("1", "startidx_1"), ("Custom", "startidx_custom")]]
                msg = await bot.send_message(
                    chat_id,
                    f"🔢 Choose starting index for <b>{html.escape(first_subj)}</b> (Total: {total}):",
                    reply_markup=ikb(kb)
                )
                state["start_prompt_id"] = msg.id
            await cq.answer()
            return

    # Per-subject starting index
    if state.get("stage") == "await_start_index_subject":
        if data.startswith("startidx_"):
            choice = data.split("_")[1]
            subj_iter = state["subjects_iter"]
            current_subj = subj_iter[0]
            if choice == "1":
                state["start_indexes"][current_subj] = 1
                subj_iter.pop(0)
                await cq.message.delete()
            elif choice == "custom":
                # ask for custom index via reply/listen
                await cq.message.delete()
                prompt = await bot.send_message(
                    chat_id,
                    f"📥 Enter starting index for <b>{html.escape(current_subj)}</b> (1‑based):"
                )
                resp = await bot.listen(chat_id)
                try:
                    idx = int(resp.text.strip())
                    if idx < 1:
                        idx = 1
                except Exception:
                    idx = 1
                state["start_indexes"][current_subj] = idx
                await prompt.delete()
                await resp.delete()
                subj_iter.pop(0)
            # Ask for next subject or resolution
            if subj_iter:
                next_sub = subj_iter[0]
                total = count_links(state["data"], next_sub)
                kb = [[("1", "startidx_1"), ("Custom", "startidx_custom")]]
                msg = await bot.send_message(
                    chat_id,
                    f"🔢 Choose starting index for <b>{html.escape(next_sub)}</b> (Total: {total}):",
                    reply_markup=ikb(kb)
                )
                state["start_prompt_id"] = msg.id
            else:
                state["stage"] = "await_resolution"
                kb = [
                    [("144p", "res144"), ("240p", "res240"), ("360p", "res360")],
                    [("480p", "res480"), ("720p", "res720"), ("1080p", "res1080")],
                ]
                msg = await bot.send_message(
                    chat_id,
                    "Please choose a resolution for all subjects:",
                    reply_markup=ikb(kb)
                )
                state["resolution_prompt_id"] = msg.id
            await cq.answer()
            return

    # Choose resolution
    if state.get("stage") == "await_resolution":
        if data.startswith("res"):
            res = data[3:]
            state["resolution"] = res
            await cq.message.delete()
            state["batch_title"] = os.path.splitext(state.get("batch_name", "batch"))[0]
            state["stage"] = "downloading"
            task = asyncio.create_task(process_downloads(cq.message, state))
            download_tasks[chat_id] = task
            await cq.answer()
            return

    await cq.answer()

# -------------------------------------------------------------------------
# Download logic

async def process_downloads(trigger_msg: Message, state: dict):
    chat_id = trigger_msg.chat.id
    try:
        data = state["data"]
        subjects = list(state["selected_subjects"])
        start_indexes = state.get("start_indexes", {})
        res = state.get("resolution", "360")
        batch_name = state.get("batch_title", "Batch")
        quality_label = f"{res}p"
        subject_links: Dict[str, List[Tuple[str, str]]] = {}
        # Build lists per subject and add chapter prefixes
        for subj in subjects:
            items = []
            for chap_name, contents in data[subj].items():
                m = re.search(r"\d+", chap_name)
                if m:
                    num = m.group().zfill(2)
                    prefix = f"CH {num} "
                else:
                    prefix = ""
                for name, url in sorted(contents.get("Lectures", []), key=lambda x: x[0]):
                    items.append((prefix + name, url))
                for name, url in sorted(contents.get("DPP Videos", []), key=lambda x: x[0]):
                    items.append((prefix + name, url))
            subject_links[subj] = items
        thumb_path = await get_default_thumb()
        total_uploaded = 0
        for subj in subjects:
            links = subject_links[subj]
            start_idx = start_indexes.get(subj, 1)
            # Skip earlier links based on start index
            to_process = links[start_idx - 1:] if start_idx > 1 else links
            count = start_idx
            for name, url in to_process:
                if state.get("cancel"):
                    await bot.send_message(chat_id, "⛔️ Operation cancelled.")
                    return
                safe = re.sub(r'[\\\\/:*?"<>|]', "", name).strip() or f"File_{count}"
                file_base = f"{str(count).zfill(3)}_{safe}".replace(" ", "_")
                try:
                    info = await bot.send_message(
                        chat_id,
                        "📥 <b>Verifying…</b>\n\n"
                        f"📄 <b>Name:</b> <b>{html.escape(name)}</b>\n"
                        f"🔰 <b>Quality:</b> <i>{quality_label}</i>\n\n"
                        f"🌐 <b>URL:</b> <code>{html.escape(url)}</code>",
                        disable_web_page_preview=True
                    )
                    downloaded = await download_video(url, "", file_base, info, name, False)
                    await info.delete()
                    await send_vid(
                        bot,
                        trigger_msg,
                        downloaded,
                        thumb_path,
                        batch_name,
                        subj,
                        quality_label,
                        name,
                        None
                    )
                    count += 1
                    total_uploaded += 1
                    await asyncio.sleep(1)
                except asyncio.CancelledError:
                    return
                except Exception as e:
                    logger.exception(f"Error processing {name}: {e}")
                    await bot.send_message(chat_id, f"❌ Error with <b>{html.escape(name)}</b>\n{str(e)}")
                    continue
            await bot.send_message(chat_id, f"✅ Completed <b>{html.escape(subj)}</b> ({len(to_process)} files).")
        await bot.send_message(
            chat_id,
            f"🎉 All subjects finished!\n\n📦 Batch: <b>{html.escape(batch_name)}</b>\n"
            f"🔗 Total Files: <b>{total_uploaded}</b>",
            disable_web_page_preview=True
        )
        # Send notes if all subjects selected
        if len(subjects) == len(state.get("subject_list", [])):
            try:
                notes_data = parse_notes(Path(state["batch_path"]))
                html_name = f"{sanitize_name(batch_name)}.html"
                html_path = os.path.join("/tmp", html_name)
                generate_notes_html(notes_data, Path(html_path), batch_name)
                await bot.send_document(
                    chat_id, html_path,
                    caption=f"📝 Notes for {html.escape(batch_name)}"
                )
                os.remove(html_path)
            except Exception as ex:
                logger.exception(f"Failed to generate notes: {ex}")
    except asyncio.CancelledError:
        # Task cancelled: exit gracefully
        return
    finally:
        download_tasks.pop(chat_id, None)
        user_state.pop(chat_id, None)

# -------------------------------------------------------------------------
if __name__ == "__main__":
    bot.run()


# Final code for use success
