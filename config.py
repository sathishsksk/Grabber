import os
from dotenv import load_dotenv
load_dotenv()

API_ID       = int(os.environ["API_ID"])
API_HASH     = os.environ["API_HASH"]
BOT_TOKEN    = os.environ["BOT_TOKEN"]
DUMP_CHANNEL = int(os.environ["DUMP_CHANNEL"])
PORT         = int(os.environ.get("PORT", 8080))
OWNER_ID     = int(os.environ.get("OWNER_ID", 0))   # Your Telegram user ID
APP_URL      = os.environ.get("APP_URL", "")

