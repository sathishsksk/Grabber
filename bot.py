"""
Grabber Bot - in_memory session + Event() keep-alive
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

# in_memory=True — no session file, no conflicts between deployments
bot = Client(
    "grabber_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    in_memory=True,
    sleep_threshold=60,
)


@bot.on_message()
async def on_any_message(client: Client, msg: Message):
    uid  = msg.from_user.id if msg.from_user else "?"
    text = msg.text or str(msg.media)
    log.info(f"📨 Message from {uid}: {text}")
    try:
        await msg.reply_text(f"✅ Bot works!\nFrom: `{uid}`\nText: `{text}`")
    except Exception as e:
        log.error(f"Reply error: {e}")


class H(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")
    def log_message(self, *a): pass


async def main():
    threading.Thread(
        target=lambda: HTTPServer(("0.0.0.0", PORT), H).serve_forever(),
        daemon=True
    ).start()
    log.info(f"🌐 Health on :{PORT}")

    await bot.start()
    me = await bot.get_me()
    log.info(f"✅ Bot ready as @{me.username}")

    try:
        await bot.send_message(
            DUMP_CHANNEL,
            f"🟢 Bot started! @{me.username}\n{datetime.now().strftime('%d %b %Y %H:%M')}",
        )
    except Exception as e:
        log.warning(f"Dump: {e}")

    # asyncio.Event().wait() — more reliable than idle() in Docker
    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
