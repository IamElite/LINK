import time, asyncio
from datetime import timedelta
from pyrogram import Client, enums, filters
from pyrogram.types import Message
from pyrogram.errors import FloodWait, InputUserDeactivated, UserIsBlocked
from database import Database

REPLY_ERROR = "<b>Use this command as a reply to any message</b>"

async def full_userbase():
    return []  # Placeholder - implement in database.py

async def del_user(user_id):
    pass  # Placeholder - implement in database.py

async def handle_stats(client, message, db: Database, bot_start_time: float):
    """Provide bot statistics to the owner"""
    # Calculate uptime
    uptime_seconds = time.time() - bot_start_time
    uptime = str(timedelta(seconds=int(uptime_seconds)))
    
    # Get stats from database
    total_users = await db.get_stat("total_users")
    total_groups = await db.get_stat("group_chats")
    total_links = await db.get_stat("total_links")
    
    stats_message = (
        f"📊 <b>Bot Statistics</b>\n\n"
        f"⏱ <b>Uptime:</b> {uptime}\n"
        f"👤 <b>Total Users:</b> {total_users}\n"
        f"👥 <b>Total Group Chats:</b> {total_groups}\n"
        f"🔗 <b>Total Links Generated:</b> {total_links}"
    )
    
    await message.reply(stats_message, parse_mode=enums.ParseMode.HTML)

async def handle_broadcast(client: Client, message: Message, db: Database):
    """Broadcast messages to all users"""
    if message.reply_to_message:
        query = await full_userbase()
        broadcast_msg = message.reply_to_message
        total = 0
        successful = 0
        blocked = 0
        deleted = 0
        unsuccessful = 0
        
        pls_wait = await message.reply("<i>Broadcasting Message.. This will Take Some Time</i>")
        for chat_id in query:
            try:
                await broadcast_msg.copy(chat_id)
                successful += 1
            except FloodWait as e:
                await asyncio.sleep(e.x)
                await broadcast_msg.copy(chat_id)
                successful += 1
            except UserIsBlocked:
                await del_user(chat_id)
                blocked += 1
            except InputUserDeactivated:
                await del_user(chat_id)
                deleted += 1
            except:
                unsuccessful += 1
                pass
            total += 1
        
        status = f"""<b><u>Broadcast Completed</u>

Total Users: <code>{total}</code>
Successful: <code>{successful}</code>
Blocked Users: <code>{blocked}</code>
Deleted Accounts: <code>{deleted}</code>
Unsuccessful: <code>{unsuccessful}</code></b>"""
        
        return await pls_wait.edit(status)

    else:
        msg = await message.reply(REPLY_ERROR)
        await asyncio.sleep(8)
        await msg.delete()
