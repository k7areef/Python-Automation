import os
import re
import asyncio
import requests
from bs4 import BeautifulSoup
from shared.database_service import get_collection, save_url, url_exists
from shared.telegram_service import send_photo_message
from dotenv import load_dotenv
from scripts.masr.configs.gate_ahram_config import (
    NEWS_URL,
    HEADERS,
    COLLECTION_NAME,
    SOURCE_NAME,
)

load_dotenv()

# Secret Keys:
TELEGRAM_TOKEN_MASR_NEWS = os.getenv("TELEGRAM_TOKEN_MASR_NEWS")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
MONGO_URI = os.getenv("MONGO_URI")
if not all([TELEGRAM_TOKEN_MASR_NEWS, TELEGRAM_CHAT_ID, MONGO_URI]):
    raise Exception("Missing environment variables")


def getUrlData(url):
    try:
        response = requests.get(url, timeout=10)
        if response.status_code != 200:
            return None

        soup = BeautifulSoup(response.text, "html.parser")
        title = soup.find("h1", id="ContentPlaceHolder1_divTitle").get_text()
        imageContainer = soup.find("div", id="ContentPlaceHolder1_divMainImage")
        imageUrl = imageContainer.find("img", src=True).get("src")
        pTagsContainer = soup.find("div", id="ContentPlaceHolder1_divContent")
        pTags = pTagsContainer.find_all("p")
        desc = f""
        for p in pTags:
            desc += f"\n{p.get_text()}\n"
        cleanDesc = f"{desc[:1000]}..." if len(desc) > 1000 else desc

        caption = f"<b>{title}</b>\n" f"{cleanDesc}\n\n" f"المصدر: <b>{SOURCE_NAME}</b>"
        return caption, imageUrl
    except Exception:
        return None


print("gate_ahram Script is Running...")

response = requests.get(
    url=NEWS_URL,
    headers=HEADERS,
    timeout=10,
)

if response.status_code == 200:
    soup = BeautifulSoup(response.text, "html.parser")
    linkItems = soup.find_all(
        "div",
        id=re.compile(r"^ContentPlaceHolder1_dlNewsContentUrgent_divOuterNews_\d+$"),
    )

    urls = []
    if linkItems:
        linkItems.reverse()
        for linkItem in linkItems:
            urls.append(linkItem.find("a", href=True).get("href"))

    if urls:
        print("Getting articles from database...")
        masrArticlesNews = get_collection(
            uri=MONGO_URI, collection_name=COLLECTION_NAME, db_name="my_db"
        )
        print(f"Get articles from database successfully\n")

        for url in urls:

            if url_exists(collection=masrArticlesNews, url=url):
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
                    token=TELEGRAM_TOKEN_MASR_NEWS,
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
                collection=masrArticlesNews,
                data={"article_url": url, "source": SOURCE_NAME},
            )
            print("Url saved to database successfully")
    print("\n✅ All Done - Existting")
