"""
Anonymous Counseling Telegram Bot
========================================
Requirements:
    pip install python-telegram-bot>=21.5 supabase>=2.10.0 aiohttp==3.9.5

Setup:
    Ensure the following environment variables are set:
        - BOT_TOKEN
        - SUPABASE_URL
        - SUPABASE_KEY
        - ADMIN_IDS (comma-separated list of IDs) or ADMIN_ID (single ID)
"""

import os
import logging
import asyncio
from datetime import datetime
from aiohttp import web

from telegram import (
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
)
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)
from supabase import create_client, Client

# ─── LOGGING ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ─── CONFIGURATION & ENVIRONMENT VARIABLES ─────────────────────────────────────
BOT_TOKEN = os.environ.get("BOT_TOKEN")
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN environment variable is required.")
if not SUPABASE_URL:
    raise ValueError("SUPABASE_URL environment variable is required.")
if not SUPABASE_KEY:
    raise ValueError("SUPABASE_KEY environment variable is required.")

# Initialize Supabase client
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Counselor list (hardcoded list for immediate authentication matching)
COUNSELOR_IDS: list[int] = [
    439115108,
    2034041406,
    # Add additional counselor IDs here
]

# Admin management config
def get_admin_ids() -> set[int]:
    admin_ids = set()
    admin_ids_str = os.environ.get("ADMIN_IDS", "")
    if admin_ids_str:
        for x in admin_ids_str.split(","):
            x = x.strip()
            if x.isdigit():
                admin_ids.add(int(x))
    admin_id_str = os.environ.get("ADMIN_ID", "")
    if admin_id_str and admin_id_str.strip().isdigit():
        admin_ids.add(int(admin_id_str.strip()))
    return admin_ids

def is_admin(uid: int) -> bool:
    return uid in get_admin_ids()

async def admin_only_check(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    uid = update.effective_user.id
    if not is_admin(uid):
        await update.message.reply_text("You are not authorized to use admin commands.")
        return False
    return True

# ─── CONVERSATION STATES ───────────────────────────────────────────────────────
REG_SEX, REG_LANG, CONNECT_TOPIC, COUNSELOR_SEX = range(4)
ADMIN_ADD_ID, ADMIN_ADD_SEX, ADMIN_RESET_ID, ADMIN_BROADCAST = range(4, 8)

# ─── KEYBOARDS ─────────────────────────────────────────────────────────────────
USER_KEYBOARD = ReplyKeyboardMarkup(
    [
        ["Help", "Connect"],
        ["Stop Counseling", "Chat History"]
    ],
    resize_keyboard=True,
    is_persistent=True
)

ADMIN_KEYBOARD = ReplyKeyboardMarkup(
    [
        ["📊 Statistics", "📋 List Counselors"],
        ["➕ Add Counselor", "➖ Remove Counselor"],
        ["🔄 Reset User Data", "📨 Broadcast Message"],
        ["❌ Close Admin Panel"]
    ],
    resize_keyboard=True,
    is_persistent=True
)

# ─── TOPIC OPTIONS (bilingual) ────────────────────────────────────────────────
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

# Maps each full button label back to its clean English topic string
TOPIC_ENGLISH = {row[0]: row[0].split(" / ")[0].strip() for row in TOPICS}

# ─── LOCALIZED STRINGS ─────────────────────────────────────────────────────────
STRINGS = {
    "English": {
        "matched": (
            "Congratulations, you have now been matched with a counselor.\n"
            "From now on, all messages you send to the bot will be sent to your anonymous counselor."
        ),
        "no_counselor": "No counselor of your gender available.",
        "session_ended_by_counselor": (
            "Your counselor has ended the session. Use Connect to find another counselor."
        ),
        "stopped": "You have stopped counseling. Use Connect to start again.",
    },
    "Amharic": {
        "matched": (
            "እንኳን ደስ አለዎት! አሁን ከአማካሪዎ ጋር ተገናኝተዋል።\n"
            "ወደ ቦቱ የሚልኩት ሁሉም መልዕክቶች ለአማካሪዎ ይላካሉ።"
        ),
        "no_counselor": "በእርስዎ ጾታ ምንም አማካሪ አልተገኘም። እባክዎ ቆይተው ደግመው ይሞክሩ።",
        "session_ended_by_counselor": (
            "አማካሪዎ ክፍለ ጊዜውን አብቅቷል። ሌላ አማካሪ ለማግኘት Connect ይጠቀሙ።"
        ),
        "stopped": "የምክር አገልግሎቱ አቁመዋል። ደግሞ ለመጀመር Connect ይጠቀሙ።",
    },
}

START_TEXT = (
    "Hello beloved user, this is the counseling team's anonymous counseling service.\n"
    "We hope we can help you in whatever you may need.\n\n"
    "Use the Help command to understand how to use the bot\n"
    "Use the Connect command to start getting counseling\n\n"
    "Always remember God loves you and so do we."
)

REGISTERED_TEXT = (
    "Congratulations!! You have registered to the bot.\n"
    "Use the Help command to learn how to use the bot\n"
    "Use the Connect command to connect with a counselor"
)

USER_HELP_TEXT = (
    "Buttons:\n"
    "Help: Show user instructions\n"
    "Connect: Connect with a counselor\n"
    "Stop Counseling: End current counseling session\n"
    "Chat History: View previous messages\n\n"
    "Usage:\n"
    "Press Connect to get started. Once matched, messages you send are automatically forwarded anonymously. "
    "To view older messages, use Chat History."
)

COUNSELOR_WELCOME_TEXT = (
    "Welcome, Counselor.\n"
    "You are registered in the system. You will be automatically matched with users seeking help.\n\n"
    "Available commands:\n"
    "/status        → See if you are currently connected to a user\n"
    "/history       → See your chat history with the current or last user\n"
    "/disconnect    → Manually end the current session\n"
    "/set_available → Set yourself as available for new users\n"
    "/set_busy      → Set yourself as busy\n"
    "/help          → Show this help"
)

# ─── DATABASE DB SYNCHRONOUS FUNCTIONS ───────────────────────────────────────────
def _get_user(uid: str) -> dict | None:
    res = supabase.table("users").select("*").eq("user_id", uid).execute()
    return res.data[0] if res.data else None

def _upsert_user(uid: str, data: dict) -> dict | None:
    data["user_id"] = uid
    res = supabase.table("users").upsert(data).execute()
    return res.data[0] if res.data else None

def _update_user(uid: str, data: dict) -> dict | None:
    res = supabase.table("users").update(data).eq("user_id", uid).execute()
    return res.data[0] if res.data else None

def _get_counselor(cid: str) -> dict | None:
    res = supabase.table("counselors").select("*").eq("user_id", cid).execute()
    return res.data[0] if res.data else None

def _upsert_counselor(cid: str, data: dict) -> dict | None:
    data["user_id"] = cid
    res = supabase.table("counselors").upsert(data).execute()
    return res.data[0] if res.data else None

def _update_counselor(cid: str, data: dict) -> dict | None:
    res = supabase.table("counselors").update(data).eq("user_id", cid).execute()
    return res.data[0] if res.data else None

def _delete_counselor(cid: str) -> dict | None:
    res = supabase.table("counselors").delete().eq("user_id", cid).execute()
    return res.data[0] if res.data else None

def _find_available_counselor(user_sex: str) -> str | None:
    sex_val = user_sex.capitalize() if user_sex else ""
    res = (
        supabase.table("counselors")
        .select("user_id")
        .eq("available", True)
        .eq("manually_busy", False)
        .is_("current_user_id", "null")
        .eq("sex", sex_val)
        .execute()
    )
    if res.data:
        return res.data[0]["user_id"]
    return None

def _match_user_with_counselor(user_id: str, user_sex: str) -> str | None:
    cid = _find_available_counselor(user_sex)
    if cid:
        claim = (
            supabase.table("counselors")
            .update({"current_user_id": user_id, "available": False})
            .eq("user_id", cid)
            .is_("current_user_id", "null")
            .execute()
        )
        if claim.data:
            supabase.table("users").update({"counselor_id": cid}).eq("user_id", user_id).execute()
            return cid
    return None

def _insert_message(user_id: str, counselor_id: str, role: str, text: str) -> None:
    supabase.table("messages").insert({
        "user_id": user_id,
        "counselor_id": counselor_id,
        "role": role,
        "text": text
    }).execute()

def _get_user_history(uid: str, limit: int) -> list:
    res = (
        supabase.table("messages")
        .select("*")
        .eq("user_id", uid)
        .order("ts", descending=False)
        .execute()
    )
    return res.data[-limit:] if res.data else []

def _get_chat_history(user_id: str, counselor_id: str, limit: int) -> list:
    res = (
        supabase.table("messages")
        .select("*")
        .eq("user_id", user_id)
        .eq("counselor_id", counselor_id)
        .order("ts", descending=False)
        .execute()
    )
    return res.data[-limit:] if res.data else []

def _get_counselor_history_user(cid: str) -> str | None:
    c_res = supabase.table("counselors").select("current_user_id").eq("user_id", cid).execute()
    if c_res.data and c_res.data[0].get("current_user_id"):
        return c_res.data[0]["current_user_id"]
    msg_res = (
        supabase.table("messages")
        .select("user_id")
        .eq("counselor_id", cid)
        .order("ts", descending=True)
        .limit(1)
        .execute()
    )
    if msg_res.data:
        return msg_res.data[0]["user_id"]
    return None

def _db_list_counselors() -> list:
    res = supabase.table("counselors").select("*").execute()
    return res.data if res.data else []

def _db_reset_user(uid: str) -> tuple[bool, str | None]:
    user = _get_user(uid)
    if not user:
        return False, None
    counselor_id = user.get("counselor_id")
    if counselor_id:
        _update_counselor(counselor_id, {"available": True, "current_user_id": None})
    supabase.table("messages").delete().eq("user_id", uid).execute()
    supabase.table("users").delete().eq("user_id", uid).execute()
    return True, counselor_id

def _db_get_all_user_ids() -> list[str]:
    res = supabase.table("users").select("user_id").execute()
    if res.data:
        return [row["user_id"] for row in res.data]
    return []

# ─── DATABASE ASYNC WRAPPERS ─────────────────────────────────────────────────────
async def get_user_db(uid: str) -> dict | None:
    try:
        return await asyncio.to_thread(_get_user, uid)
    except Exception as e:
        logger.error("Error in get_user_db: %s", e)
        return None

async def upsert_user_db(uid: str, data: dict) -> dict | None:
    try:
        return await asyncio.to_thread(_upsert_user, uid, data)
    except Exception as e:
        logger.error("Error in upsert_user_db: %s", e)
        return None

async def update_user_db(uid: str, data: dict) -> dict | None:
    try:
        return await asyncio.to_thread(_update_user, uid, data)
    except Exception as e:
        logger.error("Error in update_user_db: %s", e)
        return None

async def get_counselor_db(cid: str) -> dict | None:
    try:
        return await asyncio.to_thread(_get_counselor, cid)
    except Exception as e:
        logger.error("Error in get_counselor_db: %s", e)
        return None

async def upsert_counselor_db(cid: str, data: dict) -> dict | None:
    try:
        return await asyncio.to_thread(_upsert_counselor, cid, data)
    except Exception as e:
        logger.error("Error in upsert_counselor_db: %s", e)
        return None

async def update_counselor_db(cid: str, data: dict) -> dict | None:
    try:
        return await asyncio.to_thread(_update_counselor, cid, data)
    except Exception as e:
        logger.error("Error in update_counselor_db: %s", e)
        return None

async def match_user_with_counselor(uid: str, user_sex: str) -> str | None:
    try:
        return await asyncio.to_thread(_match_user_with_counselor, uid, user_sex)
    except Exception as e:
        logger.error("Error matching user: %s", e)
        return None

async def insert_message_db(user_id: str, counselor_id: str, role: str, text: str) -> None:
    try:
        await asyncio.to_thread(_insert_message, user_id, counselor_id, role, text)
    except Exception as e:
        logger.error("Error inserting message: %s", e)

async def get_user_history_db(uid: str, limit: int) -> list:
    try:
        return await asyncio.to_thread(_get_user_history, uid, limit)
    except Exception as e:
        logger.error("Error fetching user history: %s", e)
        return []

async def get_chat_history_db(user_id: str, counselor_id: str, limit: int) -> list:
    try:
        return await asyncio.to_thread(_get_chat_history, user_id, counselor_id, limit)
    except Exception as e:
        logger.error("Error fetching chat history: %s", e)
        return []

async def get_counselor_history_user_db(cid: str) -> str | None:
    try:
        return await asyncio.to_thread(_get_counselor_history_user, cid)
    except Exception as e:
        logger.error("Error fetching counselor last/current user: %s", e)
        return None

async def is_counselor(uid: int) -> bool:
    if uid in COUNSELOR_IDS:
        return True
    c = await get_counselor_db(str(uid))
    return c is not None

# ─── USER REGISTRATION & /start ────────────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    uid = update.effective_user.id

    # Admin check
    if is_admin(uid):
        await update.message.reply_text(
            "Welcome, Administrator. Use the panel below to manage the bot.",
            reply_markup=ADMIN_KEYBOARD
        )
        return ConversationHandler.END

    # Counselor check
    if await is_counselor(uid):
        counselor = await get_counselor_db(str(uid))
        if not counselor or counselor.get("sex") is None:
            await update.message.reply_text(
                "Welcome Counselor. Before you start, please select your sex for matching purposes.",
                reply_markup=ReplyKeyboardMarkup(
                    [["Male", "Female"]], one_time_keyboard=True, resize_keyboard=True
                )
            )
            return COUNSELOR_SEX

        await update.message.reply_text(
            COUNSELOR_WELCOME_TEXT,
            reply_markup=ReplyKeyboardRemove()
        )
        return ConversationHandler.END

    # User path
    user = await get_user_db(str(uid))
    if user and user.get("registered"):
        if user.get("counselor_id"):
            await update.message.reply_text(
                "You are still connected to a counselor. Use Stop Counseling to end the session.",
                reply_markup=USER_KEYBOARD
            )
        else:
            await update.message.reply_text(
                REGISTERED_TEXT,
                reply_markup=USER_KEYBOARD
            )
        return ConversationHandler.END

    # Register
    await update.message.reply_text(START_TEXT, reply_markup=ReplyKeyboardRemove())
    await update.message.reply_text(
        "Before you can use the bot, you have to answer the following questions:\n\nWhat is your sex?",
        reply_markup=ReplyKeyboardMarkup(
            [["Male", "Female"]], one_time_keyboard=True, resize_keyboard=True
        )
    )
    return REG_SEX

async def reg_sex(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    uid = update.effective_user.id
    if await is_counselor(uid):
        return ConversationHandler.END

    text = update.message.text.strip()
    if text not in ["Male", "Female"]:
        await update.message.reply_text(
            "Please select your sex using the buttons below (Male or Female).",
            reply_markup=ReplyKeyboardMarkup([["Male", "Female"]], one_time_keyboard=True, resize_keyboard=True)
        )
        return REG_SEX

    context.user_data["reg_sex"] = text
    await update.message.reply_text(
        "Choose your preferred language / የፈለጉትን ቋንቋ ይምረጡ",
        reply_markup=ReplyKeyboardMarkup(
            [["Amharic", "English"]], one_time_keyboard=True, resize_keyboard=True
        )
    )
    return REG_LANG

async def reg_lang(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    uid = update.effective_user.id
    if await is_counselor(uid):
        return ConversationHandler.END

    text = update.message.text.strip()
    if text not in ["Amharic", "English"]:
        await update.message.reply_text(
            "Please select your preferred language (Amharic or English).",
            reply_markup=ReplyKeyboardMarkup([["Amharic", "English"]], one_time_keyboard=True, resize_keyboard=True)
        )
        return REG_LANG

    user_data = {
        "sex": context.user_data["reg_sex"],
        "language": text,
        "registered": True,
        "counselor_id": None,
        "topic": None
    }
    await upsert_user_db(str(uid), user_data)
    await update.message.reply_text(
        REGISTERED_TEXT,
        reply_markup=USER_KEYBOARD
    )
    return ConversationHandler.END

async def counselor_reg_sex(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    uid = update.effective_user.id
    if not await is_counselor(uid):
        return ConversationHandler.END

    text = update.message.text.strip()
    if text not in ["Male", "Female"]:
        await update.message.reply_text(
            "Please select your sex using the buttons below (Male or Female).",
            reply_markup=ReplyKeyboardMarkup([["Male", "Female"]], one_time_keyboard=True, resize_keyboard=True)
        )
        return COUNSELOR_SEX

    c_data = {
        "sex": text,
        "available": True,
        "manually_busy": False,
        "current_user_id": None
    }
    await upsert_counselor_db(str(uid), c_data)
    await update.message.reply_text(
        COUNSELOR_WELCOME_TEXT,
        reply_markup=ReplyKeyboardRemove()
    )
    return ConversationHandler.END

# ─── CANCEL HANDLER ────────────────────────────────────────────────────────────
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    uid = update.effective_user.id
    if await is_counselor(uid):
        await update.message.reply_text("Operation cancelled.", reply_markup=ReplyKeyboardRemove())
    else:
        user = await get_user_db(str(uid))
        if user and user.get("registered"):
            await update.message.reply_text("Operation cancelled.", reply_markup=USER_KEYBOARD)
        else:
            await update.message.reply_text("Operation cancelled.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

async def admin_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Admin operation cancelled.", reply_markup=ADMIN_KEYBOARD)
    return ConversationHandler.END

# ─── CONNECT & TOPIC SELECTION ────────────────────────────────────────────────
async def connect(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    uid = update.effective_user.id
    if await is_counselor(uid):
        await update.message.reply_text("This command is for users only.")
        return ConversationHandler.END

    user = await get_user_db(str(uid))
    if not user or not user.get("registered"):
        await update.message.reply_text(
            "You are not registered yet. Please send /start and complete registration first."
        )
        return ConversationHandler.END

    if user.get("counselor_id") is not None:
        await update.message.reply_text(
            "You are already connected to a counselor. Use Stop Counseling to end the session.",
            reply_markup=USER_KEYBOARD
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
    if await is_counselor(uid):
        return ConversationHandler.END

    text = update.message.text.strip()
    if text in ["Help", "Connect", "Stop Counseling", "Chat History"]:
        return await route_user_button(update, context, text)

    user = await get_user_db(str(uid))
    if not user:
        await update.message.reply_text("User record not found. Please type /start.")
        return ConversationHandler.END

    raw_topic = text
    topic = TOPIC_ENGLISH.get(raw_topic, raw_topic.split(" / ")[0].strip())
    
    await update_user_db(str(uid), {"topic": topic})
    
    user_sex = user.get("sex")
    if not user_sex:
        await update.message.reply_text("Error: sex choice is missing. Please type /start to fix.")
        return ConversationHandler.END

    cid = await match_user_with_counselor(str(uid), user_sex)
    lang = user.get("language") or "English"

    if cid is None:
        no_couns_text = STRINGS.get(lang, STRINGS["English"])["no_counselor"]
        await update.message.reply_text(no_couns_text, reply_markup=USER_KEYBOARD)
        return ConversationHandler.END

    matched_text = STRINGS.get(lang, STRINGS["English"])["matched"]
    await update.message.reply_text(matched_text, reply_markup=USER_KEYBOARD)

    # Notify counselor
    sex_label = user.get("sex") or "Not specified"
    lang_label = user.get("language") or "Not specified"
    topic_label = topic or "Not specified"

    try:
        await context.bot.send_message(
            chat_id=int(cid),
            text=(
                "🔔 You have been matched with a user.\n\n"
                f"📋 Topic:    {topic_label}\n"
                f"👤 Sex:      {sex_label}\n"
                f"🌐 Language: {lang_label}\n\n"
                "All messages from the user will appear here. "
                "Your replies will be sent to them.\n"
                "Use /disconnect to end the session."
            )
        )
    except Exception as e:
        logger.warning("Failed to notify counselor %s: %s", cid, e)

    return ConversationHandler.END

# ─── ROUTING & PERSISTENT USER BUTTONS ─────────────────────────────────────────
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    uid = update.effective_user.id
    if await is_counselor(uid):
        await update.message.reply_text(COUNSELOR_WELCOME_TEXT)
    else:
        await update.message.reply_text(USER_HELP_TEXT)

async def route_user_button(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str) -> int:
    if text == "Help":
        await help_command(update, context)
    elif text == "Connect":
        return await connect(update, context)
    elif text == "Stop Counseling":
        await stop_counseling(update, context)
    elif text == "Chat History":
        await chat_history(update, context)
    return ConversationHandler.END

# ─── STOP COUNSELING ───────────────────────────────────────────────────────────
async def stop_counseling(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    uid = update.effective_user.id
    if await is_counselor(uid):
        await update.message.reply_text("This command is for users only.")
        return

    user = await get_user_db(str(uid))
    if not user or not user.get("counselor_id"):
        await update.message.reply_text(
            "You are not currently in a counseling session. Press Connect to start one.",
            reply_markup=USER_KEYBOARD
        )
        return

    cid = user["counselor_id"]

    await update_user_db(str(uid), {"counselor_id": None})
    await update_counselor_db(cid, {"available": True, "current_user_id": None})

    lang = user.get("language") or "English"
    stopped_text = STRINGS.get(lang, STRINGS["English"])["stopped"]
    await update.message.reply_text(stopped_text, reply_markup=USER_KEYBOARD)

    try:
        await context.bot.send_message(
            chat_id=int(cid),
            text="The user has ended the counseling session. You are now available for new users."
        )
    except Exception as e:
        logger.warning("Could not notify counselor %s of user disconnect: %s", cid, e)

# ─── USER CHAT HISTORY ─────────────────────────────────────────────────────────
async def chat_history(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    uid = update.effective_user.id
    if await is_counselor(uid):
        await update.message.reply_text("This command is for users only.")
        return

    limit = 20
    if context.args:
        try:
            limit = int(context.args[0])
        except ValueError:
            await update.message.reply_text("Invalid limit. Usage: /chat_history or /chat_history 50")
            return

    history = await get_user_history_db(str(uid), limit)
    if not history:
        await update.message.reply_text("No chat history found.")
        return

    lines = []
    for e in history:
        ts_str = e.get("ts")
        if ts_str:
            try:
                ts_dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                ts_str = ts_dt.strftime("%Y-%m-%d %H:%M")
            except Exception:
                pass
        role = e.get("role")
        text = e.get("text")
        lines.append(f"[{ts_str}] {role}: {text}")

    reply = "\n".join(lines)
    if len(reply) > 4000:
        reply = "...(truncated)\n" + reply[-4000:]

    await update.message.reply_text(reply)

# ─── COUNSELOR COMMANDS ────────────────────────────────────────────────────────
async def counselor_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    uid = update.effective_user.id
    if not await is_counselor(uid):
        await update.message.reply_text("This command is for counselors only.")
        return

    c = await get_counselor_db(str(uid))
    if not c:
        await update.message.reply_text("Your database record is missing. Please type /start first.")
        return

    if c.get("current_user_id"):
        user = await get_user_db(c["current_user_id"])
        topic = user.get("topic") if user else "Unknown"
        sex = user.get("sex") if user else "Unknown"
        lang = user.get("language") if user else "Unknown"
        msg = f"You are currently connected to a user.\nTopic: {topic}\nSex: {sex}\nLanguage: {lang}\nType /disconnect to end the session."
    elif c.get("manually_busy"):
        msg = "You are set as busy. Use /set_available to receive new users."
    else:
        msg = "You are available and will receive new users."

    await update.message.reply_text(msg)

async def counselor_history(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    uid = update.effective_user.id
    if not await is_counselor(uid):
        await update.message.reply_text("This command is for counselors only.")
        return

    limit = 20
    if context.args:
        try:
            limit = int(context.args[0])
        except ValueError:
            await update.message.reply_text("Invalid limit. Usage: /history or /history 50")
            return

    user_id = await get_counselor_history_user_db(str(uid))
    if not user_id:
        await update.message.reply_text("No chat history found.")
        return

    history = await get_chat_history_db(user_id, str(uid), limit)
    if not history:
        await update.message.reply_text("No chat history found.")
        return

    lines = []
    for e in history:
        ts_str = e.get("ts")
        if ts_str:
            try:
                ts_dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                ts_str = ts_dt.strftime("%Y-%m-%d %H:%M")
            except Exception:
                pass
        role = e.get("role")
        text = e.get("text")
        lines.append(f"[{ts_str}] {role}: {text}")

    reply = "\n".join(lines)
    if len(reply) > 4000:
        reply = "...(truncated)\n" + reply[-4000:]

    await update.message.reply_text(reply)

async def counselor_disconnect(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    uid = update.effective_user.id
    if not await is_counselor(uid):
        await update.message.reply_text("This command is for counselors only.")
        return

    c = await get_counselor_db(str(uid))
    if not c or not c.get("current_user_id"):
        await update.message.reply_text("You are not currently connected to any user.")
        return

    user_id = c["current_user_id"]

    await update_counselor_db(str(uid), {"available": True, "current_user_id": None})
    await update_user_db(user_id, {"counselor_id": None})

    await update.message.reply_text("Session ended. You are now available for new users.")

    user = await get_user_db(user_id)
    lang = user.get("language") if user else "English"
    stopped_text = STRINGS.get(lang, STRINGS["English"])["session_ended_by_counselor"]

    try:
        await context.bot.send_message(
            chat_id=int(user_id),
            text=stopped_text,
            reply_markup=USER_KEYBOARD
        )
    except Exception as e:
        logger.warning("Could not notify user %s of counselor disconnect: %s", user_id, e)

async def set_available(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    uid = update.effective_user.id
    if not await is_counselor(uid):
        await update.message.reply_text("This command is for counselors only.")
        return

    c = await get_counselor_db(str(uid))
    if not c:
        await update.message.reply_text("Your database record is missing. Please type /start first.")
        return

    available_val = True if c.get("current_user_id") is None else False
    await update_counselor_db(str(uid), {"manually_busy": False, "available": available_val})
    await update.message.reply_text("You are now available and will receive new users.")

async def set_busy(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    uid = update.effective_user.id
    if not await is_counselor(uid):
        await update.message.reply_text("This command is for counselors only.")
        return

    await update_counselor_db(str(uid), {"manually_busy": True, "available": False})
    await update.message.reply_text(
        "You are now set as busy. You won't receive new users until you use /set_available.\n(Any active session continues normally.)"
    )

# ─── MESSAGE FORWARDING ────────────────────────────────────────────────────────
async def forward_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    sender_id = update.effective_user.id
    text = update.message.text

    # Route Admin buttons if this user is also Admin
    if is_admin(sender_id) and text in [
        "📊 Statistics", "📋 List Counselors", "➖ Remove Counselor",
        "➕ Add Counselor", "🔄 Reset User Data", "📨 Broadcast Message",
        "❌ Close Admin Panel"
    ]:
        await route_admin_button(update, context, text)
        return

    # Check counselor role
    if await is_counselor(sender_id):
        c = await get_counselor_db(str(sender_id))
        if not c:
            await update.message.reply_text("Your details are missing from database. Please run /start first.")
            return

        current_user_id = c.get("current_user_id")
        if not current_user_id:
            await update.message.reply_text("You are not connected to any user right now.")
            return

        try:
            await context.bot.send_message(chat_id=int(current_user_id), text=text)
            await insert_message_db(current_user_id, str(sender_id), "Counselor", text)
        except Exception as e:
            logger.error("Failed to forward counselor→user (%s): %s", current_user_id, e)
            await update.message.reply_text("Could not deliver your message to the user.")
        return

    # Route user keyboard buttons
    if text == "Help":
        await help_command(update, context)
        return
    elif text == "Connect":
        return
    elif text == "Stop Counseling":
        await stop_counseling(update, context)
        return
    elif text == "Chat History":
        await chat_history(update, context)
        return

    # User role
    user = await get_user_db(str(sender_id))
    if not user or not user.get("registered"):
        await update.message.reply_text("Please register first using /start.")
        return

    cid = user.get("counselor_id")
    if not cid:
        await update.message.reply_text(
            "You are not connected to a counselor. Press Connect to start a session.",
            reply_markup=USER_KEYBOARD
        )
        return

    try:
        await context.bot.send_message(chat_id=int(cid), text=text)
        await insert_message_db(str(sender_id), cid, "User", text)
    except Exception as e:
        logger.error("Failed to forward user→counselor (%s): %s", cid, e)
        await update.message.reply_text("Could not deliver your message to the counselor.")

# ─── ADMIN COMMANDS ────────────────────────────────────────────────────────────
async def admin_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await admin_only_check(update, context):
        return
    await update.message.reply_text(
        "Welcome to the Admin Panel. Choose an option from the menu below:",
        reply_markup=ADMIN_KEYBOARD
    )

def _get_statistics():
    users_res = supabase.table("users").select("user_id").execute()
    couns_res = supabase.table("counselors").select("user_id").execute()
    active_res = (
        supabase.table("counselors")
        .select("user_id")
        .eq("available", False)
        .not_.is_("current_user_id", "null")
        .execute()
    )
    return {
        "total_users": len(users_res.data) if users_res.data else 0,
        "total_counselors": len(couns_res.data) if couns_res.data else 0,
        "active_sessions": len(active_res.data) if active_res.data else 0
    }

async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await admin_only_check(update, context):
        return
    try:
        stats = await asyncio.to_thread(_get_statistics)
        msg = (
            f"📊 Bot Statistics:\n"
            f"Total Users: {stats['total_users']}\n"
            f"Total Counselors: {stats['total_counselors']}\n"
            f"Active Sessions: {stats['active_sessions']}"
        )
        await update.message.reply_text(msg)
    except Exception as e:
        logger.error("Error retrieving statistics: %s", e)
        await update.message.reply_text("Error retrieving statistics.")

async def admin_list_counselors(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await admin_only_check(update, context):
        return
    try:
        counselors = await asyncio.to_thread(_db_list_counselors)
        if not counselors:
            await update.message.reply_text("No counselors registered in Supabase.")
            return
        
        lines = []
        for c in counselors:
            status = "🟢 Available" if (c.get("available") and not c.get("manually_busy")) else ("🟡 Connected" if c.get("current_user_id") else "🔴 Busy")
            gender = c.get("sex") or "Not set"
            lines.append(f"ID: {c['user_id']} | Sex: {gender} | Status: {status}")
            
        await update.message.reply_text("\n".join(lines))
    except Exception as e:
        logger.error("Error listing counselors: %s", e)
        await update.message.reply_text("Error listing counselors.")

async def admin_remove_counselor_inline(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await admin_only_check(update, context):
        return
    try:
        counselors = await asyncio.to_thread(_db_list_counselors)
        if not counselors:
            await update.message.reply_text("No counselors found.")
            return
        
        keyboard = []
        for c in counselors:
            cid = c["user_id"]
            sex_icon = "👨" if c.get("sex", "").lower() == "male" else "👩"
            status_icon = "🟢" if (c.get("available") and not c.get("manually_busy")) else ("🟡" if c.get("current_user_id") else "🔴")
            btn_text = f"ID: {cid} {sex_icon} {status_icon}"
            keyboard.append([InlineKeyboardButton(btn_text, callback_data=f"remove_counselor:{cid}")])
        
        await update.message.reply_text(
            "Select a counselor to remove from Supabase (this cannot be undone):",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    except Exception as e:
        logger.error("Error setting up inline removal: %s", e)
        await update.message.reply_text("Error setting up inline removal.")

async def remove_counselor_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    
    if not await admin_only_check(update, context):
        return
        
    data = query.data
    prefix, cid = data.split(":", 1)
    
    admin_id = update.effective_user.id
    if str(admin_id) == str(cid):
        await query.edit_message_text("❌ You cannot remove yourself from the counselor list.")
        return
        
    c = await get_counselor_db(cid)
    if c:
        current_user_id = c.get("current_user_id")
        if current_user_id:
            await update_user_db(current_user_id, {"counselor_id": None})
            try:
                user = await get_user_db(current_user_id)
                lang = user.get("language") if user else "English"
                stopped_text = STRINGS.get(lang, STRINGS["English"])["session_ended_by_counselor"]
                await context.bot.send_message(
                    chat_id=int(current_user_id),
                    text=stopped_text,
                    reply_markup=USER_KEYBOARD
                )
            except Exception as e:
                logger.warning("Could not notify user %s on counselor removal: %s", current_user_id, e)
                
    try:
        await asyncio.to_thread(_delete_counselor, cid)
        await query.edit_message_text(f"✅ Counselor {cid} has been successfully removed.")
    except Exception as e:
        logger.error("Error removing counselor %s: %s", cid, e)
        await query.edit_message_text(f"❌ Failed to remove counselor {cid}.")

# ─── ADMIN CONVERSATION FLOWS ──────────────────────────────────────────────────
async def admin_add_counselor_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not await admin_only_check(update, context):
        return ConversationHandler.END
    await update.message.reply_text(
        "Please send the numeric Telegram User ID of the new counselor:",
        reply_markup=ReplyKeyboardRemove()
    )
    return ADMIN_ADD_ID

async def admin_add_counselor_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not await admin_only_check(update, context):
        return ConversationHandler.END
    text = update.message.text.strip()
    
    if text in ["📊 Statistics", "📋 List Counselors", "➖ Remove Counselor", "➕ Add Counselor", "🔄 Reset User Data", "📨 Broadcast Message", "❌ Close Admin Panel"]:
        return await route_admin_button(update, context, text)
        
    if not text.isdigit():
        await update.message.reply_text("Invalid ID. Please enter a numeric User ID:")
        return ADMIN_ADD_ID

    context.user_data["add_counselor_id"] = text
    await update.message.reply_text(
        "Please select the counselor's sex:",
        reply_markup=ReplyKeyboardMarkup([["Male", "Female"]], one_time_keyboard=True, resize_keyboard=True)
    )
    return ADMIN_ADD_SEX

async def admin_add_counselor_sex(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not await admin_only_check(update, context):
        return ConversationHandler.END
    text = update.message.text.strip()
    
    if text in ["📊 Statistics", "📋 List Counselors", "➖ Remove Counselor", "➕ Add Counselor", "🔄 Reset User Data", "📨 Broadcast Message", "❌ Close Admin Panel"]:
        return await route_admin_button(update, context, text)

    if text not in ["Male", "Female"]:
        await update.message.reply_text(
            "Invalid sex. Please select using the buttons (Male or Female):",
            reply_markup=ReplyKeyboardMarkup([["Male", "Female"]], one_time_keyboard=True, resize_keyboard=True)
        )
        return ADMIN_ADD_SEX

    cid = context.user_data.get("add_counselor_id")
    if not cid:
        await update.message.reply_text("Error: counselor ID missing. Please restart the flow.", reply_markup=ADMIN_KEYBOARD)
        return ConversationHandler.END

    c_data = {
        "sex": text,
        "available": True,
        "manually_busy": False,
        "current_user_id": None
    }
    await upsert_counselor_db(cid, c_data)
    await update.message.reply_text(
        f"Counselor {cid} ({text}) successfully added to Supabase.",
        reply_markup=ADMIN_KEYBOARD
    )
    return ConversationHandler.END

async def admin_reset_user_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not await admin_only_check(update, context):
        return ConversationHandler.END
    await update.message.reply_text(
        "Please send the numeric Telegram User ID of the user to reset (this will delete their registration details and all chat history):",
        reply_markup=ReplyKeyboardRemove()
    )
    return ADMIN_RESET_ID

async def admin_reset_user_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not await admin_only_check(update, context):
        return ConversationHandler.END
    text = update.message.text.strip()
    
    if text in ["📊 Statistics", "📋 List Counselors", "➖ Remove Counselor", "➕ Add Counselor", "🔄 Reset User Data", "📨 Broadcast Message", "❌ Close Admin Panel"]:
        return await route_admin_button(update, context, text)

    if not text.isdigit():
        await update.message.reply_text("Invalid ID. Please enter a numeric User ID:")
        return ADMIN_RESET_ID

    try:
        success, counselor_id = await asyncio.to_thread(_db_reset_user, text)
        if success:
            await update.message.reply_text(f"User {text} and all their messages have been successfully deleted.", reply_markup=ADMIN_KEYBOARD)
            if counselor_id:
                try:
                    await context.bot.send_message(
                        chat_id=int(counselor_id),
                        text="The user you were connected to has had their data reset. The session is ended and you are available."
                    )
                except Exception as e:
                    logger.warning("Could not notify counselor %s of user reset: %s", counselor_id, e)
        else:
            await update.message.reply_text(f"User {text} was not found in the database.", reply_markup=ADMIN_KEYBOARD)
    except Exception as e:
        logger.error("Error resetting user data for %s: %s", text, e)
        await update.message.reply_text("Error resetting user data.", reply_markup=ADMIN_KEYBOARD)
        
    return ConversationHandler.END

async def admin_broadcast_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not await admin_only_check(update, context):
        return ConversationHandler.END
    await update.message.reply_text(
        "Please send the message text you want to broadcast to all registered users:",
        reply_markup=ReplyKeyboardRemove()
    )
    return ADMIN_BROADCAST

async def admin_broadcast_send(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not await admin_only_check(update, context):
        return ConversationHandler.END
    text = update.message.text
    
    if text in ["📊 Statistics", "📋 List Counselors", "➖ Remove Counselor", "➕ Add Counselor", "🔄 Reset User Data", "📨 Broadcast Message", "❌ Close Admin Panel"]:
        return await route_admin_button(update, context, text)

    try:
        user_ids = await asyncio.to_thread(_db_get_all_user_ids)
        if not user_ids:
            await update.message.reply_text("No users to broadcast to.", reply_markup=ADMIN_KEYBOARD)
            return ConversationHandler.END
        
        await update.message.reply_text(f"Starting broadcast to {len(user_ids)} users...")
        success_count = 0
        failure_count = 0
        
        for uid in user_ids:
            try:
                await context.bot.send_message(chat_id=int(uid), text=text)
                success_count += 1
            except Exception as e:
                logger.warning("Failed to broadcast message to user %s: %s", uid, e)
                failure_count += 1
                
        await update.message.reply_text(
            f"Broadcast completed.\nSuccessful: {success_count}\nFailed: {failure_count}",
            reply_markup=ADMIN_KEYBOARD
        )
    except Exception as e:
        logger.error("Error during broadcast: %s", e)
        await update.message.reply_text("Error occurred during broadcast.", reply_markup=ADMIN_KEYBOARD)
        
    return ConversationHandler.END

async def admin_close(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    uid = update.effective_user.id
    if await is_counselor(uid):
        await update.message.reply_text("Admin panel closed.", reply_markup=ReplyKeyboardRemove())
    else:
        user = await get_user_db(str(uid))
        if user and user.get("registered"):
            await update.message.reply_text("Admin panel closed. Returning to user menu.", reply_markup=USER_KEYBOARD)
        else:
            await update.message.reply_text("Admin panel closed.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

async def route_admin_button(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str) -> int:
    if text == "📊 Statistics":
        await admin_stats(update, context)
        return ConversationHandler.END
    elif text == "📋 List Counselors":
        await admin_list_counselors(update, context)
        return ConversationHandler.END
    elif text == "➖ Remove Counselor":
        await admin_remove_counselor_inline(update, context)
        return ConversationHandler.END
    elif text == "➕ Add Counselor":
        return await admin_add_counselor_start(update, context)
    elif text == "🔄 Reset User Data":
        return await admin_reset_user_start(update, context)
    elif text == "📨 Broadcast Message":
        return await admin_broadcast_start(update, context)
    elif text == "❌ Close Admin Panel":
        return await admin_close(update, context)
    return ConversationHandler.END

# ─── RENDER HEALTH CHECK SERVER ────────────────────────────────────────────────
async def handle_health(request: web.Request) -> web.Response:
    return web.Response(text="Bot is alive")

async def start_health_check_server() -> None:
    app = web.Application()
    app.router.add_get("/", handle_health)
    app.router.add_get("/health", handle_health)
    
    port = int(os.environ.get("PORT", 8080))
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logger.info("Health check server started on port %d", port)

async def post_init(application: Application) -> None:
    await start_health_check_server()

# ─── MAIN FUNCTION ─────────────────────────────────────────────────────────────
def main() -> None:
    # Build python-telegram-bot application
    app = Application.builder().token(BOT_TOKEN).post_init(post_init).build()

    # User registration conversation handler
    reg_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            REG_SEX: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, reg_sex)
            ],
            REG_LANG: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, reg_lang)
            ],
            COUNSELOR_SEX: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, counselor_reg_sex)
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True,
    )

    # User connection conversation handler
    connect_handler = ConversationHandler(
        entry_points=[
            CommandHandler("connect", connect),
            MessageHandler(filters.Regex("^Connect$"), connect)
        ],
        states={
            CONNECT_TOPIC: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, connect_topic)
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True,
    )

    # Admin actions conversation handler
    admin_flow_handler = ConversationHandler(
        entry_points=[
            CommandHandler("admin", admin_start),
            MessageHandler(filters.Regex("^➕ Add Counselor$"), admin_add_counselor_start),
            MessageHandler(filters.Regex("^🔄 Reset User Data$"), admin_reset_user_start),
            MessageHandler(filters.Regex("^📨 Broadcast Message$"), admin_broadcast_start),
        ],
        states={
            ADMIN_ADD_ID: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_add_counselor_id)
            ],
            ADMIN_ADD_SEX: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_add_counselor_sex)
            ],
            ADMIN_RESET_ID: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_reset_user_id)
            ],
            ADMIN_BROADCAST: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_broadcast_send)
            ],
        },
        fallbacks=[
            CommandHandler("cancel", admin_cancel),
            MessageHandler(filters.Regex("^❌ Close Admin Panel$"), admin_close),
        ],
        allow_reentry=True,
    )

    # Register conversation handlers first (they have high priority)
    app.add_handler(reg_handler)
    app.add_handler(connect_handler)
    app.add_handler(admin_flow_handler)

    # Inline query handler for counselor removal
    app.add_handler(CallbackQueryHandler(remove_counselor_callback, pattern="^remove_counselor:"))

    # Standard Help command
    app.add_handler(CommandHandler("help", help_command))

    # User commands (in addition to button clicks)
    app.add_handler(CommandHandler("stop_counseling", stop_counseling))
    app.add_handler(CommandHandler("chat_history", chat_history))

    # Counselor commands
    app.add_handler(CommandHandler("status", counselor_status))
    app.add_handler(CommandHandler("history", counselor_history))
    app.add_handler(CommandHandler("disconnect", counselor_disconnect))
    app.add_handler(CommandHandler("set_available", set_available))
    app.add_handler(CommandHandler("set_busy", set_busy))

    # General admin commands / menu handlers
    app.add_handler(CommandHandler("admin", admin_start))
    app.add_handler(MessageHandler(filters.Regex("^📊 Statistics$"), admin_stats))
    app.add_handler(MessageHandler(filters.Regex("^📋 List Counselors$"), admin_list_counselors))
    app.add_handler(MessageHandler(filters.Regex("^➖ Remove Counselor$"), admin_remove_counselor_inline))
    app.add_handler(MessageHandler(filters.Regex("^❌ Close Admin Panel$"), admin_close))

    # Text message forwarding handler (handles matching session messages)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, forward_message))

    # Start long polling
    logger.info("Starting Telegram Bot long polling...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
