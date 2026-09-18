import os
import asyncio
import requests
from bs4 import BeautifulSoup
from shared.database_service import get_collection, save_to_database, url_exists
from shared.telegram_service import send_photo_message
from dotenv import load_dotenv
from scripts.real_madrid.configs.as_config import (
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

# RSS Feed الخاص ببرشلونة/ريال مدريد في صحيفة أس (ضد الحظر)
RSS_FEED_URL = "https://as.com/rss/futbol/real_madrid.xml"

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

        titleEle = article.find("h1", class_="a_t") or article.find("h1")
        imageContainerEle = article.find("div", class_="a_e_m") or article.find("figure")
        if not titleEle:
            return None

        raw_title = titleEle.get_text(strip=True)
        img_tag = imageContainerEle.find("img") if imageContainerEle else article.find("img")
        imageUrl = img_tag.get("src") or img_tag.get("data-src") if img_tag else ""

        authorEle = article.find("a", class_="a_md_a_n") or article.find("span", class_="a_md_a_n")
        raw_authorName = authorEle.get_text(strip=True) if authorEle else "صحيفة أس"

        subTitleEle = article.find(class_="a_st")
        raw_subTitle = subTitleEle.get_text(strip=True) if subTitleEle else ""
        if len(raw_subTitle) > 800:
            raw_subTitle = raw_subTitle[:800]

        publishedAtEle = article.find("div", class_="a_md_f") or article.find("time")
        raw_publishedAt = publishedAtEle.get_text(strip=True) if publishedAtEle else ""

        raw_texts = [raw_title, raw_subTitle, raw_authorName, raw_publishedAt]
        translated = translate_batch(raw_texts)

        title, subTitle, authorName, publishedAt = translated

        if subTitle:
            subTitle = f"\n\n{subTitle}"

        caption = f"<b>{title}</b>{subTitle}\n\n{publishedAt}"
        return caption, imageUrl, authorName

    except Exception as e:
        print(f"Exception ERR in getUrlData: {e}")
        return None


print("Run Real Madrid.As Script")

try:
    response = requests.get(RSS_FEED_URL, headers=HEADERS, timeout=10)
    if response.status_code == 200:
        soup = BeautifulSoup(response.content, "xml")
        items = soup.find_all("item")
        urls = []

        for item in items:
            link = item.find("link")
            if link and link.text:
                urls.append(link.text.strip())

        if urls:
            urls.reverse()

            print("Getting articles from database...")
            realMadridArticlesCollection = get_collection(
                uri=MONGO_URI, collection_name=COLLECTION_NAME, db_name="my_db"
            )
            print(f"Get articles from database successfully\n")

            for url in urls:
                print(url)
                if url_exists(collection=realMadridArticlesCollection, url=url):
                    print("☑️ Url in database - Skipping")
                    continue

                print("\n⌛ Url not in database - Working")
                data = getUrlData(url)
                if not data:
                    print("Faild to get url page - Skipping\n")
                    continue

                caption, imageUrl, authorName = data

                if not imageUrl:
                    print("Missing Image URL - Skipping\n")
                    continue

                print("Send message to telegram - Sending...")
                status = asyncio.run(
                    send_photo_message(
                        token=TELEGRAM_TOKEN_REAL_MADRID,
                        chat_id=TELEGRAM_CHAT_ID,
                        caption=caption,
                        photo_url=imageUrl,
                        source_url=url,
                        buttonText=f"{authorName} عبر صحيفة ٱس",
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
        else:
            print("Urls not avalibale - Exitting...")
    else:
        print(f"🚫 Request Fail: {response.status_code} - Exitting...")
except Exception as e:
    print(f"Error fetching RSS: {e}")
