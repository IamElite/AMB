import os
import asyncio
import random
from pyrogram import Client, filters, enums
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import FloodWait, InputUserDeactivated, UserIsBlocked, PeerIdInvalid, UserNotParticipant, ChatAdminRequired
import motor.motor_asyncio

# --- CONFIGURATION ---
api_id = int(os.getenv("API_ID", "28188113"))
api_hash = os.getenv("API_HASH", "81719734c6a0af15e5d35006655c1f84")
bot_token = os.getenv("BOT_TOKEN", "8585167958:AAFfVSeMuMeQaX1nswKWLrVWzjwSgv2xrgc")
mongo_url = os.getenv("MONGO_URL", "mongodb+srv://MentionMembers:MentionMembers@mentionmembers.yog0s3w.mongodb.net")
owner_id = int(os.getenv("OWNER_ID", "1679112664"))
fsub_channels = [int(x) for x in os.getenv("FSUB_CHANNELS", "").split()]

# --- REACTION EMOJIS ---
REACTION_EMOJIS = ["👍", "❤️", "🔥", "🥰", "👏", "😁", "🎉", "🤩", "👌"]

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
db = Database(mongo_url, "MentionBotDB")
app = Client("mention_bot", api_id=api_id, api_hash=api_hash, bot_token=bot_token)

# --- FSUB HELPER FUNCTION ---
async def get_fsub_buttons(bot, user_id):
    if not fsub_channels:
        return True, None

    missing_channels = []
    for channel_id in fsub_channels:
        try:
            member = await bot.get_chat_member(channel_id, user_id)
            if member.status in [enums.ChatMemberStatus.BANNED, enums.ChatMemberStatus.LEFT]:
                raise UserNotParticipant
        except UserNotParticipant:
            try:
                chat = await bot.get_chat(channel_id)
                link = chat.invite_link
                if not link:
                    link = await bot.export_chat_invite_link(channel_id)
                missing_channels.append((chat.title, link))
            except Exception as e:
                print(f"Error in FSub Channel {channel_id}: {e}")
                continue
        except Exception:
            continue

    if not missing_channels:
        return True, None

    buttons = []
    for title, link in missing_channels:
        buttons.append([InlineKeyboardButton(text=f"Join {title}", url=link)])
    
    return False, InlineKeyboardMarkup(buttons)

# --- COMMANDS ---

@app.on_message(filters.command("start"))
async def start(bot, message):
    try:
        await message.react(emoji=random.choice(REACTION_EMOJIS))
    except:
        pass 

    is_joined, buttons = await get_fsub_buttons(bot, message.from_user.id)
    if not is_joined:
        return await message.reply_text(
            "**⚠️ Access Denied!**\n\nPlease join our updates channels to use this bot.",
            reply_markup=buttons
        )

    await db.add_user(message.from_user.id)

    if message.chat.type in [enums.ChatType.GROUP, enums.ChatType.SUPERGROUP]:
        await db.add_chat(message.chat.id)
        await message.reply_text(f"Hey {message.from_user.mention}, I am ready! Use `/all` to tag everyone.")
    else:
        await message.reply_text(f"Hey {message.from_user.mention}, I am ready! Add me to your group and use `/all`.")

@app.on_message(filters.new_chat_members)
async def added_to_group(bot, message):
    for member in message.new_chat_members:
        if member.id == (await bot.get_me()).id:
            await db.add_chat(message.chat.id)
            try:
                await message.react(emoji=random.choice(REACTION_EMOJIS))
            except:
                pass
            await message.reply_text(
                "Thanks for adding me! 😎\n"
                "1. Promote me as **Admin**.\n"
                "2. Use `/all` to tag everyone."
            )

@app.on_message(filters.command("stats") & filters.user(owner_id))
async def stats(bot, message):
    users = await db.total_users_count()
    groups = await db.total_chat_count()
    await message.reply_text(f"📊 **Bot Stats:**\n\n👤 Users: {users}\n👥 Groups: {groups}")

@app.on_message(filters.command(["broadcast", "gcast"]) & filters.user(owner_id))
async def broadcast(bot, message):
    if not message.reply_to_message:
        return await message.reply_text("Reply to a message to broadcast.")
    
    msg = await message.reply_text("🚀 Broadcasting started...")
    
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
        return await message.reply_text("This command only works in groups.")
    
    # --- Step 1: Bot Admin Check ---
    # Agar Bot admin nahi hai to wo members fetch nahi kar payega
    try:
        bot_member = await bot.get_chat_member(message.chat.id, "me")
        if bot_member.status != enums.ChatMemberStatus.ADMINISTRATOR:
            return await message.reply_text("❌ **I am not Admin!**\nPlease make me Admin to tag everyone.")
    except Exception as e:
        return await message.reply_text(f"Error checking permissions: {e}")

    # --- Step 2: FSub Check ---
    if message.from_user:
        is_joined, buttons = await get_fsub_buttons(bot, message.from_user.id)
        if not is_joined:
            return await message.reply_text(
                f"Hey {message.from_user.mention}, please join the channel first to use this command!",
                reply_markup=buttons
            )

    try:
        await db.add_chat(message.chat.id)
    except:
        pass

    # --- Step 3: User Admin Check ---
    if message.from_user:
        try:
            member = await bot.get_chat_member(message.chat.id, message.from_user.id)
            if member.status not in [enums.ChatMemberStatus.ADMINISTRATOR, enums.ChatMemberStatus.OWNER]:
                return await message.reply_text("🚫 **Admin Only!**\nYou need to be an Admin or Owner to use this command.")
        except:
            return
    
    text = message.text.replace("/all", "").replace("@all", "").strip()
    if not text: text = "Hi everyone!"

    # Command Message Delete karne ka try karein
    try:
        await message.delete()
    except:
        pass # Agar delete permission nahi hai to ignore karo

    mentions = []
    try:
        async for member in bot.get_chat_members(message.chat.id):
            if not member.user.is_bot and not member.user.is_deleted:
                mentions.append(f"<a href='tg://user?id={member.user.id}'>\u200b</a>")
    except ChatAdminRequired:
        return await message.reply_text("❌ **I need Admin Rights!**\nI cannot fetch members list. Make me admin.")
    except Exception as e:
        return await message.reply_text(f"❌ Error fetching members: {e}")

    if not mentions:
        return await message.reply_text("❌ No members found to tag!")

    chunk_size = 100 
    reply_id = message.reply_to_message.id if message.reply_to_message else None

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
        except Exception as e:
            print(f"Error sending batch: {e}")

if __name__ == "__main__":
    print("Bot Started...")
    app.run()
