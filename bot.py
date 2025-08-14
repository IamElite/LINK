import os, re, base64, asyncio
from dotenv import load_dotenv
from aiohttp import web
from pyrogram import Client, filters, enums, idle
from pyrogram.handlers import ChatJoinRequestHandler
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import PeerIdInvalid, ChannelInvalid, UserAlreadyParticipant

# ---------- CONFIG ----------
load_dotenv()
API_ID    = int(os.getenv("API_ID", 0))
API_HASH  = os.getenv("API_HASH", "")
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
OWNER_ID  = int(os.getenv("OWNER_ID", 0))
LOGGER_ID = int(os.getenv("LOGGER_ID", 0))   # <- MUST be -1002536216907

ADMINS = [7074383232, OWNER_ID, 1679112664]
for x in os.environ.get("ADMINS", "").split():
    if x.isdigit():
        ADMINS.append(int(x))

# ---------- CLIENT ----------
app = Client("link_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# ---------- HELPERS ----------
def gen_enc(msg_id: int) -> str:
    raw = f"get-{msg_id * abs(LOGGER_ID)}"
    return base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")

async def dec_enc(enc: str) -> int:
    pad = "=" * (4 - len(enc) % 4)
    dec = base64.urlsafe_b64decode(enc + pad).decode()
    if not dec.startswith("get-"):
        raise ValueError("Bad format")
    return int(dec.split("-")[1]) // abs(LOGGER_ID)

# ---------- COMMANDS ----------
@app.on_message(filters.command("start"))
async def start(c, m):
    uid = m.from_user.id
    mention = f"[{m.from_user.first_name}](tg://user?id={uid})"
    if len(m.command) < 2:
        txt = f"👋 **Welcome,{' Admin' if uid in ADMINS else ''} {mention}**"
        return await m.reply(txt)

    try:
        raw = m.text.split(maxsplit=1)[1]
        parts = re.split(r"\n| ", raw.strip(), maxsplit=1)
        enc = re.sub(r"[^\w\-]", "", parts[0])
        mid = await dec_enc(enc)
        msg = await c.get_messages(LOGGER_ID, mid)
        if not msg.text:
            raise ValueError("Empty")

        caption = parts[1].strip() if len(parts) > 1 else "🔓 **Content Unlocked!**"
        url = msg.text.strip()

        # ensure valid URL
        if not url.startswith(("http://", "https://", "tg://")):
            url = f"https://t.me/{url.lstrip('@')}"

        await m.reply(
            caption,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Your Link", url=url)]]),
            protect_content=True
        )
    except Exception as e:
        await m.reply("❌ Invalid/expired link.")

# ---------- ADMIN HANDLER ----------
@app.on_message(filters.private & filters.user(ADMINS))
async def admin_handler(c, m):
    if m.text and m.text.startswith("/"):
        return

    if m.forward_from_chat and m.forward_from_chat.id == LOGGER_ID:
        mid = m.forward_from_message_id
    elif m.text:
        parts = re.split(r"\n| ", m.text.strip(), maxsplit=1)
        link = parts[0].strip()
        caption = parts[1].strip() if len(parts) > 1 else None

        try:
            msg = await c.send_message(LOGGER_ID, link)
            mid = msg.id
        except Exception as e:
            return await m.reply(f"❌ {e}")
    else:
        return await m.reply("❌ Send text or forward.")

    enc = gen_enc(mid)
    bot_link = f"https://t.me/{c.me.username}?start={enc}"
    share_btn = InlineKeyboardButton("🔁 Share URL", url=f"https://t.me/share/url?url={bot_link}")

    await m.reply(
        f"✅ **Secure Link Created!**\n\n{bot_link}",
        reply_markup=InlineKeyboardMarkup([[share_btn]])
    )

# ---------- WEB HEALTH ----------
async def run_web():
    web_app = web.Application()
    async def health(_):
        return web.Response(text=f"Bot @{app.me.username or 'link_bot'} is alive!")
    web_app.router.add_get("/", health)
    runner = web.AppRunner(web_app)
    await runner.setup()
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    print(f"🌍 Web server on 0.0.0.0:{port}")

# ---------- WARM LOGGER (CHANNEL) ----------
async def warm_logger():
    try:
        # For channels we can't join; just make any call to warm cache
        await app.get_chat(LOGGER_ID)
    except PeerIdInvalid:
        print("⚠️ Bot is not admin in the LOGGER channel or LOGGER_ID is wrong.")
    except Exception as e:
        print(f"⚠️ Logger warm failed: {e}")

# ---------- MAIN ----------
async def main():
    await app.start()
    await warm_logger()
    await run_web()
    try:
        await app.send_message(OWNER_ID, "✅ Bot started!")
    except Exception as e:
        print(f"⚠️ Owner ping failed: {e}")
    print(f"🤖 @{app.me.username} running!")
    await idle()

if __name__ == "__main__":
    asyncio.run(main())
