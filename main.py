import os
import asyncio
from pyrogram import Client, filters, enums
from pyrogram.types import Message
from pyrogram.errors import FloodWait, InputUserDeactivated, UserIsBlocked
import motor.motor_asyncio

# --- CONFIGURATION (Env Vars se uthayega) ---
API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH", "")
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
MONGO_URL = os.getenv("MONGO_URL", "")
OWNER_ID = int(os.getenv("OWNER_ID", "0"))

# --- MONGODB HELPER ---
class Database:
    def __init__(self, uri, database_name):
        self._client = motor.motor_asyncio.AsyncIOMotorClient(uri)
        self.db = self._client[database_name]
        self.col = self.db.users

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

db = Database(MONGO_URL, "MentionBotDB")
app = Client("mention_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# --- COMMANDS ---

@app.on_message(filters.command("start") & filters.private)
async def start(bot, message):
    await db.add_user(message.from_user.id)
    await message.reply_text(f"Hey {message.from_user.mention}, main ready hu! Group me add karo aur `/all` use karo.")

@app.on_message(filters.command("stats") & filters.user(OWNER_ID))
async def stats(bot, message):
    count = await db.total_users_count()
    await message.reply_text(f"📊 **Total Users:** {count}")

@app.on_message(filters.command(["broadcast", "gcast"]) & filters.user(OWNER_ID))
async def broadcast(bot, message):
    if not message.reply_to_message:
        return await message.reply_text("Reply to a message to broadcast.")
    
    msg = await message.reply_text("🚀 Broadcasting...")
    users = await db.get_all_users()
    sent, failed = 0, 0
    
    async for user in users:
        try:
            await message.reply_to_message.copy(chat_id=user['id'])
            sent += 1
        except FloodWait as e:
            await asyncio.sleep(e.value)
            await message.reply_to_message.copy(chat_id=user['id'])
            sent += 1
        except (InputUserDeactivated, UserIsBlocked):
            await db.delete_user(user['id'])
            failed += 1
        except:
            failed += 1
            
    await msg.edit_text(f"✅ Broadcast Done!\nSent: {sent} | Failed: {failed}")

@app.on_message(filters.command("all") | filters.regex(r"^@all"))
async def tag_all(bot, message: Message):
    if message.chat.type == enums.ChatType.PRIVATE:
        return await message.reply_text("Use this in a group.")

    # Check Admin Permissions
    try:
        member = await bot.get_chat_member(message.chat.id, message.from_user.id)
        if member.status not in [enums.ChatMemberStatus.ADMINISTRATOR, enums.ChatMemberStatus.OWNER]:
            return
    except:
        return

    # Message Text Setup
    text = message.text.replace("/all", "").replace("@all", "").strip()
    if not text: text = "Hi everyone!"

    # Invisible Mention Logic
    mentions = []
    async for member in bot.get_chat_members(message.chat.id):
        if not member.user.is_bot and not member.user.is_deleted:
            # \u200b is zero width space (invisible)
            mentions.append(f"<a href='tg://user?id={member.user.id}'>\u200b</a>")

    # Batch Sending (Max 100 mentions per msg allows reliable tagging)
    chunk_size = 100 
    if message.reply_to_message:
        reply_id = message.reply_to_message.id
    else:
        reply_id = None

    # Pehla message bhejte hain
    await message.delete()
    
    for i in range(0, len(mentions), chunk_size):
        batch = mentions[i:i + chunk_size]
        hidden_tags = "".join(batch)
        final_msg = f"{text}{hidden_tags}" # Text + Invisible Tags
        
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
