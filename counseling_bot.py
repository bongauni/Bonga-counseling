"""
Anonymous Counseling Telegram Bot — Full Edition with Admin Panel
==================================================================
Deploy on Render as Web Service:
    Build Command:  pip install -r requirements.txt
    Start Command:  python counseling_bot.py

Environment variables (set on Render):
    BOT_TOKEN      - Telegram bot token
    SUPABASE_URL   - Supabase project URL
    SUPABASE_KEY   - Supabase anon/public key
    ADMIN_ID       - Your Telegram numeric user ID
"""

import os
import asyncio
import logging
from datetime import datetime

from telegram import (
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
    CallbackQueryHandler,
)
from supabase import create_client, Client
from aiohttp import web

# ─── ENVIRONMENT ──────────────────────────────────────────────────────────
BOT_TOKEN = os.getenv("BOT_TOKEN")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

if not all([BOT_TOKEN, SUPABASE_URL, SUPABASE_KEY]):
    raise ValueError("Missing environment variables: BOT_TOKEN, SUPABASE_URL, SUPABASE_KEY")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ─── COUNSELOR LIST (hardcoded – can also be managed via admin panel) ──────
COUNSELOR_IDS = [
    439115108,      # female counselor
    2034041406,     # male counselor
    # Add more as needed – they will be auto‑added to Supabase on first /start
]

# ─── LOGGING ──────────────────────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s - %name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ─── CONVERSATION STATES ──────────────────────────────────────────────────
REG_SEX, REG_LANG, CONNECT_TOPIC, COUNSELOR_SEX = range(4)

# ─── TOPICS (bilingual buttons) ───────────────────────────────────────────
TOPICS = [
    ["identity crisis / የማንነት ቀውስ"],
    ["Depression/anxiety / ድብርት/ጭንቀት"],
    ["Alcohol/drug addiction / አልኮል/አደንዛዥ ዕፅ ሱሰኝነት"],
    ["pre-marital sex/ sexual issues / ጋብቻ በፊት ወሲብ/የወሲብ ችግሮች"],
    ["porn/masterbation / ፖርን/ማስተርቤሽን"],
    ["social media addiction / ማህበራዊ ሚዲያ ሱሰኝነት"],
    ["losing faith/ spiritual life / እምነት ማጣት/መንፈሳዊ ሕይወት"],
    ["time management / ጊዜ አጠቃቀም"],
    ["loneliness / ብቸኝነት"],
    ["Family issues / የቤተሰብ ጉዳዮች"],
    ["Relationship issues / የፍቅር ግንኙነት ጉዳዮች"],
    ["Academic counseling / የትምህርት ጉዳይ ምክር"],
    ["other / ሌላ"],
]
TOPIC_ENGLISH = {row[0]: row[0].split(" / ")[0].strip() for row in TOPICS}

# ─── LOCALISED STRINGS ────────────────────────────────────────────────────
STRINGS = {
    "English": {
        "matched": "Congratulations, you have now been matched with a counselor.\nFrom now on, all messages you send to the bot will be sent to your anonymous counselor.",
        "no_counselor": "No counselors are online right now. Please try again later.",
        "session_ended_by_counselor": "Your counselor has ended the session. Use /connect to find another counselor.",
        "stopped": "You have stopped counseling. Use /connect to start again.",
    },
    "Amharic": {
        "matched": "እንኳን ደስ አለዎት! አሁን ከአማካሪዎ ጋር ተገናኝተዋል።\nወደ ቦቱ የሚልኩት ሁሉም መልዕክቶች ለአማካሪዎ ይላካሉ።",
        "no_counselor": "አሁን ምንም አማካሪ አልተገኘም። እባክዎ ቆይተው ደግመው ይሞክሩ።",
        "session_ended_by_counselor": "አማካሪዎ ክፍለ ጊዜውን አብቅቷል። ሌላ አማካሪ ለማግኘት /connect ይጠቀሙ።",
        "stopped": "የምክር አገልግሎቱ አቁመዋል። ደግሞ ለመጀመር /connect ይጠቀሙ።",
    },
}

# ─── STATIC MESSAGES ──────────────────────────────────────────────────────
START_TEXT = (
    "Hello beloved user, this is the counseling team's anonymous counseling service.\n"
    "We hope we can help you in whatever you may need.\n\n"
    "Use the /help command to understand how to use the bot\n"
    "Use the /connect command to start getting counseling\n\n"
    "Always remember God loves you and so do we."
)
REGISTERED_TEXT = (
    "Congratulations!! You have registered to the bot.\n"
    "Use the /help command to learn how to use the bot\n"
    "Use the /connect command to connect with a counselor"
)
USER_HELP_TEXT = (
    "Commands: \n"
    "/connect: connect with a counselor\n"
    "/stop_counseling: stop counseling with your counselor\n"
    "/chat_history: get a history of your chat with the counselor\n\n"
    "Usage: \n"
    "To start getting anonymous counseling, use the /connect command\n"
    "After connecting with a counselor, every message you send to the bot will be sent to the counselor. "
    "The bot will also send you the messages sent from the counselor\n"
    "Use the /chat_history command to get a history of your chat. "
    "You can add a limit to the command to see more messages like so: /chat_history {limit}"
)
COUNSELOR_WELCOME_TEXT = (
    "Welcome, Counselor.\n"
    "You are registered in the system. You will be automatically matched with users seeking help.\n\n"
    "Available commands:\n"
    "/status        → See if you are currently connected to a user\n"
    "/history       → See your chat history with the current or last user\n"
    "/disconnect    → Manually end the current session (user will be informed)\n"
    "/set_available → Set yourself as available for new users (default)\n"
    "/set_busy      → Set yourself as busy (won't receive new users)\n"
    "/help          → Show this help"
)
USER_ONLY_MSG = "This command is for users only."
COUNSELOR_ONLY_MSG = "This command is for counselors only."

# ─── SUPABASE HELPER FUNCTIONS ────────────────────────────────────────────

def is_counselor(uid: int) -> bool:
    return uid in COUNSELOR_IDS

def get_user(uid: int) -> dict:
    resp = supabase.table("users").select("*").eq("user_id", str(uid)).execute()
    if resp.data:
        return resp.data[0]
    new_user = {
        "user_id": str(uid),
        "sex": None,
        "language": None,
        "registered": False,
        "counselor_id": None,
        "topic": None,
    }
    supabase.table("users").insert(new_user).execute()
    return new_user

def update_user(uid: int, updates: dict):
    supabase.table("users").update(updates).eq("user_id", str(uid)).execute()

def get_counselor(cid: int) -> dict:
    if not is_counselor(cid):
        return None
    resp = supabase.table("counselors").select("*").eq("user_id", str(cid)).execute()
    if resp.data:
        return resp.data[0]
    new_counselor = {
        "user_id": str(cid),
        "available": True,
        "manually_busy": False,
        "current_user_id": None,
        "sex": None,
    }
    supabase.table("counselors").insert(new_counselor).execute()
    return new_counselor

def update_counselor(cid: int, updates: dict):
    supabase.table("counselors").update(updates).eq("user_id", str(cid)).execute()

def find_available_counselor(user_sex: str) -> int | None:
    if not user_sex:
        return None
    norm_sex = user_sex.strip().lower()
    resp = supabase.table("counselors") \
        .select("user_id") \
        .eq("sex", norm_sex) \
        .eq("available", True) \
        .eq("manually_busy", False) \
        .is_("current_user_id", "null") \
        .limit(1) \
        .execute()
    if resp.data:
        return int(resp.data[0]["user_id"])
    return None

def append_user_message(uid: int, cid: int, role: str, text: str):
    supabase.table("messages").insert({
        "user_id": str(uid),
        "counselor_id": str(cid),
        "role": role,
        "text": text,
        "ts": datetime.now().isoformat(),
    }).execute()

def append_counselor_message(cid: int, uid: int, role: str, text: str):
    supabase.table("messages").insert({
        "user_id": str(uid),
        "counselor_id": str(cid),
        "role": role,
        "text": text,
        "ts": datetime.now().isoformat(),
    }).execute()

def get_user_history(uid: int, limit: int = 20) -> list:
    resp = supabase.table("messages") \
        .select("*") \
        .eq("user_id", str(uid)) \
        .order("ts", desc=False) \
        .limit(limit) \
        .execute()
    return resp.data

def get_counselor_history(cid: int, limit: int = 20) -> list:
    resp = supabase.table("messages") \
        .select("*") \
        .eq("counselor_id", str(cid)) \
        .order("ts", desc=False) \
        .limit(limit) \
        .execute()
    return resp.data

def user_str(uid: int, key: str) -> str:
    user = get_user(uid)
    lang = user.get("language") or "English"
    return STRINGS.get(lang, STRINGS["English"])[key]

# ─── HEALTH CHECK SERVER ──────────────────────────────────────────────────
async def health_check(request):
    return web.Response(text="Bot is alive")

async def run_health_server():
    port = int(os.environ.get("PORT", 8080))
    app = web.Application()
    app.router.add_get("/", health_check)
    app.router.add_get("/health", health_check)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logger.info(f"Health check server running on port {port}")
    await asyncio.Event().wait()

# ─── TELEGRAM HANDLERS ────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    uid = update.effective_user.id

    # Counselor path
    if is_counselor(uid):
        rec = get_counselor(uid)
        if rec is None:
            await update.message.reply_text("You are not authorised as a counselor.")
            return ConversationHandler.END
        if rec.get("sex") is None:
            await update.message.reply_text(
                "Before you start, please select your sex for matching purposes.",
                reply_markup=ReplyKeyboardMarkup(
                    [["Male", "Female"]], one_time_keyboard=True, resize_keyboard=True
                ),
            )
            return COUNSELOR_SEX
        await update.message.reply_text(COUNSELOR_WELCOME_TEXT, reply_markup=ReplyKeyboardRemove())
        return ConversationHandler.END

    # User path
    user = get_user(uid)
    await update.message.reply_text(START_TEXT, reply_markup=ReplyKeyboardRemove())

    if user.get("counselor_id") is not None:
        await update.message.reply_text(
            "You are still connected to a counselor. Use /stop_counseling to end the session."
        )
        return ConversationHandler.END

    if user.get("registered"):
        await update.message.reply_text(REGISTERED_TEXT)
        return ConversationHandler.END

    # Start registration
    await update.message.reply_text(
        "Before you can use the bot, you have to answer the following questions:\n\nWhat is your sex?",
        reply_markup=ReplyKeyboardMarkup(
            [["Male", "Female"]], one_time_keyboard=True, resize_keyboard=True
        ),
    )
    return REG_SEX

async def reg_sex(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    uid = update.effective_user.id
    if is_counselor(uid):
        return ConversationHandler.END
    update_user(uid, {"sex": update.message.text})
    await update.message.reply_text(
        "Choose your preferred language",
        reply_markup=ReplyKeyboardMarkup(
            [["Amharic", "English"]], one_time_keyboard=True, resize_keyboard=True
        ),
    )
    return REG_LANG

async def reg_lang(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    uid = update.effective_user.id
    if is_counselor(uid):
        return ConversationHandler.END
    update_user(uid, {"language": update.message.text, "registered": True})
    await update.message.reply_text(REGISTERED_TEXT, reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

async def counselor_reg_sex(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    uid = update.effective_user.id
    if not is_counselor(uid):
        return ConversationHandler.END
    update_counselor(uid, {"sex": update.message.text.strip().lower()})
    await update.message.reply_text(COUNSELOR_WELCOME_TEXT, reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    uid = update.effective_user.id
    if is_counselor(uid):
        await update.message.reply_text(COUNSELOR_WELCOME_TEXT)
    else:
        await update.message.reply_text(USER_HELP_TEXT)

async def connect(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    uid = update.effective_user.id
    if is_counselor(uid):
        await update.message.reply_text(USER_ONLY_MSG)
        return ConversationHandler.END

    user = get_user(uid)
    if not user.get("registered"):
        await update.message.reply_text(
            "You are not registered yet. Please send /start and complete registration first."
        )
        return ConversationHandler.END
    if user.get("counselor_id"):
        await update.message.reply_text(
            "You are already connected to a counselor. Use /stop_counseling to end the current session first."
        )
        return ConversationHandler.END

    await update.message.reply_text(
        "Please choose your main concern so we can connect you with the best counselor for you.\n"
        "እባክዎ ዋና ምክር የፈለጉበትን ጉዳይ ይምረጡ — ይህን የምንጠይቀው ከትክክልኛ አማካሪ ጋር ለማገናኘት እንዲረዳን ነው፡፡",
        reply_markup=ReplyKeyboardMarkup(TOPICS, one_time_keyboard=True, resize_keyboard=True),
    )
    return CONNECT_TOPIC

async def connect_topic(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    uid = update.effective_user.id
    if is_counselor(uid):
        return ConversationHandler.END

    raw_topic = update.message.text
    topic_en = TOPIC_ENGLISH.get(raw_topic, raw_topic.split(" / ")[0].strip())

    user = get_user(uid)
    user_sex = user.get("sex")
    if not user_sex:
        await update.message.reply_text("Your sex was not recorded. Please /start again.", reply_markup=ReplyKeyboardRemove())
        return ConversationHandler.END

    cid = find_available_counselor(user_sex)
    if cid is None:
        await update.message.reply_text(
            "No counselor of your gender is available right now. Please try again later.",
            reply_markup=ReplyKeyboardRemove(),
        )
        return ConversationHandler.END

    # Store topic and connect
    update_user(uid, {"topic": topic_en, "counselor_id": str(cid)})
    update_counselor(cid, {"available": False, "current_user_id": str(uid)})

    await update.message.reply_text(
        user_str(uid, "matched"),
        reply_markup=ReplyKeyboardRemove(),
    )

    # Notify counselor
    try:
        await context.bot.send_message(
            chat_id=cid,
            text=(
                f"🔔 You have been matched with a user.\n\n"
                f"📋 Topic:    {topic_en}\n"
                f"👤 Sex:      {user.get('sex')}\n"
                f"🌐 Language: {user.get('language')}\n\n"
                "All messages from the user will appear here. "
                "Your replies will be sent to them.\n"
                "Use /disconnect to end the session."
            ),
        )
    except Exception as e:
        logger.warning("Could not notify counselor %s: %s", cid, e)

    return ConversationHandler.END

async def stop_counseling(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    uid = update.effective_user.id
    if is_counselor(uid):
        await update.message.reply_text(USER_ONLY_MSG)
        return

    user = get_user(uid)
    cid = user.get("counselor_id")
    if not cid:
        await update.message.reply_text("You are not currently in a counseling session. Use /connect to start one.")
        return

    # Clear connection
    update_user(uid, {"counselor_id": None})
    update_counselor(int(cid), {"available": True, "manually_busy": False, "current_user_id": None})

    await update.message.reply_text(user_str(uid, "stopped"))

    try:
        await context.bot.send_message(
            chat_id=int(cid),
            text="🔔 The user has ended the counseling session. You are now available for new users.",
        )
    except Exception as e:
        logger.warning("Could not notify counselor %s: %s", cid, e)

async def chat_history(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    uid = update.effective_user.id
    if is_counselor(uid):
        await update.message.reply_text(USER_ONLY_MSG)
        return

    limit = 20
    if context.args:
        try:
            limit = int(context.args[0])
        except ValueError:
            await update.message.reply_text("Invalid limit. Usage: /chat_history or /chat_history 50")
            return

    history = get_user_history(uid, limit)
    if not history:
        await update.message.reply_text("No chat history found.")
        return

    lines = [f"[{h['ts'][:16]}] {h['role']}: {h['text']}" for h in history]
    reply = "\n".join(lines)
    if len(reply) > 4000:
        reply = "...(truncated)\n" + reply[-4000:]
    await update.message.reply_text(reply)

# ─── COUNSELOR COMMANDS ───────────────────────────────────────────────────
async def counselor_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    uid = update.effective_user.id
    if not is_counselor(uid):
        await update.message.reply_text(COUNSELOR_ONLY_MSG)
        return
    rec = get_counselor(uid)
    if rec["current_user_id"]:
        await update.message.reply_text("You are currently helping a user. Type /disconnect to end.")
    elif rec.get("manually_busy"):
        await update.message.reply_text("You are set as busy. Use /set_available to receive users.")
    else:
        await update.message.reply_text("You are available and will receive new users.")

async def counselor_history(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    uid = update.effective_user.id
    if not is_counselor(uid):
        await update.message.reply_text(COUNSELOR_ONLY_MSG)
        return
    limit = 20
    if context.args:
        try:
            limit = int(context.args[0])
        except ValueError:
            await update.message.reply_text("Invalid limit. Usage: /history or /history 50")
            return
    history = get_counselor_history(uid, limit)
    if not history:
        await update.message.reply_text("No chat history found.")
        return
    lines = [f"[{h['ts'][:16]}] {h['role']}: {h['text']}" for h in history]
    reply = "\n".join(lines)
    if len(reply) > 4000:
        reply = "...(truncated)\n" + reply[-4000:]
    await update.message.reply_text(reply)

async def counselor_disconnect(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    uid = update.effective_user.id
    if not is_counselor(uid):
        await update.message.reply_text(COUNSELOR_ONLY_MSG)
        return
    rec = get_counselor(uid)
    user_id = rec.get("current_user_id")
    if not user_id:
        await update.message.reply_text("You are not currently connected to any user.")
        return
    # Disconnect
    update_counselor(uid, {"available": True, "manually_busy": False, "current_user_id": None})
    update_user(int(user_id), {"counselor_id": None})
    await update.message.reply_text("Session ended. You are now available for new users.")
    try:
        await context.bot.send_message(
            chat_id=int(user_id),
            text=user_str(int(user_id), "session_ended_by_counselor"),
        )
    except Exception as e:
        logger.warning("Could not notify user %s: %s", user_id, e)

async def set_available(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    uid = update.effective_user.id
    if not is_counselor(uid):
        await update.message.reply_text(COUNSELOR_ONLY_MSG)
        return
    rec = get_counselor(uid)
    update_counselor(uid, {"manually_busy": False, "available": rec["current_user_id"] is None})
    await update.message.reply_text("✅ You are now available and will receive new users.")

async def set_busy(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    uid = update.effective_user.id
    if not is_counselor(uid):
        await update.message.reply_text(COUNSELOR_ONLY_MSG)
        return
    update_counselor(uid, {"manually_busy": True, "available": False})
    await update.message.reply_text(
        "🔴 You are now set as busy. You won't receive new users until you use /set_available.\n"
        "(Any active session continues normally.)"
    )

# ─── ADMIN COMMANDS ───────────────────────────────────────────────────────
def is_admin(uid: int) -> bool:
    return uid == ADMIN_ID

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    uid = update.effective_user.id
    if not is_admin(uid):
        await update.message.reply_text("⛔ You are not authorised as admin.")
        return

    keyboard = [
        [InlineKeyboardButton("📊 Statistics", callback_data="admin_stats")],
        [InlineKeyboardButton("➕ Add Counselor", callback_data="admin_add_counselor")],
        [InlineKeyboardButton("➖ Remove Counselor", callback_data="admin_remove_counselor")],
        [InlineKeyboardButton("📋 List Counselors", callback_data="admin_list_counselors")],
        [InlineKeyboardButton("🔄 Reset User Data", callback_data="admin_reset_user")],
        [InlineKeyboardButton("📨 Broadcast Message", callback_data="admin_broadcast")],
        [InlineKeyboardButton("❌ Close", callback_data="admin_close")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("🛠️ Admin Control Panel\nSelect an action:", reply_markup=reply_markup)

async def admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id
    if not is_admin(uid):
        await query.edit_message_text("⛔ Unauthorised.")
        return

    data = query.data

    if data == "admin_stats":
        users_count = supabase.table("users").select("user_id", count="exact").execute().count
        counselors_count = supabase.table("counselors").select("user_id", count="exact").execute().count
        active_sessions = supabase.table("counselors").select("user_id").eq("available", False).is_("current_user_id", "not.null").execute().count
        await query.edit_message_text(
            f"📊 Statistics\n"
            f"👤 Users: {users_count}\n"
            f"💬 Counselors: {counselors_count}\n"
            f"🔗 Active sessions: {active_sessions}",
            parse_mode="Markdown"
        )

    elif data == "admin_add_counselor":
        context.user_data["admin_action"] = "add_counselor"
        await query.edit_message_text(
            "➕ Add a new counselor\n\n"
            "Send the counselor's Telegram numeric user ID.\n"
            "Example: `439115108`\n\n"
            "Then send their gender: `male` or `female`.\n"
            "You can cancel with /cancel."
        )

    elif data == "admin_remove_counselor":
        context.user_data["admin_action"] = "remove_counselor"
        await query.edit_message_text(
            "➖ Remove a counselor\n\n"
            "Send the Telegram numeric user ID of the counselor to remove."
        )

    elif data == "admin_list_counselors":
        resp = supabase.table("counselors").select("user_id, sex, available, current_user_id").execute()
        if not resp.data:
            await query.edit_message_text("No counselors found.")
            return
        lines = []
        for c in resp.data:
            status = "🟢 available" if c["available"] else "🔴 busy"
            if c["current_user_id"]:
                status += f" (helping {c['current_user_id']})"
            lines.append(f"`{c['user_id']}` – {c['sex'] or 'no sex'} – {status}")
        msg = "📋 Counselors:\n" + "\n".join(lines)
        await query.edit_message_text(msg, parse_mode="Markdown")

    elif data == "admin_reset_user":
        context.user_data["admin_action"] = "reset_user"
        await query.edit_message_text(
            "🔄 Reset user data\n\n"
            "Send the Telegram numeric user ID of the user to reset.\n"
            "Their registration, topic, and chat history will be deleted."
        )

    elif data == "admin_broadcast":
        context.user_data["admin_action"] = "broadcast"
        await query.edit_message_text(
            "📨 Broadcast message\n\n"
            "Send the message you want to broadcast to all users.\n"
            "Use /cancel to abort."
        )

    elif data == "admin_close":
        await query.edit_message_text("Admin panel closed.")

async def admin_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    uid = update.effective_user.id
    if not is_admin(uid):
        return
    action = context.user_data.get("admin_action")
    if not action:
        return
    text = update.message.text.strip()

    if action == "add_counselor":
        if "pending_counselor_id" not in context.user_data:
            if not text.isdigit():
                await update.message.reply_text("❌ Invalid ID. Send a numeric user ID.")
                return
            context.user_data["pending_counselor_id"] = text
            await update.message.reply_text("Now send the gender: `male` or `female`")
            return
        else:
            gender = text.lower()
            if gender not in ["male", "female"]:
                await update.message.reply_text("❌ Gender must be 'male' or 'female'.")
                return
            cid = context.user_data.pop("pending_counselor_id")
            existing = supabase.table("counselors").select("user_id").eq("user_id", cid).execute()
            if existing.data:
                supabase.table("counselors").update({"sex": gender}).eq("user_id", cid).execute()
                await update.message.reply_text(f"✅ Counselor `{cid}` updated to gender `{gender}`.")
            else:
                supabase.table("counselors").insert({
                    "user_id": cid,
                    "sex": gender,
                    "available": True,
                    "manually_busy": False,
                    "current_user_id": None,
                }).execute()
                await update.message.reply_text(f"✅ Counselor `{cid}` added with gender `{gender}`.\n⚠️ Note: Hardcoded COUNSELOR_IDS in code does not auto-update. Restart or add manually to the list.")
            del context.user_data["admin_action"]

    elif action == "remove_counselor":
        if not text.isdigit():
            await update.message.reply_text("❌ Send a valid numeric user ID.")
            return
        cid = text
        result = supabase.table("counselors").delete().eq("user_id", cid).execute()
        if result.data:
            await update.message.reply_text(f"✅ Counselor `{cid}` removed from database.")
        else:
            await update.message.reply_text(f"❌ Counselor `{cid}` not found.")
        del context.user_data["admin_action"]

    elif action == "reset_user":
        if not text.isdigit():
            await update.message.reply_text("❌ Send a valid numeric user ID.")
            return
        uid_reset = text
        supabase.table("messages").delete().eq("user_id", uid_reset).execute()
        result = supabase.table("users").delete().eq("user_id", uid_reset).execute()
        if result.data:
            await update.message.reply_text(f"✅ User `{uid_reset}` and all their data deleted.")
        else:
            await update.message.reply_text(f"❌ User `{uid_reset}` not found.")
        del context.user_data["admin_action"]

    elif action == "broadcast":
        users = supabase.table("users").select("user_id").execute()
        success = 0
        fail = 0
        for user in users.data:
            try:
                await context.bot.send_message(chat_id=int(user["user_id"]), text=f"📢 Broadcast from admin:\n\n{text}")
                success += 1
            except Exception as e:
                logger.warning(f"Broadcast failed to {user['user_id']}: {e}")
                fail += 1
        await update.message.reply_text(f"✅ Broadcast sent to {success} users. Failed: {fail}")
        del context.user_data["admin_action"]

    else:
        del context.user_data["admin_action"]

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Operation cancelled.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

# ─── MESSAGE FORWARDING ───────────────────────────────────────────────────
async def forward_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    sender_id = update.effective_user.id
    text = update.message.text

    # Counselor → User
    if is_counselor(sender_id):
        rec = get_counselor(sender_id)
        if not rec:
            await update.message.reply_text("You are not recognised as a counselor.")
            return
        user_id = rec.get("current_user_id")
        if not user_id:
            await update.message.reply_text("You are not connected to any user right now.")
            return
        try:
            await context.bot.send_message(chat_id=int(user_id), text=text)
            append_user_message(int(user_id), sender_id, "Counselor", text)
            append_counselor_message(sender_id, int(user_id), "You", text)
            await update.message.reply_text("✅ Message sent to user.")
        except Exception as e:
            logger.error("Forward counselor->user error: %s", e)
            await update.message.reply_text("⚠️ Could not deliver your message.")
        return

    # User → Counselor
    user = get_user(sender_id)
    if not user.get("registered"):
        await update.message.reply_text("Please send /start to register before using the bot.")
        return
    cid = user.get("counselor_id")
    if not cid:
        await update.message.reply_text("You are not connected to a counselor. Use /connect to start a session.")
        return
    try:
        await context.bot.send_message(chat_id=int(cid), text=text)
        append_user_message(sender_id, int(cid), "You", text)
        append_counselor_message(int(cid), sender_id, "User", text)
    except Exception as e:
        logger.error("Forward user->counselor error: %s", e)
        await update.message.reply_text("⚠️ Could not deliver your message to the counselor.")

# ─── MAIN ─────────────────────────────────────────────────────────────────
async def main():
    # Start health check server (keeps Render Web Service alive)
    asyncio.create_task(run_health_server())

    # Build Telegram application
    app = Application.builder().token(BOT_TOKEN).build()

    # Conversation handlers (must be added first)
    reg_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            REG_SEX: [MessageHandler(filters.Regex("^(Male|Female)$"), reg_sex)],
            REG_LANG: [MessageHandler(filters.Regex("^(Amharic|English)$"), reg_lang)],
            COUNSELOR_SEX: [MessageHandler(filters.Regex("^(Male|Female)$"), counselor_reg_sex)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True,
    )
    connect_handler = ConversationHandler(
        entry_points=[CommandHandler("connect", connect)],
        states={CONNECT_TOPIC: [MessageHandler(filters.TEXT & ~filters.COMMAND, connect_topic)]},
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True,
    )
    app.add_handler(reg_handler)
    app.add_handler(connect_handler)

    # Command handlers (non‑conversation)
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("stop_counseling", stop_counseling))
    app.add_handler(CommandHandler("chat_history", chat_history))
    app.add_handler(CommandHandler("status", counselor_status))
    app.add_handler(CommandHandler("history", counselor_history))
    app.add_handler(CommandHandler("disconnect", counselor_disconnect))
    app.add_handler(CommandHandler("set_available", set_available))
    app.add_handler(CommandHandler("set_busy", set_busy))
    app.add_handler(CommandHandler("admin", admin_panel))
    app.add_handler(CallbackQueryHandler(admin_callback))

    # Admin text input handler – only runs if admin_action is set, otherwise passes
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, admin_message_handler), group=1)

    # Catch‑all message forwarder (lowest priority – runs after all other handlers)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, forward_message))

    logger.info("Bot is running...")

    await app.initialize()
    await app.start()
    await app.updater.start_polling()

    # Keep alive
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())
