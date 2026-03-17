"""
╔══════════════════════════════════════════════════════╗
║       🕵️  TELEGRAM MEDIA GRABBER BOT  v3.0 🕵️        ║
║   python-telegram-bot (Bot API) — always works       ║
╚══════════════════════════════════════════════════════╝
"""

import os
import re
import asyncio
import logging
import threading
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters,
)
from telegram.constants import ParseMode

from pyrogram import Client
from pyrogram.enums import ChatType, MessageMediaType
from pyrogram.errors import (
    FloodWait, ChannelPrivate,
    UsernameNotOccupied, UsernameInvalid, PeerIdInvalid,
    MessageIdInvalid, SessionPasswordNeeded,
)

import sessions as sess

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
log = logging.getLogger(__name__)

API_ID       = int(os.environ["API_ID"])
API_HASH     = os.environ["API_HASH"]
BOT_TOKEN    = os.environ["BOT_TOKEN"]
DUMP_CHANNEL = int(os.environ["DUMP_CHANNEL"])
PORT         = int(os.environ.get("PORT", 8080))
APP_URL      = os.environ.get("APP_URL", "")

# ─── Bot client (python-telegram-bot) ────────────────────────────────────────
ptb = Application.builder().token(BOT_TOKEN).build()

# ─── Grab sessions ────────────────────────────────────────────────────────────
grab_sessions: dict[int, dict] = {}
watched: dict[str, dict] = {}
login_clients: dict[int, Client] = {}  # stores live pyrogram client during login

# ─── Extension map ────────────────────────────────────────────────────────────
EXT_MAP = {
    "jpg":("📸","Photo"),   "jpeg":("📸","Photo"),  "png":("📸","Photo"),
    "gif":("🎞️","GIF"),    "webp":("📸","Photo"),  "bmp":("📸","Photo"),
    "mp4":("🎬","Video"),   "mkv":("🎬","Video"),   "avi":("🎬","Video"),
    "mov":("🎬","Video"),   "flv":("🎬","Video"),   "wmv":("🎬","Video"),
    "webm":("🎬","Video"),  "ts":("🎬","Video"),
    "mp3":("🎵","Music"),   "flac":("🎵","Music"),  "wav":("🎵","Music"),
    "aac":("🎵","Music"),   "ogg":("🎵","Music"),   "m4a":("🎵","Music"),
    "opus":("🎵","Music"),  "wma":("🎵","Music"),
    "pdf":("📄","PDF"),
    "doc":("📝","Document"),  "docx":("📝","Document"),
    "xls":("📊","Spreadsheet"), "xlsx":("📊","Spreadsheet"),
    "ppt":("📊","Presentation"), "pptx":("📊","Presentation"),
    "txt":("📝","Text"),    "csv":("📊","CSV"),
    "zip":("🗜️","Archive"), "rar":("🗜️","Archive"),
    "7z":("🗜️","Archive"),  "tar":("🗜️","Archive"), "gz":("🗜️","Archive"),
    "py":("💻","Code"),     "js":("💻","Code"),     "html":("💻","Code"),
    "apk":("📱","APK"),
}

MEDIA_ICONS = {
    MessageMediaType.PHOTO:     ("📸","Photo"),
    MessageMediaType.VIDEO:     ("🎬","Video"),
    MessageMediaType.AUDIO:     ("🎵","Music"),
    MessageMediaType.VOICE:     ("🎤","Voice"),
    MessageMediaType.DOCUMENT:  ("📄","Document"),
    MessageMediaType.ANIMATION: ("🎞️","GIF"),
    MessageMediaType.VIDEO_NOTE:("📹","Video Note"),
}

# ─── Helpers ──────────────────────────────────────────────────────────────────
def get_file_info(msg) -> tuple:
    filename, size = "", 0
    if msg.document:
        filename = msg.document.file_name or ""
        size     = msg.document.file_size or 0
    elif msg.video:
        filename = msg.video.file_name or ""
        size     = msg.video.file_size or 0
    elif msg.audio:
        filename = msg.audio.file_name or msg.audio.title or ""
        size     = msg.audio.file_size or 0
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext in EXT_MAP:
        emoji, cat = EXT_MAP[ext]
    elif msg.media and msg.media in MEDIA_ICONS:
        emoji, cat = MEDIA_ICONS[msg.media]
    else:
        emoji, cat = ("📦","File")
    return emoji, cat, filename, size

def human_size(b: int) -> str:
    for u in ["B","KB","MB","GB"]:
        if b < 1024: return f"{b:.1f} {u}"
        b /= 1024
    return f"{b:.2f} TB"

def make_caption(msg, src_title: str, src_link: str) -> str:
    emoji, cat, fname, size = get_file_info(msg)
    lines = [f"{emoji}  *{cat}*"]
    if fname:    lines.append(f"📂  `{fname}`")
    if size:     lines.append(f"💾  {human_size(size)}")
    lines.append(f"📡  *Source:* {src_title}")
    if src_link: lines.append(f"🔗  {src_link}")
    if msg.date: lines.append(f"🕐  {msg.date.strftime('%d %b %Y')}")
    return "\n".join(lines)

def has_media(msg) -> bool:
    return bool(
        msg.photo or msg.video or msg.audio or msg.document or
        msg.voice or msg.animation or msg.video_note or msg.sticker
    )

def matches_pattern(msg, pattern: str) -> bool:
    if not pattern or pattern == "*":
        return True
    _, _, fname, _ = get_file_info(msg)
    text        = (msg.text or msg.caption or "").lower()
    fname_lower = fname.lower()
    regex = "^" + re.escape(pattern).replace(r"\*",".*").replace(r"\?",".") + "$"
    return bool(
        re.search(regex, fname_lower, re.I) or
        re.search(regex, text, re.I) or
        pattern.lower() in fname_lower or
        pattern.lower() in text
    )

def get_pyro_client(uid: int) -> Client | None:
    if sess.is_logged_in(uid):
        return sess.get_client(uid)
    return None


# ─── /start ───────────────────────────────────────────────────────────────────
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid    = update.effective_user.id
    logged = sess.is_logged_in(uid)
    status = "✅  *Logged in* — using your account" if logged else "⚠️  *Not logged in* — /login for private chats"
    await update.message.reply_text(
        "🕵️  *MEDIA GRABBER BOT*\n\n"
        f"{status}\n\n"
        "╔══════════════════════════════╗\n"
        "║        📋  COMMANDS          ║\n"
        "╠══════════════════════════════╣\n"
        "║  /login   — Login account    ║\n"
        "║  /logout  — Logout account   ║\n"
        "║  /search  — Search media     ║\n"
        "║  /grab    — Grab from link   ║\n"
        "║  /watch   — Monitor channel  ║\n"
        "║  /unwatch — Stop monitoring  ║\n"
        "║  /list    — Watched list     ║\n"
        "║  /stop    — Cancel grab      ║\n"
        "║  /status  — Bot status       ║\n"
        "║  /help    — Full guide       ║\n"
        "╚══════════════════════════════╝",
        parse_mode=ParseMode.MARKDOWN,
    )

# ─── /help ────────────────────────────────────────────────────────────────────
async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📖  *HOW TO USE*\n\n"
        "━━━━━━━━━━━━━━━━━\n"
        "🔐  *LOGIN* — /login\n"
        "━━━━━━━━━━━━━━━━━\n"
        "Login so bot accesses private chats you're in.\n\n"
        "━━━━━━━━━━━━━━━━━\n"
        "🔍  *SEARCH* — /search\n"
        "━━━━━━━━━━━━━━━━━\n"
        "• /search `*.mp3` — all MP3 files\n"
        "• /search `*.jpg` — all photos\n"
        "• /search `*.pdf` — all PDFs\n"
        "• /search `*.apk` — all APKs\n"
        "• /search `bigil` — by filename\n"
        "• /search `today market graph` — any text\n"
        "• /search `*` — ALL media\n\n"
        "━━━━━━━━━━━━━━━━━\n"
        "🪝  *GRAB* — /grab\n"
        "━━━━━━━━━━━━━━━━━\n"
        "• /grab @channel\n"
        "• /grab @channel `*.mp3`\n"
        "• /grab https://t.me/ch/123 — single post\n\n"
        "━━━━━━━━━━━━━━━━━\n"
        "👁  *WATCH* — /watch\n"
        "━━━━━━━━━━━━━━━━━\n"
        "• /watch @channel\n"
        "• /watch @channel `*.mp3`\n"
        "• /unwatch @channel\n"
        "• /list — show all watched\n\n"
        "📦  All files → dump channel with source info.",
        parse_mode=ParseMode.MARKDOWN,
    )

# ─── /login ───────────────────────────────────────────────────────────────────
async def cmd_login(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if sess.is_logged_in(uid):
        c  = sess.get_client(uid)
        me = await c.get_me()
        await update.message.reply_text(
            f"✅  Already logged in as *{me.first_name}*\nUse /logout to switch.",
            parse_mode=ParseMode.MARKDOWN,
        )
        return
    sess.set_state(uid, {"step": "phone"})
    await update.message.reply_text(
        "🔐  *LOGIN WITH YOUR TELEGRAM ACCOUNT*\n\n"
        "Allows bot to access private chats you're in.\n\n"
        "🛡  _Session stored only on this server._\n"
        "_No other user can access your session._\n"
        "Revoke: /logout or Telegram → Settings → Devices.\n\n"
        "━━━━━━━━━━━━━━━━━\n"
        "📱  Send phone number with country code:\n"
        "Example: `+919876543210`",
        parse_mode=ParseMode.MARKDOWN,
    )

# ─── /logout ──────────────────────────────────────────────────────────────────
async def cmd_logout(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    c   = sess.get_client(uid)
    if c:
        try: await c.stop()
        except Exception: pass
    sess.remove_client(uid)
    sess.delete_session(uid)
    sess.clear_state(uid)
    await update.message.reply_text(
        "✅  *Logged out!*\nSession removed.\nAlso revoke: Telegram → Settings → Devices.",
        parse_mode=ParseMode.MARKDOWN,
    )

# ─── /status ──────────────────────────────────────────────────────────────────
async def cmd_status(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid    = update.effective_user.id
    logged = sess.is_logged_in(uid)
    acc    = "⚠️  Not logged in"
    if logged:
        try:
            me_u = await sess.get_client(uid).get_me()
            acc  = f"✅  *{me_u.first_name}* (@{me_u.username or 'N/A'})"
        except Exception: pass
    await update.message.reply_text(
        f"🤖  *Bot Status*\n\n"
        f"👤  Account: {acc}\n"
        f"👁  Watching: *{len(watched)}*\n"
        f"💾  Dump: `{DUMP_CHANNEL}`\n"
        f"🟢  Running\n"
        f"🕐  {datetime.now().strftime('%d %b %Y %H:%M')}",
        parse_mode=ParseMode.MARKDOWN,
    )

# ─── /stop ────────────────────────────────────────────────────────────────────
async def cmd_stop(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid in grab_sessions:
        grab_sessions[uid]["running"] = False
        await update.message.reply_text("🛑  Grab cancelled!")
    else:
        await update.message.reply_text("ℹ️  No active grab.")

# ─── /list ────────────────────────────────────────────────────────────────────
async def cmd_list(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not watched:
        await update.message.reply_text("📋  Nothing watched.\nUse /watch @channel.", parse_mode=ParseMode.MARKDOWN)
        return
    lines = ["👁  *Watched Channels:*\n"]
    for key, info in watched.items():
        lines.append(f"• *{info['title']}* — `{info['pattern']}`")
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)

# ─── /search ─────────────────────────────────────────────────────────────────
async def cmd_search(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    args = update.message.text.split(None, 1)
    if len(args) < 2:
        await update.message.reply_text(
            "🔍  *Search Usage:*\n\n"
            "• /search `*.mp3`\n• /search `*.jpg`\n• /search `*.pdf`\n"
            "• /search `bigil`\n• /search `*` — all media",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    uid     = update.effective_user.id
    pattern = args[1].strip()
    pyro    = get_pyro_client(uid)
    logged  = pyro is not None
    query   = pattern.replace("*","").replace("."," ").strip() or pattern

    if not logged:
        await update.message.reply_text(
            "⚠️  *Not logged in!*\n\nUse /login first to search across your chats.",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    status = await update.message.reply_text(
        f"🔍  Searching `{pattern}`…\n✅  Using your account\n⏳  Please wait…",
        parse_mode=ParseMode.MARKDOWN,
    )

    found, failed, checked = 0, 0, 0
    try:
        async for dialog in pyro.get_dialogs():
            chat = dialog.chat
            if chat.type not in (ChatType.CHANNEL, ChatType.SUPERGROUP, ChatType.GROUP):
                continue
            checked += 1
            try:
                async for m in pyro.search_messages(chat.id, query=query, limit=100):
                    if not has_media(m) or not matches_pattern(m, pattern):
                        continue
                    src_title = chat.title or chat.username or str(chat.id)
                    src_link  = f"https://t.me/{chat.username}/{m.id}" if chat.username else f"(ID:{chat.id})"
                    try:
                        await pyro.copy_message(
                            chat_id=DUMP_CHANNEL, from_chat_id=chat.id,
                            message_id=m.id,
                            caption=make_caption(m, src_title, src_link),
                        )
                        found += 1
                        await asyncio.sleep(0.5)
                    except FloodWait as e:
                        await asyncio.sleep(e.value + 2)
                    except Exception as e:
                        log.warning(f"Copy: {e}"); failed += 1
            except (ChannelPrivate,): pass
            except FloodWait as e: await asyncio.sleep(e.value + 2)
            except Exception as e: log.warning(f"Search: {e}")

            if found > 0 and found % 15 == 0:
                try:
                    await status.edit_text(
                        f"🔍  Searching `{pattern}`…\n📦  Found: *{found}*\n📡  Checked: {checked}",
                        parse_mode=ParseMode.MARKDOWN,
                    )
                except Exception: pass

        await status.edit_text(
            f"✅  *Search Complete!*\n\n🔍  Pattern: `{pattern}`\n"
            f"📦  Collected: *{found}*\n📡  Checked: {checked}\n"
            f"⚠️  Failed: {failed}\n\n📥  Check dump channel!",
            parse_mode=ParseMode.MARKDOWN,
        )
    except Exception as e:
        await status.edit_text(f"❌  Error: `{e}`", parse_mode=ParseMode.MARKDOWN)

# ─── /grab ────────────────────────────────────────────────────────────────────
async def cmd_grab(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    parts = update.message.text.split(None, 2)
    if len(parts) < 2:
        await update.message.reply_text(
            "🪝  *Grab Usage:*\n\n"
            "• /grab @channel\n• /grab @channel `*.mp3`\n"
            "• /grab https://t.me/channel\n• /grab https://t.me/channel/123",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    uid     = update.effective_user.id
    target  = parts[1].strip()
    pattern = parts[2].strip() if len(parts) > 2 else "*"
    pyro    = get_pyro_client(uid)
    logged  = pyro is not None

    if not logged:
        await update.message.reply_text(
            "⚠️  *Not logged in!*\n\nUse /login first to grab from channels.",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    single_msg_id = None
    m2 = re.search(r"t\.me/([^/]+)/(\d+)", target)
    if m2:
        target        = f"@{m2.group(1)}"
        single_msg_id = int(m2.group(2))

    if target.startswith("https://t.me/"):
        target = "@" + target.split("t.me/")[-1].split("/")[0]
    if not target.startswith("@") and not target.lstrip("-").isdigit():
        target = "@" + target

    status = await update.message.reply_text(
        f"🪝  Connecting to `{target}`…", parse_mode=ParseMode.MARKDOWN
    )

    try:
        chat      = await pyro.get_chat(target)
        src_title = chat.title or chat.username or str(chat.id)
        src_link  = f"https://t.me/{chat.username}" if chat.username else f"ID:{chat.id}"
    except (ChannelPrivate, UsernameNotOccupied, UsernameInvalid, PeerIdInvalid) as e:
        await status.edit_text(
            f"❌  Cannot access `{target}`\n\n🔒  Make sure you are a member of this chat.",
            parse_mode=ParseMode.MARKDOWN,
        )
        return
    except Exception as e:
        await status.edit_text(f"❌  Error: `{e}`", parse_mode=ParseMode.MARKDOWN)
        return

    found, failed = 0, 0
    try:
        if single_msg_id:
            m3 = await pyro.get_messages(chat.id, single_msg_id)
            if has_media(m3):
                await pyro.copy_message(
                    chat_id=DUMP_CHANNEL, from_chat_id=chat.id, message_id=m3.id,
                    caption=make_caption(m3, src_title, f"{src_link}/{m3.id}"),
                )
                found = 1
        else:
            grab_sessions[uid] = {"running": True}
            await status.edit_text(
                f"🪝  Grabbing *{src_title}*\n🎯  `{pattern}`\n⏳  /stop to cancel",
                parse_mode=ParseMode.MARKDOWN,
            )
            async for m3 in pyro.get_chat_history(chat.id):
                if not grab_sessions.get(uid, {}).get("running"): break
                if not has_media(m3) or not matches_pattern(m3, pattern): continue
                link = f"{src_link}/{m3.id}" if chat.username else src_link
                try:
                    await pyro.copy_message(
                        chat_id=DUMP_CHANNEL, from_chat_id=chat.id,
                        message_id=m3.id, caption=make_caption(m3, src_title, link),
                    )
                    found += 1
                    await asyncio.sleep(0.8)
                except FloodWait as e: await asyncio.sleep(e.value + 2)
                except MessageIdInvalid: pass
                except Exception as e:
                    log.warning(f"Copy: {e}"); failed += 1
                if found > 0 and found % 20 == 0:
                    try:
                        await status.edit_text(
                            f"🪝  Grabbing *{src_title}*\n📦  *{found}* grabbed\n⏳  /stop to cancel",
                            parse_mode=ParseMode.MARKDOWN,
                        )
                    except Exception: pass
            grab_sessions.pop(uid, None)

        await status.edit_text(
            f"✅  *Grab Complete!*\n\n📡  *{src_title}*\n🎯  `{pattern}`\n"
            f"📦  Collected: *{found}*\n⚠️  Failed: {failed}\n\n📥  Check dump channel!",
            parse_mode=ParseMode.MARKDOWN,
        )
    except Exception as e:
        await status.edit_text(f"❌  Error: `{e}`", parse_mode=ParseMode.MARKDOWN)
    finally:
        grab_sessions.pop(uid, None)

# ─── /watch ───────────────────────────────────────────────────────────────────
async def cmd_watch(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    parts = update.message.text.split(None, 2)
    if len(parts) < 2:
        await update.message.reply_text("👁  Usage:\n• /watch @channel\n• /watch @channel `*.mp3`", parse_mode=ParseMode.MARKDOWN)
        return
    uid     = update.effective_user.id
    target  = parts[1].strip()
    pattern = parts[2].strip() if len(parts) > 2 else "*"
    pyro    = get_pyro_client(uid)
    if not pyro:
        await update.message.reply_text("⚠️  Use /login first.", parse_mode=ParseMode.MARKDOWN)
        return
    if not target.startswith("@") and not target.lstrip("-").isdigit():
        target = "@" + target
    try:
        chat  = await pyro.get_chat(target)
        key   = str(chat.id)
        title = chat.title or chat.username or key
        watched[key] = {"pattern": pattern, "title": title, "owner": uid}
        await update.message.reply_text(
            f"👁  *Now Watching!*\n\n📡  *{title}*\n🎯  `{pattern}`\n✅  Auto-collecting new media.",
            parse_mode=ParseMode.MARKDOWN,
        )
    except Exception as e:
        await update.message.reply_text(f"❌  Error: `{e}`", parse_mode=ParseMode.MARKDOWN)

# ─── /unwatch ─────────────────────────────────────────────────────────────────
async def cmd_unwatch(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    parts = update.message.text.split(None, 1)
    if len(parts) < 2:
        await update.message.reply_text("Usage: /unwatch @channel", parse_mode=ParseMode.MARKDOWN)
        return
    uid    = update.effective_user.id
    target = parts[1].strip()
    pyro   = get_pyro_client(uid)
    if not pyro:
        await update.message.reply_text("⚠️  Use /login first.", parse_mode=ParseMode.MARKDOWN)
        return
    if not target.startswith("@") and not target.lstrip("-").isdigit():
        target = "@" + target
    try:
        chat = await pyro.get_chat(target)
        key  = str(chat.id)
        if key in watched:
            watched.pop(key)
            await update.message.reply_text(f"✅  Stopped watching *{chat.title}*.", parse_mode=ParseMode.MARKDOWN)
        else:
            await update.message.reply_text(f"ℹ️  Not watching *{chat.title}*.", parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        await update.message.reply_text(f"❌  Error: `{e}`", parse_mode=ParseMode.MARKDOWN)

async def handle_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid   = update.effective_user.id
    state = sess.get_state(uid)
    if not state:
        return
    step = state.get("step")
    text = (update.message.text or "").strip()

    if step == "phone":
        if not text.startswith("+"):
            await update.message.reply_text(
                "❌  Include country code.\nExample: `+919876543210`",
                parse_mode=ParseMode.MARKDOWN,
            )
            return
        status = await update.message.reply_text("⏳  Sending OTP…")
        try:
            from telethon import TelegramClient
            from telethon.sessions import StringSession
            uc = TelegramClient(StringSession(), API_ID, API_HASH)
            await uc.connect()
            result = await uc.send_code_request(text)
            login_clients[uid] = uc
            sess.set_state(uid, {
                "step":       "otp",
                "phone":      text,
                "phone_hash": result.phone_code_hash,
            })
            await status.edit_text(
                "📩  *OTP sent to your Telegram!*\n\n"
                "⚡  Send the code *within 2 minutes*.\n"
                "Format: `1 2 3 4 5`  or  `12345`",
                parse_mode=ParseMode.MARKDOWN,
            )
        except Exception as e:
            await status.edit_text(f"❌  Failed: `{e}`", parse_mode=ParseMode.MARKDOWN)
            sess.clear_state(uid)

    elif step == "otp":
        from telethon import TelegramClient
        from telethon.errors import SessionPasswordNeededError
        code       = text.replace(" ", "")
        phone      = state["phone"]
        phone_hash = state["phone_hash"]
        uc         = login_clients.get(uid)
        if not uc:
            sess.clear_state(uid)
            await update.message.reply_text("⏰  Session expired. /login again.", parse_mode=ParseMode.MARKDOWN)
            return
        if not uc.is_connected():
            await uc.connect()
        try:
            await uc.sign_in(phone, code, phone_code_hash=phone_hash)
            session_str = uc.session.save()
            sess.save_session(uid, session_str)
            # Start a Pyrogram client from the Telethon session string for grab/search
            from pyrogram import Client as PyroClient
            pyro = PyroClient(
                f"user_{uid}",
                api_id=API_ID,
                api_hash=API_HASH,
                session_string=session_str,
                in_memory=True,
            )
            await pyro.start()
            sess.set_client(uid, pyro)
            login_clients.pop(uid, None)
            sess.clear_state(uid)
            me = await uc.get_me()
            await update.message.reply_text(
                f"✅  *Logged in as {me.first_name}!*\n"
                f"👤  @{me.username or 'N/A'}\n\n"
                "🎉  Bot can now access all your private chats!",
                parse_mode=ParseMode.MARKDOWN,
            )
        except SessionPasswordNeededError:
            login_clients[uid] = uc
            sess.set_state(uid, {"step": "2fa", "phone": phone, "phone_hash": phone_hash})
            await update.message.reply_text(
                "🔐  *2FA Required*\nSend your Telegram 2FA password:",
                parse_mode=ParseMode.MARKDOWN,
            )
        except Exception as e:
            login_clients.pop(uid, None)
            sess.clear_state(uid)
            await update.message.reply_text(
                f"❌  Login failed: `{e}`\n\nTry /login again.",
                parse_mode=ParseMode.MARKDOWN,
            )

    elif step == "2fa":
        from telethon import TelegramClient
        uc = login_clients.get(uid)
        if not uc:
            sess.clear_state(uid)
            await update.message.reply_text("⏰  Session expired. /login again.", parse_mode=ParseMode.MARKDOWN)
            return
        if not uc.is_connected():
            await uc.connect()
        try:
            await uc.sign_in(password=text)
            session_str = uc.session.save()
            sess.save_session(uid, session_str)
            from pyrogram import Client as PyroClient
            pyro = PyroClient(
                f"user_{uid}",
                api_id=API_ID,
                api_hash=API_HASH,
                session_string=session_str,
                in_memory=True,
            )
            await pyro.start()
            sess.set_client(uid, pyro)
            login_clients.pop(uid, None)
            sess.clear_state(uid)
            me = await uc.get_me()
            await update.message.reply_text(
                f"✅  *Logged in as {me.first_name}!*\n2FA verified. 🎉",
                parse_mode=ParseMode.MARKDOWN,
            )
        except Exception as e:
            login_clients.pop(uid, None)
            sess.clear_state(uid)
            await update.message.reply_text(
                f"❌  Wrong password: `{e}`\nTry /login again.",
                parse_mode=ParseMode.MARKDOWN,
            )

# ─── Keep-alive ───────────────────────────────────────────────────────────────
async def keep_alive():
    import aiohttp
    await asyncio.sleep(60)
    async with aiohttp.ClientSession() as session:
        while True:
            try:
                url = f"{APP_URL.rstrip('/')}/health" if APP_URL else f"http://localhost:{PORT}/health"
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as r:
                    log.info(f"💓 Keep-alive: {r.status}")
            except Exception as e:
                log.warning(f"Keep-alive: {e}")
            await asyncio.sleep(240)

# ─── Health server ────────────────────────────────────────────────────────────
class H(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")
    def log_message(self, *a): pass

# ─── Register handlers ────────────────────────────────────────────────────────
ptb.add_handler(CommandHandler("start",   cmd_start))
ptb.add_handler(CommandHandler("help",    cmd_help))
ptb.add_handler(CommandHandler("login",   cmd_login))
ptb.add_handler(CommandHandler("logout",  cmd_logout))
ptb.add_handler(CommandHandler("status",  cmd_status))
ptb.add_handler(CommandHandler("stop",    cmd_stop))
ptb.add_handler(CommandHandler("list",    cmd_list))
ptb.add_handler(CommandHandler("search",  cmd_search))
ptb.add_handler(CommandHandler("grab",    cmd_grab))
ptb.add_handler(CommandHandler("watch",   cmd_watch))
ptb.add_handler(CommandHandler("unwatch", cmd_unwatch))
ptb.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

# ─── Main ─────────────────────────────────────────────────────────────────────
async def main():
    sess.load()

    # Health server in thread
    threading.Thread(
        target=lambda: HTTPServer(("0.0.0.0", PORT), H).serve_forever(),
        daemon=True,
    ).start()
    log.info(f"🌐 Health on :{PORT}")

    # Restore user sessions
    await sess.restore_all()

    # Keep-alive task
    asyncio.create_task(keep_alive())

    # Start bot with polling
    await ptb.initialize()
    await ptb.start()
    await ptb.updater.start_polling(
        drop_pending_updates=True,
        allowed_updates=["message", "callback_query"],
    )

    log.info("✅ Bot ready — waiting for messages...")

    # Send startup notification
    try:
        me = await ptb.bot.get_me()
        await ptb.bot.send_message(
            DUMP_CHANNEL,
            f"🟢 Bot started!\n@{me.username}\n{datetime.now().strftime('%d %b %Y %H:%M')}",
        )
    except Exception as e:
        log.warning(f"Dump: {e}")

    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
