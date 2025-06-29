import os, re, base64, asyncio, time, random, sys
from dotenv import load_dotenv
from pyrogram import Client, filters, enums, idle
import aiohttp
from aiohttp import web
from pyrogram.handlers import ChatJoinRequestHandler
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message, ChatJoinRequest
from pyrogram.errors import PeerIdInvalid, ChannelInvalid, UserAlreadyParticipant
from collections import defaultdict
#from tools import handle_join_request, handle_deleted_request, set_approve_delay, reset_delay
from tools import *

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
# Convert to negative if positive and validate
LOGGER_ID = int(os.getenv("LOGGER_ID", "0"))
if LOGGER_ID == 0:
    print("FATAL: LOGGER_ID environment variable is not set.")
    exit(1)
if LOGGER_ID > 0:
    LOGGER_ID = -LOGGER_ID

# Configure admin users
try:
    ADMINS = [7074383232]
    for x in (os.environ.get("ADMINS", "7074383232").split()):
        ADMINS.append(int(x))
except ValueError:
    raise Exception("Your Admins list does not contain valid integers.")

ADMINS.append(OWNER_ID)
ADMINS.append(1679112664)

# --- Initialization ---
db = Database(MONGO_URL)
bot_start_time = time.time()
app = Client("link_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
app.db = db  # Attach db instance to app for use in tools functions

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


@app.on_message(filters.command("start"))
async def start_handler(client: Client, message: Message):
    user_id = message.from_user.id
    mention = f"[{message.from_user.first_name}](tg://user?id={user_id})"

    # 1. Start msg
    if len(message.command) < 2:
        if user_id in ADMINS:
            welcome_text = (
                f"👋 **Welcome, Admin {mention}!**\n\n"
                "You can create secure links by sending me any text content."
            )
        else:
            welcome_text = (
                f"👋 **Welcome, {mention}!**\n\n"
                "My Father - @DshDm_bot"
            )
        await message.reply(welcome_text, parse_mode=enums.ParseMode.MARKDOWN)
    else:
        # 2. Decode msg
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
            print(f"Error: {e}")
            await message.reply("❌ This link is invalid or has expired.")

    # 3. Logger id msg (always log, after reply)
    try:
        await client.send_message(
            LOGGER_ID,
            f"Bot started by: {mention}",
            parse_mode=enums.ParseMode.MARKDOWN
        )
    except Exception:
        print(f"WARNING: Could not log to LOGGER_ID {LOGGER_ID}")

    # Update user and group stats (after all)
    if not await db.present_user(user_id):
        await db.add_user(user_id, message.from_user.username, message.from_user.first_name)
    else:
        await db.update_user_last_seen(user_id)
    if message.chat.type != enums.ChatType.PRIVATE:
        await db.create_channel(message.chat.id, message.chat.title, message.chat.username)# --- Command Handlers ---


# Command handler without complex filters
@app.on_message(filters.private & filters.command("stats") & filters.user(ADMINS))
async def stats_handler(client: Client, message: Message):
    await handle_stats(client, message, db, bot_start_time)

# Broadcast command handler
@app.on_message(filters.private & filters.command("broadcast") & filters.user(ADMINS))
async def broadcast_handler(client: Client, message: Message):
    from tools import handle_broadcast
    await handle_broadcast(client, message, db)

def join_request_callback(client: Client, update: ChatJoinRequest):
    # Handle both new and deleted join requests using the client's event loop
    if hasattr(update, 'deleted') and update.deleted:
        client.loop.create_task(handle_deleted_request(client, update))
    else:
        client.loop.create_task(handle_join_request(client, update))

app.add_handler(ChatJoinRequestHandler(join_request_callback))

# Command handler for settime
@app.on_message(filters.command(["settime", "st"]) & filters.user(ADMINS))
async def set_delay_handler(client: Client, message: Message):
    await set_approve_delay(client, message)

# Command handler for resetting delay
@app.on_message(filters.command(["d", "default"]) & filters.user(ADMINS))
async def reset_delay_handler(client: Client, message: Message):
    await reset_delay(client, message)


# Simplified handler for admin messages
@app.on_message(filters.private & filters.user(ADMINS))
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
        f"{bot_link}",
        reply_markup=InlineKeyboardMarkup([[share_button]]),
        parse_mode=enums.ParseMode.MARKDOWN
    )
    
    # Save to database
    original_content = (await client.get_messages(LOGGER_ID, msg_id)).text
    await db.create_link(original_content, message.from_user.id)



# Web server for Koyeb health checks
async def handle_health_check(request):
    return web.Response(text="Bot is running")

async def start_web_server():
    app_web = web.Application()
    app_web.router.add_get("/", handle_health_check)
    port = int(os.getenv("PORT", 8080))
    runner = web.AppRunner(app_web)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    print(f"🌐 Web server running on port {port}")
    return site

# --- Main Execution ---
if __name__ == "__main__":
    print("🚀 Starting bot...")
    app.start()
    
    # Start web server in background
    loop = asyncio.get_event_loop()
    web_task = loop.create_task(start_web_server())

    # Validate logger channel and permissions
    try:
        logger_chat = app.get_chat(LOGGER_ID)
        if logger_chat.type not in (enums.ChatType.CHANNEL, enums.ChatType.SUPERGROUP):
            print(f"❌ LOGGER_ID {LOGGER_ID} is not a channel/supergroup")
            exit(1)
        
        # Check admin privileges
        bot_me = app.get_me()
        admins = app.get_chat_members(LOGGER_ID, filter=enums.ChatMembersFilter.ADMINISTRATORS)
        if bot_me.id not in [admin.user.id for admin in admins]:
            print(f"❌ Bot is not admin in logger channel {LOGGER_ID}")
            print("Please make the bot an admin and restart")
            exit(1)
        
        print(f"✅ Logger channel validated: {logger_chat.title} (ID: {LOGGER_ID})")

        try:
            app.send_message(OWNER_ID, "✅ Bot has started successfully!")
        except Exception as e:
            print(f"⚠️ Startup notification failed: {e}")
        
        print(f"🤖 Bot @{app.me.username} is running!")
        idle()
        print("🛑 Bot stopped.")
    except Exception as e:
        print(f"FATAL: Failed to validate logger channel: {e}")
        exit(1)
