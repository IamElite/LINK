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

# Join request handling functions
pending_requests = defaultdict(dict)

async def delayed_approve(client: Client, chat_id: int, user_id: int, delay: int):
    """Approve join request after specified delay"""
    try:
        await asyncio.sleep(delay)
        await client.approve_chat_join_request(chat_id, user_id)
    except (ChannelInvalid, PeerIdInvalid, UserAlreadyParticipant):
        pass  # Handle errors silently
    except Exception as e:
        print(f"Error approving join request: {e}")
    finally:
        # Cleanup - remove from pending requests regardless of outcome
        if chat_id in pending_requests and user_id in pending_requests[chat_id]:
            del pending_requests[chat_id][user_id]

async def handle_join_request(client: Client, update):
    """Handle new join requests with delayed approval"""
    chat_id = update.chat.id
    user_id = update.from_user.id
    
    # Get delay setting
    if not hasattr(client, 'db'):
        print("Error: client has no db attribute")
        return
    
    channel = await client.db.channels.find_one({"channel_id": chat_id})
    delay = channel.get("approve_delay", 180) if channel else 180
    
    # Schedule approval
    task = asyncio.create_task(delayed_approve(client, chat_id, user_id, delay))
    pending_requests[chat_id][user_id] = task

async def handle_deleted_request(client: Client, update):
    """Handle canceled join requests"""
    chat_id = update.chat.id
    user_id = update.from_user.id
    if chat_id in pending_requests and user_id in pending_requests[chat_id]:
        pending_requests[chat_id][user_id].cancel()
        del pending_requests[chat_id][user_id]

async def set_approve_delay(client: Client, message: Message):
    """Set approval delay for join requests with flexible arguments"""
    if message.chat.type not in (enums.ChatType.GROUP, enums.ChatType.SUPERGROUP, enums.ChatType.CHANNEL, enums.ChatType.PRIVATE):
        await message.reply("❌ This command can only be used in groups, channels or private chats")
        return
    
    args = message.command[1:]
    if not args:
        await message.reply("Usage: /settime <time> (e.g., 30s, 2m, 1d)\nOr for channels: /settime <channel_id/link/username> <time>")
        return
    
    # Check if we're setting delay for a specific channel (private chat or channel specified)
    target_chat_id = None
    time_str = None
    
    if message.chat.type == enums.ChatType.PRIVATE:
        if len(args) < 2:
            await message.reply("Usage: /settime <channel_id/link/username> <time>")
            return
        target = args[0]
        time_str = args[1]
        
        try:
            # Try to resolve channel identifier
            chat = await client.get_chat(target)
            if chat.type not in (enums.ChatType.CHANNEL, enums.ChatType.SUPERGROUP):
                await message.reply("❌ The specified chat is not a channel")
                return
            target_chat_id = chat.id
        except Exception as e:
            await message.reply(f"❌ Could not find channel: {e}")
            return
    else:
        # In a group/channel, use current chat
        target_chat_id = message.chat.id
        time_str = args[0]
    
    try:
        delay_seconds = parse_time(time_str)
    except ValueError:
        await message.reply("❌ Invalid time format. Use formats like: 30s, 2m, 1d")
        return
    
    # Ensure channel exists in DB
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
    
    # Get chat title for response
    try:
        chat = await client.get_chat(target_chat_id)
        chat_name = chat.title
    except:
        chat_name = f"ID {target_chat_id}"
    
    await message.reply(f"✅ Join requests for {chat_name} will now be accepted after {time_str} delay")

async def reset_delay(client: Client, message: Message):
    """Reset approval delay to default 3 minutes"""
    if message.chat.type not in (enums.ChatType.GROUP, enums.ChatType.SUPERGROUP, enums.ChatType.CHANNEL, enums.ChatType.PRIVATE):
        await message.reply("❌ This command can only be used in groups, channels or private chats")
        return
    
    args = message.command[1:]
    target_chat_id = None
    
    if message.chat.type == enums.ChatType.PRIVATE:
        if not args:
            await message.reply("Usage: /d <channel_id/link/username>")
            return
        target = args[0]
        
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
        # In a group/channel, use current chat
        target_chat_id = message.chat.id
    
    # Get current delay before resetting
    try:
        channel = await client.db.channels.find_one({"channel_id": target_chat_id})
        current_delay = channel.get("approve_delay", 180) if channel else 180
    except:
        current_delay = 180
    
    # Reset to default 3 minutes (180 seconds)
    if not hasattr(client, 'db'):
        await message.reply("❌ Database not initialized")
        return
    
    if not await client.db.channels.find_one({"channel_id": target_chat_id}):
        try:
            chat = await client.get_chat(target_chat_id)
            await client.db.create_channel(target_chat_id, chat.title, chat.username)
        except Exception as e:
            print(f"Error creating channel entry: {e}")
    
    # Only update if current delay is different from default
    if current_delay != 180:
        await client.db.set_approve_delay(target_chat_id, 180)
    
    # Get chat title for response
    try:
        chat = await client.get_chat(target_chat_id)
        chat_name = chat.title
    except:
        chat_name = f"ID {target_chat_id}"
    
    # Convert seconds to human-readable format
    def format_delay(seconds):
        if seconds < 60:
            return f"{seconds} seconds"
        minutes = seconds // 60
        return f"{minutes} minutes"
    
    # Show appropriate message based on whether value changed
    if current_delay == 180:
        await message.reply(f"✅ Join request delay for {chat_name} is already set to default (3 minutes)")
    else:
        await message.reply(
            f"✅ Join request delay for {chat_name} reset:\n"
            f"Previous: {format_delay(current_delay)}\n"
            f"New: 3 minutes"
        )

def parse_time(time_str: str) -> int:
    """Convert time string to seconds (e.g., '30s' -> 30, '2m' -> 120)"""
    time_str = time_str.lower()
    if time_str.endswith('s'):
        return int(time_str[:-1])
    elif time_str.endswith('m'):
        return int(time_str[:-1]) * 60
    elif time_str.endswith('h'):
        return int(time_str[:-1]) * 3600
    elif time_str.endswith('d'):
        return int(time_str[:-1]) * 86400
    else:
        return int(time_str)  # Assume seconds if no suffix

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
