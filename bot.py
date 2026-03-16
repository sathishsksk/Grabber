import asyncio
import logging
from aiohttp import web
from pyrogram import Client, filters, idle
from pyrogram.types import Message
from config import API_ID, API_HASH, BOT_TOKEN, PORT

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

bot = Client("grabber_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

@bot.on_message()
async def catch_all(client: Client, msg: Message):
    log.info(f"✅ GOT MESSAGE: {msg.text} from {getattr(msg.from_user, 'id', '?')}")
    await msg.reply_text("✅ Bot is working!")

async def health(_): return web.Response(text="OK")

async def main():
    webapp = web.Application()
    webapp.router.add_get("/health", health)
    webapp.router.add_get("/", health)
    runner = web.AppRunner(webapp)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", PORT).start()
    log.info(f"Health on :{PORT}")
    await bot.start()
    log.info(f"Bot started as @{(await bot.get_me()).username}")
    await idle()
    await bot.stop()

if __name__ == "__main__":
    asyncio.run(main())
