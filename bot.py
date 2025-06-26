
import os, re, base64, asyncio, time
from dotenv import load_dotenv
from pyrogram import Client, filters, enums, idle
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message
from pyrogram.errors import PeerIdInvalid, ChannelInvalid

# --- Dependency Handling ---
try:
    from database import Database
except ImportError:
    print("FATAL: 'database.py' not found. Please ensure it exists.")
    exit()

try:
    from tools import handle_stats
except ImportError:
    print("WARNING: 'tools.py' not found. The /stats command will not work.")
    async def handle_stats(client, message, db, bot_start_time):
        await message.reply("Stats module is missing.")

# --- Configuration ---
load_dotenv()

API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH", "")
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
OWNER_ID = int(os.getenv("OWNER_ID", "0"))
MONGO_URL = os.getenv("MONGO_URL", "")
LOGGER_ID = int(os.getenv("LOGGER_ID", "0"))

# --- Initialization ---
db = Database(MONGO_URL)
bot_start_time = time.time()
app = Client("link_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

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

# --- Command Handlers ---
@app.on_message(filters.command("start"))
async def handle_start(client: Client, message: Message):
    user_id = message.from_user.id
    
    # Update user and group stats
    await db.create_user(user_id, message.from_user.username, message.from_user.first_name)
    await db.update_user_last_seen(user_id)
    
    if message.chat.type != enums.ChatType.PRIVATE:
        await db.create_channel(message.chat.id, message.chat.title, message.chat.username)

    # Log start event
    identifier = f"User {user_id}" if message.from_user else f"Chat {message.chat.id}"
    try:
        await client.send_message(LOGGER_ID, f"Bot started by: {identifier}")
    except:
        print(f"WARNING: Could not log to LOGGER_ID {LOGGER_ID}")

    # Process start parameter
    if len(message.command) < 2:
        await message.reply("👋 Welcome! Send me any link to store it securely.")
        return

    try:
        encoded_str = re.sub(r'[^\w\-]', '', message.command[1])
        msg_id = await decode_encoded_string(encoded_str)
        msg = await client.get_messages(LOGGER_ID, msg_id)
        
        if not msg.text:
            raise ValueError("No content found")

        content = msg.text
        content_button = InlineKeyboardButton(
            "Access Content",
            url=content if content.startswith("http") else f"https://t.me/{content.lstrip('@')}"
        )
        
        await message.reply(
            "🔒 Protected content:",
            reply_markup=InlineKeyboardMarkup([[content_button]]),
            protect_content=True
        )

    except Exception as e:
        print(f"Error: {e}")
        await message.reply("❌ This link is invalid or has expired.")

# Command handler without complex filters
@app.on_message(filters.private & filters.command("stats") & filters.user(OWNER_ID))
async def stats_handler(client: Client, message: Message):
    await handle_stats(client, message, db, bot_start_time)

# Simplified handler for owner messages
@app.on_message(filters.private & filters.user(OWNER_ID))
async def owner_handler(client: Client, message: Message):
    # Skip if it's a command
    if message.text and message.text.startswith('/'):
        return
    
    # Handle forwarded messages
    if message.forward_from_chat and message.forward_from_chat.id == LOGGER_ID:
        msg_id = message.forward_from_message_id
    # Handle text messages
    elif message.text:
        try:
            log_msg = await client.send_message(LOGGER_ID, message.text)
            msg_id = log_msg.id
        except Exception as e:
            await message.reply(f"❌ Error saving content: {e}")
            return
    else:
        await message.reply("❌ Please send text content or forward a message")
        return

    # Generate shareable link
    encoded_string = generate_encoded_string(msg_id)
    bot_link = f"https://t.me/{app.me.username}?start={encoded_string}"
    share_button = InlineKeyboardButton("🔁 Share URL", url=f"https://telegram.me/share/url?url={bot_link}")
    
    await message.reply(
        f"✅ **Secure Link Created!**\n\n"
        f"Share this link: {bot_link}",
        parse_mode=enums.ParseMode.MARKDOWN
    )
    
    # Save to database
    original_content = (await client.get_messages(LOGGER_ID, msg_id)).text
    await db.create_link(original_content, message.from_user.id)

# --- Main Execution ---
if __name__ == "__main__":
    print("🚀 Starting bot...")
    app.start()
    
    try:
        app.send_message(OWNER_ID, "✅ Bot has started successfully!")
    except Exception as e:
        print(f"⚠️ Startup notification failed: {e}")
    
    print(f"🤖 Bot @{app.me.username} is running!")
    idle()
    print("🛑 Bot stopped.")
