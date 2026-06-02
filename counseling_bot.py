"""
Anonymous Counseling Telegram Bot — v4
========================================
Requirements:
    pip install python-telegram-bot==20.7

Setup:
    1. Create a bot via @BotFather and paste the token into BOT_TOKEN.
    2. Add every counselor's Telegram numeric user ID to COUNSELOR_IDS.
    3. Run:  python counseling_bot.py

What's new in v3 (on top of v2):
    - /connect now asks the user to TYPE their concern freely instead of
      picking from a fixed topic keyboard. Any text is accepted as the topic.
    - The TOPICS button list has been removed entirely.

What's new in v4 (on top of v3):
    - /connect shows bilingual topic buttons (English / Amharic on each button).
    - Only the English portion is stored internally and shown to counselors.
"""

import json
import logging
import os
from datetime import datetime

from telegram import (
    ReplyKeyboardMarkup,  # still used in registration (/start sex + language)
    ReplyKeyboardRemove,
    Update,
)
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

# ─── CONFIG ────────────────────────────────────────────────────────────────────

BOT_TOKEN = "8159834691:AAEzVha1MyJbNsurJ0-avt7nzy3OohSgD20"

COUNSELOR_IDS: list[int] = [
    439115108,
    2034041406,
    # Add more counselor IDs here
]

DATA_FILE = "data.json"

# ─── CONVERSATION STATES ───────────────────────────────────────────────────────

REG_SEX, REG_LANG, CONNECT_TOPIC, COUNSELOR_SEX = range(4)

# ─── TOPIC OPTIONS (bilingual) ────────────────────────────────────────────────
# Each button shows "English / Amharic". Only the English part is stored.

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

# Maps each full button label back to its clean English topic string.
TOPIC_ENGLISH = {row[0]: row[0].split(" / ")[0].strip() for row in TOPICS}


# ─── LOGGING ───────────────────────────────────────────────────────────────────

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ─── PERSISTENCE ───────────────────────────────────────────────────────────────

def load_data() -> dict:
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"users": {}, "counselors": {}}


def save_data(data: dict) -> None:
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def get_user(data: dict, uid: int) -> dict:
    key = str(uid)
    if key not in data["users"]:
        data["users"][key] = {
            "sex": None,
            "language": None,
            "registered": False,
            "counselor_id": None,
            "topic": None,
            "history": [],
        }
    return data["users"][key]


def get_counselor(data: dict, cid: int) -> dict:
    key = str(cid)
    if key not in data["counselors"]:
        data["counselors"][key] = {
            "available": True,
            "manually_busy": False,
            "current_user_id": None,
            "sex": None,
            "history": [],
        }
    rec = data["counselors"][key]
    # Back-compat: ensure new fields exist in older data.json files
    rec.setdefault("manually_busy", False)
    rec.setdefault("history", [])
    rec.setdefault("sex", None)
    return rec


def find_available_counselor(data: dict, user_sex: str) -> int | None:
    """Return the first counselor who matches the user's sex, is available, and is not currently assigned."""
    normalized_sex = (user_sex or "").strip().lower()
    for cid in COUNSELOR_IDS:
        rec = get_counselor(data, cid)
        if rec.get("sex") is None:
            continue
        if rec.get("sex", "").strip().lower() != normalized_sex:
            continue
        if rec["available"] and not rec["manually_busy"] and rec["current_user_id"] is None:
            return cid
    return None


def append_user_history(data: dict, uid: int, role: str, text: str) -> None:
    """Append to the user's history. role = 'You' | 'Counselor'"""
    get_user(data, uid)["history"].append({
        "ts": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "role": role,
        "text": text,
    })


def append_counselor_history(data: dict, cid: int, role: str, text: str) -> None:
    """Append to the counselor's history. role = 'User' | 'You'"""
    get_counselor(data, cid)["history"].append({
        "ts": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "role": role,
        "text": text,
    })


def is_counselor(uid: int) -> bool:
    return uid in COUNSELOR_IDS


# ─── LOCALISED STRINGS ─────────────────────────────────────────────────────────
# Messages sent TO the user are localised based on their language preference.
# Add / extend Amharic translations here as needed.

STRINGS = {
    "English": {
        "matched": (
            "Congratulations, you have now been matched with a counselor.\n"
            "From now on, all messages you send to the bot will be sent to your anonymous counselor."
        ),
        "no_counselor": "No counselors are online right now. Please try again later.",
        "session_ended_by_counselor": (
            "Your counselor has ended the session. Use /connect to find another counselor."
        ),
        "stopped": "You have stopped counseling. Use /connect to start again.",
    },
    "Amharic": {
        "matched": (
            "እንኳን ደስ አለዎት! አሁን ከአማካሪዎ ጋር ተገናኝተዋል።\n"
            "ወደ ቦቱ የሚልኩት ሁሉም መልዕክቶች ለአማካሪዎ ይላካሉ።"
        ),
        "no_counselor": "አሁን ምንም አማካሪ አልተገኘም። እባክዎ ቆይተው ደግመው ይሞክሩ።",
        "session_ended_by_counselor": (
            "አማካሪዎ ክፍለ ጊዜውን አብቅቷል። ሌላ አማካሪ ለማግኘት /connect ይጠቀሙ።"
        ),
        "stopped": "የምክር አገልግሎቱ አቁመዋል። ደግሞ ለመጀመር /connect ይጠቀሙ።",
    },
}


def user_str(data: dict, uid: int, key: str) -> str:
    """Return the localised string for a user's preferred language."""
    lang = get_user(data, uid).get("language") or "English"
    return STRINGS.get(lang, STRINGS["English"])[key]


# ─── STATIC TEXTS ──────────────────────────────────────────────────────────────

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

USER_ONLY_MSG     = "This command is for users only."
COUNSELOR_ONLY_MSG = "This command is for counselors only."


# ─── /start ────────────────────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    uid = update.effective_user.id

    # ── Counselor path ──
    if is_counselor(uid):
        data = load_data()
        rec = get_counselor(data, uid)   # ensure record exists
        save_data(data)

        if rec.get("sex") is None:
            await update.message.reply_text(
                "Before you start, please select your sex for matching purposes.",
                reply_markup=ReplyKeyboardMarkup(
                    [["Male", "Female"]], one_time_keyboard=True, resize_keyboard=True
                ),
            )
            return COUNSELOR_SEX

        await update.message.reply_text(
            COUNSELOR_WELCOME_TEXT, reply_markup=ReplyKeyboardRemove()
        )
        return ConversationHandler.END

    # ── User path ──
    data = load_data()
    user = get_user(data, uid)

    await update.message.reply_text(START_TEXT, reply_markup=ReplyKeyboardRemove())

    if user["counselor_id"] is not None:
        await update.message.reply_text(
            "You are still connected to a counselor. Use /stop_counseling to end the session."
        )
        save_data(data)
        return ConversationHandler.END

    if user["registered"]:
        await update.message.reply_text(REGISTERED_TEXT)
        save_data(data)
        return ConversationHandler.END

    # Begin registration
    await update.message.reply_text(
        "Before you can use the bot, you have to answer the following questions:\n\nWhat is your sex?",
        reply_markup=ReplyKeyboardMarkup(
            [["Male", "Female"]], one_time_keyboard=True, resize_keyboard=True
        ),
    )
    save_data(data)
    return REG_SEX


async def reg_sex(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    uid = update.effective_user.id
    if is_counselor(uid):
        return ConversationHandler.END

    data = load_data()
    get_user(data, uid)["sex"] = update.message.text
    save_data(data)

    await update.message.reply_text(
        "Choose your preferred language",
        reply_markup=ReplyKeyboardMarkup(
            [["Amharic", "English"]], one_time_keyboard=True, resize_keyboard=True
        ),
    )
    return REG_LANG


async def counselor_reg_sex(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    uid = update.effective_user.id
    if not is_counselor(uid):
        return ConversationHandler.END

    data = load_data()
    rec = get_counselor(data, uid)
    rec["sex"] = update.message.text.strip().lower()
    save_data(data)

    await update.message.reply_text(
        COUNSELOR_WELCOME_TEXT, reply_markup=ReplyKeyboardRemove()
    )
    return ConversationHandler.END


async def reg_lang(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    uid = update.effective_user.id
    if is_counselor(uid):
        return ConversationHandler.END

    data = load_data()
    user = get_user(data, uid)
    user["language"] = update.message.text
    user["registered"] = True
    save_data(data)

    await update.message.reply_text(REGISTERED_TEXT, reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END


# ─── /help ─────────────────────────────────────────────────────────────────────

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if is_counselor(update.effective_user.id):
        await update.message.reply_text(COUNSELOR_WELCOME_TEXT)
    else:
        await update.message.reply_text(USER_HELP_TEXT)


# ─── /connect (user only) ──────────────────────────────────────────────────────

async def connect(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    uid = update.effective_user.id

    if is_counselor(uid):
        await update.message.reply_text(USER_ONLY_MSG)
        return ConversationHandler.END

    data = load_data()
    user = get_user(data, uid)

    if not user["registered"]:
        await update.message.reply_text(
            "You are not registered yet. Please send /start and complete registration first."
        )
        return ConversationHandler.END

    if user["counselor_id"] is not None:
        await update.message.reply_text(
            "You are already connected to a counselor. "
            "Use /stop_counseling to end the current session first."
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

    data = load_data()
    user = get_user(data, uid)
    # Store only the English part (before " / "); fall back to the raw text
    # in case the user somehow sends something not in the keyboard.
    raw_topic = update.message.text
    user["topic"] = TOPIC_ENGLISH.get(raw_topic, raw_topic.split(" / ")[0].strip())

    cid = find_available_counselor(data, user["sex"])
    if cid is None:
        await update.message.reply_text(
            "No counselor of your gender is available right now. Please try again later.",
            reply_markup=ReplyKeyboardRemove(),
        )
        save_data(data)
        return ConversationHandler.END

    # Link counselor ↔ user
    counselor = get_counselor(data, cid)
    counselor["available"] = False
    counselor["current_user_id"] = uid
    user["counselor_id"] = cid
    save_data(data)

    await update.message.reply_text(
        user_str(data, uid, "matched"),
        reply_markup=ReplyKeyboardRemove(),
    )

    # Notify counselor — include user's sex, language, and topic
    sex_label   = user.get("sex")      or "Not specified"
    lang_label  = user.get("language") or "Not specified"
    topic_label = user.get("topic")    or "Not specified"

    try:
        await context.bot.send_message(
            chat_id=cid,
            text=(
                "🔔 You have been matched with a user.\n\n"
                f"📋 Topic:    {topic_label}\n"
                f"👤 Sex:      {sex_label}\n"
                f"🌐 Language: {lang_label}\n\n"
                "All messages from the user will appear here. "
                "Your replies will be sent to them.\n"
                "Use /disconnect to end the session."
            ),
        )
    except Exception as e:
        logger.warning("Could not notify counselor %s: %s", cid, e)

    return ConversationHandler.END


# ─── /stop_counseling (user only) ─────────────────────────────────────────────

async def stop_counseling(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    uid = update.effective_user.id

    if is_counselor(uid):
        await update.message.reply_text(USER_ONLY_MSG)
        return

    data = load_data()
    user = get_user(data, uid)

    if user["counselor_id"] is None:
        await update.message.reply_text(
            "You are not currently in a counseling session. Use /connect to start one."
        )
        return

    cid = user["counselor_id"]
    counselor = get_counselor(data, cid)
    counselor["available"] = True
    counselor["manually_busy"] = False
    counselor["current_user_id"] = None
    user["counselor_id"] = None
    save_data(data)

    await update.message.reply_text(user_str(data, uid, "stopped"))

    try:
        await context.bot.send_message(
            chat_id=cid,
            text="🔔 The user has ended the counseling session. You are now available for new users.",
        )
    except Exception as e:
        logger.warning("Could not notify counselor %s: %s", cid, e)


# ─── /chat_history (user only) ────────────────────────────────────────────────

async def chat_history(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    uid = update.effective_user.id

    if is_counselor(uid):
        await update.message.reply_text(USER_ONLY_MSG)
        return

    data = load_data()
    user = get_user(data, uid)

    limit = 20
    if context.args:
        try:
            limit = int(context.args[0])
        except ValueError:
            await update.message.reply_text(
                "Invalid limit. Usage: /chat_history or /chat_history 50"
            )
            return

    history = user["history"]
    if not history:
        await update.message.reply_text("No chat history found.")
        return

    entries = history[-limit:]
    lines = [f"[{e['ts']}] {e['role']}: {e['text']}" for e in entries]
    reply = "\n".join(lines)

    if len(reply) > 4000:
        reply = "...(truncated)\n" + reply[-4000:]

    await update.message.reply_text(reply)


# ─── COUNSELOR COMMANDS ────────────────────────────────────────────────────────

async def counselor_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    uid = update.effective_user.id
    if not is_counselor(uid):
        await update.message.reply_text(COUNSELOR_ONLY_MSG)
        return

    data = load_data()
    rec = get_counselor(data, uid)

    if rec["current_user_id"] is not None:
        msg = "You are currently helping a user. Type /disconnect to end."
    elif rec.get("manually_busy"):
        msg = "You are set as busy. Use /set_available to receive users."
    else:
        msg = "You are available and will receive new users."

    await update.message.reply_text(msg)


async def counselor_history(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    uid = update.effective_user.id
    if not is_counselor(uid):
        await update.message.reply_text(COUNSELOR_ONLY_MSG)
        return

    data = load_data()
    rec = get_counselor(data, uid)

    limit = 20
    if context.args:
        try:
            limit = int(context.args[0])
        except ValueError:
            await update.message.reply_text("Invalid limit. Usage: /history or /history 50")
            return

    history = rec.get("history", [])
    if not history:
        await update.message.reply_text("No chat history found.")
        return

    entries = history[-limit:]
    lines = [f"[{e['ts']}] {e['role']}: {e['text']}" for e in entries]
    reply = "\n".join(lines)

    if len(reply) > 4000:
        reply = "...(truncated)\n" + reply[-4000:]

    await update.message.reply_text(reply)


async def counselor_disconnect(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    uid = update.effective_user.id
    if not is_counselor(uid):
        await update.message.reply_text(COUNSELOR_ONLY_MSG)
        return

    data = load_data()
    rec = get_counselor(data, uid)

    if rec["current_user_id"] is None:
        await update.message.reply_text("You are not currently connected to any user.")
        return

    user_id = rec["current_user_id"]
    user = get_user(data, user_id)

    rec["available"] = True
    rec["manually_busy"] = False
    rec["current_user_id"] = None
    user["counselor_id"] = None
    save_data(data)

    await update.message.reply_text("Session ended. You are now available for new users.")

    try:
        await context.bot.send_message(
            chat_id=user_id,
            text=user_str(data, user_id, "session_ended_by_counselor"),
        )
    except Exception as e:
        logger.warning("Could not notify user %s: %s", user_id, e)


async def set_available(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    uid = update.effective_user.id
    if not is_counselor(uid):
        await update.message.reply_text(COUNSELOR_ONLY_MSG)
        return

    data = load_data()
    rec = get_counselor(data, uid)
    rec["manually_busy"] = False
    if rec["current_user_id"] is None:
        rec["available"] = True
    save_data(data)
    await update.message.reply_text("✅ You are now available and will receive new users.")


async def set_busy(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    uid = update.effective_user.id
    if not is_counselor(uid):
        await update.message.reply_text(COUNSELOR_ONLY_MSG)
        return

    data = load_data()
    rec = get_counselor(data, uid)
    rec["manually_busy"] = True
    rec["available"] = False
    save_data(data)
    await update.message.reply_text(
        "🔴 You are now set as busy. You won't receive new users until you use /set_available.\n"
        "(Any active session continues normally.)"
    )


# ─── MESSAGE FORWARDING ────────────────────────────────────────────────────────

async def forward_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    sender_id = update.effective_user.id
    text = update.message.text
    data = load_data()

    # ── Counselor → User ──
    if is_counselor(sender_id):
        rec = get_counselor(data, sender_id)
        user_id = rec.get("current_user_id")
        if user_id is None:
            await update.message.reply_text("You are not connected to any user right now.")
            return

        try:
            await context.bot.send_message(chat_id=user_id, text=text)
            append_user_history(data, user_id, "Counselor", text)
            append_counselor_history(data, sender_id, "You", text)
            save_data(data)
            await update.message.reply_text("✅ Message sent to user.")
        except Exception as e:
            logger.error("Failed to forward counselor→user (%s): %s", user_id, e)
            await update.message.reply_text("⚠️ Could not deliver your message to the user.")
        return

    # ── User → Counselor ──
    user = get_user(data, sender_id)
    if not user["registered"]:
        await update.message.reply_text("Please send /start to register before using the bot.")
        return

    cid = user.get("counselor_id")
    if cid is None:
        await update.message.reply_text(
            "You are not connected to a counselor. Use /connect to start a session."
        )
        return

    try:
        # Append language tag when user prefers Amharic so counselor is aware
        await context.bot.send_message(chat_id=cid, text=text)
        append_user_history(data, sender_id, "You", text)
        append_counselor_history(data, cid, "User", text)
        save_data(data)
    except Exception as e:
        logger.error("Failed to forward user→counselor (%s): %s", cid, e)
        await update.message.reply_text("⚠️ Could not deliver your message to the counselor.")


# ─── CANCEL ────────────────────────────────────────────────────────────────────

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Operation cancelled.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END


# ─── MAIN ──────────────────────────────────────────────────────────────────────

def main() -> None:
    app = Application.builder().token(BOT_TOKEN).build()

    # Registration conversation (/start)
    reg_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            REG_SEX:         [MessageHandler(filters.Regex("^(Male|Female)$"), reg_sex)],
            REG_LANG:        [MessageHandler(filters.Regex("^(Amharic|English)$"), reg_lang)],
            COUNSELOR_SEX:   [MessageHandler(filters.Regex("^(Male|Female)$"), counselor_reg_sex)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True,
    )

    # Connect conversation (/connect)
    connect_handler = ConversationHandler(
        entry_points=[CommandHandler("connect", connect)],
        states={
            CONNECT_TOPIC: [MessageHandler(filters.TEXT & ~filters.COMMAND, connect_topic)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True,
    )

    app.add_handler(reg_handler)
    app.add_handler(connect_handler)

    # Shared command (role-aware inside the handler)
    app.add_handler(CommandHandler("help", help_command))

    # User-only commands
    app.add_handler(CommandHandler("stop_counseling", stop_counseling))
    app.add_handler(CommandHandler("chat_history",    chat_history))

    # Counselor-only commands
    app.add_handler(CommandHandler("status",        counselor_status))
    app.add_handler(CommandHandler("history",       counselor_history))
    app.add_handler(CommandHandler("disconnect",    counselor_disconnect))
    app.add_handler(CommandHandler("set_available", set_available))
    app.add_handler(CommandHandler("set_busy",      set_busy))

    # Plain text forwarding — lowest priority, handles all non-command messages
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, forward_message))

    logger.info("Bot is running...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()