import os
import asyncio
import random
from pyrogram import Client, filters, enums, idle
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import (
    FloodWait, InputUserDeactivated, UserIsBlocked,
    UserNotParticipant, ChatAdminRequired
)
import motor.motor_asyncio

BOT_INFO = "v2.3.0 | Ghost Tag Mode | Markdown Style"

api_id = int(os.getenv("API_ID", "28188113"))
api_hash = os.getenv("API_HASH", "81719734c6a0af15e5d35006655c1f84")
bot_token = os.getenv("BOT_TOKEN", "8585167958:AAFfVSeMuMeQaX1nswKWLrVWzjwSgv2xrgc")
mongo_url = os.getenv("MONGO_URL", "mongodb+srv://MentionMembers:MentionMembers@mentionmembers.yog0s3w.mongodb.net")

owner_ids = [int(x) for x in os.getenv("OWNER_ID", "1679112664").split()]
fsub_channels = [int(x) for x in os.getenv("FSUB_CHANNELS", "").split()]

REACTION_EMOJIS = ["👍", "❤️", "🔥", "🥰", "👏", "😁", "🎉", "🤩", "👌"]


# ================= DATABASE =================

class Database:
    def __init__(self, uri, name):
        self.client = motor.motor_asyncio.AsyncIOMotorClient(uri)
        self.db = self.client[name]
        self.users = self.db.users
        self.groups = self.db.groups

    async def add_user(self, uid):
        if not await self.users.find_one({"id": uid}):
            await self.users.insert_one({"id": uid})

    async def add_chat(self, cid):
        if not await self.groups.find_one({"id": cid}):
            await self.groups.insert_one({"id": cid})

    async def delete_user(self, uid):
        await self.users.delete_many({"id": uid})

    async def delete_chat(self, cid):
        await self.groups.delete_many({"id": cid})

    async def total_users(self):
        return await self.users.count_documents({})

    async def total_chats(self):
        return await self.groups.count_documents({})

    async def get_all_users(self):
        return self.users.find({})

    async def get_all_chats(self):
        return self.groups.find({})


db = Database(mongo_url, "MentionBotDB")
app = Client("mention_bot", api_id=api_id, api_hash=api_hash, bot_token=bot_token)


# ================= FSUB =================

async def get_fsub_buttons(bot, user_id):
    if not fsub_channels:
        return True, None

    buttons = []
    for ch in fsub_channels:
        try:
            m = await bot.get_chat_member(ch, user_id)
            if m.status in [enums.ChatMemberStatus.LEFT, enums.ChatMemberStatus.BANNED]:
                raise UserNotParticipant
        except:
            chat = await bot.get_chat(ch)
            link = chat.invite_link or await bot.export_chat_invite_link(ch)
            buttons.append([InlineKeyboardButton(f"Join {chat.title}", url=link)])

    if buttons:
        return False, InlineKeyboardMarkup(buttons)

    return True, None


# ================= START =================

@app.on_message(filters.command("start"))
async def start(_, m):
    await db.add_user(m.from_user.id)
    await m.reply_text("**✅ Bot Ready!** Add me to a group.")


# ================= STATS =================

@app.on_message(filters.command("stats") & filters.user(owner_ids))
async def stats(_, m):
    await m.reply_text(
        f"**📊 Stats**\nUsers: `{await db.total_users()}`\nGroups: `{await db.total_chats()}`"
    )


# ================= REPORT / ADMIN =================

@app.on_message(filters.command(["report", "admin"]))
async def report_admins(bot, message):
    if message.chat.type not in [enums.ChatType.GROUP, enums.ChatType.SUPERGROUP]:
        return await message.reply_text("**⚠️ Groups Only!**")

    raw = message.text or ""
    clean = raw.replace("/report", "").replace("/admin", "").strip()

    if clean:
        text = f"⚠️ <b>Report:</b> {clean}"
    elif message.reply_to_message:
        text = "⚠️ <b>Reported to Admins!</b> ☝️"
    else:
        text = "🆘 <b>Admins Called!</b>"

    admins = []
    async for member in bot.get_chat_members(
        message.chat.id,
        filter=enums.ChatMembersFilter.ADMINISTRATORS
    ):
        if (
            member.status in [enums.ChatMemberStatus.ADMINISTRATOR, enums.ChatMemberStatus.OWNER]
            and not member.user.is_bot
            and not member.user.is_deleted
        ):
            admins.append(member.user.id)


    if not admins:
        return await message.reply_text("**❌ No Admins Found!**")

    mentions = "".join(
        f'<a href="tg://user?id={i}">&#8288;</a>' for i in admins
    )

    await bot.send_message(
        message.chat.id,
        f"{text} {mentions}",
        reply_to_message_id=message.id,
        parse_mode=enums.ParseMode.HTML
    )


# ================= /ALL (FIXED – SINGLE MESSAGE) =================

@app.on_message(filters.command("all"))
async def tag_all(bot, message: Message):
    if message.chat.type not in [enums.ChatType.GROUP, enums.ChatType.SUPERGROUP]:
        return await message.reply_text("**⚠️ Groups Only!**")

    bot_member = await bot.get_chat_member(message.chat.id, "me")
    if bot_member.status != enums.ChatMemberStatus.ADMINISTRATOR:
        return await message.reply_text("**❌ Make me Admin!**")

    member = await bot.get_chat_member(message.chat.id, message.from_user.id)
    if member.status not in [enums.ChatMemberStatus.ADMINISTRATOR, enums.ChatMemberStatus.OWNER] and message.from_user.id not in owner_ids:
        return await message.reply_text("**🚫 Admins Only!**")

    raw_text = message.text or ""
    clean_text = raw_text.replace("/all", "").strip()
    
    if clean_text:
        text = clean_text
    elif message.reply_to_message:
        text = "**Check this out!** ☝️"
    else:
        text = "Hi everyone! 👋"

    try:
        await message.delete()
    except:
        pass

    mentions = []
    async for m in bot.get_chat_members(message.chat.id):
        if not m.user.is_bot and not m.user.is_deleted:
            mentions.append(f"[\u200b](tg://user?id={m.user.id})")

    await bot.send_message(
        message.chat.id,
        f"{text} {''.join(mentions)}",
        parse_mode=enums.ParseMode.MARKDOWN,
        reply_to_message_id=message.reply_to_message.id if message.reply_to_message else None
    )


# ================= RUN =================

async def main():
    await app.start()
    for owner in owner_ids:
        await app.send_message(owner, f"🚀 Bot Started\n`{BOT_INFO}`")
    await idle()
    await app.stop()

if __name__ == "__main__":
    asyncio.get_event_loop().run_until_complete(main())
