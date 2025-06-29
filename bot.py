import os, re, base64, asyncio, time, random, sys, logging, threading
from dotenv import load_dotenv
from pyrogram import Client, filters, enums, idle
from pyrogram.handlers import ChatJoinRequestHandler
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message, ChatJoinRequest
from pyrogram.errors import PeerIdInvalid, ChannelInvalid, UserAlreadyParticipant
from flask import Flask

# --- Logging Setup ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Environment Variables ---
load_dotenv()

API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH", "")
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
OWNER_ID = int(os.getenv("OWNER_ID", "0"))
MONGO_URL = os.getenv("MONGO_URL", "")
LOGGER_ID = int(os.getenv("LOGGER_ID", "0"))

# Validate LOGGER_ID
if LOGGER_ID == 0:
    logger.error("FATAL: LOGGER_ID environment variable is not set.")
    exit(1)
if LOGGER_ID > 0:
    LOGGER_ID = -LOGGER_ID

# Load ADMINS
ADMINS = [int(admin) for admin in os.getenv("ADMINS", "").split()] + [OWNER_ID, 1679112664]

# --- Bot Initialization ---
try:
    from database import Database
    db = Database(MONGO_URL)
except ImportError:
    logger.error("FATAL: 'database.py' not found.")
    exit(1)

app = Client("link_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
app.db = db
bot_start_time = time.time()

# --- Flask Server for Health Check ---
flask_app = Flask(__name__)

@flask_app.route('/')
@flask_app.route('/health')
def home():
    logger.info("Health check accessed")
    return "Bot is running"

def run_flask():
    port = int(os.getenv("PORT", 8000))
    logger.info(f"Starting Flask server on port {port}")
    flask_app.run(host="0.0.0.0", port=port)

# --- Helper Functions ---
def generate_encoded_string(msg_id: int) -> str:
    raw_str = f"get-{msg_id * abs(LOGGER_ID)}"
    return base64.urlsafe_b64encode(raw_str.encode()).decode().rstrip("=")

async def decode_encoded_string(encoded_str: str) -> int:
    padding = "=" * (4 - len(encoded_str) % 4)
    decoded_str = base64.urlsafe_b64decode(encoded_str + padding).decode()
    if not decoded_str.startswith("get-"):
        raise ValueError("Invalid encoded format.")
    return int(decoded_str.split("-")[1]) // abs(LOGGER_ID)

# --- LOGGER_ID Validation ---
async def is_logger_id_valid(client: Client):
    try:
        await client.get_chat(LOGGER_ID)
        return True
    except (PeerIdInvalid, ChannelInvalid):
        logger.error(f"Invalid LOGGER_ID: {LOGGER_ID}")
        return False

# --- Command Handlers ---
@app.on_message(filters.command("start"))
async def start_handler(client: Client, message: Message):
    user_id = message.from_user.id
    mention = f"[{message.from_user.first_name}](tg://user?id={user_id})"
    if len(message.command) < 2:
        welcome_text = f"👋 **Welcome, {'Admin ' if user_id in ADMINS else ''}{mention}!**\n\n" + \
                       ("You can create secure links." if user_id in ADMINS else "My Father - @DshDm_bot")
        await message.reply(welcome_text, parse_mode=enums.ParseMode.MARKDOWN)
    else:
        try:
            encoded_str = re.sub(r'[^\w\-]', '', message.command[1])
            msg_id = await decode_encoded_string(encoded_str)
            msg = await client.get_messages(LOGGER_ID, msg_id)
            if not msg.text:
                raise ValueError("No content found")
            content = msg.text
            content_button = InlineKeyboardButton(
                "Your Link",
                url=content if content.startswith("http") else f"https://t.me/{content.lstrip('@')}"
            )
            await message.reply(
                f"🔓 **Content Unlocked!**",
                reply_markup=InlineKeyboardMarkup([[content_button]]),
                protect_content=True,
                parse_mode=enums.ParseMode.MARKDOWN
            )
        except Exception as e:
            logger.error(f"Error in start_handler: {e}")
            await message.reply("❌ This link is invalid or has expired.")

    if await is_logger_id_valid(client):
        try:
            await client.send_message(LOGGER_ID, f"Bot started by: {mention}", parse_mode=enums.ParseMode.MARKDOWN)
        except Exception as e:
            logger.warning(f"Could not log to LOGGER_ID {LOGGER_ID}: {e}")

    if not await db.present_user(user_id):
        await db.add_user(user_id, message.from_user.username, message.from_user.first_name)
    else:
        await db.update_user_last_seen(user_id)
    if message.chat.type != enums.ChatType.PRIVATE:
        await db.create_channel(message.chat.id, message.chat.title, message.chat.username)

# --- Main Execution ---
if __name__ == "__main__":
    print("🚀 Starting bot...")
    app.start()
    
    # Start Flask server in a separate thread
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.start()

    try:
        logger_chat = app.get_chat(LOGGER_ID)
        if logger_chat.type not in (enums.ChatType.CHANNEL, enums.ChatType.SUPERGROUP):
            logger.error(f"❌ LOGGER_ID {LOGGER_ID} is not a channel/supergroup")
            exit(1)
        bot_me = app.get_me()
        admins = app.get_chat_members(LOGGER_ID, filter=enums.ChatMembersFilter.ADMINISTRATORS)
        if not any(admin.user.id == bot_me.id for admin in admins):
            logger.error(f"❌ Bot is not admin in logger channel {LOGGER_ID}")
            exit(1)
        logger.info(f"✅ Logger channel validated: {logger_chat.title} (ID: {LOGGER_ID})")
        try:
            app.send_message(OWNER_ID, "✅ Bot has started successfully!")
        except Exception as e:
            logger.warning(f"Startup notification failed: {e}")
        print(f"🤖 Bot @{app.me.username} is running!")
        idle()
        print("🛑 Bot stopped.")
    except Exception as e:
        logger.error(f"FATAL: Failed to validate logger channel: {e}")
        exit(1)
