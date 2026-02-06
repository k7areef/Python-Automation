BASE_URL = "https://gate.ahram.org.eg"
NEWS_URL = f"{BASE_URL}/Portal/13/أخبار.aspx"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/121.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "ar,en-US;q=0.9,en;q=0.8",
    "Referer": "https://gate.ahram.org.eg/",
    "Connection": "keep-alive",
}

COLLECTION_NAME = "masr_articles"
SOURCE_NAME = "بوابة الأهرام"
