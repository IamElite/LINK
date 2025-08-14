import os, re, base64, asyncio, time
from dotenv import load_dotenv
from pyrogram import Client, filters, enums, idle
from pyrogram.handlers import ChatJoinRequestHandler
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message, ChatJoinRequest
from pyrogram.errors import PeerIdInvalid

# --- DB + tools ---
try:
    from database import Database
except ImportError:
    print("FATAL: 'database.py' not found.")
    exit()

try:
    from tools import handle_stats, handle_broadcast, set_approve_delay, reset_delay
except ImportError:
    print("WARNING: tools.py missing — certain commands disabled.")
    async def handle_stats(*a, **k): pass
    async def handle_broadcast(*a, **k): pass
    async def set_approve_delay(*a, **k): pass
    async def reset_delay(*a, **k): pass

# --- Load env ---
load_dotenv()
API_ID       = int(os.getenv("API_ID", "0"))
API_HASH     = os.getenv("API_HASH", "")
BOT_TOKEN    = os.getenv("BOT_TOKEN", "")
OWNER_ID     = int(os.getenv("OWNER_ID", "0"))
MONGO_URL    = os.getenv("MONGO_URL", "")
LOGGER_ID    = int(os.getenv("LOGGER_ID", "0"))

# --- Admins ---
ADMINS = []
for x in os.getenv("ADMINS", str(OWNER_ID)).split():
    if x.isdigit():
        ADMINS.append(int(x))
ADMINS.append(OWNER_ID)

# --- Init ---
db = Database(MONGO_URL)
bot_start_time = time.time()
app = Client("link_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
app.db = db

# --- Logger resolver (numeric only) ---
_logger_chat_id_cache = None
async def get_logger_chat_id(client: Client) -> int:
    """Force-resolve LOGGER_ID so restart doesn't trigger PeerIdInvalid."""
    global _logger_chat_id_cache
    if _logger_chat_id_cache:
        return _logger_chat_id_cache
    chat = await client.get_chat(LOGGER_ID)
    _logger_chat_id_cache = chat.id
    return _logger_chat_id_cache

# --- Helpers ---
def generate_encoded_string(msg_id: int) -> str:
    raw_str = f"get-{msg_id}"
    return base64.urlsafe_b64encode(raw_str.encode()).decode().rstrip("=")

async def decode_encoded_string(encoded_str: str) -> int:
    padding = "=" * (4 - len(encoded_str) % 4)
    decoded_str = base64.urlsafe_b64decode(encoded_str + padding).decode()
    if not decoded_str.startswith("get-"):
        raise ValueError("Invalid encoded format.")
    return int(decoded_str.split("-")[1])

def normalize_url(raw: str) -> str:
    raw = (raw or "").strip()
    if raw.startswith(("http://", "https://", "tg://")): return raw
    if raw.startswith("@"): return f"https://t.me/{raw[1:]}"
    if re.fullmatch(r"[A-Za-z0-9_]{3,}", raw): return f"https://t.me/{raw}"
    return raw

def parse_link_and_caption(text: str):
    text = (text or "").strip()
    if not text: return "", "Content Unlocked!"
    if "\n" in text:
        first, rest = text.split("\n", 1)
        return normalize_url(first.strip()), rest.strip() or "Content Unlocked!"
    parts = text.split(maxsplit=1)
    return normalize_url(parts[0]), (parts[1].strip() if len(parts) > 1 else "Content Unlocked!")

# --- Handlers ---
@app.on_message(filters.command("start"))
async def start_handler(client, message: Message):
    user_id = message.from_user.id
    mention = f"[{message.from_user.first_name}](tg://user?id={user_id})"

    if len(message.command) < 2:
        txt = (
            f"👋 **Welcome, Admin {mention}!**\n\nSend `<url>` then new line `<caption>`"
            if user_id in ADMINS else f"👋 **Welcome, {mention}!**\n\nMy Father - @DshDm_bot"
        )
        await message.reply(txt, parse_mode=enums.ParseMode.MARKDOWN)
    else:
        try:
            msg_id = await decode_encoded_string(re.sub(r"[^\w\-]", "", message.command[1]))
            msg = await client.get_messages(await get_logger_chat_id(client), msg_id)
            if not msg or not msg.text: raise ValueError("No content found")
            if "||" in msg.text:
                link, caption = [x.strip() for x in msg.text.split("||", 1)]
            else:
                link, caption = parse_link_and_caption(msg.text)
            await message.reply(
                f"🔓 **{caption}**",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Your Link", url=normalize_url(link))]]),
                protect_content=True, parse_mode=enums.ParseMode.MARKDOWN
            )
        except Exception:
            await message.reply("❌ This link is invalid or has expired.")

    try:
        await client.send_message(await get_logger_chat_id(client), f"Bot started by: {mention}")
    except Exception as e:
        print(f"Log fail: {e}")

    if not await db.present_user(user_id):
        await db.add_user(user_id, message.from_user.username, message.from_user.first_name)
    else:
        await db.update_user_last_seen(user_id)
    if message.chat.type != enums.ChatType.PRIVATE:
        await db.create_channel(message.chat.id, message.chat.title, message.chat.username)

@app.on_message(filters.private & filters.command("stats") & filters.user(ADMINS))
async def stats_handler_cmd(c, m): await handle_stats(c, m, db, bot_start_time)

@app.on_message(filters.private & filters.command("broadcast") & filters.user(ADMINS))
async def broadcast_handler(c, m): await handle_broadcast(c, m, db)

def join_request_callback(c, u: ChatJoinRequest):
    if getattr(u, "deleted", False):
        c.loop.create_task(handle_deleted_request(c, u))
    else:
        c.loop.create_task(handle_join_request(c, u))
app.add_handler(ChatJoinRequestHandler(join_request_callback))

@app.on_message(filters.command(["settime", "st"]) & filters.user(ADMINS))
async def set_delay_handler(c, m): await set_approve_delay(c, m)

@app.on_message(filters.command(["d", "default"]) & filters.user(ADMINS))
async def reset_delay_handler(c, m): await reset_delay(c, m)

@app.on_message(filters.private & filters.user(ADMINS))
async def owner_handler(client, message: Message):
    if message.text and message.text.startswith("/"): return
    try:
        log_chat_id = await get_logger_chat_id(client)
    except Exception as e:
        await message.reply(f"❌ Logger not configured: {e}")
        return

    if message.forward_from_chat and message.forward_from_chat.id == log_chat_id:
        msg_id = message.forward_from_message_id
        original_content = (await client.get_messages(log_chat_id, msg_id)).text or ""
    elif message.text:
        link, caption = parse_link_and_caption(message.text)
        if not link:
            await message.reply("❌ Send valid `<url>` then new line `<caption>`")
            return
        try:
            log_msg = await client.send_message(log_chat_id, f"{link}||{caption}")
            msg_id = log_msg.id
            original_content = f"{link}||{caption}"
        except PeerIdInvalid:
            await message.reply("❌ Logger chat not reachable.")
            return
        except Exception as e:
            await message.reply(f"❌ Error saving content: {e}")
            return
    else:
        await message.reply("❌ Send `<url>` + caption or forward from logger.")
        return

    bot_link = f"https://t.me/{(await app.get_me()).username}?start={generate_encoded_string(msg_id)}"
    await message.reply(
        f"✅ **Secure Link Created!**\n\n{bot_link}",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔁 Share URL", url=f"https://telegram.me/share/url?url={bot_link}")]]),
        parse_mode=enums.ParseMode.MARKDOWN
    )
    await db.create_link(original_content, message.from_user.id)

# --- Main ---
if __name__ == "__main__":
    print("🚀 Starting bot...")
    app.start()
    try:
        asyncio.get_event_loop().run_until_complete(get_logger_chat_id(app))
        me = asyncio.get_event_loop().run_until_complete(app.get_me())
        try:
            asyncio.get_event_loop().run_until_complete(app.send_message(OWNER_ID, "✅ Bot started!"))
        except Exception as e:
            print(f"Startup notify fail: {e}")
        print(f"🤖 Bot @{me.username} is running.")
    except Exception as e:
        print(f"❌ Startup error: {e}")
    idle()
    print("🛑 Bot stopped.")
