"""
Minimal Grabber Bot - No filters, no complexity
"""
import os
import asyncio
import logging
import threading
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

bot = Client("grabber_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)


# ── Raw handler — NO filters at all ───────────────────────────────────────────
@bot.on_message()
async def on_any_message(client: Client, msg: Message):
    uid  = msg.from_user.id if msg.from_user else "?"
    text = msg.text or str(msg.media)
    log.info(f"📨 Message from {uid}: {text}")
    try:
        await msg.reply_text(
            f"✅ Bot received your message!\n"
            f"Text: `{text}`\n"
            f"From: `{uid}`",
        )
    except Exception as e:
        log.error(f"Reply error: {e}")


# ── Health server in thread ────────────────────────────────────────────────────
class H(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")
    def log_message(self, *a): pass

def health():
    HTTPServer(("0.0.0.0", PORT), H).serve_forever()


# ── Main ──────────────────────────────────────────────────────────────────────
async def main():
    threading.Thread(target=health, daemon=True).start()
    log.info(f"🌐 Health on :{PORT}")

    await bot.start()
    me = await bot.get_me()
    log.info(f"✅ Bot started as @{me.username} — send any message to test")

    try:
        await bot.send_message(DUMP_CHANNEL, f"🟢 Bot started!\n@{me.username}\n{datetime.now()}")
    except Exception as e:
        log.warning(f"Dump message: {e}")

    await asyncio.get_event_loop().create_future()  # run forever


if __name__ == "__main__":
    asyncio.run(main())
