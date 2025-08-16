import time, asyncio
from datetime import timedelta
from pyrogram import Client, enums, filters
from pyrogram.types import Message, ChatJoinRequest
from pyrogram.errors import FloodWait, InputUserDeactivated, UserIsBlocked
from database import Database
from collections import defaultdict
import asyncio
from pyrogram import enums
from pyrogram.errors import ChannelInvalid, PeerIdInvalid, UserAlreadyParticipant

REPLY_ERROR = "<b>Use this command as a reply to any message</b>"
pending_requests = defaultdict(dict)

async def delayed_approve(client: Client, chat_id: int, user_id: int, delay: int):
    try:
        await asyncio.sleep(delay)
        if chat_id in pending_requests and user_id in pending_requests[chat_id]:
            await client.approve_chat_join_request(chat_id, user_id)
            print(f"Approved join request for user {user_id} in chat {chat_id} after {delay} seconds")
    except (ChannelInvalid, PeerIdInvalid, UserAlreadyParticipant):
        pass
    except Exception as e:
        print(f"Error approving join request: {e}")
    finally:
        if chat_id in pending_requests and user_id in pending_requests[chat_id]:
            del pending_requests[chat_id][user_id]

async def handle_join_request(client: Client, update):
    chat_id = update.chat.id
    user_id = update.from_user.id
    
    if not hasattr(client, 'db'):
        print("Error: client has no db attribute")
        return
    
    channel = await client.db.channels.find_one({"channel_id": chat_id})
    if channel and "approve_delay" in channel:
        delay = channel["approve_delay"]
    else:
        default_setting = await client.db.channels.find_one({"channel_id": "default"})
        delay = default_setting.get("approve_delay", 180) if default_setting else 180
    
    task = asyncio.create_task(delayed_approve(client, chat_id, user_id, delay))
    pending_requests[chat_id][user_id] = task


async def handle_deleted_request(client: Client, update):
    chat_id = update.chat.id
    user_id = update.from_user.id
    if chat_id in pending_requests and user_id in pending_requests[chat_id]:
        pending_requests[chat_id][user_id].cancel()
        del pending_requests[chat_id][user_id]


async def set_approve_delay(client: Client, message: Message):
    if message.chat.type not in (enums.ChatType.GROUP, enums.ChatType.SUPERGROUP, enums.ChatType.CHANNEL, enums.ChatType.PRIVATE):
        await message.reply("❌ This command can only be used in groups, channels or private chats")
        return
    
    args = message.command[1:]
    if not args:
        await message.reply("Usage: /settime <time> (e.g., 30s, 2mi, 1d)\nOr for channels: /settime <channel_id/link/username> <time>")
        return
    
    target_chat_id = None
    time_str = None
    
    if message.chat.type == enums.ChatType.PRIVATE:
        if len(args) < 2:
            await message.reply("Usage: /settime <channel_id/link/username> <time>")
            return
        target = args[0]
        time_str = args[1]
        try:
            chat = await client.get_chat(target)
            if chat.type not in (enums.ChatType.CHANNEL, enums.ChatType.SUPERGROUP):
                await message.reply("❌ The specified chat is not a channel")
                return
            target_chat_id = chat.id
        except Exception as e:
            await message.reply(f"❌ Could not find channel: {e}")
            return
    else:
        target_chat_id = message.chat.id
        time_str = args[0]
    
    try:
        delay_seconds = parse_time(time_str)
    except ValueError:
        await message.reply("❌ Invalid time format. Use formats like: 30s, 2mi, 1h, 1d")
        return
    
    if not hasattr(client, 'db'):
        await message.reply("❌ Database not initialized")
        return
    
    if not await client.db.channels.find_one({"channel_id": target_chat_id}):
        try:
            chat = await client.get_chat(target_chat_id)
            await client.db.create_channel(target_chat_id, chat.title, chat.username)
        except Exception as e:
            print(f"Error creating channel entry: {e}")
    
    await client.db.set_approve_delay(target_chat_id, delay_seconds)
    
    try:
        chat = await client.get_chat(target_chat_id)
        chat_name = chat.title
    except:
        chat_name = f"ID {target_chat_id}"
    
    await message.reply(f"✅ Join requests for {chat_name} will now be accepted after {time_str} delay")



async def reset_delay(client: Client, message: Message):
    if message.chat.type not in (enums.ChatType.GROUP, enums.ChatType.SUPERGROUP, 
                               enums.ChatType.CHANNEL, enums.ChatType.PRIVATE):
        return await message.reply("❌ Groups/Channels/Private only")

    args = message.command[1:]
    db_setting = await client.db.channels.find_one({"channel_id": "default"})
    current = db_setting.get("approve_delay", 180) if db_setting else 180

    def fmt_time(sec):
        return (f"{sec//86400}d" if sec >= 86400 else
                f"{sec//3600}h" if sec >= 3600 else
                f"{sec//60}mi" if sec >= 60 else
                f"{sec}s")

    if not args:
        return await message.reply(
            f"⏳ Current delay: <b>{fmt_time(current)}</b>\n"
            f"Usage: <code>/d 30s/5mi/2h/1d</code>"
        )

    try:
        new_delay = parse_time(args[0])
    except ValueError:
        return await message.reply("❌ Invalid format. Use: 30s, 5m, 2h, 1d")

    if not hasattr(client, 'db'):
        return await message.reply("⚠️ DB Error")

    await client.db.set_approve_delay("default", new_delay)
    await message.reply(
        f"✅ Delay updated\n"
        f"Old: <b>{fmt_time(current)}</b>\n"
        f"New: <b>{fmt_time(new_delay)}</b>"
    )



def parse_time(time_str: str) -> int:
    time_str = time_str.lower()
    if time_str.endswith('s'):
        return int(time_str[:-1])
    elif time_str.endswith('mi'):
        return int(time_str[:-2]) * 60
    elif time_str.endswith('h'):
        return int(time_str[:-1]) * 3600
    elif time_str.endswith('d'):
        return int(time_str[:-1]) * 86400
    else:
        return int(time_str)



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
        try:
            # Get all user IDs from database
            query = await db.get_all_user_ids()
            
            broadcast_msg = message.reply_to_message
            total = 0
            successful = 0
            blocked = 0
            deleted = 0
            unsuccessful = 0
            
            pls_wait = await message.reply(f"<i>Broadcasting to {len(query)} users... This may take some time</i>")
            
            for chat_id in query:
                try:
                    # Check if we can send messages to this user
                    user_chat = await client.get_chat(chat_id)
                    if user_chat.type == enums.ChatType.PRIVATE:
                        await broadcast_msg.copy(chat_id)
                        successful += 1
                    else:
                        # Skip non-private chats
                        unsuccessful += 1
                except FloodWait as e:
                    await asyncio.sleep(e.x)
                    await broadcast_msg.copy(chat_id)
                    successful += 1
                except (UserIsBlocked, InputUserDeactivated):
                    # Remove blocked/deactivated users
                    await db.delete_user(chat_id)
                    if isinstance(e, UserIsBlocked):
                        blocked += 1
                    else:
                        deleted += 1
                except Exception as e:
                    # Handle other errors
                    if "USER_IS_BLOCKED" in str(e):
                        await db.delete_user(chat_id)
                        blocked += 1
                    elif "USER_DEACTIVATED" in str(e):
                        await db.delete_user(chat_id)
                        deleted += 1
                    else:
                        unsuccessful += 1
                total += 1
            
            status = f"""<b><u>Broadcast Completed</u>

Total Users: <code>{total}</code>
Successful: <code>{successful}</code>
Blocked Users: <code>{blocked}</code>
Deleted Accounts: <code>{deleted}</code>
Unsuccessful: <code>{unsuccessful}</code></b>"""
            
            return await pls_wait.edit(status)
        
        except Exception as e:
            error_msg = f"Broadcast failed: {type(e).__name__} - {str(e)}"
            await message.reply(f"❌ {error_msg}")

    else:
        msg = await message.reply(REPLY_ERROR)
        await asyncio.sleep(8)
        await msg.delete()

# Help message texts
ADMIN_HELP_TEXT = (
    "🛠 **Aᴅᴍɪɴ Hᴇʟᴘ** 🛠\n\n"
    "**Cᴏᴍᴍᴀɴᴅs:**\n"
    "/start - Bᴏᴛ ᴋᴀ ᴜsᴇ ᴋᴀʀɴᴇ ᴋᴀ ᴛᴀʀɪᴋᴀ\n"
    "/stats - Bᴏᴛ ᴋᴇ sᴛᴀᴛɪsᴛɪᴄs ᴅᴇᴋʜᴇ\n"
    "/broadcast - Sᴀʙʜɪ ᴜsᴇʀs ᴋᴏ ᴍᴇssᴀɢᴇ ʙʜᴇᴊᴇ\n"
    "/settime [seconds] - Aᴘᴘʀᴏᴠᴇ ᴅᴇʟᴀʏ sᴇᴛ ᴋᴀʀᴇ\n"
    "/default - Dᴇꜰᴀᴜʟᴛ ᴅᴇʟᴀʏ ᴘᴀʀ ʀᴇsᴇᴛ ᴋᴀʀᴇ\n\n"
    "**Lɪɴᴋ Bᴀɴᴀɴᴇ ᴋᴀ Tᴀʀɪᴋᴀ:**\n"
    "1. Kᴏɪ ʙʜɪ ʟɪɴᴋ ʙʜᴇᴊᴏ\n"
    "2. Aɢᴀʀ ᴄᴀᴘᴛɪᴏɴ ᴀᴅᴅ ᴋᴀʀɴᴀ ʜᴏ, ᴛᴏ ʟɪɴᴋ ᴋᴇ ʙᴀᴀᴅ sᴘᴀᴄᴇ ᴅᴇᴋᴀʀ ᴄᴀᴘᴛɪᴏɴ ʟɪᴋʜᴏ\n"
    "3. Aɢᴀʀ ᴄᴀᴘᴛɪᴏɴ ɴᴀʜɪɴ ᴅɪʏᴀ, ᴛᴏ 'Cᴏɴᴛᴇɴᴛ Uɴʟᴏᴄᴋᴇᴅ!' ᴅᴇꜰᴀᴜʟᴛ ʜᴏɢᴀ"
)

USER_HELP_TEXT = (
    "ℹ️ **User  Help** ℹ️\n\n"
    "**Cᴏᴍᴍᴀɴᴅs:**\n"
    "/start - Bᴏᴛ ᴋᴏ sᴛᴀʀᴛ ᴋᴀʀᴇ\n"
    "/help - Yᴇ ʜᴇʟᴘ ᴍᴇssᴀɢᴇ ᴅᴇᴋʜᴇ\n\n"
    "**Lɪɴᴋ U s e  K a r n e  K a  T a r i k a:**\n"
    "1. Kᴏɪ ʙʜɪ sᴇᴄᴜʀᴇ ʟɪɴᴋ ᴘᴀsᴛᴇ ᴋᴀʀᴇɪɴ\n"
    "2. Cᴏɴᴛᴇɴᴛ ᴀᴜᴛᴏᴍᴀᴛɪᴄᴀʟʟʏ ᴜɴʟᴏᴄᴋ ʜᴏ ᴊᴀʏᴇɢᴀ"
)





