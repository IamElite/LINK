import motor.motor_asyncio
from datetime import datetime

class Database:
    def __init__(self, mongo_url, db_name="link_bot"):
        self.client = motor.motor_asyncio.AsyncIOMotorClient(mongo_url)
        self.db = self.client[db_name]
        self.users = self.db.users
        self.channels = self.db.channels
        self.links = self.db.links
        self.stats = self.db.stats

    async def create_user(self, user_id, username, first_name):
        user_data = {
            "user_id": user_id,
            "username": username,
            "first_name": first_name,
            "created_at": datetime.now(),
            "last_seen": datetime.now()
        }
        await self.users.insert_one(user_data)
        await self.update_stat("total_users", 1)

    async def update_user_last_seen(self, user_id):
        await self.users.update_one(
            {"user_id": user_id},
            {"$set": {"last_seen": datetime.now()}}
        )

    async def create_channel(self, channel_id, title, username):
        channel_data = {
            "channel_id": channel_id,
            "title": title,
            "username": username,
            "created_at": datetime.now()
        }
        await self.channels.insert_one(channel_data)

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
