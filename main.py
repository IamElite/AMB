import os
import asyncio
from pyrogram import Client, filters, enums
from pyrogram.types import Message
from pyrogram.errors import FloodWait, InputUserDeactivated, UserIsBlocked, PeerIdInvalid
import motor.motor_asyncio

# --- CONFIGURATION ---
API_ID = int(os.getenv("API_ID", "28188113"))
API_HASH = os.getenv("API_HASH", "81719734c6a0af15e5d35006655c1f84"))
BOT_TOKEN = os.getenv("BOT_TOKEN", "8551333890:AAGYD3inPZw9UAYLu8DCuGhfTU41AyBuVv4")
MONGO_URL = os.getenv("MONGO_URL", "mongodb+srv://ar:durgesh@ar.yqov3el.mongodb.net/?retryWrites=true&w=majority")
OWNER_ID = int(os.getenv("OWNER_ID", "1679112664"))

# --- MONGODB HELPER ---
class Database:
    def __init__(self, uri, database_name):
        self._client = motor.motor_asyncio.AsyncIOMotorClient(uri)
        self.db = self._client[database_name]
        self.col = self.db.users
        self.grp = self.db.groups

    # --- USER METHODS ---
    async def add_user(self, id):
        if not await self.is_user_exist(id):
            await self.col.insert_one({'id': int(id)})

    async def is_user_exist(self, id):
        return bool(await self.col.find_one({'id': int(id)}))

    async def total_users_count(self):
        return await self.col.count_documents({})

    async def get_all_users(self):
        return self.col.find({})

    async def delete_user(self, user_id):
        await self.col.delete_many({'id': int(user_id)})

    # --- GROUP METHODS ---
    async def add_chat(self, chat_id):
        if not await self.is_chat_exist(chat_id):
            await self.grp.insert_one({'id': int(chat_id)})

    async def is_chat_exist(self, chat_id):
        return bool(await self.grp.find_one({'id': int(chat_id)}))

    async def total_chat_count(self):
        return await self.grp.count_documents({})

    async def get_all_chats(self):
        return self.grp.find({})

    async def delete_chat(self, chat_id):
        await self.grp.delete_many({'id': int(chat_id)})

# Initialize Database and Bot
db = Database(MONGO_URL, "MentionBotDB")
app = Client("mention_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# --- COMMANDS ---

@app.on_message(filters.command("start") & filters.private)
async def start(bot, message):
    await db.add_user(message.from_user.id)
    await message.reply_text(f"Hey {message.from_user.mention}, main ready hu! Group me add karo aur `/all` use karo.")

# --- NEW: AUTO SAVE WHEN ADDED TO GROUP ---
@app.on_message(filters.new_chat_members)
async def added_to_group(bot, message):
    for member in message.new_chat_members:
        # Agar naya member khud Bot hai
        if member.id == (await bot.get_me()).id:
            await db.add_chat(message.chat.id)
            await message.reply_text(
                "Thanks for adding me! 😎\n"
                "1. Promote me as **Admin**.\n"
                "2. Use `/all` to tag everyone."
            )

@app.on_message(filters.command("stats") & filters.user(OWNER_ID))
async def stats(bot, message):
    users = await db.total_users_count()
    groups = await db.total_chat_count()
    await message.reply_text(f"📊 **Bot Stats:**\n\n👤 Users: {users}\n👥 Groups: {groups}")

@app.on_message(filters.command(["broadcast", "gcast"]) & filters.user(OWNER_ID))
async def broadcast(bot, message):
    if not message.reply_to_message:
        return await message.reply_text("Reply to a message to broadcast.")
    
    msg = await message.reply_text("🚀 Broadcasting started...")
    
    # Broadcast to Users
    users = await db.get_all_users()
    sent_users, failed_users = 0, 0
    async for user in users:
        try:
            await message.reply_to_message.copy(chat_id=user['id'])
            sent_users += 1
        except FloodWait as e:
            await asyncio.sleep(e.value)
            await message.reply_to_message.copy(chat_id=user['id'])
            sent_users += 1
        except (InputUserDeactivated, UserIsBlocked):
            await db.delete_user(user['id'])
            failed_users += 1
        except:
            failed_users += 1
            
    # Broadcast to Groups
    groups = await db.get_all_chats()
    sent_groups, failed_groups = 0, 0
    async for group in groups:
        try:
            await message.reply_to_message.copy(chat_id=group['id'])
            sent_groups += 1
        except FloodWait as e:
            await asyncio.sleep(e.value)
            await message.reply_to_message.copy(chat_id=group['id'])
            sent_groups += 1
        except:
            # Agar bot group se remove ho gaya hai to DB se hata do
            await db.delete_chat(group['id'])
            failed_groups += 1

    await msg.edit_text(
        f"✅ **Broadcast Complete**\n\n"
        f"👤 **Users:** {sent_users} sent, {failed_users} failed\n"
        f"👥 **Groups:** {sent_groups} sent, {failed_groups} failed"
    )

@app.on_message(filters.command("all") | filters.regex(r"^@all"))
async def tag_all(bot, message: Message):
    if message.chat.type not in [enums.ChatType.GROUP, enums.ChatType.SUPERGROUP]:
        return await message.reply_text("Yeh command sirf groups mein kaam karti hai.")
    
    # --- FALLBACK: SAVE GROUP IF NOT EXIST ---
    # Agar offline tha aur add hua, to ye line sure karegi ki ab DB me save ho jaye
    try:
        await db.add_chat(message.chat.id)
    except:
        pass

    # Permissions Check
    if message.from_user:
        try:
            member = await bot.get_chat_member(message.chat.id, message.from_user.id)
            if member.status not in [enums.ChatMemberStatus.ADMINISTRATOR, enums.ChatMemberStatus.OWNER]:
                return 
        except:
            return
    
    text = message.text.replace("/all", "").replace("@all", "").strip()
    if not text: text = "Hi everyone!"

    mentions = []
    async for member in bot.get_chat_members(message.chat.id):
        if not member.user.is_bot and not member.user.is_deleted:
            mentions.append(f"<a href='tg://user?id={member.user.id}'>\u200b</a>")

    chunk_size = 100 
    reply_id = message.reply_to_message.id if message.reply_to_message else None

    await message.delete()
    
    for i in range(0, len(mentions), chunk_size):
        batch = mentions[i:i + chunk_size]
        hidden_tags = "".join(batch)
        final_msg = f"{text}{hidden_tags}"
        
        try:
            if reply_id:
                await bot.send_message(message.chat.id, final_msg, reply_to_message_id=reply_id, parse_mode=enums.ParseMode.HTML)
            else:
                await bot.send_message(message.chat.id, final_msg, parse_mode=enums.ParseMode.HTML)
            await asyncio.sleep(3)
        except FloodWait as e:
            await asyncio.sleep(e.value)

if __name__ == "__main__":
    print("Bot Started...")
    app.run()
