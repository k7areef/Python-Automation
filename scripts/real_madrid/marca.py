import os
import re
import time
import asyncio
import requests
from io import BytesIO
from bs4 import BeautifulSoup
from googletrans import Translator
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

TELEGRAM_TOKEN_REAL_MADRID = os.getenv("TELEGRAM_TOKEN_REAL_MADRID")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
MONGO_URI = os.getenv("MONGO_URI")

if not all([TELEGRAM_TOKEN_REAL_MADRID, TELEGRAM_CHAT_ID, MONGO_URI]):
    raise Exception("Missing environment variables")

translator = Translator()

async def safe_translate(text):
    if not text:
        return ""
    for attempt in range(3):
        try:
            res = await translator.translate(text, dest="ar")
            if res and res.text:
                return res.text
        except Exception as e:
            print(f"Translation retry {attempt + 1} failed: {e}")
            await asyncio.sleep(2)
    return text

async def getUrlData(url):
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        if response.status_code != 200:
            return None

        soup = BeautifulSoup(response.text, "html.parser")
        article = soup.find("article") or soup

        titleEle = article.find("h1", class_=re.compile(r"ue-c-article__headline", re.I)) or article.find("h1")
        if not titleEle:
            print("❗ Missing elements - Skipping")
            print(f"🔗 URL for checking: {url}\n")
            return None

        raw_title = titleEle.get_text(strip=True)
        title = await safe_translate(raw_title)

        subTitleEle = article.find("p", class_=re.compile(r"ue-c-article__standfirst", re.I))
        subTitle = await safe_translate(subTitleEle.get_text(strip=True)) if subTitleEle else ""

        pTags = article.find_all("p", class_=re.compile(r"ue-c-article__paragraph", re.I))
        if pTags:
            desc_text = pTags[0].get_text(strip=True)[:700]
            desc = await safe_translate(desc_text)
        else:
            desc = ""

        authorEle = article.find("div", class_=re.compile(r"ue-c-article__byline-name", re.I)) or article.find("span", class_=re.compile(r"author", re.I))
        authorName = await safe_translate(authorEle.get_text(strip=True)) if authorEle else "MARCA"

        publishedAtEle = article.find("div", class_=re.compile(r"ue-c-article__publishdate", re.I))
        publishedAt = await safe_translate(" ".join(publishedAtEle.get_text().split())) if publishedAtEle else ""

        subTitle = ("\n" + subTitle + "\n") if subTitle else ""
        desc = "\n" + desc + "\n" if desc else ""
        caption = f"<b>{title}</b>\n" f"{subTitle}" f"{desc}" f"\n\n{publishedAt}"

        return caption, authorName

    except Exception as e:
        print(f"Exception ERR: {e}")
        return None

async def main():
    print("\nmarca Script is Running...")

    response = requests.get(
        url=NEWS_URL,
        headers=HEADERS,
        timeout=10,
    )

    responseCode = response.status_code

    if responseCode == 200:
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
                if not aTag:
                    continue

                url = aTag.get("href")
                if not url:
                    continue

                urls.append(url)

                imageEle = article.find("img", class_=re.compile(r"ue-c-cover-content__image", re.I)) or article.find("img")
                if not imageEle:
                    continue

                imageSrc = imageEle.get("src") or imageEle.get("data-src")
                if imageSrc:
                    articlesImages[url] = imageSrc
        else:
            raise Exception("No articles avaliable - Exitting...")

        if urls:
            urls.reverse()
            try:
                print("Getting articles from database...")
                realMadridArticlesCollection = get_collection(
                    uri=MONGO_URI, collection_name=COLLECTION_NAME, db_name="my_db"
                )
                print(f"Get articles from database successfully\n")

                for url in urls:
                    if url_exists(collection=realMadridArticlesCollection, url=url):
                        print("☑️ Url in database - Continue")
                        continue

                    print("\n⌛ Url not in database - Working")
                    data = await getUrlData(url)

                    if not data:
                        print("❗ No data avaliable - Skipping")
                        print(f"🔗 URL for checking: {url}\n")
                        continue

                    caption, authorName = data

                    imageUrl = articlesImages.get(url)
                    if not imageUrl:
                        continue

                    imageUrl = re.sub(r"(?<!:)//", "/", imageUrl)
                    imageResponse = requests.get(imageUrl, headers=HEADERS)

                    if not imageResponse.status_code == 200:
                        print("Fail to get image - Continue")
                        continue

                    photo = BytesIO(imageResponse.content)

                    print("Send message to telegram - Sending...")
                    status = await send_photo_message(
                        token=TELEGRAM_TOKEN_REAL_MADRID,
                        chat_id=TELEGRAM_CHAT_ID,
                        caption=caption,
                        photo_url=photo,
                        source_url=url,
                        buttonText=f"{authorName} عبر صحيفة ماركا",
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
            raise Exception("Urls not avalibale - Exitting...")
    else:
        raise Exception(f"🚫 Request Fail: {response.status_code} - Exitting...")

if __name__ == "__main__":
    asyncio.run(main())
