"""
Advanced YouTube / multi-platform downloader bot.

Upload strategy:
  • file < 2 GB  →  Pyrogram MTProto (direct to Telegram, bypasses Bot API 50 MB cap)
  • file ≥ 2 GB  →  smart cloud upload (file.io → transfer.sh → 0x0.st)

Keep-alive:
  A lightweight Flask server runs on port 8080 so UptimeRobot can ping
  the bot every 5 minutes and keep it alive 24/7.
"""
import asyncio
import logging
import os
import re
import shutil
import time
import uuid
from pathlib import Path

from pyrogram import Client, filters
from pyrogram.types import (
    Message,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    CallbackQuery,
)
from pyrogram.enums import ParseMode

from config import API_ID, API_HASH, BOT_TOKEN, PYROGRAM_LIMIT
from downloader import get_info, download as yt_download
from cloud import smart_cloud_upload
from progress import ProgressReporter
import keep_alive

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
log = logging.getLogger(__name__)

app = Client(
    "yt_dl_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
)

# ── Helpers ────────────────────────────────────────────────────────────────────

YOUTUBE_RE = re.compile(
    r"(https?://)?(www\.)?"
    r"(youtube\.com/(watch\?v=|shorts/|embed/|live/)|youtu\.be/|music\.youtube\.com/)"
    r"[\w\-]{4,}"
)

GENERIC_URL_RE = re.compile(r"https?://\S+")


def is_supported_url(text: str) -> bool:
    return bool(GENERIC_URL_RE.search(text))


def fmt_duration(sec: int) -> str:
    if not sec:
        return "N/A"
    h, rem = divmod(int(sec), 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def fmt_size(b: int) -> str:
    for u in ("B", "KB", "MB", "GB"):
        if b < 1024:
            return f"{b:.1f} {u}"
        b /= 1024
    return f"{b:.1f} TB"


def quality_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📱 360p",  callback_data="dl:360p"),
            InlineKeyboardButton("📺 720p",  callback_data="dl:720p"),
        ],
        [
            InlineKeyboardButton("🎬 1080p", callback_data="dl:1080p"),
            InlineKeyboardButton("🎵 MP3",   callback_data="dl:mp3"),
        ],
    ])


# In-memory store: maps message_id → url (cleared after download)
pending: dict[int, str] = {}

# ── Handlers ───────────────────────────────────────────────────────────────────

@app.on_message(filters.command("start"))
async def cmd_start(client: Client, msg: Message):
    await msg.reply_text(
        "👋 **Welcome to Advanced YT Downloader!**\n\n"
        "Send me any YouTube (or other platform) link and choose your quality.\n\n"
        "✅ **Qualities:** 360p • 720p • 1080p • MP3\n"
        "🚀 **Large files** are uploaded via MTProto (no 50 MB limit!)\n"
        "☁️ **Files > 2 GB** are uploaded to fast cloud storage.\n\n"
        "Just paste a URL to begin →",
        parse_mode=ParseMode.MARKDOWN,
    )


@app.on_message(filters.command("help"))
async def cmd_help(client: Client, msg: Message):
    await msg.reply_text(
        "**How to use:**\n"
        "1. Send any video URL (YouTube, Instagram, Twitter, etc.)\n"
        "2. Choose quality via the inline buttons\n"
        "3. Wait for download + upload\n\n"
        "**Upload method:**\n"
        "• < 2 GB → sent directly to Telegram (MTProto)\n"
        "• ≥ 2 GB → uploaded to cloud, link sent to you\n\n"
        "**Supported sites:** anything yt-dlp supports (~1000+ sites)",
        parse_mode=ParseMode.MARKDOWN,
    )


@app.on_message(filters.text & ~filters.command(["start", "help"]))
async def handle_link(client: Client, msg: Message):
    text = msg.text.strip()
    if not is_supported_url(text):
        await msg.reply_text(
            "❌ Please send a valid video URL.\n"
            "Example: `https://www.youtube.com/watch?v=...`",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    status = await msg.reply_text("🔍 Fetching video info…")

    info = get_info(text)
    if not info:
        await status.edit_text(
            "❌ Could not fetch video info.\n"
            "The video may be private, geo-blocked, or the URL is unsupported."
        )
        return

    title     = info.get("title", "Unknown")
    uploader  = info.get("uploader") or info.get("channel", "Unknown")
    duration  = fmt_duration(info.get("duration", 0))
    views     = f"{info.get('view_count', 0):,}" if info.get("view_count") else "N/A"
    thumbnail = info.get("thumbnail", "")

    # Store URL keyed by the info-message id we're about to send
    caption = (
        f"🎬 **{title}**\n\n"
        f"👤 {uploader}\n"
        f"⏱ {duration}  •  👁 {views}\n\n"
        f"📥 **Choose quality to download:**"
    )

    await status.delete()

    try:
        sent = await msg.reply_photo(
            photo=thumbnail,
            caption=caption,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=quality_keyboard(),
        )
    except Exception:
        sent = await msg.reply_text(
            caption,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=quality_keyboard(),
        )

    pending[sent.id] = text


@app.on_callback_query(filters.regex(r"^dl:"))
async def handle_quality(client: Client, query: CallbackQuery):
    await query.answer()

    # Retrieve the URL from the message this button belongs to
    msg_id = query.message.id
    url = pending.pop(msg_id, None)

    if not url:
        await query.message.reply_text(
            "⚠️ Session expired. Please send the URL again."
        )
        return

    quality = query.data.split(":")[1]   # e.g. "720p" or "mp3"
    label   = quality.upper() if quality != "mp3" else "MP3 Audio"

    # Remove inline buttons so it can't be clicked twice
    try:
        await query.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    status = await query.message.reply_text(
        f"⏳ **Downloading {label}…**\nThis may take a while for large files.",
        parse_mode=ParseMode.MARKDOWN,
    )

    job_id  = str(uuid.uuid4())[:8]
    job_dir = f"/tmp/yt_downloads/{job_id}"

    try:
        # ── Download ──────────────────────────────────────────────────────────
        await status.edit_text(
            f"📥 **Downloading {label}…**\n`[yt-dlp is running]`",
            parse_mode=ParseMode.MARKDOWN,
        )

        result = await yt_download(url, quality, job_id)

        file_path  = result["path"]
        thumb_path = result.get("thumb_path")
        title      = result["title"]
        duration   = int(result.get("duration") or 0)
        file_size  = os.path.getsize(file_path)

        log.info(
            "Downloaded: %s  size=%s  quality=%s",
            title, fmt_size(file_size), quality,
        )

        # ── Upload decision ───────────────────────────────────────────────────
        if file_size >= PYROGRAM_LIMIT:
            # Cloud upload path
            await status.edit_text(
                f"☁️ **File is {fmt_size(file_size)} — uploading to cloud…**\n"
                "This may take several minutes.",
                parse_mode=ParseMode.MARKDOWN,
            )
            link = await smart_cloud_upload(file_path)
            if link:
                await status.edit_text(
                    f"✅ **{title}** is ready!\n\n"
                    f"☁️ **Download link:** {link}\n\n"
                    f"⚠️ Link may expire. Download quickly!",
                    parse_mode=ParseMode.MARKDOWN,
                )
            else:
                await status.edit_text(
                    "❌ Cloud upload failed. File may be too large for all providers."
                )
            return

        # MTProto upload (Pyrogram — no 50 MB Bot API cap)
        await status.edit_text(
            f"📤 **Uploading {label} via MTProto…**\n"
            f"Size: {fmt_size(file_size)}",
            parse_mode=ParseMode.MARKDOWN,
        )

        pr = ProgressReporter(status, f"Uploading {label}")

        send_kwargs = dict(
            chat_id=query.message.chat.id,
            progress=pr.callback,
        )

        if quality == "mp3":
            await client.send_audio(
                **send_kwargs,
                audio=file_path,
                title=title,
                duration=duration,
                thumb=thumb_path,
                caption=f"🎵 **{title}**",
                parse_mode=ParseMode.MARKDOWN,
            )
        else:
            await client.send_video(
                **send_kwargs,
                video=file_path,
                duration=duration,
                thumb=thumb_path,
                caption=f"🎬 **{title}** [{label}]",
                parse_mode=ParseMode.MARKDOWN,
                supports_streaming=True,
            )

        await status.edit_text(f"✅ **Done!** Enjoy your {label} download.")

    except Exception as e:
        log.exception("Error during download/upload")
        await status.edit_text(
            f"❌ **Error:** `{str(e)[:300]}`\n\nPlease try again or choose a different quality.",
            parse_mode=ParseMode.MARKDOWN,
        )
    finally:
        # ── Storage cleanup — always runs, even on error ──────────────────────
        # Remove the entire per-job temp folder (video + thumbnail + fragments)
        if os.path.isdir(job_dir):
            shutil.rmtree(job_dir, ignore_errors=True)
            log.info("Cleaned up job dir: %s", job_dir)


# ── Main ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # 1. Start keep-alive HTTP server on 0.0.0.0:8080 (or $PORT in production)
    keep_alive.start()

    # 2. Start Pyrogram bot (blocks until stopped)
    log.info("Starting Advanced YT Downloader Bot (Pyrogram MTProto)…")
    app.run()
