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
```

Push → redeploy → send `/start` to the bot → check logs.

---

## Two Possible Results

**If you see `✅ GOT MESSAGE` in logs** → the full bot.py has a bug I need to fix. Send me the log.

**If you still see nothing** → Telegram isn't delivering updates at all. Do these checks:

**Check 1** — Go to [@BotFather](https://t.me/BotFather) → `/mybots` → `@Grabber_skbot` → **Bot Settings** → **Group Privacy** → make sure it says **Disabled** (not enabled).

**Check 2** — Open the bot in Telegram and check if there's a **START** button visible. Click it — don't just type `/start`.

**Check 3** — Test the bot token directly in your browser:
```
https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getMe
```
If this returns your bot info, the token is valid.

**Check 4** — Check if another app is using the same token:
```
https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getUpdates
