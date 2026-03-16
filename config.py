import os
from dotenv import load_dotenv
load_dotenv()

API_ID       = int(os.environ["API_ID"])
API_HASH     = os.environ["API_HASH"]
BOT_TOKEN    = os.environ["BOT_TOKEN"]
DUMP_CHANNEL = int(os.environ["DUMP_CHANNEL"])
PORT         = int(os.environ.get("PORT", 8080))
APP_URL      = os.environ.get("APP_URL", "")

# Optional: comma-separated Telegram user IDs allowed to use the bot
# Leave empty to allow everyone
ALLOWED_USERS = [
    int(x.strip())
    for x in os.environ.get("ALLOWED_USERS", "").split(",")
    if x.strip().isdigit()
]
