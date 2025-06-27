import time, asyncio
from datetime import timedelta
from pyrogram import Client, enums, filters
from pyrogram.types import Message
from pyrogram.errors import FloodWait, InputUserDeactivated, UserIsBlocked
from database import Database

REPLY_ERROR = "<b>Use this command as a reply to any message</b>"

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
            print(f"Broadcast: Found {len(query)} users in database")
            
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
                        print(f"Broadcast: Sent to {chat_id} successfully")
                    else:
                        # Skip non-private chats
                        print(f"Broadcast: Skipping non-private chat {chat_id}")
                        unsuccessful += 1
                except FloodWait as e:
                    await asyncio.sleep(e.x)
                    await broadcast_msg.copy(chat_id)
                    successful += 1
                    print(f"Broadcast: Sent to {chat_id} after waiting {e.x} seconds")
                except (UserIsBlocked, InputUserDeactivated):
                    # Remove blocked/deactivated users
                    await db.delete_user(chat_id)
                    if isinstance(e, UserIsBlocked):
                        blocked += 1
                        print(f"Broadcast: User blocked - {chat_id}")
                    else:
                        deleted += 1
                        print(f"Broadcast: User deactivated - {chat_id}")
                except Exception as e:
                    # Handle other errors
                    if "USER_IS_BLOCKED" in str(e):
                        await db.delete_user(chat_id)
                        blocked += 1
                        print(f"Broadcast: User blocked - {chat_id}")
                    elif "USER_DEACTIVATED" in str(e):
                        await db.delete_user(chat_id)
                        deleted += 1
                        print(f"Broadcast: User deactivated - {chat_id}")
                    else:
                        unsuccessful += 1
                        print(f"Broadcast error for {chat_id}: {type(e).__name__} - {str(e)}")
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
            print(error_msg)
            await message.reply(f"❌ {error_msg}")

    else:
        msg = await message.reply(REPLY_ERROR)
        await asyncio.sleep(8)
        await msg.delete()
