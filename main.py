import asyncio
import logging
import os

from aiogram import Bot, Dispatcher, F, types
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    ChatMemberUpdated,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)
from aiohttp import web
import psycopg2

# Logging sozlamalari
logging.basicConfig(level=logging.INFO)

# Environment o'zgaruvchilari
BOT_TOKEN = os.getenv("BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")
PORT = int(os.getenv("PORT", 8080))

# Admin Telegram ID va Kanal sozlamalari
ADMIN_ID = 761158313
CHANNEL_USERNAME = "@jadid_kitoblar_dokoni"
CHANNEL_LINK = "https://t.me/jadid_kitoblar_dokoni"

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
    # invite_link ustuni qo'shildi
    cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY,
                first_name VARCHAR(255),
                username VARCHAR(255),
                referrer_id BIGINT,
                invite_link VARCHAR(255),
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
def save_user(user_id, first_name, username, referrer_id=None, invite_link=None):
  try:
    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()
    cursor.execute(
        """
            INSERT INTO users (user_id, first_name, username, referrer_id, invite_link)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (user_id) DO UPDATE 
            SET first_name = EXCLUDED.first_name, username = EXCLUDED.username;
        """,
        (user_id, first_name, username, referrer_id, invite_link),
    )
    conn.commit()
    cursor.close()
    conn.close()
  except Exception as e:
    logging.error(f"Foydalanuvchini saqlashda xatolik: {e}")


# Foydalanuvchining shaxsiy invite linkini bazaga yozish (agar hali bo'lmasa)
def update_user_invite_link(user_id, invite_link):
  try:
    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()
    cursor.execute(
        """
            UPDATE users SET invite_link = %s WHERE user_id = %s;
        """,
        (invite_link, user_id),
    )
    conn.commit()
    cursor.close()
    conn.close()
  except Exception as e:
    logging.error(f"Invite linkni saqlashda xatolik: {e}")


# Invite link bo'yicha egasini (referrer_id) topish
def get_user_by_invite_link(invite_link):
  try:
    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT user_id FROM users WHERE invite_link = %s;", (invite_link,)
    )
    res = cursor.fetchone()
    cursor.close()
    conn.close()
    return res[0] if res else None
  except Exception as e:
    logging.error(f"Invite link egasini topishda xatolik: {e}")
    return None


# Taklif qilingan do'stlar soni
def get_referral_count(user_id):
  try:
    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT COUNT(*) FROM users WHERE referrer_id = %s;", (user_id,)
    )
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
    cursor.execute("UPDATE users SET referrer_id = NULL, invite_link = NULL;")
    conn.commit()
    cursor.close()
    conn.close()
    return True
  except Exception as e:
    logging.error(f"Natijalarni tozalashda xatolik: {e}")
    return False


# Kanalga obuna bo'lganligini tekshirish funksiyasi
async def check_subscription(user_id: int) -> bool:
  try:
    member = await bot.get_chat_member(chat_id=CHANNEL_USERNAME, user_id=user_id)
    if member.status in ["creator", "administrator", "member"]:
      return True
    return False
  except TelegramBadRequest:
    return True
  except Exception:
    return False


# Asosiy menyu klaviaturasi
def main_menu_keyboard(user_id):
  buttons = [
      [KeyboardButton(text="📚 Kitoblar katalogi")],
      [
          KeyboardButton(text="🔗 Taklif havolasi"),
          KeyboardButton(text="📊 Mening statistikam"),
      ],
      [KeyboardButton(text="🏆 Top taklif qilganlar")],
  ]
  if user_id == ADMIN_ID:
    buttons.append([KeyboardButton(text="⚙️ Natijalarni bekor qilish (Admin)")])

  return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)


@dp.message(CommandStart())
async def start_handler(message: types.Message):
  user_id = message.from_user.id
  first_name = message.from_user.first_name
  username = message.from_user.username

  is_subscribed = await check_subscription(user_id)

  if not is_subscribed:
    subscribe_keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📢 Kanalga obuna bo'lish", url=CHANNEL_LINK
                )
            ],
            [
                InlineKeyboardButton(
                    text="✅ Obunani tekshirish", callback_data="check_sub"
                )
            ],
        ]
    )
    await message.answer(
        f"❌ Hurmatli <b>{first_name}</b>, botimizdan foydalanish uchun avval"
        f" quyidagi kanalimizga obuna boʻlishingiz kerak:",
        parse_mode="HTML",
        reply_markup=subscribe_keyboard,
    )
    return

  save_user(user_id, first_name, username)

  welcome_text = (
      f"Assalomu alaykum, <b>{first_name}</b>!\n\n"
      f"<b>«Jadid kitoblar doʻkoni»</b> botiga xush kelibsiz! 📖\n"
      f"Kanalimiz: Jadid kitoblar do'koni\n\n"
      f"Quyidagi menyudan kerakli boʻlimni tanlang."
  )
  await message.answer(
      welcome_text,
      parse_mode="HTML",
      reply_markup=main_menu_keyboard(user_id),
      disable_web_page_preview=True,
  )


@dp.callback_query(lambda c: c.data == "check_sub")
async def process_check_sub(callback_query: types.CallbackQuery):
  user_id = callback_query.from_user.id
  first_name = callback_query.from_user.first_name
  username = callback_query.from_user.username

  is_subscribed = await check_subscription(user_id)

  if not is_subscribed:
    await callback_query.answer(
        "❌ Siz hali kanalga obuna bo'lmadingiz!", show_alert=True
    )
    return

  await callback_query.message.delete()
  save_user(user_id, first_name, username)

  welcome_text = (
      f"Rahmat, <b>{first_name}</b>! Obunangiz tasdiqlandi ✅\n\n"
      f"<b>«Jadid kitoblar doʻkoni»</b> botiga xush kelibsiz! 📖\n"
      f"Kanalimiz: Jadid kitoblar do'koni\n\n"
      f"Quyidagi menyudan kerakli boʻlimni tanlang."
  )
  await callback_query.message.answer(
      welcome_text,
      parse_mode="HTML",
      reply_markup=main_menu_keyboard(user_id),
      disable_web_page_preview=True,
  )


# Taklif havolasini yaratish (Har bir foydalanuvchiga kanal uchun unikal taklif havolasi yaratib beradi)
@dp.message(lambda msg: msg.text == "🔗 Taklif havolasi")
async def referral_link_handler(message: types.Message):
  user_id = message.from_user.id

  try:
    # Kanal uchun unikal taklif havolasi yaratish (Har bir foydalanuvchiga alohida link)
    invite_link_obj = await bot.create_chat_invite_link(
        chat_id=CHANNEL_USERNAME, name=f"User_{user_id}"
    )
    ref_link = invite_link_obj.invite_link

    # Linkni bazaga saqlab qo'yamiz, kim qo'shilganini aniqlash uchun
    update_user_invite_link(user_id, ref_link)

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📢 Kanalga o'tish", url=ref_link)]
        ]
    )

    text = (
        f"🔗 <b>Sizning shaxsiy taklif havolangiz:</b>\n"
        f"<code>{ref_link}</code>\n\n"
        f"Doʻstlaringizga shu havolani yuboring va ularni kanalga taklif qiling!"
    )
    await message.answer(
        text,
        parse_mode="HTML",
        reply_markup=keyboard,
        disable_web_page_preview=True,
    )
  except Exception as e:
    logging.error(f"Invite link yaratishda xatolik: {e}")
    await message.answer(
        "❌ Havola yaratishda xatolik yuz berdi. Bot kanalga administrator"
        " qilinganligini tekshiring."
    )


# Mening statistikamni chiqarish
@dp.message(lambda msg: msg.text == "📊 Mening statistikam")
async def stats_handler(message: types.Message):
  user_id = message.from_user.id
  ref_count = get_referral_count(user_id)

  text = (
      f"📊 <b>Sizning statistikangiz:</b>\n\n"
      f"👥 Siz taklif qilgan do'stlar soni: <b>{ref_count} ta</b>\n\n"
      f"Kanalimiz linkini do'stlaringizga yuboring va ularni taklif qiling!"
  )
  await message.answer(text, parse_mode="HTML", disable_web_page_preview=True)


# Top taklif qilganlar (Reyting)
@dp.message(lambda msg: msg.text == "🏆 Top taklif qilganlar")
async def leaderboard_handler(message: types.Message):
  top_users = get_leaderboard()
  if not top_users:
    await message.answer("🏆 Hozircha hech kim taklif qilmagan yoki reyting bo'sh.")
    return

  text = "🏆 <b>Eng ko'p taklif qilganlar (TOP-10):</b>\n\n"
  for idx, (first_name, username, count) in enumerate(top_users, start=1):
    user_display = (
        f"@{username}"
        if username
        else first_name
        if first_name
        else "Foydalanuvchi"
    )
    text += f"{idx}. {user_display} — <b>{count} ta</b>\n"

  await message.answer(text, parse_mode="HTML")


# Admin uchun natijalarni bekor qilish tugmasi
@dp.message(lambda msg: msg.text == "⚙️ Natijalarni bekor qilish (Admin)")
async def reset_handler(message: types.Message):
  if message.from_user.id != ADMIN_ID:
    await message.answer("⛔️ Sizda bu amalni bajarish uchun huquq yo'q!")
    return

  if reset_all_referrals():
    await message.answer(
        "✅ Barcha referral natijalari muvaffaqiyatli bekor qilindi (nolga"
        " tenglashtirildi)!"
    )
  else:
    await message.answer("❌ Natijalarni bekor qilishda xatolik yuz berdi.")


@dp.message(lambda msg: msg.text == "📚 Kitoblar katalogi")
async def catalog_handler(message: types.Message):
  await message.answer(
      f"📚 Kitoblar katalogi bilan tanishish uchun kanalimizga o'ting:"
      f" <a href='{CHANNEL_LINK}'>{CHANNEL_LINK}</a>",
      parse_mode="HTML",
      disable_web_page_preview=True,
  )


# Foydalanuvchi kanalga maxsus havola orqali qo'shilganda ishlaydiganhandler
@dp.chat_member(F.chat.username == CHANNEL_USERNAME.lstrip("@"))
async def track_chat_member(event: ChatMemberUpdated):
  # Faqat a'zo bo'lgan holatni tekshiramiz
  if (
      event.old_chat_member.status in ["left", "kicked"]
      and event.new_chat_member.status in ["member", "administrator", "creator"]
  ):
    user = event.new_chat_member.user
    invite_link = event.invite_link  # Foydalangan havola

    if invite_link and invite_link.invite_link:
      link_url = invite_link.invite_link
      # Bu havola kimga tegishli ekanligini bazadan topamiz
      referrer_id = get_user_by_invite_link(link_url)

      if referrer_id and referrer_id != user.id:
        # Bazaga foydalanuvchini va uning referrer_id sini yozamiz
        save_user(
            user_id=user.id,
            first_name=user.first_name,
            username=user.username,
            referrer_id=referrer_id,
            invite_link=link_url,
        )
        try:
          # Taklif qilgan odamga xabar yuborish
          await bot.send_message(
              chat_id=referrer_id,
              text=(
                  f"🎉 Tabriklaymiz! Sizning taklif havolangiz orqali"
                  f" <b>{user.first_name}</b> kanalimizga qoʻshildi! 👥"
              ),
              parse_mode="HTML",
          )
        except Exception as e:
          logging.error(f"Referrerga xabar yuborishda xatolik: {e}")


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
      dp.start_polling(
          bot,
          drop_pending_updates=True,
          allowed_updates=[
              "message",
              "callback_query",
              "chat_member",
              "my_chat_member",
          ],
      ),
  )


if __name__ == "__main__":
  asyncio.run(main())
          
