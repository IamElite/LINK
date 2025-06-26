import os, re, base64, asyncio, time
from dotenv import load_dotenv
from pyrogram import Client, filters, enums, idle
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message
from pyrogram.errors import PeerIdInvalid

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

load_dotenv()

API_ID = int(os.getenv("API_ID", "0").strip())
API_HASH = os.getenv("API_HASH", "").strip()
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
OWNER_ID = int(os.getenv("OWNER_ID", "0").strip())
MONGO_URL = os.getenv("MONGO_URL", "").strip()
LOGGER_ID = int(os.getenv("LOGGER_ID", "0").strip()) 

db = Database(MONGO_URL)
bot_start_time = time.time()
app = Client("link_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

def generate_encoded_string(msg_id: int) -> str:
    raw_str = f"get-{msg_id * abs(LOGGER_ID)}"
    return base64.urlsafe_b64encode(raw_str.encode()).decode().rstrip("=")

async def decode_encoded_string(encoded_str: str) -> int:
    padding = "=" * (4 - len(encoded_str) % 4)
    decoded_str = base64.urlsafe_b64decode(encoded_str + padding).decode()
    
    if not decoded_str.startswith("get-"):
        raise ValueError("Invalid encoded format.")
        
    number = int(decoded_str.split("-")[1])
    return number // abs(LOGGER_ID)

@app.on_message(filters.command("start"))
async def handle_start(client: Client, message: Message):
    user_id = message.from_user.id
    
    await db.create_user(user_id, message.from_user.username, message.from_user.first_name)
    await db.update_user_last_seen(user_id)
    if message.chat.type != enums.ChatType.PRIVATE:
        await db.create_channel(message.chat.id, message.chat.title, message.chat.username)

    identifier = f"User {user_id} (@{message.from_user.username or 'N/A'})" if message.from_user else f"Chat {message.chat.id} ({message.chat.title or 'N/A'})"
    try:
        await client.send_message(LOGGER_ID, f"Bot started by: {identifier} from chat {message.chat.id} (Type: {message.chat.type.name})")
    except (ValueError, PeerIdInvalid) as e:
        print(f"CRITICAL: Could not log to LOGGER_ID {LOGGER_ID}. Error: {e}. Please ensure the bot is an admin there and the ID is correct.")
    
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
            "Click here for your link",
            url=link if link.startswith("http") else f"https://t.me/{link.lstrip('@')}"
        )
        await message.reply(
            "🔒 Protected link (Content protection enabled):\n",
            reply_markup=InlineKeyboardMarkup([[link_button]]),
            protect_content=True
        )

    except Exception as e:
        print(f"Error processing start link: {e}")
        await message.reply("❌ This link is invalid or has expired.")

@app.on_message(filters.command("stats") & filters.user(OWNER_ID))
async def stats_command_handler(client: Client, message: Message):
    await handle_stats(client, message, db, bot_start_time)

@app.on_message(filters.private & filters.user(OWNER_ID) & ~filters.command([]))
async def handle_owner_message(client: Client, message: Message):
    msg_id = 0
    if message.forward_from_chat and message.forward_from_chat.id == LOGGER_ID:
        msg_id = message.forward_from_message_id
    
    elif message.text:
        try:
            log_msg = await client.send_message(LOGGER_ID, message.text)
            msg_id = log_msg.id
        except Exception as e:
            await message.reply(f"❌ Could not save message to logger channel: {e}. Please check LOGGER_ID and bot's admin status in the channel.")
            return
    
    else:
        await message.reply("❌ Invalid format. Please send text or forward a message from the logger channel.")
        return
        
    encoded_string = generate_encoded_string(msg_id)
    bot_link = f"https://t.me/{app.me.username}?start={encoded_string}"
    share_button = InlineKeyboardButton("🔁 Share URL", url=f"https://telegram.me/share/url?url={bot_link}")
    
    await message.reply(
        f"✅ **Link Generated!**\n\n`{bot_link}`",
        reply_markup=InlineKeyboardMarkup([[share_button]]),
        parse_mode=enums.ParseMode.MARKDOWN
    )
    if message.text:
        original_link = message.text
    else:
        try:
            original_link = (await client.get_messages(LOGGER_ID, msg_id)).text
        except Exception as e:
            print(f"WARNING: Could not fetch original link content from LOGGER_ID for saving: {e}")
            original_link = "N/A"

    await db.create_link(original_link, message.from_user.id)

if __name__ == "__main__":
    print("Starting the bot...")
    app.start()
    try:
        app.send_message(OWNER_ID, "✅ Bot has started successfully!")
    except Exception as e:
        print(f"⚠️ Could not send startup notification to OWNER_ID {OWNER_ID}: {e}. Please ensure OWNER_ID is correct and bot can send messages to them.")
    print(f"🤖 Bot @{app.me.username} is now running!")
    idle()
    print("Bot stopped.")
