import os
import re
import asyncio
import requests
from io import BytesIO
from bs4 import BeautifulSoup
from shared.database_service import get_collection, save_to_database, url_exists
from shared.telegram_service import send_photo_message
from dotenv import load_dotenv
from scripts.real_madrid.configs.official_news_config import (
    BASE_URL,
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


def translate_batch(texts):
    """ترجمة مجموعة نصوص في طلب واحد لتفادي Rate Limits"""
    if not texts or not any(texts):
        return texts

    joined_text = " ||| ".join(texts)
    url = f"https://api.mymemory.translated.net/get?q={requests.utils.quote(joined_text)}&langpair=es|ar"

    for attempt in range(3):
        try:
            res = requests.get(url, timeout=10)
            if res.status_code == 200:
                data = res.json()
                translated_joined = data.get("responseData", {}).get("translatedText", "")
                if translated_joined:
                    translated_list = translated_joined.split(" ||| ")
                    if len(translated_list) == len(texts):
                        return translated_list
        except Exception as e:
            print(f"Translation ERR (Attempt {attempt + 1}): {e}")

    return texts


def getArticleData(url):
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        if response.status_code != 200:
            return None

        soup = BeautifulSoup(response.text, "html.parser")
        article = soup.find("article") or soup

        titleEle = article.find("h1", class_="news-detail__title") or article.find("h1")
        imageEle = article.find("img", class_="news-detail__img", src=True) or article.find("img", src=True)

        if not titleEle or not imageEle:
            return None

        raw_title = titleEle.get_text(strip=True)
        imageUrl = imageEle.get("src") or ""

        # Extract Subtitle & Description:
        subtitleEle = article.find("div", class_="news-detail__excerpt")
        raw_subtitle = ""
        if subtitleEle:
            pTag = subtitleEle.find("p")
            if pTag:
                raw_subtitle = pTag.get_text(strip=True)

        raw_desc = ""
        descriptionContainers = article.find_all("div", class_="news-detail__main--text")
        if descriptionContainers:
            pTag = descriptionContainers[0].find("p")
            if pTag:
                raw_desc = pTag.get_text(strip=True)[:500]

        # Batch translation:
        raw_texts = [raw_title, raw_subtitle, raw_desc]
        translated = translate_batch(raw_texts)
        title, subtitle, desc = translated

        subtitle = f"\n\n{subtitle}" if subtitle else ""
        desc = f"\n\n{desc}" if desc else ""

        caption = f"<b>{title}</b>{subtitle}{desc}"

        return caption, imageUrl

    except Exception as e:
        print(f"Exception ERR in getArticleData: {e}")
        return None


def fetch_urls():
    try:
        print(f"Fetching official news from: {NEWS_URL}")
        response = requests.get(NEWS_URL, headers=HEADERS, timeout=10)
        if response.status_code != 200:
            print(f"Fail status code: {response.status_code}")
            return []

        soup = BeautifulSoup(response.text, "html.parser")
        articles = soup.find_all("app-news-item")
        urls = []

        if articles:
            for article in articles:
                link = article.find("a", href=True)
                image = article.find("img", class_="rm-news-item__image", src=True)
                if not link or not image:
                    continue
                url = link.get("href")
                if not url.startswith("http"):
                    url = f"{BASE_URL}{url}"
                if url not in urls:
                    urls.append(url)

        return urls
    except Exception as e:
        print(f"Error fetching Official News: {e}")
        return []


print("\nOfficial News Script is Running...")

urls = fetch_urls()

if urls:
    urls.reverse()

    try:
        print("Getting articles from database...")
        realMadridArticlesCollection = get_collection(
            uri=MONGO_URI, collection_name=COLLECTION_NAME, db_name="my_db"
        )
        print("Get articles from database successfully\n")

        for url in urls:
            print(url)
            if url_exists(collection=realMadridArticlesCollection, url=url):
                print("☑️ Url in database - Continue")
                continue

            print("\n⌛ Url not in database - Working")
            data = getArticleData(url)

            if not data:
                print("❗ No data available - Skipping")
                print(f"🔗 URL for checking: {url}\n")
                continue

            caption, imageUrl = data

            if not imageUrl:
                print("Missing Image URL - Skipping\n")
                continue

            imageResponse = requests.get(imageUrl, headers=HEADERS)
            if imageResponse.status_code != 200:
                print("Fail to get image - Continue")
                continue

            photo = BytesIO(imageResponse.content)

            print("Send message to telegram - Sending...")
            status = asyncio.run(
                send_photo_message(
                    token=TELEGRAM_TOKEN_REAL_MADRID,
                    chat_id=TELEGRAM_CHAT_ID,
                    caption=caption,
                    photo_url=photo,
                    source_url=url,
                    buttonText="الموقع الرسمي لريال مدريد",
                )
            )

            if status == True or status == "TIMEOUT":
                print("Save url to database - Saving...")
                save_to_database(
                    collection=realMadridArticlesCollection,
                    data={"article_url": url, "source": SOURCE_NAME},
                )
                print("✅ Url saved to database successfully\n")
            else:
                print("Message failed strictly. Not saving to DB - Skipping\n")

        print("\n✅ All Done - Exiting")

    except Exception as e:
        print(e)
else:
    print("🚫 Urls not available - Exiting...")
