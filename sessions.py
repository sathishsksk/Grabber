"""
sessions.py — Secure per-user session manager

Each user's Pyrogram session string is stored in sessions.json.
Only the server owner (you) can access this file.
Other bot users CANNOT see or use each other's sessions.
Each user's client is isolated — user A's client cannot be used by user B.
"""

import json
import logging
import os

from pyrogram import Client
from config import API_ID, API_HASH

log = logging.getLogger(__name__)

SESSIONS_FILE = "sessions.json"

# In-memory stores
_sessions: dict[str, str]       = {}   # {str(user_id): session_string}
_clients:  dict[int, Client]    = {}   # {user_id: active Client}
_states:   dict[int, dict]      = {}   # {user_id: login state dict}


# ── Persistence ───────────────────────────────────────────────────────────────
def load():
    global _sessions
    if os.path.exists(SESSIONS_FILE):
        try:
            _sessions = json.load(open(SESSIONS_FILE, "r"))
            log.info(f"Loaded {len(_sessions)} saved sessions")
        except Exception as e:
            log.warning(f"Could not load sessions: {e}")
            _sessions = {}


def _save():
    try:
        json.dump(_sessions, open(SESSIONS_FILE, "w"), indent=2)
    except Exception as e:
        log.error(f"Could not save sessions: {e}")


# ── Session ops ───────────────────────────────────────────────────────────────
def save_session(uid: int, session_str: str):
    _sessions[str(uid)] = session_str
    _save()


def delete_session(uid: int):
    _sessions.pop(str(uid), None)
    _save()


def get_session(uid: int) -> str | None:
    return _sessions.get(str(uid))


def all_sessions() -> dict:
    return dict(_sessions)


# ── Client ops ────────────────────────────────────────────────────────────────
def set_client(uid: int, c: Client):
    _clients[uid] = c


def get_client(uid: int) -> Client | None:
    return _clients.get(uid)


def remove_client(uid: int):
    _clients.pop(uid, None)


def is_logged_in(uid: int) -> bool:
    c = _clients.get(uid)
    return c is not None and c.is_connected


# ── Login state ops ───────────────────────────────────────────────────────────
def set_state(uid: int, state: dict):
    _states[uid] = state


def get_state(uid: int) -> dict | None:
    return _states.get(uid)


def clear_state(uid: int):
    _states.pop(uid, None)


# ── Restore all saved sessions on bot startup ─────────────────────────────────
async def restore_all():
    restored = 0
    for uid_str, session_str in list(_sessions.items()):
        uid = int(uid_str)
        try:
            c = Client(
                name=f"user_{uid}",
                api_id=API_ID,
                api_hash=API_HASH,
                session_string=session_str,
                in_memory=True,
            )
            await c.start()
            set_client(uid, c)
            restored += 1
            log.info(f"✅ Restored session for user {uid}")
        except Exception as e:
            log.warning(f"⚠️  Could not restore session for {uid}: {e}")
            # Remove broken session
            delete_session(uid)
    log.info(f"Session restore complete: {restored}/{len(_sessions)} restored")
