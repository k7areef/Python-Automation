import os
import asyncio
import requests
from bs4 import BeautifulSoup
from shared.database_service import get_collection, save_url, url_exists
from shared.telegram_service import send_photo_message
from dotenv import load_dotenv
from scripts.real_madrid.configs.official_news_config import (
    BASE_URL,
    NEWS_URL,
    HEADERS,
    COLLECTION_NAME,
)

load_dotenv()

# Secret Keys:
TELEGRAM_TOKEN_REAL_MADRID = os.getenv("TELEGRAM_TOKEN_REAL_MADRID")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
MONGO_URI = os.getenv("MONGO_URI")
if not all([TELEGRAM_TOKEN_REAL_MADRID, TELEGRAM_CHAT_ID, MONGO_URI]):
    raise Exception("Missing environment variables")


def getUrlData(url):
    try:
        response = requests.get(url, timeout=10)
        if response.status_code != 200:
            return None

        soup = BeautifulSoup(response.text, "html.parser")
        article = soup.find("article")
        if not article:
            return None

        header = article.find("header")
        if not header:
            return None

        title = header.find("h1").get_text(strip=True)
        desc = (
            header.find("div", class_="news-detail__excerpt")
            .find("p")
            .get_text(strip=True)
        )
        image = header.find("img", class_="news-detail__img").get("src")

        caption = f"<b>{title}</b>\n{desc}"
        return caption, image
    except Exception:
        return None


print("official_news Script is Running...")

newsListsElements = []
response = requests.get(
    url=NEWS_URL,
    headers=HEADERS,
    timeout=10,
)
if response.status_code == 200:
    soup = BeautifulSoup(response.text, "html.parser")
    newsListsElements = soup.find_all("div", class_="rm-news__list")

    if newsListsElements:

        urlsExtracted = []
        newsUrlsList = []

        # Extrac Urls:
        for newsList in newsListsElements:
            links = newsList.find_all("a", href=True)
            for link in links:
                urlsExtracted.append(f"{BASE_URL}{link.get('href')}")

        # Set Urls:
        urlsExtracted.reverse()

        for url in urlsExtracted:
            newsUrlsList.append(url)

        try:

            print("Getting articles from database...")
            realMadridArticlesCollection = get_collection(
                uri=MONGO_URI, collection_name=COLLECTION_NAME, db_name="my_db"
            )
            print(f"Get articles from database successfully\n")

            for url in newsUrlsList:
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
                save_url(collection=realMadridArticlesCollection, url=url)
                print("Url saved to database successfully\n")

            print("Script End - Exitting...")
        except Exception as e:
            print(e)
