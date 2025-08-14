import os, re, base64, asyncio, time, random
from dotenv import load_dotenv
from pyrogram import Client, filters, enums, idle
from pyrogram.handlers import ChatJoinRequestHandler
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message, ChatJoinRequest
from pyrogram.errors import PeerIdInvalid, ChannelInvalid, UserAlreadyParticipant, BadRequest # Import BadRequest
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
LOGGER_ID = int(os.getenv("LOGGER_ID", "0")) # This should be the correct numeric ID

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

# --- Helper Function to determine button URL ---
def get_button_url(content: str) -> str:
    """Determines the correct URL for the inline button."""
    if content.startswith("http"):
        return content # Already a full URL
    elif content.startswith("@"):
        # Username starting with @
        return f"https://t.me/{content.lstrip('@')}"
    else:
        # Assume it's a username without @
        return f"https://t.me/{content}"
    # Add more conditions if needed for other content types

# --- Startup Hook ---
@app.on_message(filters.command("forcesubscribe") & filters.user(ADMINS)) # Dummy filter, just need the hook
async def on_startup(client: Client):
    """Runs once when the bot starts."""
    print("Bot started. Attempting to resolve LOGGER_ID peer...")
    try:
        # Force Pyrogram to resolve and cache the LOGGER_ID peer
        await client.get_chat(LOGGER_ID)
        print(f"Successfully resolved LOGGER_ID: {LOGGER_ID}")
    except PeerIdInvalid:
        print(f"CRITICAL ERROR: Cannot resolve LOGGER_ID {LOGGER_ID}. Please check the ID and ensure the bot is a member/admin.")
        # Optionally, you could raise an exception here to stop the bot
        # raise
    except Exception as e:
        print(f"Warning: Error resolving LOGGER_ID {LOGGER_ID}: {e}")

# --- Command Handlers ---

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
            # Ensure peer is resolved before fetching message
            await client.get_chat(LOGGER_ID)
            msg = await client.get_messages(LOGGER_ID, msg_id)
            if not msg.text:
                raise ValueError("No content found")

            # --- Modified Part: Parse content and caption ---
            lines = msg.text.splitlines()
            if len(lines) >= 2:
                content = lines[0].strip() # Strip whitespace from content
                custom_caption = '\n'.join(lines[1:]).strip() # Join remaining lines as caption and strip
            else:
                content = msg.text.strip() # Strip if only one line
                custom_caption = "Content Unlocked!" # Default caption

            # --- Determine the button URL ---
            button_url = get_button_url(content)

            # --- Create Button ---
            content_button = InlineKeyboardButton(
                "Your Link", # Button text remains fixed
                url=button_url # Use the determined URL
            )

            # --- Send Reply ---
            await message.reply(
                f"🔓 **{custom_caption}**", # Use custom or default caption
                reply_markup=InlineKeyboardMarkup([[content_button]]),
                protect_content=True,
                parse_mode=enums.ParseMode.MARKDOWN
            )
        except PeerIdInvalid:
             print(f"Error: PeerIdInvalid when trying to access LOGGER_ID {LOGGER_ID} in /start. Ensure bot is admin/member.")
             await message.reply("❌ Sorry, there seems to be a configuration issue with the content storage. Please contact the admin.")
        except BadRequest as e: # Catch specific Telegram API errors
            if "BUTTON_URL_INVALID" in str(e):
                 print(f"Error creating button for content '{content}': {e}")
                 await message.reply("❌ Sorry, the link associated with this code seems to be invalid or cannot be used to create a button.")
            else:
                 raise # Re-raise if it's a different BadRequest
        except Exception as e:
            print(f"Error in /start: {e}")
            await message.reply("❌ This link is invalid or has expired.")

    # 3. Logger id msg (always log, after reply)
    try:
        # Ensure peer is resolved before logging
        await client.get_chat(LOGGER_ID)
        await client.send_message(
            LOGGER_ID,
            f"Bot started by: {mention}",
            parse_mode=enums.ParseMode.MARKDOWN
        )
    except PeerIdInvalid:
         print(f"WARNING: Could not log to LOGGER_ID {LOGGER_ID} - PeerIdInvalid. Ensure bot is admin/member.")
    except Exception as e:
        print(f"WARNING: Could not log to LOGGER_ID {LOGGER_ID}: {e}")

    # Update user and group stats (after all)
    if not await db.present_user(user_id):
        await db.add_user(user_id, message.from_user.username, message.from_user.first_name)
    else:
        await db.update_user_last_seen(user_id)
    if message.chat.type != enums.ChatType.PRIVATE:
        await db.create_channel(message.chat.id, message.chat.title, message.chat.username)


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
    # Handle text messages (Admin sends link + optional caption)
    elif message.text:
        try:
            # Split the message text into lines
            lines = message.text.strip().splitlines()
            if not lines:
                 await message.reply("❌ Please send text content or forward a message")
                 return

            # First line is the content (link/username)
            content = lines[0].strip()

            # Check if content is valid (basic check)
            if not content:
                await message.reply("❌ Please provide the content (link or username) on the first line.")
                return

            # Remaining lines are the caption
            caption_lines = lines[1:] # This will be empty list if no caption
            # Join the caption lines back with newlines
            caption = '\n'.join(caption_lines).strip() if caption_lines else "Content Unlocked!" # Default caption, stripped

            # Combine content and caption for storage
            final_content_to_store = f"{content}\n{caption}"

            # --- Ensure peer is resolved before saving ---
            await client.get_chat(LOGGER_ID)
            # Save the combined content to LOGGER chat
            log_msg = await client.send_message(LOGGER_ID, final_content_to_store)
            msg_id = log_msg.id
        except PeerIdInvalid:
             print(f"Error: PeerIdInvalid when trying to save content to LOGGER_ID {LOGGER_ID}. Ensure bot is admin/member.")
             await message.reply("❌ Error saving content: Cannot access the storage chat. Please check bot configuration.")
             return # Stop processing if save fails
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

    # Save to database (you might want to save the original content separately if needed)
    # Ensure peer is resolved before fetching message for DB
    await client.get_chat(LOGGER_ID)
    original_content = (await client.get_messages(LOGGER_ID, msg_id)).text
    await db.create_link(original_content, message.from_user.id)



# --- Main Execution ---
if __name__ == "__main__":
    print("🚀 Starting bot...")
    app.start()

    # --- Call the startup hook ---
    try:
       app.loop.run_until_complete(on_startup(app))
    except Exception as e:
       print(f"Error in startup hook: {e}")
    # --- End Startup Hook Call ---

    try:
        app.send_message(OWNER_ID, "✅ Bot has started successfully!")
    except Exception as e:
        print(f"⚠️ Startup notification failed: {e}")

    print(f"🤖 Bot @{app.me.username} is running!")
    idle()
    print("🛑 Bot stopped.")
