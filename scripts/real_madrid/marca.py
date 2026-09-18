import os
import re
import html
import requests
from bs4 import BeautifulSoup

# --- CONFIGURATION ---
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

MARCA_URL = "https://www.marca.com/futbol/real-madrid.html?intcmp=MENUMARCA&s_kw=real-madrid"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    )
}

# --- HELPER FUNCTIONS ---
def clean_html(text):
    """تنظيف النص من أي وسم HTML غير مدعوم في تليجرام لمنع فشل الإرسال"""
    if not text:
        return ""
    text = html.unescape(text)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</?p>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\n\s*\n", "\n\n", text)
    return text.strip()

def escape_html_entities(text):
    """تشفير العلامات الخاصة لمنع كسر الـ HTML Parser في تليجرام"""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

def translate_batch(texts):
    """ترجمة مجموعة نصوص دفعة واحدة باستخدام Google Translate GTX (مجاني وبدون Limit)"""
    if not texts or not any(texts):
        return texts

    joined_text = " ||| ".join(texts)
    try:
        url = f"https://translate.googleapis.com/translate_a/single?client=gtx&sl=es&tl=ar&dt=t&q={requests.utils.quote(joined_text)}"
        res = requests.get(url, headers=HEADERS, timeout=12)

        if res.status_code == 200:
            result = res.json()
            # تجميع أجزاء الترجمة (علشان لو النص طويل جيلبرت بيقسمه)
            translated_joined = "".join([item[0] for item in result[0] if item and item[0]])
            translated_list = translated_joined.split(" ||| ")

            if len(translated_list) == len(texts):
                return [t.strip() for t in translated_list]
    except Exception as e:
        print(f"❌ Translation Error: {e}")

    return texts

def send_telegram_photo(photo_url, caption):
    """إرسال الخبر بالصورة وتحديد HTML Parse Mode"""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "photo": photo_url,
        "caption": caption,
        "parse_mode": "HTML"
    }
    try:
        res = requests.post(url, json=payload, timeout=15)
        return res.status_code == 200
    except Exception as e:
        print(f"❌ Telegram Send Error: {e}")
        return False

# --- ARTICLE SCRAPING ---
def get_article_details(article_url):
    """سحب تفاصيل المقالة: الصورة، الكاتب، المحتوى الكامل"""
    try:
        res = requests.get(article_url, headers=HEADERS, timeout=10)
        if res.status_code != 200:
            return None
        
        soup = BeautifulSoup(res.text, "html.parser")

        # 1. Image
        image_url = None
        img_tag = soup.find("meta", property="og:image")
        if img_tag and img_tag.get("content"):
            image_url = img_tag["content"]

        # 2. Author
        author = "Marca"
        author_tag = soup.find("span", class_=re.compile(r"ue-c-article__author-name|author"))
        if author_tag:
            author = author_tag.get_text(strip=True)

        # 3. Full Content Paragraphs
        paragraphs = []
        body = soup.find("div", class_=re.compile(r"ue-c-article__body|article-body"))
        if body:
            for p in body.find_all("p"):
                txt = p.get_text(strip=True)
                if txt and not txt.startswith("Sigue el canal"):  # استبعاد إعلانات القنوات
                    paragraphs.append(txt)
        
        content = "\n\n".join(paragraphs) if paragraphs else ""

        return {
            "image_url": image_url,
            "author": author,
            "content": content
        }
    except Exception as e:
        print(f"❌ Error fetching article details ({article_url}): {e}")
        return None

# --- MAIN EXECUTION ---
def main():
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("❌ Missing Telegram Credentials!")
        return

    print("🔍 Scraping Marca Real Madrid section...")
    res = requests.get(MARCA_URL, headers=HEADERS, timeout=10)
    if res.status_code != 200:
        print("❌ Failed to fetch Marca main page")
        return

    soup = BeautifulSoup(res.text, "html.parser")
    articles = soup.find_all("article")

    # قراءة المقالات المعالجة سابقاً لمنع التكرار
    processed_urls = set()
    if os.path.exists("processed_marca.txt"):
        with open("processed_marca.txt", "r", encoding="utf-8") as f:
            processed_urls = set(line.strip() for line in f if line.strip())

    new_processed = set(processed_urls)

    for article in articles:
        header = article.find(["h2", "h3"])
        if not header:
            continue
        
        link_tag = header.find("a")
        if not link_tag or not link_tag.get("href"):
            continue

        article_url = link_tag["href"]
        if not article_url.startswith("http"):
            article_url = f"https://www.marca.com{article_url}"

        if article_url in processed_urls:
            continue

        title = header.get_text(strip=True)

        # سحب التفاصيل من داخل المقال
        details = get_article_details(article_url)
        if not details or not details["content"]:
            continue

        author = details["author"]
        content = details["content"]
        image_url = details["image_url"]

        # ترجمة (العنوان + المحتوى) دفعة واحدة عبر Google Translate GTX
        print(f"🌐 Translating: {title[:30]}...")
        translated = translate_batch([title, content])
        
        translated_title = clean_html(translated[0])
        translated_content = clean_html(translated[1])

        # تجهيز الرسالة لتليجرام بصيغة HTML
        safe_title = escape_html_entities(translated_title)
        safe_author = escape_html_entities(author)
        safe_content = escape_html_entities(translated_content)

        # اقتصاص المحتوى لو تعدّى حد تليجرام (1024 حرف للـ Caption مع الصورة)
        max_content_len = 800
        if len(safe_content) > max_content_len:
            safe_content = safe_content[:max_content_len] + "..."

        caption = (
            f"<b>{safe_title}</b>\n\n"
            f"✍️ <b>الكاتب:</b> {safe_author}\n\n"
            f"{safe_content}\n\n"
            f"🔗 <a href='{article_url}'>المصدر: Marca</a>"
        )

        # إرسال الرسالة
        if image_url:
            success = send_telegram_photo(image_url, caption)
        else:
            # لو الصورة مش موجودة يبعت كـ النص بس
            telegram_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
            payload = {
                "chat_id": TELEGRAM_CHAT_ID,
                "text": caption,
                "parse_mode": "HTML",
                "disable_web_page_preview": False
            }
            res_msg = requests.post(telegram_url, json=payload, timeout=15)
            success = res_msg.status_code == 200

        if success:
            print(f"✅ Sent successfully: {translated_title[:30]}")
            new_processed.add(article_url)
            # تسجيل الخبر فوراً لعدم تكراره
            with open("processed_marca.txt", "a", encoding="utf-8") as f:
                f.write(f"{article_url}\n")
        else:
            print(f"⚠️ Failed to send article: {article_url}")

if __name__ == "__main__":
    main()
