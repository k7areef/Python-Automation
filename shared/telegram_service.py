import telegram
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.error import TelegramError


async def send_photo_message(
    token, chat_id, caption, photo_url, source_url, buttonText
):
    bot = telegram.Bot(token)
    keyboard = [[InlineKeyboardButton(buttonText, url=source_url)]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    try:
        async with bot:
            await bot.send_photo(
                chat_id=chat_id,
                photo=photo_url,
                caption=caption,
                reply_markup=reply_markup,
                parse_mode=ParseMode.HTML,
                read_timeout=30,
                write_timeout=30,
            )
        return True

    except telegram.error.TimedOut:
        print("SEND TELEGRAM ERR: Timeout (Message might be sent)")
        return "TIMEOUT"

    except telegram.error.BadRequest as e:
        print(f"SEND TELEGRAM ERR: Bad Request (Won't reach): {e}")
        return False

    except Exception as e:
        print(f"SEND TELEGRAM ERR: General Error: {e}")
        return False


async def send_text_message(token, chat_id, text, buttonText, source_url):
    bot = telegram.Bot(token)

    keyboard = [[InlineKeyboardButton(buttonText, url=source_url)]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    try:
        async with bot:
            await bot.send_message(
                chat_id=chat_id,
                text=text,
                reply_markup=reply_markup,
                parse_mode=ParseMode.HTML,
            )
        return True

    except TelegramError as e:
        print(f"SEND TELEGRAM ERR: {e}")
        return False

    except Exception as e:
        print(f"SEND TELEGRAM ERR: {e}")
        return False
