"""
╔══════════════════════════════════════════════════════╗
║       🕵️  TELEGRAM MEDIA GRABBER BOT  v2.0 🕵️        ║
║   Search · Grab · Watch · Multi-user · Never Sleeps  ║
╚══════════════════════════════════════════════════════╝
"""

import os
import re
import asyncio
import logging
from datetime import datetime

import aiohttp
from aiohttp import web
from pyrogram import Client, filters, idle
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
    DUMP_CHANNEL, PORT, APP_URL, ALLOWED_USERS,
)

# ─── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
log = logging.getLogger(__name__)

# ─── Bot client ───────────────────────────────────────────────────────────────
bot = Client(
    "grabber_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
)

# ─── Active grab sessions (user_id → {running: bool}) ────────────────────────
grab_sessions: dict[int, dict] = {}

# ─── Extension → (emoji, category) ───────────────────────────────────────────
EXT_MAP = {
    "jpg":("📸","Photo"),  "jpeg":("📸","Photo"), "png":("📸","Photo"),
    "gif":("🎞️","GIF"),   "webp":("📸","Photo"), "bmp":("📸","Photo"),
    "mp4":("🎬","Video"),  "mkv":("🎬","Video"),  "avi":("🎬","Video"),
    "mov":("🎬","Video"),  "flv":("🎬","Video"),  "wmv":("🎬","Video"),
    "webm":("🎬","Video"), "ts":("🎬","Video"),
    "mp3":("🎵","Music"),  "flac":("🎵","Music"), "wav":("🎵","Music"),
    "aac":("🎵","Music"),  "ogg":("🎵","Music"),  "m4a":("🎵","Music"),
    "opus":("🎵","Music"), "wma":("🎵","Music"),
    "pdf":("📄","PDF"),
    "doc":("📝","Document"), "docx":("📝","Document"),
    "xls":("📊","Spreadsheet"), "xlsx":("📊","Spreadsheet"),
    "ppt":("📊","Presentation"), "pptx":("📊","Presentation"),
    "txt":("📝","Text"),   "csv":("📊","CSV"),
    "zip":("🗜️","Archive"), "rar":("🗜️","Archive"),
    "7z":("🗜️","Archive"),  "tar":("🗜️","Archive"), "gz":("🗜️","Archive"),
    "py":("💻","Code"),    "js":("💻","Code"),    "html":("💻","Code"),
    "json":("💻","Code"),  "xml":("💻","Code"),   "sql":("💻","Code"),
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


# ─── Access control ───────────────────────────────────────────────────────────
def is_allowed(uid: int) -> bool:
    if not ALLOWED_USERS:
        return True   # open to all if not configured
    return uid in ALLOWED_USERS


# NEW — safe
def allowed_filter(_, __, msg: Message):
    if not msg.from_user:
        return False
    if not ALLOWED_USERS:
        return True   # no restriction set → allow all
    return msg.from_user.id in ALLOWED_USERS

allowed = filters.create(allowed_filter)


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
    if fname:       lines.append(f"📂  `{fname}`")
    if size:        lines.append(f"💾  {human_size(size)}")
    lines.append(   f"📡  *Source:* {src_title}")
    if src_link:    lines.append(f"🔗  {src_link}")
    if msg.date:    lines.append(f"🕐  {msg.date.strftime('%d %b %Y')}")
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
    text = (msg.text or msg.caption or "").lower()
    fname_lower = fname.lower()
    regex = "^" + re.escape(pattern).replace(r"\*",".*").replace(r"\?",".") + "$"
    return bool(
        re.search(regex, fname_lower, re.I) or
        re.search(regex, text, re.I) or
        pattern.lower() in fname_lower or
        pattern.lower() in text
    )


def get_active_client(uid: int) -> Client:
    """Return user's own session client if logged in, else bot client."""
    if sess.is_logged_in(uid):
        return sess.get_client(uid)
    return bot


# ─── /start ───────────────────────────────────────────────────────────────────
@bot.on_message(filters.private & filters.command("start") & allowed)
async def cmd_start(client: Client, msg: Message):
    uid = msg.from_user.id
    logged = sess.is_logged_in(uid)
    status_line = "✅  *Logged in* — using your account" if logged else "⚠️  *Not logged in* — using bot access only"

    await msg.reply_text(
        "🕵️  **MEDIA GRABBER BOT**\n\n"
        f"{status_line}\n\n"
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
@bot.on_message(filters.private & filters.command("help") & allowed)
async def cmd_help(client: Client, msg: Message):
    await msg.reply_text(
        "📖  **HOW TO USE**\n\n"

        "━━━━━━━━━━━━━━━━━\n"
        "🔐  **LOGIN FIRST** — `/login`\n"
        "━━━━━━━━━━━━━━━━━\n"
        "Login with your Telegram account so the bot can\n"
        "access private groups/channels *you* are a member of.\n\n"

        "━━━━━━━━━━━━━━━━━\n"
        "🔍  **SEARCH** — `/search`\n"
        "━━━━━━━━━━━━━━━━━\n"
        "• `/search *.mp3` — all MP3 files\n"
        "• `/search *.jpg` — all photos\n"
        "• `/search *.pdf` — all PDFs\n"
        "• `/search *.apk` — all APKs\n"
        "• `/search *.mkv` — all videos\n"
        "• `/search bigil` — files named bigil\n"
        "• `/search today market graph` — any text\n"
        "• `/search *` — ALL media\n\n"

        "━━━━━━━━━━━━━━━━━\n"
        "🪝  **GRAB** — `/grab`\n"
        "━━━━━━━━━━━━━━━━━\n"
        "• `/grab @channel` — grab all media\n"
        "• `/grab @channel *.mp3` — only MP3s\n"
        "• `/grab https://t.me/ch` — using link\n"
        "• `/grab https://t.me/ch/123` — single post\n\n"

        "━━━━━━━━━━━━━━━━━\n"
        "👁  **WATCH** — `/watch`\n"
        "━━━━━━━━━━━━━━━━━\n"
        "• `/watch @channel` — auto-collect new posts\n"
        "• `/watch @channel *.mp3` — only MP3s\n"
        "• `/unwatch @channel` — stop\n"
        "• `/list` — show all watched\n\n"

        "📦  All files go to your dump channel\n"
        "     with source + category in caption.",
        parse_mode=ParseMode.MARKDOWN,
    )


# ─── /login ───────────────────────────────────────────────────────────────────
@bot.on_message(filters.private & filters.command("login") & allowed)
async def cmd_login(client: Client, msg: Message):
    uid = msg.from_user.id

    if sess.is_logged_in(uid):
        c  = sess.get_client(uid)
        me = await c.get_me()
        await msg.reply_text(
            f"✅  Already logged in as **{me.first_name}** (@{me.username or 'N/A'})\n\n"
            f"Use /logout to switch accounts.",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    sess.set_state(uid, {"step": "phone"})
    await msg.reply_text(
        "🔐  **LOGIN WITH YOUR TELEGRAM ACCOUNT**\n\n"
        "This allows the bot to access channels/groups\n"
        "that *you* are a member of.\n\n"
        "🛡  *Your session is stored only on this server.*\n"
        "*No one else can use or see your session.*\n"
        "You can revoke it anytime with /logout or from\n"
        "Telegram → Settings → Devices.\n\n"
        "━━━━━━━━━━━━━━━━━\n"
        "📱  Send your phone number with country code:\n"
        "Example: `+919876543210`",
        parse_mode=ParseMode.MARKDOWN,
    )


# ─── /logout ──────────────────────────────────────────────────────────────────
@bot.on_message(filters.private & filters.command("logout") & allowed)
async def cmd_logout(client: Client, msg: Message):
    uid = msg.from_user.id
    c   = sess.get_client(uid)
    if c:
        try:
            await c.stop()
        except Exception:
            pass
    sess.remove_client(uid)
    sess.delete_session(uid)
    sess.clear_state(uid)
    await msg.reply_text(
        "✅  **Logged out successfully!**\n\n"
        "Your session has been removed from this server.\n"
        "You can also revoke it from Telegram → Settings → Devices.",
        parse_mode=ParseMode.MARKDOWN,
    )


# ─── Login flow handler ───────────────────────────────────────────────────────
ALL_COMMANDS = ["start","help","login","logout","search","grab",
                "watch","unwatch","list","stop","status"]

@bot.on_message(
    filters.private & ~filters.command(ALL_COMMANDS) & allowed
)
async def handle_login_flow(client: Client, msg: Message):
    uid   = msg.from_user.id
    state = sess.get_state(uid)
    if not state:
        return

    step = state.get("step")
    text = (msg.text or "").strip()

    # ── Step 1: Phone number ──────────────────────────────────────────────────
    if step == "phone":
        if not text.startswith("+"):
            await msg.reply_text(
                "❌  Please include country code.\nExample: `+919876543210`",
                parse_mode=ParseMode.MARKDOWN,
            )
            return

        status = await msg.reply_text("⏳  Sending OTP to your Telegram…")
        try:
            user_client = Client(
                name=f"user_{uid}",
                api_id=API_ID,
                api_hash=API_HASH,
                in_memory=True,
            )
            await user_client.connect()
            sent = await user_client.send_code(text)
            sess.set_state(uid, {
                "step":            "otp",
                "phone":           text,
                "phone_code_hash": sent.phone_code_hash,
                "client":          user_client,
            })
            await status.edit_text(
                "📩  **OTP sent!**\n\n"
                "Check your Telegram messages and send the code here.\n"
                "Format: `1 2 3 4 5`  or  `12345`",
                parse_mode=ParseMode.MARKDOWN,
            )
        except FloodWait as e:
            await status.edit_text(f"⚠️  Too many attempts. Wait {e.value}s and try again.")
            sess.clear_state(uid)
        except Exception as e:
            await status.edit_text(f"❌  Failed to send OTP: `{e}`", parse_mode=ParseMode.MARKDOWN)
            sess.clear_state(uid)

    # ── Step 2: OTP ───────────────────────────────────────────────────────────
    elif step == "otp":
        code        = text.replace(" ", "")
        phone       = state["phone"]
        phone_hash  = state["phone_code_hash"]
        user_client = state["client"]

        try:
            await user_client.sign_in(phone, phone_hash, code)
            session_str = await user_client.export_session_string()
            sess.save_session(uid, session_str)
            sess.set_client(uid, user_client)
            sess.clear_state(uid)

            me = await user_client.get_me()
            await msg.reply_text(
                f"✅  **Logged in as {me.first_name}!**\n\n"
                f"👤  Name: {me.first_name} {me.last_name or ''}\n"
                f"📱  Phone: `{phone}`\n\n"
                f"🎉  Now /search, /grab, /watch will use your account\n"
                f"and can access all private chats you're in!",
                parse_mode=ParseMode.MARKDOWN,
            )
        except SessionPasswordNeeded:
            sess.set_state(uid, {
                "step":   "2fa",
                "client": user_client,
            })
            await msg.reply_text(
                "🔐  **2FA Password Required**\n\n"
                "Your account has Two-Step Verification enabled.\n"
                "Send your Telegram 2FA password:",
                parse_mode=ParseMode.MARKDOWN,
            )
        except Exception as e:
            await msg.reply_text(
                f"❌  Wrong OTP or expired.\n`{e}`\n\nTry /login again.",
                parse_mode=ParseMode.MARKDOWN,
            )
            sess.clear_state(uid)

    # ── Step 3: 2FA password ──────────────────────────────────────────────────
    elif step == "2fa":
        user_client = state["client"]
        try:
            await user_client.check_password(text)
            session_str = await user_client.export_session_string()
            sess.save_session(uid, session_str)
            sess.set_client(uid, user_client)
            sess.clear_state(uid)

            me = await user_client.get_me()
            await msg.reply_text(
                f"✅  **Logged in as {me.first_name}!**\n\n"
                f"2FA verified successfully. 🎉\n"
                f"Bot now has full access to your channels!",
                parse_mode=ParseMode.MARKDOWN,
            )
        except Exception as e:
            await msg.reply_text(
                f"❌  Wrong password.\n`{e}`\n\nTry /login again.",
                parse_mode=ParseMode.MARKDOWN,
            )
            sess.clear_state(uid)


# ─── /search ─────────────────────────────────────────────────────────────────
@bot.on_message(filters.private & filters.command("search") & allowed)
async def cmd_search(client: Client, msg: Message):
    args = msg.text.split(None, 1)
    if len(args) < 2:
        await msg.reply_text(
            "🔍  **Search Usage:**\n\n"
            "• `/search *.mp3`\n"
            "• `/search *.jpg`\n"
            "• `/search *.pdf`\n"
            "• `/search *.apk`\n"
            "• `/search bigil`\n"
            "• `/search today market graph`\n"
            "• `/search *`  ← all media",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    uid     = msg.from_user.id
    pattern = args[1].strip()
    active  = get_active_client(uid)
    logged  = sess.is_logged_in(uid)

    status = await msg.reply_text(
        f"🔍  Searching for `{pattern}`…\n"
        f"{'✅  Using your account' if logged else '⚠️  Using bot access (login for more results)'}\n"
        f"⏳  Scanning your chats…",
        parse_mode=ParseMode.MARKDOWN,
    )

    query   = pattern.replace("*","").replace("."," ").strip() or pattern
    found   = 0
    failed  = 0
    checked = 0

    try:
        async for dialog in active.get_dialogs():
            chat = dialog.chat
            if chat.type not in (
                ChatType.CHANNEL, ChatType.SUPERGROUP, ChatType.GROUP
            ):
                continue

            checked += 1
            try:
                async for m in active.search_messages(chat.id, query=query, limit=100):
                    if not has_media(m):
                        continue
                    if not matches_pattern(m, pattern):
                        continue

                    src_title = chat.title or chat.username or str(chat.id)
                    src_link  = (
                        f"https://t.me/{chat.username}/{m.id}"
                        if chat.username else f"(ID: {chat.id})"
                    )
                    caption = make_caption(m, src_title, src_link)

                    try:
                        await bot.copy_message(
                            chat_id=DUMP_CHANNEL,
                            from_chat_id=chat.id,
                            message_id=m.id,
                            caption=caption,
                            parse_mode=ParseMode.MARKDOWN,
                        )
                        found += 1
                        await asyncio.sleep(0.5)
                    except FloodWait as e:
                        await asyncio.sleep(e.value + 2)
                    except Exception as e:
                        log.warning(f"Copy failed: {e}")
                        failed += 1

            except (ChannelPrivate, ChatAdminRequired):
                pass
            except FloodWait as e:
                await asyncio.sleep(e.value + 2)
            except Exception as e:
                log.warning(f"Search in {getattr(chat,'id','?')}: {e}")

            if found > 0 and found % 15 == 0:
                try:
                    await status.edit_text(
                        f"🔍  Searching `{pattern}`…\n"
                        f"📦  Found: **{found}** files\n"
                        f"📡  Checked: {checked} chats",
                        parse_mode=ParseMode.MARKDOWN,
                    )
                except Exception:
                    pass

        await status.edit_text(
            f"✅  **Search Complete!**\n\n"
            f"🔍  Pattern: `{pattern}`\n"
            f"📦  Collected: **{found}** files\n"
            f"📡  Checked: {checked} chats\n"
            f"⚠️  Failed: {failed}\n\n"
            f"📥  Check your dump channel!",
            parse_mode=ParseMode.MARKDOWN,
        )

    except Exception as e:
        log.error(f"Search error: {e}")
        await status.edit_text(f"❌  Search error: `{e}`", parse_mode=ParseMode.MARKDOWN)


# ─── /grab ────────────────────────────────────────────────────────────────────
@bot.on_message(filters.private & filters.command("grab") & allowed)
async def cmd_grab(client: Client, msg: Message):
    parts = msg.text.split(None, 2)
    if len(parts) < 2:
        await msg.reply_text(
            "🪝  **Grab Usage:**\n\n"
            "• `/grab @channel`\n"
            "• `/grab @channel *.mp3`\n"
            "• `/grab https://t.me/channel`\n"
            "• `/grab https://t.me/channel/123`  ← single post",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    uid     = msg.from_user.id
    target  = parts[1].strip()
    pattern = parts[2].strip() if len(parts) > 2 else "*"
    active  = get_active_client(uid)
    logged  = sess.is_logged_in(uid)

    # Parse single post ID
    single_msg_id = None
    m2 = re.search(r"t\.me/([^/]+)/(\d+)", target)
    if m2:
        target        = f"@{m2.group(1)}"
        single_msg_id = int(m2.group(2))

    # Normalize target
    if target.startswith("https://t.me/"):
        target = "@" + target.split("t.me/")[-1].split("/")[0]
    if not target.startswith("@") and not target.lstrip("-").isdigit():
        target = "@" + target

    status = await msg.reply_text(
        f"🪝  Connecting to `{target}`…\n"
        f"{'✅  Using your account' if logged else '⚠️  Using bot access'}",
        parse_mode=ParseMode.MARKDOWN,
    )

    try:
        chat      = await active.get_chat(target)
        src_title = chat.title or chat.username or str(chat.id)
        src_link  = f"https://t.me/{chat.username}" if chat.username else f"ID:{chat.id}"
    except (UsernameNotOccupied, UsernameInvalid, PeerIdInvalid, ChannelPrivate) as e:
        await status.edit_text(
            f"❌  Cannot access `{target}`\n\n"
            f"{'🔒  This is a private chat. Login with /login first.' if not logged else str(e)}\n\n"
            f"Make sure you are a member of this chat.",
            parse_mode=ParseMode.MARKDOWN,
        )
        return
    except Exception as e:
        await status.edit_text(f"❌  Error: `{e}`", parse_mode=ParseMode.MARKDOWN)
        return

    found  = 0
    failed = 0

    try:
        if single_msg_id:
            # Single post grab
            m3 = await active.get_messages(chat.id, single_msg_id)
            if has_media(m3):
                caption = make_caption(m3, src_title, f"{src_link}/{m3.id}")
                await bot.copy_message(
                    chat_id=DUMP_CHANNEL,
                    from_chat_id=chat.id,
                    message_id=m3.id,
                    caption=caption,
                    parse_mode=ParseMode.MARKDOWN,
                )
                found = 1
        else:
            # Full history grab
            grab_sessions[uid] = {"running": True}
            await status.edit_text(
                f"🪝  Grabbing from **{src_title}**\n"
                f"🎯  Pattern: `{pattern}`\n"
                f"⏳  Scanning history… (send /stop to cancel)",
                parse_mode=ParseMode.MARKDOWN,
            )

            async for m3 in active.get_chat_history(chat.id):
                if not grab_sessions.get(uid, {}).get("running"):
                    break
                if not has_media(m3):
                    continue
                if not matches_pattern(m3, pattern):
                    continue

                link    = f"{src_link}/{m3.id}" if chat.username else src_link
                caption = make_caption(m3, src_title, link)

                try:
                    await bot.copy_message(
                        chat_id=DUMP_CHANNEL,
                        from_chat_id=chat.id,
                        message_id=m3.id,
                        caption=caption,
                        parse_mode=ParseMode.MARKDOWN,
                    )
                    found += 1
                    await asyncio.sleep(0.8)
                except FloodWait as e:
                    await asyncio.sleep(e.value + 2)
                except MessageIdInvalid:
                    pass
                except Exception as e:
                    log.warning(f"Copy failed: {e}")
                    failed += 1

                if found > 0 and found % 20 == 0:
                    try:
                        await status.edit_text(
                            f"🪝  Grabbing **{src_title}**\n"
                            f"📦  Grabbed: **{found}** files\n"
                            f"⏳  Still running… send /stop to cancel",
                            parse_mode=ParseMode.MARKDOWN,
                        )
                    except Exception:
                        pass

            grab_sessions.pop(uid, None)

        await status.edit_text(
            f"✅  **Grab Complete!**\n\n"
            f"📡  Source: **{src_title}**\n"
            f"🎯  Pattern: `{pattern}`\n"
            f"📦  Collected: **{found}** files\n"
            f"⚠️  Failed: {failed}\n\n"
            f"📥  Check your dump channel!",
            parse_mode=ParseMode.MARKDOWN,
        )

    except FloodWait as e:
        await asyncio.sleep(e.value)
        await status.edit_text(f"⚠️  Flood wait. Retry in {e.value}s.")
    except Exception as e:
        log.error(f"Grab error: {e}")
        await status.edit_text(f"❌  Grab failed: `{e}`", parse_mode=ParseMode.MARKDOWN)
    finally:
        grab_sessions.pop(uid, None)


# ─── /stop ────────────────────────────────────────────────────────────────────
@bot.on_message(filters.private & filters.command("stop") & allowed)
async def cmd_stop(client: Client, msg: Message):
    uid = msg.from_user.id
    if uid in grab_sessions:
        grab_sessions[uid]["running"] = False
        await msg.reply_text("🛑  Grab cancelled!")
    else:
        await msg.reply_text("ℹ️  No active grab running.")


# ─── /watch & /unwatch ────────────────────────────────────────────────────────
watched: dict[str, dict] = {}

@bot.on_message(filters.private & filters.command("watch") & allowed)
async def cmd_watch(client: Client, msg: Message):
    parts = msg.text.split(None, 2)
    if len(parts) < 2:
        await msg.reply_text(
            "👁  **Watch Usage:**\n\n"
            "• `/watch @channel`\n"
            "• `/watch @channel *.mp3`",
            parse_mode=ParseMode.MARKDOWN,
        )
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
            f"👁  **Now Watching!**\n\n"
            f"📡  Channel: **{title}**\n"
            f"🎯  Pattern: `{pattern}`\n\n"
            f"All new matching media will be auto-collected. ✅",
            parse_mode=ParseMode.MARKDOWN,
        )
    except Exception as e:
        await msg.reply_text(f"❌  Error: `{e}`", parse_mode=ParseMode.MARKDOWN)


@bot.on_message(filters.private & filters.command("unwatch") & allowed)
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
            await msg.reply_text(f"ℹ️  **{chat.title}** is not being watched.", parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        await msg.reply_text(f"❌  Error: `{e}`", parse_mode=ParseMode.MARKDOWN)


@bot.on_message(filters.private & filters.command("list") & allowed)
async def cmd_list(client: Client, msg: Message):
    if not watched:
        await msg.reply_text(
            "📋  Nothing being watched.\n\nUse `/watch @channel` to start.",
            parse_mode=ParseMode.MARKDOWN,
        )
        return
    lines = ["👁  **Watched Channels:**\n"]
    for key, info in watched.items():
        lines.append(f"• **{info['title']}** — `{info['pattern']}`")
    await msg.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)


# ─── /status ──────────────────────────────────────────────────────────────────
@bot.on_message(filters.private & filters.command("status") & allowed)
async def cmd_status(client: Client, msg: Message):
    uid    = msg.from_user.id
    logged = sess.is_logged_in(uid)
    me_bot = await bot.get_me()

    account_line = "✅  Logged in"
    if logged:
        try:
            me_user   = await sess.get_client(uid).get_me()
            account_line = f"✅  Logged in as **{me_user.first_name}** (@{me_user.username or 'N/A'})"
        except Exception:
            pass
    else:
        account_line = "⚠️  Not logged in (use /login)"

    await msg.reply_text(
        f"🤖  **Bot Status**\n\n"
        f"🤖  Bot: @{me_bot.username}\n"
        f"👤  Account: {account_line}\n"
        f"👁  Watching: **{len(watched)}** channels\n"
        f"💾  Dump: `{DUMP_CHANNEL}`\n"
        f"🟢  Status: **Running**\n"
        f"🕐  Time: {datetime.now().strftime('%d %b %Y %H:%M')}",
        parse_mode=ParseMode.MARKDOWN,
    )


# ─── Auto-collect from watched channels ───────────────────────────────────────
@bot.on_message(filters.channel | filters.group)
async def on_new_post(client: Client, msg: Message):
    key  = str(msg.chat.id)
    info = watched.get(key)
    if not info:
        return
    if not has_media(msg):
        return
    if not matches_pattern(msg, info.get("pattern", "*")):
        return

    src_title = msg.chat.title or msg.chat.username or str(msg.chat.id)
    src_link  = (
        f"https://t.me/{msg.chat.username}/{msg.id}"
        if msg.chat.username else f"(ID: {msg.chat.id})"
    )
    caption = make_caption(msg, src_title, src_link)

    try:
        await bot.copy_message(
            chat_id=DUMP_CHANNEL,
            from_chat_id=msg.chat.id,
            message_id=msg.id,
            caption=caption,
            parse_mode=ParseMode.MARKDOWN,
        )
        log.info(f"Auto-collected from {src_title}: msg {msg.id}")
    except FloodWait as e:
        await asyncio.sleep(e.value + 1)
    except Exception as e:
        log.warning(f"Auto-collect failed: {e}")


# ─── Health server ────────────────────────────────────────────────────────────
async def health_handler(_):
    return web.Response(text="🟢 Grabber Bot is running!")


async def start_health():
    web_app = web.Application()
    web_app.router.add_get("/",       health_handler)
    web_app.router.add_get("/health", health_handler)
    runner = web.AppRunner(web_app)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", PORT).start()
    log.info(f"🌐 Health server on :{PORT}")


async def keep_alive():
    """Ping every 4 minutes to prevent Koyeb from sleeping."""
    await asyncio.sleep(60)
    async with aiohttp.ClientSession() as session:
        while True:
            try:
                url = f"{APP_URL.rstrip('/')}/health" if APP_URL else f"http://localhost:{PORT}/health"
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as r:
                    log.info(f"💓 Keep-alive: {r.status}")
            except Exception as e:
                log.warning(f"Keep-alive failed: {e}")
            await asyncio.sleep(240)


# ─── Main ─────────────────────────────────────────────────────────────────────
async def main():
    # Load saved sessions from disk
    sess.load()

    await start_health()
    asyncio.create_task(keep_alive())

    await bot.start()
    me = await bot.get_me()
    log.info(f"🕵️ Grabber Bot started as @{me.username}")

    # Restore all saved user sessions
    await sess.restore_all()

    # Startup message to dump channel
    try:
        saved_count = len(sess.all_sessions())
        await bot.send_message(
            DUMP_CHANNEL,
            f"🟢  **Grabber Bot Started!**\n"
            f"🤖  @{me.username}\n"
            f"👥  {saved_count} user session(s) restored\n"
            f"🕐  {datetime.now().strftime('%d %b %Y %H:%M')}",
            parse_mode=ParseMode.MARKDOWN,
        )
    except Exception:
        pass

    await idle()
    await bot.stop()


if __name__ == "__main__":
    asyncio.run(main())
