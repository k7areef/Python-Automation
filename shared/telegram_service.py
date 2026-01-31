import telegram
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode


async def send_photo_message(token, chat_id, caption, photo_url, source_url):
    bot = telegram.Bot(token)

    keyboard = [[InlineKeyboardButton("الخبر كامل من الموقع الرسمي", url=source_url)]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    async with bot:
        await bot.send_photo(
            chat_id=chat_id,
            photo=photo_url,
            caption=caption,
            reply_markup=reply_markup,
            parse_mode=ParseMode.HTML,
        )
