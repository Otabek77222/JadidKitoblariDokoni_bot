import os
import logging
import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart, Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
import psycopg2
from aiohttp import web

# Logging sozlamalari
logging.basicConfig(level=logging.INFO)

# Environment o'zgaruvchilari
BOT_TOKEN = os.getenv("BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")
PORT = int(os.getenv("PORT", 8080))

# Admin Telegram ID (FAQAT SIZ REYTINGNI BEKOR QILA OLASIZ)
ADMIN_ID = 761158313

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

# Eng ko'p taklif qilgan TOP 10 talikni olish
def get_leaderboard():
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT u.first_name, u.username, COUNT(r.user_id) as ref_count
            FROM users u
            JOIN users r ON u.user_id = r.referrer_id
            GROUP BY u.user_id, u.first_name, u.username
            ORDER BY ref_count DESC
            LIMIT 10;
        """)
        top_users = cursor.fetchall()
        cursor.close()
        conn.close()
        return top_users
    except Exception as e:
        logging.error(f"Reytingni olishda xatolik: {e}")
        return []

# Barcha referral ulashuvlarni bekor qilish (Reset)
def reset_all_referrals():
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET referrer_id = NULL;")
        conn.commit()
        cursor.close()
        conn.close()
        return True
    except Exception as e:
        logging.error(f"Natijalarni tozalashda xatolik: {e}")
        return False

# Asosiy menyu klaviaturasi
def main_menu_keyboard(user_id):
    buttons = [
        [KeyboardButton(text="📚 Kitoblar katalogi")],
        [KeyboardButton(text="🔗 Taklif havolasi"), KeyboardButton(text="📊 Mening statistikaim")],
        [KeyboardButton(text="🏆 Top taklif qilganlar")]
    ]
    # Agar foydalanuvchi Admin bo'lsa, tozalash tugmasi ko'rinadi
    if user_id == ADMIN_ID:
        buttons.append([KeyboardButton(text="⚙️ Natijalarni bekor qilish (Admin)")])

    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

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
    await message.answer(welcome_text, parse_mode="HTML", reply_markup=main_menu_keyboard(user_id))

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

# Top taklif qilganlar (Reyting)
@dp.message(lambda msg: msg.text == "🏆 Top taklif qilganlar")
async def leaderboard_handler(message: types.Message):
    top_users = get_leaderboard()
    if not top_users:
        await message.answer("🏆 Hozircha hech kim taklif qilmagan yoki reyting bo'sh.")
        return

    text = "🏆 <b>Eng ko'p taklif qilganlar (TOP-10):</b>\n\n"
    for idx, (first_name, username, count) in enumerate(top_users, start=1):
        user_display = f"@{username}" if username else first_name
        text += f"{idx}. {user_display} — <b>{count} ta</b>\n"

    await message.answer(text, parse_mode="HTML")

# Admin uchun natijalarni bekor qilish tugmasi
@dp.message(lambda msg: msg.text == "⚙️ Natijalarni bekor qilish (Admin)")
async def reset_handler(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔️ Sizda bu amalni bajarish uchun huquq yo'q!")
        return

    if reset_all_referrals():
        await message.answer("✅ Barcha referral natijalari muvaffaqiyatli bekor qilindi (nolga tenglashtirildi)!")
    else:
        await message.answer("❌ Natijalarni bekor qilishda xatolik yuz berdi.")

@dp.message(lambda msg: msg.text == "📚 Kitoblar katalogi")
async def catalog_handler(message: types.Message):
    await message.answer("📚 Tez orada kitoblar katalogi joylashtiriladi!")

# Web Server Render uchun
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
    await asyncio.gather(
        start_web_server(),
        dp.start_polling(bot)
    )

if __name__ == "__main__":
    asyncio.run(main())
    
