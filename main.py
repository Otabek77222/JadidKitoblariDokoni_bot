import asyncio
import logging

from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

BOT_TOKEN = "8813903836:AAFJyQuFnTqm8w0KBnpoU7-7pnfFJFOoSww"

CHANNEL_USERNAME = "@jadid_kitoblar_dokoni"
CHANNEL_LINK = "https://t.me/jadid_kitoblar_dokoni"

dp = Dispatcher()


def subscribe_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📢 Kanalga obuna bo‘lish",
                    url=CHANNEL_LINK
                )
            ],
            [
                InlineKeyboardButton(
                    text="✅ Obunani tekshirish",
                    callback_data="check_subscription"
                )
            ]
        ]
    )


async def is_subscribed(bot: Bot, user_id: int):
    try:
        member = await bot.get_chat_member(
            chat_id=CHANNEL_USERNAME,
            user_id=user_id
        )

        return member.status in [
            "member",
            "administrator",
            "creator"
        ]

    except Exception as e:
        logging.error(e)
        return False


@dp.message(CommandStart())
async def start_handler(message: types.Message, bot: Bot):

    if await is_subscribed(bot, message.from_user.id):

        await message.answer(
            "🎉 Xush kelibsiz!\n\n"
            "Siz kanalimizga obuna bo‘lgansiz.\n"
            "📚 Jadid kitoblar do‘konidan foydalanishingiz mumkin."
        )

    else:

        await message.answer(
            "📚 <b>Jadid kitoblar do‘koni</b>\n\n"
            "Botdan foydalanish uchun avval "
            "kanalimizga obuna bo‘ling 👇",
            reply_markup=subscribe_keyboard(),
            parse_mode="HTML"
        )


@dp.callback_query(lambda c: c.data == "check_subscription")
async def check_subscription(
    callback: types.CallbackQuery,
    bot: Bot
):

    if await is_subscribed(
        bot,
        callback.from_user.id
    ):

        await callback.message.edit_text(
            "🎉 <b>Tabriklaymiz!</b>\n\n"
            "Siz kanalimizga muvaffaqiyatli obuna bo‘lgansiz.\n\n"
            "📚 Jadid kitoblar do‘koniga xush kelibsiz!",
            parse_mode="HTML"
        )

        await callback.answer(
            "✅ Obunangiz tasdiqlandi!"
        )

    else:

        await callback.answer(
            "❌ Siz hali kanalga obuna bo‘lmagansiz.",
            show_alert=True
        )


async def main():

    logging.basicConfig(level=logging.INFO)

    bot = Bot(token=BOT_TOKEN)

    print("🤖 Bot ishga tushdi...")

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
