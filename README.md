# 🕵️ Telegram Media Grabber Bot

Search, grab and auto-collect media from Telegram channels and groups.

## ✨ Features

| Feature | Description |
|---|---|
| 🔍 **Global Search** | Search all your joined chats by extension or filename |
| 🪝 **Grab** | Pull all media from any channel/group link |
| 👁 **Watch** | Auto-collect new posts from monitored channels |
| 📋 **Source Caption** | Every file tagged with original source info |
| 🏷️ **Categories** | Auto-labeled: 📸 Photo, 🎵 Music, 🎬 Video, 📄 Doc... |
| 💓 **Never Sleeps** | Keep-alive ping prevents Koyeb from sleeping |

## 📋 Commands

| Command | Description |
|---|---|
| `/search *.mp3` | Search all MP3s across joined chats |
| `/search *.jpg` | Search all photos |
| `/search *.pdf` | Search all PDFs |
| `/search bigil` | Search by filename |
| `/grab @channel` | Grab all media from channel |
| `/grab @channel *.mp3` | Grab only MP3s |
| `/grab https://t.me/ch/123` | Grab single post |
| `/watch @channel` | Auto-collect new media |
| `/watch @channel *.mp3` | Auto-collect MP3s only |
| `/unwatch @channel` | Stop monitoring |
| `/list` | Show watched channels |
| `/stop` | Cancel active grab |
| `/status` | Bot info |

## 🚀 Deploy on Koyeb (Free)

### Step 1 — Get Credentials
- `API_ID` + `API_HASH` → [my.telegram.org](https://my.telegram.org)
- `BOT_TOKEN` → [@BotFather](https://t.me/BotFather)
- `DUMP_CHANNEL` → Create a private channel, get ID via [@userinfobot](https://t.me/userinfobot)

### Step 2 — Prepare Bot
- Add your bot as **admin** to your dump channel
- Add your bot as **admin** to any private channels you want to grab from

### Step 3 — Deploy
1. Push this repo to GitHub
2. Go to [koyeb.com](https://koyeb.com) → Sign up with GitHub
3. **Create App** → GitHub → select this repo
4. Builder: **Dockerfile**
5. Port: **8080**
6. Health check path: `/health`
7. Add environment variables:

```
API_ID=your_api_id
API_HASH=your_api_hash
BOT_TOKEN=your_bot_token
DUMP_CHANNEL=-1001234567890
APP_URL=https://your-app.koyeb.app
```

8. Click **Deploy** ✅

## 📁 File Structure

```
├── bot.py           # Main bot
├── config.py        # Environment variables
├── requirements.txt
├── Dockerfile
└── sample.env
```

## ⚠️ Rules

- ✅ Public channels — freely accessible
- ✅ Private channels/groups you are a **member or admin** of
- ❌ Private channels you are **not a member** of
- ❌ Do not redistribute copyrighted content publicly
