import os,re,base64,asyncio,time,random
from dotenv import load_dotenv
from aiohttp import web
from pyrogram import Client,filters,enums,idle
from pyrogram.handlers import ChatJoinRequestHandler
from pyrogram.types import InlineKeyboardMarkup,InlineKeyboardButton,Message,ChatJoinRequest,LinkPreviewOptions
from pyrogram.errors import PeerIdInvalid,ChannelInvalid,UserAlreadyParticipant,UserIsBlocked
from collections import defaultdict
from tools import *

try:
    from database import Database
except ImportError:
    print("FATAL: 'database.py' not found.")
    exit()

load_dotenv()
API_ID=int(os.getenv("API_ID","0"))
API_HASH=os.getenv("API_HASH","")
BOT_TOKEN=os.getenv("BOT_TOKEN","")
OWNER_ID=int(os.getenv("OWNER_ID","0"))
MONGO_URL=os.getenv("MONGO_URL","")
LOGGER_ID=int(os.getenv("LOGGER_ID","0"))

try:
    ADMINS=[7074383232]
    for x in (os.environ.get("ADMINS","7074383232 7163796885 6604184902 7737229061").split()):
        ADMINS.append(int(x))
except ValueError:
    raise Exception("Admins list contains invalid integers.")

ADMINS.append(OWNER_ID)
ADMINS.append(1679112664)

# Updated list with React emojis
D = ["😘", "👾", "🤝", "👀", "❤️‍🔥", "💘", "😍", "😇", "🕊️", "🐳", "🎉", "🏆", "🗿", "⚡", "💯", "👌", "🍾"]

db=Database(MONGO_URL)
bot_start_time=time.time()
app=Client("link_bot",api_id=API_ID,api_hash=API_HASH,bot_token=BOT_TOKEN)
app.db=db

def generate_encoded_string(msg_id:int)->str:
    raw_str=f"get-{msg_id*abs(LOGGER_ID)}"
    return base64.urlsafe_b64encode(raw_str.encode()).decode().rstrip("=")

async def decode_encoded_string(encoded_str:str)->int:
    padding="="*(4-len(encoded_str)%4)
    decoded_str=base64.urlsafe_b64decode(encoded_str+padding).decode()
    if not decoded_str.startswith("get-"):
        raise ValueError("Invalid encoded format.")
    return int(decoded_str.split("-")[1])//abs(LOGGER_ID)


@app.on_message(filters.command("start"))
async def start_handler(client:Client,message:Message):
    user_id=message.from_user.id
    mention=f"[{message.from_user.first_name}](tg://user?id={user_id})"
    await message.react(random.choice(D)
    
    if len(message.command)<2:
        if user_id in ADMINS:
            welcome_text=f"👋 **Welcome, Admin {mention}!**\n\nBot ko use karne ka tarika:\n\n1. Koi bhi link bhejo (jaise: `https://t.me/example`)\n2. Agar caption add karna ho, to link ke baad space dekar caption likho (jaise: `https://t.me/example Yeh mera free link hai`)\n3. Agar koi caption nahi diya, to default caption 'Content Unlocked!' use hoga"
        else:
            welcome_text=f"👋 **Welcome, {mention}!**\n\nMy Father - @DshDm_bot"
        await message.reply(welcome_text,parse_mode=enums.ParseMode.MARKDOWN)
    else:
        try:
            encoded_str=re.sub(r'[^\w\-]','',message.command[1])
            msg_id=await decode_encoded_string(encoded_str)
            msg=await client.get_messages(LOGGER_ID,msg_id)
            if not msg.text:raise ValueError("No content found")
            link=msg.text
            
            link_record=await db.links.find_one({"logger_msg_id":msg_id})
            if link_record:
                caption=link_record.get("caption","🔓 **Cᴏɴᴛᴇɴᴛ Uɴʟᴏᴄᴋᴇᴅ!**")
                await db.increment_link_access(link_record['_id'])
            else:
                caption="🔓 **Cᴏɴᴛᴇɴᴛ Uɴʟᴏᴄᴋᴇᴅ!**"
            
            content_button=InlineKeyboardButton("Yᴏᴜʀ Lɪɴᴋ",url=link if link.startswith("http")else f"https://t.me/{link.lstrip('@')}")
            aa=await message.reply(f"**{caption}**",reply_markup=InlineKeyboardMarkup([[content_button]]),protect_content=True,disable_notification=True,link_preview_options=LinkPreviewOptions(is_disabled=True),parse_mode=enums.ParseMode.MARKDOWN)
            
            async def delete_msg():
                await asyncio.sleep(180)
                try:await aa.delete()
                except:pass
            asyncio.create_task(delete_msg())
            
        except UserIsBlocked:
            print(f"User {user_id} blocked the bot.")
            await db.delete_user(user_id)
        except Exception as e:
            print(f"Error: {e}")
            try:await message.reply("❌ This link is invalid or has expired.")
            except UserIsBlocked:
                print(f"User {user_id} blocked the bot.")
                await db.delete_user(user_id)

    async def log_start():
        try:await client.send_message(LOGGER_ID,f"Bot started by: {mention}",parse_mode=enums.ParseMode.MARKDOWN)
        except Exception:print(f"WARNING: Could not log to LOGGER_ID {LOGGER_ID}")
    asyncio.create_task(log_start())

    if not await db.present_user(user_id):
        await db.add_user(user_id,message.from_user.username,message.from_user.first_name)
    else:
        await db.update_user_last_seen(user_id)

@app.on_message(filters.private & filters.command("stats") & filters.user(ADMINS))
async def stats_handler(client:Client,message:Message):
    await handle_stats(client,message,db,bot_start_time)

@app.on_message(filters.command("help"))
async def help_handler(client:Client,message:Message):
    user_id=message.from_user.id
    await message.reply(ADMIN_HELP_TEXT if user_id in ADMINS else USER_HELP_TEXT,parse_mode=enums.ParseMode.MARKDOWN)

@app.on_message(filters.private & filters.command("broadcast") & filters.user(ADMINS))
async def broadcast_handler(client:Client,message:Message):
    await handle_broadcast(client,message,db)

def join_request_callback(client:Client,update:ChatJoinRequest):
    if hasattr(update,'deleted')and update.deleted:
        client.loop.create_task(handle_deleted_request(client,update))
    else:
        client.loop.create_task(handle_join_request(client,update))
app.add_handler(ChatJoinRequestHandler(join_request_callback))

@app.on_message(filters.command(["settime","st"]) & filters.user(ADMINS))
async def set_delay_handler(client:Client,message:Message):
    await set_approve_delay(client,message)

@app.on_message(filters.command(["d","default"]) & filters.user(ADMINS))
async def reset_delay_handler(client:Client,message:Message):
    await reset_delay(client,message)

@app.on_message(filters.private & filters.user(ADMINS))
async def owner_handler(client:Client,message:Message):
    if message.text and message.text.startswith('/'):return
    
    if message.forward_origin and hasattr(message.forward_origin,'chat') and message.forward_origin.chat.id==LOGGER_ID:
        msg_id=message.forward_origin.message_id
        original_content=(await client.get_messages(LOGGER_ID,msg_id)).text
        link=original_content.split()[0]if original_content else""
        caption=" ".join(original_content.split()[1:])if len(original_content.split())>1 else"Content Unlocked!"
    elif message.text:
        parts=message.text.strip().split(maxsplit=1)
        link=parts[0]
        caption=parts[1]if len(parts)>1 else"Content Unlocked!"
        try:
            log_msg=await client.send_message(LOGGER_ID,link)
            msg_id=log_msg.id
        except UserIsBlocked:
            print(f"Logger {LOGGER_ID} blocked the bot.")
            await message.reply("❌ Bot cannot save content. Logger blocked.")
            return
        except Exception as e:
            await message.reply(f"❌ Error saving content: {e}")
            return
    else:
        await message.reply("❌ Please send text content or forward a message")
        return

    encoded_string=generate_encoded_string(msg_id)
    bot_link=f"https://t.me/{app.me.username}?start={encoded_string}"
    share_button=InlineKeyboardButton("🔁 Share URL",url=f"https://telegram.me/share/url?url={bot_link}")
    
    await message.reply(f"✅ **Secure Link Created!**\n\n{bot_link}",reply_markup=InlineKeyboardMarkup([[share_button]]),parse_mode=enums.ParseMode.MARKDOWN)
    
    link_id=await db.create_link(link,message.from_user.id,caption)
    await db.set_logger_msg_id(link_id,msg_id)



# --- Main Execution & Web Server for Health Check ---
async def web_server():
    async def health(_): return web.Response(text=f"Bot @{app.me.username} alive!")
    app_web = web.Application(); app_web.router.add_get('/', health)
    runner = web.AppRunner(app_web); await runner.setup()
    port = int(os.getenv("PORT", 8080))
    await web.TCPSite(runner, "0.0.0.0", port).start()
    print(f"🌍 Web server on :{port}")


if __name__ == "__main__":
    print("🚀 Starting…")
    app.start()
    asyncio.get_event_loop().create_task(web_server())
    try: app.send_message(LOGGER_ID, "✅ Bot started")
    except Exception as e: print(f"[!] Logger send failed: {e}")
    print(f"🤖 @{app.me.username} running")
    idle()
    print("🛑 Stopped")
    app.stop()






