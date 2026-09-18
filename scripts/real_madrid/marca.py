import os
import asyncio
import requests
import xml.etree.ElementTree as ET
from bs4 import BeautifulSoup
from shared.database_service import get_collection, save_to_database, url_exists
from shared.telegram_service import send_photo_message
from dotenv import load_dotenv
from scripts.real_madrid.configs.marca_config import (
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

# RSS Feed الرسمي لصحيفة ماركا (خاص بريال مدريد)
RSS_FEED_URL = "https://e00-marca.uecdn.es/rss/futbol/real-madrid.xml"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}


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


def getUrlData(url):
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        if response.status_code != 200:
            return None

        soup = BeautifulSoup(response.text, "html.parser")
        article = soup.find("article") or soup

        # Title & Image:
        titleEle = article.find("h1", class_=re.compile(r"ue-c-article__headline", re.I)) or article.find("h1")
        if not titleEle:
            return None

        raw_title = titleEle.get_text(strip=True)

        imageEle = article.find("img", class_=re.compile(r"ue-c-cover-content__image", re.I)) or article.find("img")
        imageUrl = ""
        if imageEle:
            imageUrl = imageEle.get("src") or imageEle.get("data-src") or ""

        # Subtitle & Desc:
        subTitleEle = article.find("p", class_=re.compile(r"ue-c-article__standfirst", re.I))
        raw_subTitle = subTitleEle.get_text(strip=True) if subTitleEle else ""

        pTags = article.find_all("p", class_=re.compile(r"ue-c-article__paragraph", re.I))
        raw_desc = pTags[0].get_text(strip=True)[:500] if pTags else ""

        # Author & Publish Date:
        authorEle = article.find("div", class_=re.compile(r"ue-c-article__byline-name", re.I)) or article.find("span", class_=re.compile(r"author", re.I))
        raw_author = authorEle.get_text(strip=True) if authorEle else "MARCA"

        publishedAtEle = article.find("div", class_=re.compile(r"ue-c-article__publishdate", re.I))
        raw_publishedAt = " ".join(publishedAtEle.get_text().split()) if publishedAtEle else ""

        # Batch translation in 1 request:
        raw_texts = [raw_title, raw_subTitle, raw_desc, raw_author, raw_publishedAt]
        translated = translate_batch(raw_texts)

        title, subTitle, desc, authorName, publishedAt = translated

        subTitle = ("\n" + subTitle + "\n") if subTitle else ""
        desc = "\n" + desc + "\n" if desc else ""
        caption = f"<b>{title}</b>\n{subTitle}{desc}\n\n{publishedAt}"

        return caption, imageUrl, authorName

    except Exception as e:
        print(f"Exception ERR in getUrlData: {e}")
        return None


def fetch_urls():
    try:
        print(f"Fetching RSS feed from Marca: {RSS_FEED_URL}")
        res = requests.get(RSS_FEED_URL, headers=HEADERS, timeout=10)
        if res.status_code != 200:
            print(f"Fail status code: {res.status_code}")
            return []

        urls = []
        root = ET.fromstring(res.content)
        for item in root.findall(".//item"):
            link = item.find("link")
            if link is not None and link.text:
                href = link.text.strip()
                if href not in urls:
                    urls.append(href)

        return urls
    except Exception as e:
        print(f"Error fetching Marca RSS: {e}")
        return []


print("\nmarca Script is Running...")

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
            data = getUrlData(url)

            if not data:
                print("❗ No data avaliable - Skipping")
                print(f"🔗 URL for checking: {url}\n")
                continue

            caption, imageUrl, authorName = data

            if not imageUrl:
                print("Missing Image URL - Skipping\n")
                continue

            imageResponse = requests.get(imageUrl, headers=HEADERS)
            if not imageResponse.status_code == 200:
                print("Fail to get image - Continue")
                continue

            from io import BytesIO
            photo = BytesIO(imageResponse.content)

            print("Send message to telegram - Sending...")
            status = asyncio.run(
                send_photo_message(
                    token=TELEGRAM_TOKEN_REAL_MADRID,
                    chat_id=TELEGRAM_CHAT_ID,
                    caption=caption,
                    photo_url=photo,
                    source_url=url,
                    buttonText=f"{authorName} عبر صحيفة ماركا",
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
