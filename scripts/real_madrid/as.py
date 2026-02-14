import os
import asyncio
import requests
from bs4 import BeautifulSoup
from deep_translator import GoogleTranslator
from shared.database_service import get_collection, save_to_database, url_exists
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

        title = ""
        imageUrl = ""
        subTitle = ""
        authorName = ""
        publishedAt = ""

        response = requests.get(url, timeout=10)
        if response.status_code != 200:
            return None

        soup = BeautifulSoup(response.text, "html.parser")
        article = soup.find("article")
        if not article:
            return None

        # Image and Title:
        titleEle = article.find("h1", class_="a_t")
        imageContainerEle = article.find("div", class_="a_e_m")
        if not all([titleEle, imageContainerEle]):
            return None
        title = translator.translate(titleEle.get_text(strip=True))
        imageUrl = imageContainerEle.find("img").get("src")

        # Author:
        authorEle = article.find("a", class_="a_md_a_n")
        authorName = translator.translate(authorEle.get_text(strip=True))

        # Description:
        subTitleEle = article.find(class_="a_st")
        if subTitleEle:
            subTitle = translator.translate(subTitle.get_text(strip=True))
        if subTitle:
            if len(subTitle) > 800:
                subTitle = f"{subTitle[:800]}...\n\n"
            else:
                subTitle = f"\n\n{subTitle}"

        # Published At:
        publishedAtEle = article.find("div", class_="a_md_f")
        if publishedAtEle:
            publishedAt = translator.translate(publishedAtEle.get_text(strip=True))

        caption = f"<b>{title}</b>" f"{subTitle}" f"\n\n{publishedAt}"
        return caption, imageUrl, authorName
    except Exception:
        return None


print("Run Real Madrid.As Script")

response = requests.get(
    url=NEWS_URL,
    headers=HEADERS,
    timeout=10,
)
if response.status_code == 200:

    # Start
    soup = BeautifulSoup(response.text, "html.parser")
    linksContainer = soup.find("div", class_="b_gr b_gr-nh")
    articles = linksContainer.find_all("div", class_="s_h")
    urls = []

    if articles:
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
            urls.append(url)
    else:
        print("No articles avaliable - Exitting...")

    if urls:
        # Reverse URLS:
        urls.reverse()

        try:

            print("Getting articles from database...")
            realMadridArticlesCollection = get_collection(
                uri=MONGO_URI, collection_name=COLLECTION_NAME, db_name="my_db"
            )
            print(f"Get articles from database successfully\n")

            for url in urls:
                print(url)
                if url_exists(collection=realMadridArticlesCollection, url=url):
                    print("Url in database - Skipping")
                    continue
                print("\nUrl not in database - Working")
                data = getUrlData(url)
                if not data:
                    print("Faild to get url page - Skipping\n")
                    continue
                caption, imageUrl, authorName = data
                # Send to telegram:
                print("Send message to telegram - Sending...")
                isSuccessSend = asyncio.run(
                    send_photo_message(
                        token=TELEGRAM_TOKEN_REAL_MADRID,
                        chat_id=TELEGRAM_CHAT_ID,
                        caption=caption,
                        photo_url=imageUrl,
                        source_url=url,
                        buttonText=f"{authorName} عبر صحيفة ٱس",
                    )
                )
                if not isSuccessSend:
                    print("Message not send to telegram - Skipping\n")
                    continue
                print("Message sended to telegram successfully")

                # Save to database:
                print("Save url to database - Saving...")
                save_to_database(
                    collection=realMadridArticlesCollection,
                    data={"article_url": url, "source": SOURCE_NAME},
                )
                print("Url saved to database successfully")

            print("✅ All Done - Exiting")
        except Exception as e:
            print(e)
    else:
        print("Urls not avalibale - Exitting...")
    # End

else:
    print(f"🚫 Request Fail: {response.status_code} - Exitting...")
