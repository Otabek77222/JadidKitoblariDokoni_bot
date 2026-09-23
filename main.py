import os
import logging
import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
import psycopg2
from aiohttp import web

# Logging sozlamalari
logging.basicConfig(level=logging.INFO)

# Environment o'zgaruvchilari
BOT_TOKEN = os.getenv("BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")
PORT = int(os.getenv("PORT", 8080))  # Render uchun port

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Supabase PostgreSQL bazasini ishga tushirish
def init_db():
    if not DATABASE_URL:
        logging.error("DATABASE_URL topilmadi!")
        return
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY,
                first_name VARCHAR(255),
                username VARCHAR(255),
                referrer_id BIGINT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        conn.commit()
        cursor.close()
        conn.close()
        logging.info("Ma'lumotlar bazasi tayyor.")
    except Exception as e:
        logging.error(f"Baza xatoligi: {e}")

# Foydalanuvchini bazaga saqlash
def save_user(user_id, first_name, username, referrer_id=None):
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO users (user_id, first_name, username, referrer_id)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (user_id) DO UPDATE 
            SET first_name = EXCLUDED.first_name, username = EXCLUDED.username;
        """, (user_id, first_name, username, referrer_id))
        conn.commit()
        cursor.close()
        conn.close()
    except Exception as e:
        logging.error(f"Foydalanuvchini saqlashda xatolik: {e}")

# Taklif qilingan do'stlar soni
def get_referral_count(user_id):
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM users WHERE referrer_id = %s;", (user_id,))
        count = cursor.fetchone()[0]
        cursor.close()
        conn.close()
        return count
    except Exception as e:
        logging.error(f"Referrallarni sanashda xatolik: {e}")
        return 0

def main_menu_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📚 Kitoblar katalogi")],
            [KeyboardButton(text="🔗 Taklif havolasi"), KeyboardButton(text="📊 Mening statistikaim")]
        ],
        resize_keyboard=True
    )

@dp.message(CommandStart())
async def start_handler(message: types.Message):
    user_id = message.from_user.id
    first_name = message.from_user.first_name
    username = message.from_user.username
    
    args = message.text.split()
    referrer_id = None
    if len(args) > 1 and args[1].isdigit():
        possible_referrer = int(args[1])
        if possible_referrer != user_id:
            referrer_id = possible_referrer

    save_user(user_id, first_name, username, referrer_id)
    
    welcome_text = (
        f"Assalomu alaykum, <b>{first_name}</b>!\n\n"
        f"<b>«Jadid kitoblar doʻkoni»</b> botiga xush kelibsiz! 📖\n"
        f"Quyidagi menyudan kerakli boʻlimni tanlang."
    )
    await message.answer(welcome_text, parse_mode="HTML", reply_markup=main_menu_keyboard())

@dp.message(lambda msg: msg.text in ["🔗 Taklif havolasi", "📊 Mening statistikaim"])
async def stats_handler(message: types.Message):
    user_id = message.from_user.id
    bot_info = await bot.get_me()
    ref_link = f"https://t.me/{bot_info.username}?start={user_id}"
    ref_count = get_referral_count(user_id)
    
    text = (
        f"🔗 <b>Sizning taklif havolangiz:</b>\n<code>{ref_link}</code>\n\n"
        f"👥 <b>Siz taklif qilgan do'stlar soni:</b> {ref_count} ta"
    )
    await message.answer(text, parse_mode="HTML")

@dp.message(lambda msg: msg.text == "📚 Kitoblar katalogi")
async def catalog_handler(message: types.Message):
    await message.answer("📚 Tez orada kitoblar katalogi joylashtiriladi!")

# Render Web Service uchun majburiy HTTP server (Timed Out xatosini oldini oladi)
async def handle_ping(request):
    return web.Response(text="Bot is running!")

async def start_web_server():
    app = web.Application()
    app.router.add_get("/", handle_ping)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()

async def main():
    init_db()
    # Web server va Bot polling rejimini bir vaqtda ishga tushiramiz
    await asyncio.gather(
        start_web_server(),
        dp.start_polling(bot)
    )

if __name__ == "__main__":
    asyncio.run(main())
    
