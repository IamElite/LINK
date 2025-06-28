import motor.motor_asyncio
from datetime import datetime

class Database:
    def __init__(self, mongo_url, db_name="link_bot"):
        self.client = motor.motor_asyncio.AsyncIOMotorClient(mongo_url)
        self.db = self.client[db_name]
        self.user_data = self.db.users  # Using the simpler demo structure
        self.channels = self.db.channels
        self.links = self.db.links
        self.stats = self.db.stats

    async def present_user(self, user_id: int):
        """Check if a user exists (demo-compatible)"""
        found = await self.user_data.find_one({'_id': user_id})
        return bool(found)

    async def add_user(self, user_id: int, username=None, first_name=None):
        """Add a user with minimal info (demo-compatible)"""
        user_data = {
            '_id': user_id,
            'created_at': datetime.now(),
            'last_seen': datetime.now()
        }
        # Only add optional fields if provided
        if username:
            user_data['username'] = username
        if first_name:
            user_data['first_name'] = first_name
        
        result = await self.user_data.insert_one(user_data)
        if result.inserted_id:
            await self.update_stat("total_users", 1)
        return result.inserted_id is not None

    async def update_user_last_seen(self, user_id):
        """Update last seen timestamp for a user"""
        await self.user_data.update_one(
            {"_id": user_id},
            {"$set": {"last_seen": datetime.now()}}
        )

    async def create_channel(self, channel_id, title, username):
        """Create a new channel entry with detailed logging"""
        try:
            channel_data = {
                "channel_id": channel_id,
                "title": title,
                "username": username,
                "created_at": datetime.now(),
                "approve_delay": 180  # Default 3 minutes
            }
            result = await self.channels.insert_one(channel_data)
            print(f"Created channel {channel_id} in database")
            return result
        except Exception as e:
            print(f"Error creating channel: {e}")
            return None

    async def set_approve_delay(self, channel_id: int, delay: int):
        """Set approval delay for join requests in seconds"""
        await self.channels.update_one(
            {"channel_id": channel_id},
            {"$set": {"approve_delay": delay}}
        )

    async def get_approve_delay(self, channel_id: int) -> int:
        """Get approval delay for a channel"""
        channel = await self.channels.find_one({"channel_id": channel_id})
        return channel.get("approve_delay", 180) if channel else 180

    async def create_link(self, link, owner_id):
        link_data = {
            "link": link,
            "owner_id": owner_id,
            "created_at": datetime.now(),
            "access_count": 0
        }
        result = await self.links.insert_one(link_data)
        await self.update_stat("total_links", 1)
        return result.inserted_id

    async def increment_link_access(self, link_id):
        await self.links.update_one(
            {"_id": link_id},
            {"$inc": {"access_count": 1}}
        )
        await self.update_stat("total_accesses", 1)

    async def update_stat(self, stat_type, increment=1):
        await self.stats.update_one(
            {"type": stat_type},
            {"$inc": {"count": increment}},
            upsert=True
        )

    async def get_stat(self, stat_type):
        stat = await self.stats.find_one({"type": stat_type})
        return stat["count"] if stat else 0

    async def get_all_stats(self):
        stats = {}
        async for stat in self.stats.find({}):
            stats[stat["type"]] = stat["count"]
        return stats

    async def get_all_user_ids(self):
        """Get all user IDs from the database (demo-compatible)"""
        user_ids = []
        async for doc in self.user_data.find({}, {'_id': 1}):
            user_ids.append(doc['_id'])
        return user_ids

    async def delete_user(self, user_id: int):
        """Delete a user from the database (demo-compatible)"""
        result = await self.user_data.delete_one({'_id': user_id})
        if result.deleted_count:
            await self.update_stat("total_users", -1)
        return result.deleted_count > 0
