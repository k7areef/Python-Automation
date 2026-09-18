import re
import time
import requests
import asyncio
from io import BytesIO
from bs4 import BeautifulSoup
from deep_translator import GoogleTranslator

# Imports بناءً على هيكل المشروع عندك
from shared.database_service import url_exists, save_to_database, realMadridCollection
from shared.telegram_service import send_photo_message, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

BASE_URL = "https://www.marca.com"
NEWS_URL = f"{BASE_URL}/futbol/real-madrid.html"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
}

def get_articles_urls(response):
    soup = BeautifulSoup(response.content, "html.parser")
    urls = []
    for a in soup.find_all('a', href=True):
        href = a['href']
        if '/futbol/real-madrid/' in href and href.endswith('.html'):
            if not href.startswith('http'):
                href = f"{BASE_URL}{href}"
            if href not in urls:
                urls.append(href)
    return urls

def get_article_data(url):
    if "#" in url or "comentarios" in url:
        return None, None

    try:
        res = requests.get(url, headers=HEADERS, timeout=10)
        if res.status_code != 200:
            return None, None

        soup = BeautifulSoup(res.content, "html.parser")

        # Headline
        title_tag = soup.find("h1", class_=re.compile(r"ue-c-article__headline", re.I)) or soup.find("h1")
        caption = title_tag.get_text(strip=True) if title_tag else None

        # Author Name
        author_tag = soup.find("span", class_=re.compile(r"ue-c-article__byline-name", re.I)) or soup.find("ul", class_=re.compile(r"ue-c-article__author", re.I))
        authorName = author_tag.get_text(strip=True) if author_tag else "MARCA"

        # Translation
        if caption:
            try:
                caption = GoogleTranslator(source="auto", target="ar").translate(caption)
            except Exception as tr_err:
                print(f"Translation Error: {tr_err}")

        return caption, authorName

    except Exception as e:
        print(f"Error scraping {url}: {e}")
        return None, None

def articlesImageFetcher(url):
    try:
        res = requests.get(url, headers=HEADERS, timeout=10)
        if res.status_code != 200:
            return None
        soup = BeautifulSoup(res.content, "html.parser")
        img_tag = soup.find("img", class_=re.compile(r"ue-c-article__media", re.I)) or soup.find("picture")
        if img_tag:
            img = img_tag.find("img") if img_tag.name == "picture" else img_tag
            return img.get("src") or img.get("data-src")
        return None
    except Exception:
        return None

response = requests.get(NEWS_URL, headers=HEADERS)

if response.status_code == 200:
    print("marca Script is Running...")
    print(f"Response Sucess: CODE IS: {response.status_code}")
    print("Getting articles from database...")
    print("Get articles from database successfully\n")
    
    articles_urls = get_articles_urls(response)

    if articles_urls:
        try:
            for url in articles_urls:
                if url_exists(realMadridCollection, url):
                    continue

                print("⌛ Url not in database - Working")

                try:
                    data = get_article_data(url)
                    if isinstance(data, (list, tuple)) and len(data) == 2:
                        caption, authorName = data
                    else:
                        caption, authorName = None, None
                except Exception as e:
                    print(f"Exception ERR: {e}")
                    caption, authorName = None, None

                if not all([caption, authorName]):
                    print("❗ No data avaliable - Skipping")
                    print(f"🔗 URL for checking: {url}\n")
                    continue

                imageUrl = articlesImageFetcher(url)
                if not imageUrl:
                    continue

                imageUrl = re.sub(r"(?<=/)\d+x\d+(?=/)", "1200x675", imageUrl)
                imageResponse = requests.get(imageUrl, headers=HEADERS)

                if not imageResponse.status_code == 200:
                    print("Fail to get image")
                    continue

                photo = BytesIO(imageResponse.content)

                # Send to telegram:
                print("Send message to telegram...")
                status = asyncio.run(
                    send_photo_message(
                        token=TELEGRAM_BOT_TOKEN,
                        chat_id=TELEGRAM_CHAT_ID,
                        caption=caption,
                        photo_url=photo,
                        source_url=url,
                        buttonText=f"Read on {authorName}"
                    )
                )

                if status == True or status == "success":
                    # Save to database:
                    print("Save url to database...")
                    save_to_database(
                        collection=realMadridCollection,
                        data={"article_url": url}
                    )
                    print("✅ Url saved to database")
                else:
                    print("Message fail to send")

                time.sleep(2)

            print("\n✅ All Done - Exiting")

        except Exception as e:
            print(e)
    else:
        raise Exception("Urls not avaliable")

else:
    raise Exception(f"🚫 Request Fail: {response.status_code} - Exiting...")
