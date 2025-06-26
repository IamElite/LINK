import os
import re
import base64
import asyncio
import time
from datetime import datetime, timedelta
from pyrogram import idle
from dotenv import load_dotenv
from pyrogram import Client, filters, enums
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message
from pyrogram.errors import PeerIdInvalid

# Assuming database.py and tools.py are in the same directory
# If they are not, you might need to adjust the import path
# For this example, we'll create placeholder classes if the files don't exist.

try:
    from database import Database
except ImportError:
    print("Warning: 'database.py' not found. Using a placeholder Database class.")
    class Database:
        def __init__(self, mongo_url):
            self.mongo_url = mongo_url
            self.users = []
            self.channels = []
            self.links = []
            self.stats = {"group_chats": 0, "users": 0}
        async def create_user(self, user_id, username, first_name):
            print(f"DB: Creating user {user_id}")
        async def update_user_last_seen(self, user_id):
            print(f"DB: Updating last seen for user {user_id}")
        async def create_channel(self, channel_id, title, username):
            print(f"DB: Creating channel {channel_id}")
            self.channels.append({"channel_id": channel_id})
        async def update_stat(self, key, value):
            print(f"DB: Updating stat {key} by {value}")
            self.stats[key] = self.stats.get(key, 0) + value
        async def create_link(self, link, owner_id):
            print(f"DB: Creating link '{link}' for owner {owner_id}")
        # Mock find_one for channel check
        async def find_one(self, query):
             class MockCollection:
                 async def find_one(self, q):
                     return next((c for c in self.channels if c['channel_id'] == q.get('channel_id')), None)
             if query == self.channels: # A bit of a hack to simulate collection access
                 return MockCollection()
             return None


try:
    from tools import handle_stats
except ImportError:
    print("Warning: 'tools.py' not found. Using a placeholder handle_stats function.")
    async def handle_stats(client, message, db, bot_start_time):
        await message.reply("Stats module not found.")


# Load environment variables
load_dotenv()

# Safely load environment variables with stripping and defaults
API_ID = int(os.getenv("API_ID", "0").strip())
API_HASH = os.getenv("API_HASH", "").strip()
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
OWNER_ID = int(os.getenv("OWNER_ID", "0").strip())
MONGO_URL = os.getenv("MONGO_URL", "").strip()
# The problematic ID is loaded here. We ensure it's stripped of any whitespace.
LOGGER_ID = int(os.getenv("LOGGER_ID", "0").strip())

# Initialize Database
db = Database(MONGO_URL)

# Statistics tracking
bot_start_time = time.time()

# Helper functions
async def get_message_id(client: Client, message: Message) -> int:
    """Extract message ID from forwarded message or link"""
    if message.forward_from_chat:
        if message.forward_from_chat.id == LOGGER_ID:
            return message.forward_from_message_id
    elif message.text:
        # Try to extract message ID from t.me link
        pattern = r"https?://t\.me/(?:c/)?([a-zA-Z0-9_]+)/(\d+)"
        match = re.search(pattern, message.text)
        if match:
            try:
                channel_username = match.group(1)
                msg_id = int(match.group(2))
                # Verify the channel is the logger channel
                chat = await client.get_chat(channel_username)
                if chat.id == LOGGER_ID:
                    return msg_id
            except Exception:
                pass
    return 0

async def encode_link(link: str, client: Client, owner_id: int) -> str:
    """Generate encoded string using logger channel ID"""
    # Send link to logger channel and get message ID
    sent_msg = await client.send_message(LOGGER_ID, link)
    msg_id = sent_msg.id
    
    # Generate encoded string using the formula
    encoded_str = f"get-{msg_id * abs(LOGGER_ID)}"
    base64_string = base64.urlsafe_b64encode(encoded_str.encode()).decode().rstrip("=")
    
    # Store link in database
    await db.create_link(link, owner_id)
    return base64_string

def generate_base64_string(msg_id: int) -> str:
    """Generate base64 string from message ID"""
    encoded_str = f"get-{msg_id * abs(LOGGER_ID)}"
    return base64.urlsafe_b64encode(encoded_str.encode()).decode().rstrip("=")

async def link_generator(client: Client, message: Message):
    """Generate shareable links from logger channel messages"""
    while True:
        try:
            # Ask for forwarded message or link
            channel_message = await client.ask(
                chat_id=message.from_user.id,
                text=(
                    "Forward a message from the logger channel (with quotes) "
                    "or send the logger channel post link"
                ),
                filters=(filters.forwarded | (filters.text & ~filters.forwarded)),
                timeout=60
            )
        except asyncio.TimeoutError:
            await message.reply("Timed out waiting for input.")
            return
        
        # Get message ID
        msg_id = await get_message_id(client, channel_message)
        if msg_id:
            try:
                # Get the message content
                msg = await client.get_messages(LOGGER_ID, msg_id)
                if not msg.text:
                    await channel_message.reply("❌ The message has no text content.")
                    continue
                    
                # Generate and return the link
                base64_string = generate_base64_string(msg_id)
                bot_link = f"https://t.me/{client.me.username}?start={base64_string}"
                reply_markup = InlineKeyboardMarkup([[
                    InlineKeyboardButton(
                        "🔁 Share URL", 
                        url=f'https://telegram.me/share/url?url={bot_link}'
                    )
                ]])
                await channel_message.reply_text(
                    f"<b>Here Is Your Link</b>\n\n{bot_link}",
                    quote=True,
                    reply_markup=reply_markup
                )
                # Store the link in database
                await db.create_link(msg.text, message.from_user.id)
                return
            except Exception as e:
                await channel_message.reply(f"❌ Error: {str(e)}")
                continue
        else:
            await channel_message.reply(
                "❌ Invalid message. Please forward a message from the logger channel "
                "or provide a valid logger channel post link.",
                quote=True
            )

async def decode_link(encoded_str: str) -> int:
    """Decode string to get original message ID"""
    # Add padding and decode
    padding = 4 - (len(encoded_str) % 4)
    if padding < 4:
        encoded_str += "=" * padding
    decoded_str = base64.urlsafe_b64decode(encoded_str).decode()
    
    # Extract message ID using the formula
    if not decoded_str.startswith("get-"):
        raise ValueError("Invalid encoded format")
    number = int(decoded_str.split("-")[1])
    return number // abs(LOGGER_ID)


# Initialize Pyrogram client
app = Client("link_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)


def is_valid_link(link: str) -> bool:
    """Check if the link is a valid Telegram entity"""
    patterns = [
        r"^https?://t\.me/[a-zA-Z0-9_]+$",
        r"^@[a-zA-Z0-9_]+$",
        r"^https?://t\.me/s/[a-zA-Z0-9_]+$",
        r"^https?://telegram\.me/[a-zA-Z0-9_]+$",
        r"^https?://telegram\.dog/[a-zA-Z0-9_]+$"
    ]
    return any(re.match(pattern, link) for pattern in patterns)

# Owner command handler with input sanitization
@app.on_message(filters.user(OWNER_ID) & ~filters.command("start"))
async def handle_owner_link(client, message):
    # Handle forwarded messages separately
    if message.forward_from or message.forward_from_chat:
        # Start the link generator for forwarded messages
        await link_generator(client, message)
        return
        
    # Sanitize input
    link = re.sub(r'[^\w@.:/-]', '', message.text.strip())
    
    if not is_valid_link(link):
        await message.reply("❌ Invalid link format. Please send a valid Telegram entity link in one of these formats:\n\n"
                            "- @username\n"
                            "- https://t.me/username\n"
                            "- https://t.me/s/channelname\n"
                            "- https://telegram.me/username")
        return
    
    # Encode and store link
    try:
        owner_id = message.from_user.id if message.from_user else 0
        base64_string = await encode_link(link, client, owner_id)
        # Create user if not exists
        if message.from_user:
            await db.create_user(
                message.from_user.id,
                message.from_user.username,
                message.from_user.first_name
            )
    except Exception as e:
        await message.reply(f"❌ Error storing link: {str(e)}")
        return
    
    # Generate bot link
    bot_link = f"https://t.me/{client.me.username}?start={base64_string}"
    
    # Create share button
    share_button = InlineKeyboardButton(
        "🔁 Share URL",
        url=f"https://telegram.me/share/url?url={bot_link}"
    )
    
    await message.reply(
        f"✅ Link stored!\n\nBot link: `{bot_link}`",
        reply_markup=InlineKeyboardMarkup([[share_button]]),
        parse_mode=enums.ParseMode.MARKDOWN
    )

# Start command handler with logging and statistics
@app.on_message(filters.command("start"))
async def handle_start(client, message):
    # Update user statistics
    if message.from_user:
        # Create user if not exists
        await db.create_user(
            message.from_user.id,
            message.from_user.username,
            message.from_user.first_name
        )
        # Update last seen
        await db.update_user_last_seen(message.from_user.id)
    
    # Update group statistics (only if not a private chat)
    if message.chat.type in [enums.ChatType.GROUP, enums.ChatType.SUPERGROUP]:
        # Check if this group is already in the database
        existing = await db.channels.find_one({"channel_id": message.chat.id})
        if not existing:
            # Create new group record
            await db.create_channel(
                message.chat.id,
                message.chat.title,
                message.chat.username
            )
            # Increment group stat only for new groups
            await db.update_stat("group_chats", 1)
    
    # Log start event
    identifier = f"User {message.from_user.id}" if message.from_user else f"Group {message.chat.id}"
    
    # --- FIX STARTS HERE ---
    # This try-except block will catch the 'Peer id invalid' error and prevent the bot from crashing.
    try:
        await client.send_message(LOGGER_ID, f"{identifier} started the bot")
    except ValueError as e:
        # This error happens if the bot cannot resolve the LOGGER_ID.
        # It's almost always because the bot is not in the channel or not an admin.
        print(f"CRITICAL ERROR: Could not send log message to LOGGER_ID: {LOGGER_ID}.")
        print(f"Error details: {e}")
        print("ACTION REQUIRED: This is likely because the bot is not an admin in the logger channel.")
        print("Please add the bot to the logger channel with admin rights to send messages.")
    except PeerIdInvalid:
        # This is a more specific Pyrogram error for the same issue.
        print(f"CRITICAL ERROR: PeerIdInvalid for LOGGER_ID: {LOGGER_ID}.")
        print("ACTION REQUIRED: Please ensure the bot is a member of the logger channel and the ID is correct.")
    except Exception as e:
        # Catch any other unexpected errors during logging.
        print(f"An unexpected error occurred when sending a log message: {e}")
    # --- FIX ENDS HERE ---

    # Check if start command has parameter
    if len(message.command) < 2:
        await message.reply("👋 Welcome! Use the link provided by the bot owner.")
        return
    
    # Sanitize input
    encoded_str = re.sub(r'[^\w\-]', '', message.command[1])
    
    try:
        msg_id = await decode_link(encoded_str)
    except Exception as e:
        print(f"⚠️ ID decoding error: {str(e)}")
        await message.reply("⚠️ Invalid link format.")
        return
    
    # Fetch link from logger channel
    try:
        msg = await client.get_messages(LOGGER_ID, msg_id)
        if not msg.text or not is_valid_link(msg.text):
            await message.reply("❌ Link not found or invalid.")
            return
        link = msg.text
    except Exception as e:
        print(f"⚠️ Error fetching message: {str(e)}")
        await message.reply("❌ Link not found. It may have expired.")
        return
    
    # Create button to open the link
    link_button = InlineKeyboardButton(
        "Here’s your link",
        url=link if link.startswith("http") else f"https://t.me/{link[1:]}"
    )
    
    await message.reply(
        "🔒 Protected link:",
        reply_markup=InlineKeyboardMarkup([[link_button]]),
        protect_content=True
    )

# Stats command handler
@app.on_message(filters.command("stats") & filters.user(OWNER_ID))
async def stats_handler(client, message):
    await handle_stats(client, message, db, bot_start_time)

# Start the bot with notification
print("Bot starting...")
app.start()

try:
    # Send startup notification (Pyrogram will handle peer resolution)
    app.send_message(OWNER_ID, "🤖 Bot started successfully!")
except Exception as e:
    print(f"⚠️ Failed to send startup notification: {str(e)}")
    print("Ensure OWNER_ID and LOGGER_ID are valid and accessible to the bot")
    print(f"OWNER_ID: {OWNER_ID}, LOGGER_ID: {LOGGER_ID}")

print("Bot is now running!")
idle()

print("Bot stopped.")
