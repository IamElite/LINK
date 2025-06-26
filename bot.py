
import os, re, base64, asyncio, time
from dotenv import load_dotenv
from pyrogram import Client, filters, enums, idle
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message
from pyrogram.errors import PeerIdInvalid

# --- Dependency Handling ---
try:
    from database import Database
except ImportError:
    # This allows the bot to run even if database.py is missing, though with limited functionality.
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

API_ID = int(os.getenv("API_ID", "0").strip())
API_HASH = os.getenv("API_HASH", "").strip()
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
OWNER_ID = int(os.getenv("OWNER_ID", "0").strip())
MONGO_URL = os.getenv("MONGO_URL", "").strip()
LOGGER_ID = int(os.getenv("LOGGER_ID", "0").strip())

# --- Initialization ---
db = Database(MONGO_URL)
bot_start_time = time.time()
app = Client("link_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# --- Helper Functions ---

def generate_encoded_string(msg_id: int) -> str:
    """Generate a Base64 encoded string from a message ID and the logger ID."""
    raw_str = f"get-{msg_id * abs(LOGGER_ID)}"
    return base64.urlsafe_b64encode(raw_str.encode()).decode().rstrip("=")

async def decode_encoded_string(encoded_str: str) -> int:
    """Decode the Base64 string to get the original message ID."""
    # Add padding if it's missing
    padding = "=" * (4 - len(encoded_str) % 4)
    decoded_str = base64.urlsafe_b64decode(encoded_str + padding).decode()
    
    if not decoded_str.startswith("get-"):
        raise ValueError("Invalid encoded format.")
        
    number = int(decoded_str.split("-")[1])
    return number // abs(LOGGER_ID)

# --- Command Handlers ---

@app.on_message(filters.command("start"))
async def handle_start(client: Client, message: Message):
    """Handles the /start command, processes encoded links, and logs user activity."""
    user_id = message.from_user.id
    
    # Update user and group stats in the database
    await db.create_user(user_id, message.from_user.username, message.from_user.first_name)
    await db.update_user_last_seen(user_id)
    if message.chat.type != enums.ChatType.PRIVATE:
        await db.create_channel(message.chat.id, message.chat.title, message.chat.username)

    # Log the start event to the logger channel
    identifier = f"User {user_id}" if message.from_user else f"Chat {message.chat.id}"
    try:
        await client.send_message(LOGGER_ID, f"Bot started by: {identifier}")
    except (ValueError, PeerIdInvalid):
        print(f"CRITICAL: Could not log to LOGGER_ID {LOGGER_ID}. Is the bot an admin there?")
    
    # Process start command parameter
    if len(message.command) < 2:
        await message.reply("👋 Welcome! Please use a link provided by the bot owner.")
        return

    encoded_str = re.sub(r'[^\w\-]', '', message.command[1])
    try:
        msg_id = await decode_encoded_string(encoded_str)
        msg = await client.get_messages(LOGGER_ID, msg_id)
        
        if not msg.text:
            raise ValueError("Message has no text.")

        link = msg.text
        link_button = InlineKeyboardButton(
            "your link",
            url=link if link.startswith("http") else f"https://t.me/{link.lstrip('@')}"
        )
        await message.reply(
            "🔒 protected link:",
            reply_markup=InlineKeyboardMarkup([[link_button]]),
            protect_content=True
        )

    except Exception as e:
        print(f"Error processing start link: {e}")
        await message.reply("❌ This link is invalid or has expired.")

@app.on_message(filters.command("stats") & filters.user(OWNER_ID))
async def stats_command_handler(client: Client, message: Message):
    """A wrapper for the handle_stats function from tools.py."""
    await handle_stats(client, message, db, bot_start_time)

@app.on_message(filters.private & filters.user(OWNER_ID) & ~filters.command([]))
async def handle_owner_message(client: Client, message: Message):
    """Handles messages from the owner to generate new encoded links."""
    msg_id = 0
    # Case 1: Message is forwarded from logger channel
    if message.forward_from_chat and message.forward_from_chat.id == LOGGER_ID:
        msg_id = message.forward_from_message_id
    
    # Case 2: Message is any text (including links)
    elif message.text:
        try:
            log_msg = await client.send_message(LOGGER_ID, message.text)
            msg_id = log_msg.id
        except PeerIdInvalid:
            await message.reply(
                "❌ I don't have access to the logger channel. Please:\n"
                "1. Add me to your logger channel\n"
                "2. Make sure the LOGGER_ID in your .env is correct\n"
                "3. Give me permission to send messages in the channel"
            )
            return
        except Exception as e:
            await message.reply(f"❌ Could not save message to logger channel: {e}")
            return
    
    # Invalid format
    else:
        await message.reply("❌ Invalid format. Please send text or forward a message from the logger channel.")
        return
        
    # Generate and send the encoded link
    encoded_string = generate_encoded_string(msg_id)
    bot_link = f"https://t.me/{app.me.username}?start={encoded_string}"
    share_button = InlineKeyboardButton("🔁 Share URL", url=f"https://telegram.me/share/url?url={bot_link}")
    
    await message.reply(
        f"✅ **Link Generated!**\n\n{bot_link}",
        reply_markup=InlineKeyboardMarkup([[share_button]]),
        parse_mode=enums.ParseMode.MARKDOWN
    )
    # Save the original link to the database
    original_link = (await client.get_messages(LOGGER_ID, msg_id)).text
    await db.create_link(original_link, message.from_user.id)


# --- Main Execution ---
if __name__ == "__main__":
    print("Starting the bot...")
    app.start()
    try:
        app.send_message(OWNER_ID, "✅ Bot has started successfully!")
    except Exception as e:
        print(f"⚠️ Could not send startup notification to OWNER_ID: {e}")
    print(f"🤖 Bot @{app.me.username} is now running!")
    idle()
    print("Bot stopped.")
