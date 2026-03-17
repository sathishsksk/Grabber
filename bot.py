"""
Grabber Bot - Fixed entry point using bot.run()
"""
import os
import logging
import threading
import asyncio
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler

from pyrogram import Client
from pyrogram.types import Message

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] — %(message)s")
log = logging.getLogger(__name__)

API_ID       = int(os.environ["API_ID"])
API_HASH     = os.environ["API_HASH"]
BOT_TOKEN    = os.environ["BOT_TOKEN"]
DUMP_CHANNEL = int(os.environ["DUMP_CHANNEL"])
PORT         = int(os.environ.get("PORT", 8080))

bot = Client(
    "grabber_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    sleep_threshold=60,
)


# ── Handlers ──────────────────────────────────────────────────────────────────
@bot.on_message()
async def on_any_message(client: Client, msg: Message):
    uid  = msg.from_user.id if msg.from_user else "?"
    text = msg.text or str(msg.media)
    log.info(f"📨 Message from {uid}: {text}")
    try:
        await msg.reply_text(f"✅ Received!\nFrom: `{uid}`\nText: `{text}`")
    except Exception as e:
        log.error(f"Reply error: {e}")


# ── Health server in thread ────────────────────────────────────────────────────
class H(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")
    def log_message(self, *a): pass

def start_health():
    HTTPServer(("0.0.0.0", PORT), H).serve_forever()


# ── Startup coroutine — called AFTER bot.run() connects ───────────────────────
async def startup(client: Client):
    me = await client.get_me()
    log.info(f"✅ Bot ready as @{me.username} — waiting for messages...")
    try:
        await client.send_message(
            DUMP_CHANNEL,
            f"🟢 Bot started!\n@{me.username}\n{datetime.now().strftime('%d %b %Y %H:%M')}",
        )
    except Exception as e:
        log.warning(f"Dump message failed: {e}")


# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    # Health in background thread
    threading.Thread(target=start_health, daemon=True).start()
    log.info(f"🌐 Health on :{PORT}")

    # bot.run() owns the event loop — most reliable for Pyrogram
    bot.run(startup(bot))
