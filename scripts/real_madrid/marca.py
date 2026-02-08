import os
import re
import asyncio
import requests
from io import BytesIO
from bs4 import BeautifulSoup
from deep_translator import GoogleTranslator
from shared.database_service import get_collection, save_to_database, url_exists
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

        title = ""
        subTitle = ""
        desc = ""
        authorName = ""
        publishedAt = ""

        response = requests.get(url, timeout=10)
        if response.status_code != 200:
            return None

        soup = BeautifulSoup(response.text, "html.parser")
        article = soup.find("article")

        titleEle = article.find("h1", class_="ue-c-article__headline")
        if not titleEle:
            print("Missing elements - Skipping\n")
            return None

        title = translator.translate(titleEle.get_text(strip=True))

        subTitleEle = article.find("p", class_="ue-c-article__standfirst")
        if subTitleEle:
            subTitle = translator.translate(subTitleEle.get_text(strip=True))

        pTags = article.find_all("p", class_="ue-c-article__paragraph")
        if pTags:
            for p in pTags:
                desc += p.get_text(strip=True)

        desc = translator.translate(desc)
        desc = f"{desc[:700]}..." if len(desc) > 700 else desc

        # Author:
        authorEle = article.find("div", class_="ue-c-article__byline-name")
        authorName = translator.translate(authorEle.get_text(strip=True))

        # Published At:
        publishedAtEle = article.find("div", class_="ue-c-article__publishdate")
        if publishedAtEle:
            publishedAt = " ".join(publishedAtEle.get_text().split())
            publishedAt = translator.translate(publishedAt)

        subTitle = ("\n" + subTitle + "\n") if subTitle else ""
        desc = "\n" + desc + "\n" if desc else ""

        caption = (
            f"<b>نشر {authorName} عبر صحيفة ماركا</b>\n\n"
            f"<b>{title}</b>\n"
            f"{subTitle}"
            f"{desc}"
            f"\n\n{publishedAt}"
        )
        return caption
    except Exception as e:
        print(f"Exception ERR: {e}")
        return None


print("\nmarca Script is Running...")

response = requests.get(
    url=NEWS_URL,
    headers=HEADERS,
    timeout=10,
)
responseCode = response.status_code

if responseCode == 200:

    # Start
    print(f"Response Sucess: CODE IS: {responseCode}")
    soup = BeautifulSoup(response.text, "html.parser")
    articles = soup.find_all("article")
    articlesImages = {}
    urls = []

    if articles:
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
            urls.append(url)

            imageEle = article.find("img", class_="ue-c-cover-content__image")
            if not imageEle:
                continue
            imageSrc = imageEle.get("src")
            articlesImages[url] = imageSrc
    else:
        raise Exception("No articles avaliable - Exitting...")

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
                if url_exists(collection=realMadridArticlesCollection, url=url):
                    print("Url in database - Continue")
                    continue
                print("Url not in database - Working")
                caption = getUrlData(url)
                if not caption:
                    continue
                imageUrl = articlesImages.get(url)
                imageUrl = re.sub(r"(?<!:)//", "/", imageUrl)
                imageResponse = requests.get(imageUrl, headers=HEADERS)
                if not imageResponse.status_code == 200:
                    print("Fail to get image - Continue")
                    continue
                photo = BytesIO(imageResponse.content)
                # Send to telegram:
                print("Send message to telegram - Sending...")
                isSuccessSend = asyncio.run(
                    send_photo_message(
                        token=TELEGRAM_TOKEN_REAL_MADRID,
                        chat_id=TELEGRAM_CHAT_ID,
                        caption=caption,
                        photo_url=photo,
                        source_url=url,
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
        raise Exception("Urls not avalibale - Exitting...")
    # End

else:
    raise Exception(f"🚫 Request Fail: {response.status_code} - Exitting...")
