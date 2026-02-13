import os
import asyncio
import requests
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


# Get Article Data:
def getArticleData(url):
    try:

        title = ""
        imageUrl = ""
        subtitle = ""
        desc = ""

        response = requests.get(url, timeout=10)
        if response.status_code != 200:
            return None

        soup = BeautifulSoup(response.text, "html.parser")
        article = soup.find("article")
        if not article:
            return None

        titleEle = article.find("h1", class_="news-detail__title")
        imageEle = article.find("img", class_="news-detail__img", src=True)

        if not all({titleEle, imageEle}):
            print("🚫 Missing Elements - Skipping")
            return None

        title = titleEle.get_text(strip=True)
        imageUrl = imageEle.get("src")

        subtitleEle = article.find("div", class_="news-detail__excerpt")
        if subtitleEle:
            subtitle = subtitleEle.find("p").get_text(strip=True)
            subtitle = ("\n\n" + subtitle + "\n") if subtitle else ""

        descriptionContainers = article.find_all(
            "div", class_="news-detail__main--text"
        )
        if descriptionContainers:
            for descriptionContainer in descriptionContainers:
                pTags = descriptionContainer.find_all("p")
                if not pTags:
                    continue
                desc += "\n" +  pTags[0].get_text(strip=True)

        if desc:
            desc = "\n" + f"{desc[:800]}..." if len(desc) > 800 else desc + "\n"

        caption = (
            f"<b>نشر الموقع الرسمي لريال مدريد</b>\n\n"
            f"<b>{title}</b>"
            f"{subtitle}"
            f"{desc}"
        )

        return caption, imageUrl
    except Exception:
        return None


# Start Print:
print("Run Real Madrid.Official News Script")
# Start Request:
response = requests.get(
    url=NEWS_URL,
    headers=HEADERS,
    timeout=10,
)
if response.status_code == 200:
    soup = BeautifulSoup(response.text, "html.parser")
    articles = soup.find_all("app-news-item")
    articlesImages = {}
    urls = []

    if articles:
        print("Articles avalibale - Start Working\n")
        for article in articles:
            image = article.find("img", class_="rm-news-item__image", src=True)
            link = article.find("a", href=True)
            if not all([link, image]):
                continue
            url = link.get("href")
            url = f"{BASE_URL}{url}"
            urls.append(url)
            imageUrl = image.get("src")
            articlesImages[url] = imageUrl
    else:
        print("No articles avaliable - Exitting...")

    if urls:
        urls.reverse()

        try:

            print("Getting articles from database...")
            realMadridArticlesCollection = get_collection(
                uri=MONGO_URI, collection_name=COLLECTION_NAME, db_name="my_db"
            )
            print(f"✅ Get articles from database successfully\n")

            for url in urls:
                if url_exists(collection=realMadridArticlesCollection, url=url):
                    print(f"\n🔗 Url: {url}")
                    print("❗ Url in database - Skipping")
                    continue

                print("\n⌛ Url not in database - Working")
                data = getArticleData(url)
                if not data:
                    print(f"Url: {url}")
                    print("🚫 Faild to get article data - Skipping")
                    continue
                caption, imageUrl = data

                # Send to telegram:
                print("- Send message to telegram - Sending...")
                isSuccessSend = asyncio.run(
                    send_photo_message(
                        token=TELEGRAM_TOKEN_REAL_MADRID,
                        chat_id=TELEGRAM_CHAT_ID,
                        caption=caption,
                        photo_url=imageUrl,
                        source_url=url,
                    )
                )
                if not isSuccessSend:
                    print("- Message not send to telegram - Skipping")
                    continue
                print("✅ Message sended to telegram successfully")

                # Save to database:
                print("Save url to database - Saving...")
                save_to_database(
                    collection=realMadridArticlesCollection,
                    data={"article_url": url, "source": SOURCE_NAME},
                )
                print("✅ Url saved to database successfully")

            print("\n✅ Script End - Exitting...")
        except Exception as e:
            print(e)
    else:
        print("Urls not avalibale - Exitting...")
else:
    print(f"🚫 Request Fail: {response.status_code} - Exitting...")
