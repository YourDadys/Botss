import logging
import sqlite3
import secrets
import string
from datetime import datetime
from typing import Optional
from threading import Thread
from flask import Flask

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    CommandHandler,
    CallbackQueryHandler,
    ChatJoinRequestHandler,
)

# ---------------- CONFIG ----------------
BOT_TOKEN = "6914214761:AAEii8JekAHyAPwovTw-eZvTxyYx8L5d5nQ"  # 🔥 Yahan apna real token daalo
CHANNEL_USERNAME = "-1002844180904"  # 🔥 Channel username (e.g., @mychannel)
BOT_OWNER_ID = 6109674139  # 🔥 Apna Telegram ID (int)
DATABASE = "bot.db"
REFS_FOR_REWARD = 5
# ----------------------------------------

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
log = logging.getLogger(__name__)

# ---------- DUMMY WEB SERVER ----------
app = Flask(__name__)

@app.route("/")
def home():
    return "Bot is alive ✅"

def run_web():
    app.run(host="0.0.0.0", port=8080)

# ---------- DB setup ----------
def init_db():
    conn = sqlite3.connect(DATABASE)
    cur = conn.cursor()
    cur.execute(
        """CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            referral_code TEXT UNIQUE,
            referred_by TEXT,
            referrals INTEGER DEFAULT 0,
            created_at TEXT
        )"""
    )
    cur.execute(
        """CREATE TABLE IF NOT EXISTS join_requests (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            request_at TEXT
        )"""
    )
    conn.commit()
    conn.close()

# ---------- DB helpers ----------
def get_user(user_id: int) -> Optional[dict]:
    conn = sqlite3.connect(DATABASE)
    cur = conn.cursor()
    cur.execute(
        "SELECT user_id, username, first_name, referral_code, referred_by, referrals, created_at FROM users WHERE user_id=?",
        (user_id,),
    )
    row = cur.fetchone()
    conn.close()
    if not row:
        return None
    return dict(
        user_id=row[0],
        username=row[1],
        first_name=row[2],
        referral_code=row[3],
        referred_by=row[4],
        referrals=row[5],
        created_at=row[6],
    )

def create_user(user_id: int, username: str, first_name: str, referred_by: Optional[str]):
    conn = sqlite3.connect(DATABASE)
    cur = conn.cursor()
    while True:
        rc = "".join(secrets.choice(string.ascii_letters + string.digits) for _ in range(6))
        try:
            cur.execute(
                "INSERT INTO users(user_id, username, first_name, referral_code, referred_by, referrals, created_at) VALUES(?,?,?,?,?,0,?)",
                (user_id, username, first_name, rc, referred_by, datetime.utcnow().isoformat()),
            )
            conn.commit()
            break
        except sqlite3.IntegrityError:
            continue
    conn.close()
    return rc

def inc_referral_by_code(referral_code: str) -> Optional[int]:
    conn = sqlite3.connect(DATABASE)
    cur = conn.cursor()
    cur.execute("SELECT user_id, referrals FROM users WHERE referral_code=?", (referral_code,))
    row = cur.fetchone()
    if not row:
        conn.close()
        return None
    user_id, current = row
    cur.execute("UPDATE users SET referrals=? WHERE user_id=?", (current + 1, user_id))
    conn.commit()
    cur.execute("SELECT referrals FROM users WHERE user_id=?", (user_id,))
    new_count = cur.fetchone()[0]
    conn.close()
    return new_count

def add_join_request(user_id: int, username: str, first_name: str):
    conn = sqlite3.connect(DATABASE)
    cur = conn.cursor()
    cur.execute(
        "INSERT OR REPLACE INTO join_requests(user_id, username, first_name, request_at) VALUES(?,?,?,?)",
        (user_id, username, first_name, datetime.utcnow().isoformat()),
    )
    conn.commit()
    conn.close()

def remove_join_request(user_id: int):
    conn = sqlite3.connect(DATABASE)
    cur = conn.cursor()
    cur.execute("DELETE FROM join_requests WHERE user_id=?", (user_id,))
    conn.commit()
    conn.close()

def list_join_requests() -> list:
    conn = sqlite3.connect(DATABASE)
    cur = conn.cursor()
    cur.execute("SELECT user_id, username, first_name, request_at FROM join_requests ORDER BY request_at ASC")
    rows = cur.fetchall()
    conn.close()
    return [{"user_id": r[0], "username": r[1], "first_name": r[2], "request_at": r[3]} for r in rows]

# ---------- Utils ----------
def make_main_kb(start_refcode: str):
    kb = [
        [InlineKeyboardButton("Verify Membership ✅", callback_data="verify")],
        [InlineKeyboardButton("Share Referral", switch_inline_query=start_refcode)],
    ]
    return InlineKeyboardMarkup(kb)

def make_post_reward_kb():
    return InlineKeyboardMarkup([[InlineKeyboardButton("Generate TEST OTP 🔢", callback_data="gen_test_otp")]])

def gen_test_phone():
    return "+999" + "".join(secrets.choice(string.digits) for _ in range(7))

def gen_test_otp():
    return "".join(secrets.choice(string.digits) for _ in range(6))

# ---------- User Commands ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    args = context.args
    referred_by = args[0] if args else None

    existing = get_user(user.id)
    if not existing:
        rc = create_user(user.id, user.username or "", user.first_name or "", referred_by)
        if referred_by:
            inc_referral_by_code(referred_by)
    else:
        rc = existing["referral_code"]

    bot_username = (await context.bot.get_me()).username
    msg = (
        f"👋 Hi {user.first_name or user.username}!\n\n"
        f"हमारे चैनल को join करें: {CHANNEL_USERNAME}\n\n"
        "Join request भेजने के बाद Verify Membership पर क्लिक करें।\n\n"
        f"📢 आपका referral code: `{rc}`\n"
        f"🔗 Referral link: `t.me/{bot_username}?start={rc}`\n\n"
        "_5 referrals पूरे करने पर एक test नंबर + OTP reward मिलेगा!_"
    )
    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN, reply_markup=make_main_kb(rc))

# Dummy callbacks
async def button_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer("Button pressed!")

async def myreferrals(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("You have 0 referrals yet!")

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Use /start to begin and /myreferrals to check status.")

async def chat_join_request_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.chat_join_request.from_user
    add_join_request(user.id, user.username or "", user.first_name or "")
    await context.bot.send_message(BOT_OWNER_ID, f"📥 New join request from {user.first_name}")

async def list_requests(update: Update, context: ContextTypes.DEFAULT_TYPE):
    reqs = list_join_requests()
    if not reqs:
        await update.message.reply_text("No join requests yet.")
        return
    msg = "\n".join(f"• {r['first_name']} ({r['username']})" for r in reqs)
    await update.message.reply_text(f"📋 Join Requests:\n{msg}")

async def approve(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("✅ Approved selected user.")

async def approve_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("✅ All users approved!")

async def decline_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ All requests declined.")

# ---------- MAIN ----------
def main():
    init_db()
    Thread(target=run_web).start()

    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_cb))
    app.add_handler(CommandHandler("myreferrals", myreferrals))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(ChatJoinRequestHandler(chat_join_request_handler))
    app.add_handler(CommandHandler("list_requests", list_requests))
    app.add_handler(CommandHandler("approve", approve))
    app.add_handler(CommandHandler("approve_all", approve_all))
    app.add_handler(CommandHandler("decline_all", decline_all))

    print("🤖 Bot running...")
    app.run_polling()

if __name__ == "__main__":
    main()
