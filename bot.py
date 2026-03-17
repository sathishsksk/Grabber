"""
╔══════════════════════════════════════════════════════╗
║       🕵️  TELEGRAM MEDIA GRABBER BOT  v2.1 🕵️        ║
║   Search · Grab · Watch · Multi-user · Never Sleeps  ║
╚══════════════════════════════════════════════════════╝
"""

import os
import re
import asyncio
import logging
import threading
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler

import aiohttp
from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.enums import ChatType, MessageMediaType, ParseMode
from pyrogram.errors import (
    FloodWait, ChannelPrivate, ChatAdminRequired,
    UsernameNotOccupied, UsernameInvalid, PeerIdInvalid,
    MessageIdInvalid, SessionPasswordNeeded,
)

import sessions as sess
from config import (
    API_ID, API_HASH, BOT_TOKEN,
    DUMP_CHANNEL, PORT, APP_URL, OWNER_ID,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
log = logging.getLogger(__name__)

bot = Client(
    "grabber_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
)

grab_sessions: dict[int, dict] = {}
watched: dict[str, dict] = {}

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
    "json":("💻","Code"),   "xml":("💻","Code"),    "sql":("💻","Code"),
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

# Access control removed — open to all users


# ─── Owner only filter ────────────────────────────────────────────────────────
def owner_filter(_, __, msg: Message):
    uid = msg.from_user.id if msg.from_user else 0
    if uid != OWNER_ID:
        log.warning(f"🚫 Unauthorized user {uid} tried to use bot")
        return False
    return True

owner_only = filters.create(owner_filter)
# ─── Helpers ──────────────────────────────────────────────────────────────────
def get_file_info(msg: Message) -> tuple[str, str, str, int]:
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

def make_caption(msg: Message, src_title: str, src_link: str) -> str:
    emoji, cat, fname, size = get_file_info(msg)
    lines = [f"{emoji}  *{cat}*"]
    if fname:    lines.append(f"📂  `{fname}`")
    if size:     lines.append(f"💾  {human_size(size)}")
    lines.append(f"📡  *Source:* {src_title}")
    if src_link: lines.append(f"🔗  {src_link}")
    if msg.date: lines.append(f"🕐  {msg.date.strftime('%d %b %Y')}")
    return "\n".join(lines)

def has_media(msg: Message) -> bool:
    return bool(
        msg.photo or msg.video or msg.audio or msg.document or
        msg.voice or msg.animation or msg.video_note or msg.sticker
    )

def matches_pattern(msg: Message, pattern: str) -> bool:
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

def get_active_client(uid: int) -> Client:
    if sess.is_logged_in(uid):
        return sess.get_client(uid)
    return bot

# ─── Commands ─────────────────────────────────────────────────────────────────
@bot.on_message(filters.private & filters.command("start") & owner_only)
async def cmd_start(client: Client, msg: Message):
    uid    = msg.from_user.id
    logged = sess.is_logged_in(uid)
    status = "✅  *Logged in* — using your account" if logged else "⚠️  *Not logged in* — /login for private chats"
    await msg.reply_text(
        "🕵️  **MEDIA GRABBER BOT**\n\n"
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

@bot.on_message(filters.private & filters.command("help") & owner_only)
async def cmd_help(client: Client, msg: Message):
    await msg.reply_text(
        "📖  **HOW TO USE**\n\n"
        "━━━━━━━━━━━━━━━━━\n"
        "🔐  **LOGIN** — `/login`\n"
        "━━━━━━━━━━━━━━━━━\n"
        "Login so bot can access private chats you're in.\n\n"
        "━━━━━━━━━━━━━━━━━\n"
        "🔍  **SEARCH** — `/search`\n"
        "━━━━━━━━━━━━━━━━━\n"
        "• `/search *.mp3` — all MP3 files\n"
        "• `/search *.jpg` — all photos\n"
        "• `/search *.pdf` — all PDFs\n"
        "• `/search *.apk` — all APKs\n"
        "• `/search bigil` — by filename\n"
        "• `/search today market graph` — any text\n"
        "• `/search *` — ALL media\n\n"
        "━━━━━━━━━━━━━━━━━\n"
        "🪝  **GRAB** — `/grab`\n"
        "━━━━━━━━━━━━━━━━━\n"
        "• `/grab @channel`\n"
        "• `/grab @channel *.mp3`\n"
        "• `/grab https://t.me/ch/123` — single post\n\n"
        "━━━━━━━━━━━━━━━━━\n"
        "👁  **WATCH** — `/watch`\n"
        "━━━━━━━━━━━━━━━━━\n"
        "• `/watch @channel` — auto-collect\n"
        "• `/watch @channel *.mp3`\n"
        "• `/unwatch @channel` — stop\n"
        "• `/list` — show all watched\n\n"
        "📦  All files → dump channel with source info.",
        parse_mode=ParseMode.MARKDOWN,
    )

@bot.on_message(filters.private & filters.command("login") & owner_only)
async def cmd_login(client: Client, msg: Message):
    uid = msg.from_user.id
    if sess.is_logged_in(uid):
        c  = sess.get_client(uid)
        me = await c.get_me()
        await msg.reply_text(
            f"✅  Already logged in as **{me.first_name}**\nUse /logout to switch.",
            parse_mode=ParseMode.MARKDOWN,
        )
        return
    sess.set_state(uid, {"step": "phone"})
    await msg.reply_text(
        "🔐  **LOGIN WITH YOUR TELEGRAM ACCOUNT**\n\n"
        "Allows bot to access private chats you're in.\n\n"
        "🛡  *Session stored only on this server.*\n"
        "*No other user can access your session.*\n"
        "Revoke: /logout or Telegram → Settings → Devices.\n\n"
        "━━━━━━━━━━━━━━━━━\n"
        "📱  Send phone with country code:\n"
        "Example: `+919876543210`",
        parse_mode=ParseMode.MARKDOWN,
    )

@bot.on_message(filters.private & filters.command("logout") & owner_only)
async def cmd_logout(client: Client, msg: Message):
    uid = msg.from_user.id
    c   = sess.get_client(uid)
    if c:
        try: await c.stop()
        except Exception: pass
    sess.remove_client(uid)
    sess.delete_session(uid)
    sess.clear_state(uid)
    await msg.reply_text(
        "✅  **Logged out!**\nSession removed.\nAlso revoke: Telegram → Settings → Devices.",
        parse_mode=ParseMode.MARKDOWN,
    )

ALL_COMMANDS = ["start","help","login","logout","search","grab",
                "watch","unwatch","list","stop","status"]

@bot.on_message(filters.private & ~filters.command(ALL_COMMANDS) & owner_only)
async def handle_login_flow(client: Client, msg: Message):
    uid   = msg.from_user.id
    state = sess.get_state(uid)
    if not state:
        return
    step = state.get("step")
    text = (msg.text or "").strip()

    if step == "phone":
        if not text.startswith("+"):
            await msg.reply_text("❌  Include country code. Example: `+919876543210`", parse_mode=ParseMode.MARKDOWN)
            return
        status = await msg.reply_text("⏳  Sending OTP…")
        try:
            uc = Client(f"user_{uid}", api_id=API_ID, api_hash=API_HASH, in_memory=True)
            await uc.connect()
            sent = await uc.send_code(text)
            sess.set_state(uid, {
                "step": "otp", "phone": text,
                "phone_code_hash": sent.phone_code_hash, "client": uc,
            })
            await status.edit_text(
                "📩  **OTP sent!**\n\nSend the code here.\nFormat: `1 2 3 4 5`",
                parse_mode=ParseMode.MARKDOWN,
            )
        except FloodWait as e:
            await status.edit_text(f"⚠️  Too many attempts. Wait {e.value}s.")
            sess.clear_state(uid)
        except Exception as e:
            await status.edit_text(f"❌  Failed: `{e}`", parse_mode=ParseMode.MARKDOWN)
            sess.clear_state(uid)

    elif step == "otp":
        code, phone = text.replace(" ",""), state["phone"]
        uc = state["client"]
        try:
            await uc.sign_in(phone, state["phone_code_hash"], code)
            session_str = await uc.export_session_string()
            sess.save_session(uid, session_str)
            sess.set_client(uid, uc)
            sess.clear_state(uid)
            me = await uc.get_me()
            await msg.reply_text(
                f"✅  **Logged in as {me.first_name}!**\n🎉  Bot can now access your private chats!",
                parse_mode=ParseMode.MARKDOWN,
            )
        except SessionPasswordNeeded:
            sess.set_state(uid, {"step": "2fa", "client": uc})
            await msg.reply_text("🔐  **2FA Required**\nSend your Telegram 2FA password:", parse_mode=ParseMode.MARKDOWN)
        except Exception as e:
            await msg.reply_text(f"❌  Wrong OTP: `{e}`\nTry /login again.", parse_mode=ParseMode.MARKDOWN)
            sess.clear_state(uid)

    elif step == "2fa":
        uc = state["client"]
        try:
            await uc.check_password(text)
            session_str = await uc.export_session_string()
            sess.save_session(uid, session_str)
            sess.set_client(uid, uc)
            sess.clear_state(uid)
            me = await uc.get_me()
            await msg.reply_text(
                f"✅  **Logged in as {me.first_name}!**\n2FA verified. 🎉",
                parse_mode=ParseMode.MARKDOWN,
            )
        except Exception as e:
            await msg.reply_text(f"❌  Wrong password: `{e}`\nTry /login again.", parse_mode=ParseMode.MARKDOWN)
            sess.clear_state(uid)

@bot.on_message(filters.private & filters.command("search") & owner_only)
async def cmd_search(client: Client, msg: Message):
    args = msg.text.split(None, 1)
    if len(args) < 2:
        await msg.reply_text(
            "🔍  **Search Usage:**\n\n"
            "• `/search *.mp3`\n• `/search *.jpg`\n• `/search *.pdf`\n"
            "• `/search *.apk`\n• `/search bigil`\n• `/search *` — all media",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    uid     = msg.from_user.id
    pattern = args[1].strip()
    active  = get_active_client(uid)
    logged  = sess.is_logged_in(uid)
    query   = pattern.replace("*","").replace("."," ").strip() or pattern

    status = await msg.reply_text(
        f"🔍  Searching `{pattern}`…\n"
        f"{'✅  Using your account' if logged else '⚠️  /login for more results'}\n⏳  Please wait…",
        parse_mode=ParseMode.MARKDOWN,
    )

    found, failed, checked = 0, 0, 0
    try:
        async for dialog in active.get_dialogs():
            chat = dialog.chat
            if chat.type not in (ChatType.CHANNEL, ChatType.SUPERGROUP, ChatType.GROUP):
                continue
            checked += 1
            try:
                async for m in active.search_messages(chat.id, query=query, limit=100):
                    if not has_media(m) or not matches_pattern(m, pattern):
                        continue
                    src_title = chat.title or chat.username or str(chat.id)
                    src_link  = f"https://t.me/{chat.username}/{m.id}" if chat.username else f"(ID:{chat.id})"
                    try:
                        await bot.copy_message(
                            chat_id=DUMP_CHANNEL, from_chat_id=chat.id,
                            message_id=m.id,
                            caption=make_caption(m, src_title, src_link),
                            parse_mode=ParseMode.MARKDOWN,
                        )
                        found += 1
                        await asyncio.sleep(0.5)
                    except FloodWait as e:
                        await asyncio.sleep(e.value + 2)
                    except Exception as e:
                        log.warning(f"Copy: {e}"); failed += 1
            except (ChannelPrivate, ChatAdminRequired): pass
            except FloodWait as e: await asyncio.sleep(e.value + 2)
            except Exception as e: log.warning(f"Search {getattr(chat,'id','?')}: {e}")

            if found > 0 and found % 15 == 0:
                try:
                    await status.edit_text(
                        f"🔍  Searching `{pattern}`…\n📦  Found: **{found}**\n📡  Checked: {checked}",
                        parse_mode=ParseMode.MARKDOWN,
                    )
                except Exception: pass

        await status.edit_text(
            f"✅  **Search Complete!**\n\n🔍  Pattern: `{pattern}`\n"
            f"📦  Collected: **{found}**\n📡  Checked: {checked}\n"
            f"⚠️  Failed: {failed}\n\n📥  Check dump channel!",
            parse_mode=ParseMode.MARKDOWN,
        )
    except Exception as e:
        await status.edit_text(f"❌  Error: `{e}`", parse_mode=ParseMode.MARKDOWN)

@bot.on_message(filters.private & filters.command("grab") & owner_only)
async def cmd_grab(client: Client, msg: Message):
    parts = msg.text.split(None, 2)
    if len(parts) < 2:
        await msg.reply_text(
            "🪝  **Grab Usage:**\n\n"
            "• `/grab @channel`\n• `/grab @channel *.mp3`\n"
            "• `/grab https://t.me/channel`\n• `/grab https://t.me/channel/123`",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    uid     = msg.from_user.id
    target  = parts[1].strip()
    pattern = parts[2].strip() if len(parts) > 2 else "*"
    active  = get_active_client(uid)
    logged  = sess.is_logged_in(uid)

    single_msg_id = None
    m2 = re.search(r"t\.me/([^/]+)/(\d+)", target)
    if m2:
        target        = f"@{m2.group(1)}"
        single_msg_id = int(m2.group(2))

    if target.startswith("https://t.me/"):
        target = "@" + target.split("t.me/")[-1].split("/")[0]
    if not target.startswith("@") and not target.lstrip("-").isdigit():
        target = "@" + target

    status = await msg.reply_text(
        f"🪝  Connecting to `{target}`…\n{'✅  Your account' if logged else '⚠️  Bot access'}",
        parse_mode=ParseMode.MARKDOWN,
    )

    try:
        chat      = await active.get_chat(target)
        src_title = chat.title or chat.username or str(chat.id)
        src_link  = f"https://t.me/{chat.username}" if chat.username else f"ID:{chat.id}"
    except (ChannelPrivate, UsernameNotOccupied, UsernameInvalid, PeerIdInvalid) as e:
        await status.edit_text(
            f"❌  Cannot access `{target}`\n\n"
            f"{'🔒  Private chat — use /login first.' if not logged else str(e)}",
            parse_mode=ParseMode.MARKDOWN,
        )
        return
    except Exception as e:
        await status.edit_text(f"❌  Error: `{e}`", parse_mode=ParseMode.MARKDOWN)
        return

    found, failed = 0, 0
    try:
        if single_msg_id:
            m3 = await active.get_messages(chat.id, single_msg_id)
            if has_media(m3):
                await bot.copy_message(
                    chat_id=DUMP_CHANNEL, from_chat_id=chat.id, message_id=m3.id,
                    caption=make_caption(m3, src_title, f"{src_link}/{m3.id}"),
                    parse_mode=ParseMode.MARKDOWN,
                )
                found = 1
        else:
            grab_sessions[uid] = {"running": True}
            await status.edit_text(
                f"🪝  Grabbing **{src_title}**\n🎯  `{pattern}`\n⏳  /stop to cancel",
                parse_mode=ParseMode.MARKDOWN,
            )
            async for m3 in active.get_chat_history(chat.id):
                if not grab_sessions.get(uid, {}).get("running"): break
                if not has_media(m3) or not matches_pattern(m3, pattern): continue
                link = f"{src_link}/{m3.id}" if chat.username else src_link
                try:
                    await bot.copy_message(
                        chat_id=DUMP_CHANNEL, from_chat_id=chat.id, message_id=m3.id,
                        caption=make_caption(m3, src_title, link),
                        parse_mode=ParseMode.MARKDOWN,
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
                            f"🪝  Grabbing **{src_title}**\n📦  **{found}** grabbed\n⏳  /stop to cancel",
                            parse_mode=ParseMode.MARKDOWN,
                        )
                    except Exception: pass
            grab_sessions.pop(uid, None)

        await status.edit_text(
            f"✅  **Grab Complete!**\n\n📡  **{src_title}**\n🎯  `{pattern}`\n"
            f"📦  Collected: **{found}**\n⚠️  Failed: {failed}\n\n📥  Check dump channel!",
            parse_mode=ParseMode.MARKDOWN,
        )
    except FloodWait as e:
        await asyncio.sleep(e.value)
        await status.edit_text(f"⚠️  Flood wait. Retry in {e.value}s.")
    except Exception as e:
        await status.edit_text(f"❌  Error: `{e}`", parse_mode=ParseMode.MARKDOWN)
    finally:
        grab_sessions.pop(uid, None)

@bot.on_message(filters.private & filters.command("stop") & owner_only)
async def cmd_stop(client: Client, msg: Message):
    uid = msg.from_user.id
    if uid in grab_sessions:
        grab_sessions[uid]["running"] = False
        await msg.reply_text("🛑  Grab cancelled!")
    else:
        await msg.reply_text("ℹ️  No active grab.")

@bot.on_message(filters.private & filters.command("watch") & owner_only)
async def cmd_watch(client: Client, msg: Message):
    parts = msg.text.split(None, 2)
    if len(parts) < 2:
        await msg.reply_text("👁  Usage:\n• `/watch @channel`\n• `/watch @channel *.mp3`", parse_mode=ParseMode.MARKDOWN)
        return
    uid     = msg.from_user.id
    target  = parts[1].strip()
    pattern = parts[2].strip() if len(parts) > 2 else "*"
    active  = get_active_client(uid)
    if not target.startswith("@") and not target.lstrip("-").isdigit():
        target = "@" + target
    try:
        chat  = await active.get_chat(target)
        key   = str(chat.id)
        title = chat.title or chat.username or key
        watched[key] = {"pattern": pattern, "title": title, "owner": uid}
        await msg.reply_text(
            f"👁  **Now Watching!**\n\n📡  **{title}**\n🎯  `{pattern}`\n✅  Auto-collecting.",
            parse_mode=ParseMode.MARKDOWN,
        )
    except Exception as e:
        await msg.reply_text(f"❌  Error: `{e}`", parse_mode=ParseMode.MARKDOWN)

@bot.on_message(filters.private & filters.command("unwatch") & owner_only)
async def cmd_unwatch(client: Client, msg: Message):
    parts = msg.text.split(None, 1)
    if len(parts) < 2:
        await msg.reply_text("Usage: `/unwatch @channel`", parse_mode=ParseMode.MARKDOWN)
        return
    uid    = msg.from_user.id
    target = parts[1].strip()
    active = get_active_client(uid)
    if not target.startswith("@") and not target.lstrip("-").isdigit():
        target = "@" + target
    try:
        chat = await active.get_chat(target)
        key  = str(chat.id)
        if key in watched:
            watched.pop(key)
            await msg.reply_text(f"✅  Stopped watching **{chat.title}**.", parse_mode=ParseMode.MARKDOWN)
        else:
            await msg.reply_text(f"ℹ️  Not watching **{chat.title}**.", parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        await msg.reply_text(f"❌  Error: `{e}`", parse_mode=ParseMode.MARKDOWN)

@bot.on_message(filters.private & filters.command("list") & owner_only)
async def cmd_list(client: Client, msg: Message):
    if not watched:
        await msg.reply_text("📋  Nothing watched.\nUse `/watch @channel`.", parse_mode=ParseMode.MARKDOWN)
        return
    lines = ["👁  **Watched Channels:**\n"]
    for key, info in watched.items():
        lines.append(f"• **{info['title']}** — `{info['pattern']}`")
    await msg.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)

@bot.on_message(filters.private & filters.command("status") & owner_only)
async def cmd_status(client: Client, msg: Message):
    uid    = msg.from_user.id
    logged = sess.is_logged_in(uid)
    me_bot = await bot.get_me()
    acc    = "⚠️  Not logged in"
    if logged:
        try:
            me_u = await sess.get_client(uid).get_me()
            acc  = f"✅  **{me_u.first_name}** (@{me_u.username or 'N/A'})"
        except Exception: pass
    await msg.reply_text(
        f"🤖  **Bot Status**\n\n🤖  @{me_bot.username}\n👤  {acc}\n"
        f"👁  Watching: **{len(watched)}**\n💾  Dump: `{DUMP_CHANNEL}`\n"
        f"🟢  Running\n🕐  {datetime.now().strftime('%d %b %Y %H:%M')}",
        parse_mode=ParseMode.MARKDOWN,
    )

@bot.on_message(filters.channel | filters.group)
async def on_new_post(client: Client, msg: Message):
    key  = str(msg.chat.id)
    info = watched.get(key)
    if not info or not has_media(msg): return
    if not matches_pattern(msg, info.get("pattern","*")): return
    src_title = msg.chat.title or msg.chat.username or str(msg.chat.id)
    src_link  = f"https://t.me/{msg.chat.username}/{msg.id}" if msg.chat.username else f"(ID:{msg.chat.id})"
    try:
        await bot.copy_message(
            chat_id=DUMP_CHANNEL, from_chat_id=msg.chat.id,
            message_id=msg.id, caption=make_caption(msg, src_title, src_link),
            parse_mode=ParseMode.MARKDOWN,
        )
    except FloodWait as e: await asyncio.sleep(e.value + 1)
    except Exception as e: log.warning(f"Auto-collect: {e}")

# ─── Keep-alive ───────────────────────────────────────────────────────────────
async def keep_alive():
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

# ─── Health server — separate thread, no event loop conflict ──────────────────
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")
    def log_message(self, *args): pass

def start_health_server():
    server = HTTPServer(("0.0.0.0", PORT), HealthHandler)
    log.info(f"🌐 Health server on :{PORT}")
    server.serve_forever()

# ─── Entry point ──────────────────────────────────────────────────────────────
async def main():
    sess.load()

    # Health server in background thread — no event loop conflict
    t = threading.Thread(target=start_health_server, daemon=True)
    t.start()

    # Start bot FIRST, then run startup tasks
    await bot.start()

    me = await bot.get_me()
    log.info(f"🕵️ Grabber Bot started as @{me.username}")

    asyncio.create_task(keep_alive())
    await sess.restore_all()

    try:
        await bot.send_message(
            DUMP_CHANNEL,
            "Started! Bot is running.\n"
            "Bot started!\n"
            f"Bot: @{me.username}\n"
            f"Time: {datetime.now().strftime('%d %b %Y %H:%M')}",
        )
    except Exception:
        pass

    log.info("✅ Bot ready — waiting for messages...")

    # Keep running forever
    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
