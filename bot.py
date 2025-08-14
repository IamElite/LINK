import os,re,base64,asyncio,time,random
from dotenv import load_dotenv
from pyrogram import Client,filters,enums,idle
from pyrogram.handlers import ChatJoinRequestHandler
from pyrogram.types import InlineKeyboardMarkup,InlineKeyboardButton,Message,ChatJoinRequest
from pyrogram.errors import PeerIdInvalid,ChannelInvalid,UserAlreadyParticipant
from collections import defaultdict
from tools import *

try:
    from database import Database
except ImportError:
    print("FATAL: 'database.py' not found.");exit()

try:
    from tools import handle_stats
except ImportError:
    async def handle_stats(c,m,db,t):await m.reply("Stats module missing.")

load_dotenv()
API_ID=int(os.getenv("API_ID","0"))
API_HASH=os.getenv("API_HASH","")
BOT_TOKEN=os.getenv("BOT_TOKEN","")
OWNER_ID=int(os.getenv("OWNER_ID","0"))
MONGO_URL=os.getenv("MONGO_URL","")
LOGGER_ID=int(os.getenv("LOGGER_ID","0"))

ADMINS=[7074383232]
for x in os.environ.get("ADMINS","7074383232").split():ADMINS.append(int(x))
ADMINS.extend([OWNER_ID,1679112664])

db=Database(MONGO_URL)
bot_start_time=time.time()
app=Client("link_bot",api_id=API_ID,api_hash=API_HASH,bot_token=BOT_TOKEN)
app.db=db

def generate_encoded_string(msg_id:int)->str:
    raw=f"get-{msg_id*abs(LOGGER_ID)}"
    return base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")

async def decode_encoded_string(encoded:str)->int:
    pad="="*(4-len(encoded)%4)
    dec=base64.urlsafe_b64decode(encoded+pad).decode()
    if not dec.startswith("get-"):raise ValueError("Bad format")
    return int(dec.split("-")[1])//abs(LOGGER_ID)

@app.on_message(filters.command("start"))
async def start(c,m):
    uid=m.from_user.id
    men=f"[{m.from_user.first_name}](tg://user?id={uid})"
    if len(m.command)<2:
        txt=f"👋 **Welcome,{' Admin'if uid in ADMINS else''} {men}!**\n\n"
        txt+=("You can create secure links…"if uid in ADMINS else"My Father - @DshDm_bot")
        return await m.reply(txt,parse_mode=enums.ParseMode.MARKDOWN)
    try:
        raw=m.text.split(maxsplit=1)[1]
        parts=re.split(r"\n| ",raw.strip(),maxsplit=1)
        enc=re.sub(r'[^\w\-]','',parts[0])
        cid=await decode_encoded_string(enc)
        msg=await c.get_messages(LOGGER_ID,cid)
        if not msg.text:raise ValueError("Empty")
        cap=parts[1].strip()if len(parts)>1 else"🔓 **Content Unlocked!**"
        await m.reply(cap,reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Your Link",url=msg.text if msg.text.startswith("http")else f"https://t.me/{msg.text.lstrip('@')}")]]),protect_content=True)
    except Exception as e:await m.reply("❌ Invalid/expired link.")

    try:await c.send_message(LOGGER_ID,f"Bot started by: {men}",parse_mode=enums.ParseMode.MARKDOWN)
    except:pass
    if not await db.present_user(uid):
        await db.add_user(uid,m.from_user.username,m.from_user.first_name)
    else:await db.update_user_last_seen(uid)
    if m.chat.type!=enums.ChatType.PRIVATE:
        await db.create_channel(m.chat.id,m.chat.title,m.chat.username)

@app.on_message(filters.private&filters.command("stats")&filters.user(ADMINS))
async def stats(c,m):await handle_stats(c,m,db,bot_start_time)
@app.on_message(filters.private&filters.command("broadcast")&filters.user(ADMINS))
async def bc(c,m):
    from tools import handle_broadcast
    await handle_broadcast(c,m,db)
def jrc(c,u):
    c.loop.create_task(handle_deleted_request(c,u)if getattr(u,'deleted',0)else handle_join_request(c,u))
app.add_handler(ChatJoinRequestHandler(jrc))
@app.on_message(filters.command(["settime","st"])&filters.user(ADMINS))
async def sd(c,m):await set_approve_delay(c,m)
@app.on_message(filters.command(["d","default"])&filters.user(ADMINS))
async def rd(c,m):await reset_delay(c,m)

@app.on_message(filters.private&filters.user(ADMINS))
async def own(c,m):
    if m.text and m.text.startswith("/"):return
    if m.forward_from_chat and m.forward_from_chat.id==LOGGER_ID:
        mid=m.forward_from_message_id
    elif m.text:
        ps=re.split(r"\n| ",m.text.strip(),maxsplit=1)
        link=ps[0].strip();cap=ps[1].strip()if len(ps)>1 else None
        try:
            lm=await c.send_message(LOGGER_ID,link)
            mid=lm.id
            if cap:await db.store_caption(mid,cap)
        except Exception as e:return await m.reply(f"❌ {e}")
    else:return await m.reply("❌ Send text or forward.")
    enc=generate_encoded_string(mid)
    bl=f"https://t.me/{c.me.username}?start={enc}"
    await m.reply("✅ **Secure Link Created!**\n\n"+bl,
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔁 Share URL",url=f"https://telegram.me/share/url?url={bl}")]]))

async def _warm():await app.get_chat(LOGGER_ID)
if __name__=="__main__":
    print("🚀 Starting bot...")
    app.start();app.run(_warm())
    try:app.send_message(OWNER_ID,"✅ Bot started!")
    except Exception as e:print(f"⚠️ {e}")
    print(f"🤖 @{app.me.username} running!")
    idle();print("🛑 Bot stopped.")
