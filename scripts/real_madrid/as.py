import os
import asyncio
import requests
from bs4 import BeautifulSoup
from deep_translator import GoogleTranslator
from shared.database_service import get_collection, save_url, url_exists
from shared.telegram_service import send_photo_message
from dotenv import load_dotenv
from scripts.real_madrid.configs.as_config import (
    NEWS_URL,
    HEADERS,
    COLLECTION_NAME,
    SOURCE_NAME,
)

load_dotenv()

# Secret Keys:
TELEGRAM_TOKEN_REAL_MADRID = os.getenv("TELEGRAM_TOKEN_REAL_MADRID")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
MONGO_URI = os.getenv("MONGO_URI")
if not all([TELEGRAM_TOKEN_REAL_MADRID, TELEGRAM_CHAT_ID, MONGO_URI]):
    raise Exception("Missing environment variables")
translator = GoogleTranslator(source="auto", target="ar")


def getUrlData(url):
    try:
        response = requests.get(url, timeout=10)
        if response.status_code != 200:
            return None

        soup = BeautifulSoup(response.text, "html.parser")
        articleContainer = soup.find("div", class_="wr-c")
        article = articleContainer.find("article")
        if not article:
            return None

        header = article.find("header")
        if not header:
            return None
        textContainer = header.find("div", class_="a_e_txt")
        title = translator.translate(
            textContainer.find("h1", class_="a_t").get_text(strip=True)
        )
        desc = translator.translate(
            textContainer.find(class_="a_st").get_text(strip=True)
        )
        imageContainer = header.find("div", class_="a_e_m")
        image = imageContainer.find("img").get("src")

        caption = f"<b>{title}</b>\n" f"{desc}\n\n" f"المصدر: <b>صحيفة اّس</b>"
        return caption, image
    except Exception:
        return None


print("as Script is Running...")

response = requests.get(
    url=NEWS_URL,
    headers=HEADERS,
    timeout=10,
)
if response.status_code == 200:
    soup = BeautifulSoup(response.text, "html.parser")
    linksContainer = soup.find("div", class_="b_gr b_gr-nh")
    articles = linksContainer.find_all("div", class_="s_h")

    newsLinks = []

    for article in articles:
        hTag = article.find("h3", class_="s_t")
        if not hTag:
            continue
        aTag = hTag.find("a")
        if not hTag:
            continue
        url = aTag.get("href")
        if not url:
            continue
        newsLinks.append(url)

    if newsLinks:
        # Reverse URLS:
        newsLinks.reverse()

        try:

            print("Getting articles from database...")
            realMadridArticlesCollection = get_collection(
                uri=MONGO_URI, collection_name=COLLECTION_NAME, db_name="my_db"
            )
            print(f"Get articles from database successfully\n")

            for url in newsLinks:
                if url_exists(collection=realMadridArticlesCollection, url=url):
                    print("Url in database - Skipping")
                    continue
                print("\nUrl not in database - Working")
                data = getUrlData(url)
                if not data:
                    print("Faild to get url page - Skipping")
                    continue
                caption, imageUrl = data
                # Send to telegram:
                print("Send message to telegram - Sending...")
                asyncio.run(
                    send_photo_message(
                        token=TELEGRAM_TOKEN_REAL_MADRID,
                        chat_id=TELEGRAM_CHAT_ID,
                        caption=caption,
                        photo_url=imageUrl,
                        source_url=url,
                    )
                )
                print("Message sended to telegram successfully")

                # Save to database:
                print("Save url to database - Saving...")
                save_url(
                    collection=realMadridArticlesCollection,
                    data={"article_url": url, "source": SOURCE_NAME},
                )
                print("Url saved to database successfully\n")
        except Exception as e:
            print(e)
