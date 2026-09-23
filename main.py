import asyncio
import logging
import os
import sqlite3
from aiohttp import web
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command, CommandStart, CommandObject
from aiogram.utils.keyboard import InlineKeyboardBuilder

BOT_TOKEN = os.environ.get("BOT_TOKEN")
CHANNEL_USERNAME = "@jadid_kitoblar_dokoni"     # Kanalingiz username'i
CHANNEL_ID = "@jadid_kitoblar_dokoni"           # Kanal ID si yoki username'i

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# --- BAZA BILAN ISHLASH (SQLite) ---
conn = sqlite3.connect("referrals.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    referrer_id INTEGER,
    ref_count INTEGER DEFAULT 0
)
""")
conn.commit()


# --- WEBSERVER (Render uchun) ---
async def handle(request):
    return web.Response(text="Bot is running!")

async def start_web_server():
    app = web.Application()
    app.router.add_get('/', handle)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 10000))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()


# --- KANALGA A'ZOLIKNI TEKSHIRISH ---
async def check_subscription(user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
        return member.status in ["creator", "administrator", "member"]
    except Exception as e:
        logging.error(f"Kanalni tekshirishda xato: {e}")
        return False


# --- START VA REFERAL HANDLER ---
@dp.message(CommandStart())
async def start_handler(message: types.Message, command: CommandObject):
    user_id = message.from_user.id
    args = command.args  # Referal bo'lib kirgan foydalanuvchi ID si

    # Baza tekshiruvi
    cursor.execute("SELECT user_id, referrer_id FROM users WHERE user_id = ?", (user_id,))
    user = cursor.fetchone()

    if not user:
        referrer_id = int(args) if args and args.isdigit() and int(args) != user_id else None
        cursor.execute("INSERT INTO users (user_id, referrer_id) VALUES (?, ?)", (user_id, referrer_id))
        conn.commit()

    # Kanalga a'zo ekanligini tekshirish
    is_subscribed = await check_subscription(user_id)

    if not is_subscribed:
        builder = InlineKeyboardBuilder()
        builder.button(text="📢 Kanalga a'zo bo'lish", url=f"https://t.me/{CHANNEL_USERNAME.replace('@', '')}")
        builder.button(text="✅ A'zolikni tasdiqlash", callback_data="check_sub")
        builder.adjust(1)

        await message.answer(
            "🎉 Xush kelibsiz!\n\nBotdan va referal tizimdan foydalanish uchun avval kanalimizga a'zo bo'ling:",
            reply_markup=builder.as_markup()
        )
    else:
        await show_main_menu(message)


@dp.callback_query(F.data == "check_sub")
async def check_sub_callback(call: types.CallbackQuery):
    user_id = call.from_user.id
    is_subscribed = await check_subscription(user_id)

    if is_subscribed:
        # Referal ballini oshirish (agar birinchi marta kirayotgan bo'lsa)
        cursor.execute("SELECT referrer_id FROM users WHERE user_id = ?", (user_id,))
        res = cursor.fetchone()
        
        if res and res[0]:
            referrer_id = res[0]
            # Referal egasining ballini 1 ga oshirish
            cursor.execute("UPDATE users SET ref_count = ref_count + 1 WHERE user_id = ?", (referrer_id,))
            # Qayta sanalmasligi uchun referrer_id ni NULL qilish
            cursor.execute("UPDATE users SET referrer_id = NULL WHERE user_id = ?", (user_id,))
            conn.commit()

            # Taklif qilgan foydalanuvchiga xabar yuborish
            try:
                cursor.execute("SELECT ref_count FROM users WHERE user_id = ?", (referrer_id,))
                count = cursor.fetchone()[0]
                await bot.send_message(
                    referrer_id,
                    f"🎉 Siz taklif qilgan foydalanuvchi kanalga qo'shildi!\nSizning jami takliflaringiz: **{count}** ta."
                )
            except Exception:
                pass

        await call.message.delete()
        await show_main_menu(call.message)
    else:
        await call.answer("❌ Siz hali kanalga a'zo bo'lmadingiz!", show_alert=True)


async def show_main_menu(event: types.Message | types.CallbackQuery):
    bot_info = await bot.get_me()
    user_id = event.from_user.id
    
    # Referal sonini olish
    cursor.execute("SELECT ref_count FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    ref_count = row[0] if row else 0

    ref_link = f"https://t.me/{bot_info.username}?start={user_id}"

    text = (
        f"🎉 **Xush kelibsiz!**\n\n"
        f"Siz kanalimizga obuna bo'lgansiz. Jadid kitoblar do'konidan foydalanishingiz mumkin.\n\n"
        f"🔗 **Sizning referal havolangiz:**\n`{ref_link}`\n\n"
        f"📊 **Siz taklif qilgan odamlar soni:** {ref_count} ta\n\n"
        f"Ushbu havolani do'stlaringizga yuboring. Ular botga kirib kanalga qo'shilsa, hisobingizga +1 odam qo'shiladi!"
    )
    
    if isinstance(event, types.Message):
        await event.answer(text, parse_mode="Markdown")
    else:
        await event.message.answer(text, parse_mode="Markdown")


# --- BOTNI ISHGA TUSHIRISH ---
async def main():
    await start_web_server()
    print("🤖 Bot ishga tushdi...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
    
