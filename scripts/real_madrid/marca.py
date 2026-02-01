import os
import asyncio
import requests
from bs4 import BeautifulSoup
from deep_translator import GoogleTranslator
from shared.database_service import get_collection, save_url, url_exists
from shared.telegram_service import send_photo_message
from dotenv import load_dotenv
from scripts.real_madrid.configs.marca_config import (
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

        articleBody = soup.find("div", class_="ue-l-article__body")
        articleHeaderContent = soup.find("div", class_="ue-l-article__header-content")

        if not all([articleBody, articleHeader]):
            print("Missing elements = Skipping")
            return None

        imageEle = articleBody.find("img", class_="ue-c-article__image")
        titleEle = articleHeaderContent.find("h1", class_="ue-c-article__headline")
        descEle = articleHeaderContent.find("p", class_="ue-c-article__standfirst")

        if not all([imageEle, titleEle, descEle]):
            print("Missing elements = Skipping")
            return None

        image = imageEle.get("src")
        title = translator.translate(titleEle.get_text(strip=True))
        desc = translator.translate(descEle.get_text(strip=True))

        caption = f"<b>{title}</b>\n" f"{desc}\n\n" f"المصدر: <b>صحيفة ماركا</b>"
        return caption, image
    except Exception:
        return None


print("\nmarca Script is Running...")

response = requests.get(
    url=NEWS_URL,
    headers=HEADERS,
    timeout=10,
)
responseCode = response.status_code

if responseCode == 200:
    print(f"Response Sucess: CODE IS: {responseCode}\n")
    soup = BeautifulSoup(response.text, "html.parser")
    articles = soup.find_all("article")
    newsLinks = []

    for article in articles:
        articleHeader = article.find("header")
        if not articleHeader:
            continue
        aTag = articleHeader.find("a")
        if not articleHeader:
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
                    print(f"Url For Check: {url}")
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
                print("Url saved to database successfully")
            print("\n✅ All Done - Exiting")
        except Exception as e:
            print(e)
