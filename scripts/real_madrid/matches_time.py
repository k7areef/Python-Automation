import os
import asyncio
import requests
from datetime import datetime
from bs4 import BeautifulSoup
from shared.telegram_service import send_text_message
from dotenv import load_dotenv
from scripts.real_madrid.configs.official_news_config import (
    MATCHES_URL,
    HEADERS,
)

load_dotenv()

# Secret Keys:
TELEGRAM_TOKEN_REAL_MADRID = os.getenv("TELEGRAM_TOKEN_REAL_MADRID")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
if not all([TELEGRAM_TOKEN_REAL_MADRID, TELEGRAM_CHAT_ID]):
    raise Exception("Missing environment variables")

# Start Print:
print("Run Real Madrid.Official News Script")
# Start Request:
response = requests.get(
    url=MATCHES_URL,
    headers=HEADERS,
    timeout=10,
)
if response.status_code == 200:
    print(f"✅ Request Success: {response.status_code}")
    soup = BeautifulSoup(response.text, "html.parser")
    cards = soup.find_all("app-all-event-card", class_="calendar-list__card")
    filteredCards = []
    matchDates = {}

    # If cards:
    if cards:
        for card in cards:
            cardCategory = card.find("p", class_="event-card__category")
            if not cardCategory:
                continue
            if cardCategory.get_text(strip=True) == "Fútbol · Primer Equipo":
                filteredCards.append(card)
    else:
        print("❗ No data avalibale - Existting")
    # If filter cards:
    if filteredCards:
        print(f"Matches This Month: {len(filteredCards)} Matches\n")
        # Extract Matche Dates:
        for card in filteredCards:
            date = ""
            title = ""
            subtitle = ""
            team1 = ""
            team2 = ""
            location = ""
            # Get Info ELements:
            cardInfoElements = card.find_all("li", class_="event-card__info")
            if not cardInfoElements:
                print("Card info elements not avaliable - Skipping\n")
                continue

            # Date and location
            dateEle = cardInfoElements[0].find("p")
            locationEle = cardInfoElements[1].find("p")
            if not all([dateEle, locationEle]):
                print(
                    "Card info elements avaliable but date or location element(s) not avalaible - Skipping\n"
                )
                continue
            date = dateEle.get_text(strip=True)
            location = locationEle.get_text(strip=True)
            if not all([date, location]):
                print("Date or Location text(s) not avaliable - Skipping\n")
                continue
            date = date.replace(" h", "")
            location = (
                location.replace("ملعب ", "ال")
                if location == "ملعب سانتياغو برنابيو"
                else location
            )
            # Date and location

            # Title
            titleEle = card.find("h3", class_="event-card__title")
            if not titleEle:
                print(
                    "Card info elements avaliable but title element not avalaible - Skipping\n"
                )
                continue
            title = titleEle.get_text(strip=True)
            # Title

            # Subtitle
            subtitleEle = card.find("p", class_="event-card__subtitle")
            if subtitleEle:
                subtitle = subtitleEle.get_text(strip=True)
            else:
                print(f"At: {date}")
                print(
                    "Card info elements avaliable but subtitle element not avalaible - Ignore\n"
                )
            # Subtitle

            # Team names
            teamNameElements = card.find_all("p", class_="rm-game__name")
            if not teamNameElements:
                print(
                    "Card info elements avaliable but team name elements not avalaible - Skipping\n"
                )
                continue
            team1 = teamNameElements[0].get_text(strip=True)
            team2 = teamNameElements[1].get_text(strip=True)
            if not all([team1, team2]):
                print(
                    "Card info elements avaliable but team 1 or team 2 not avalaible - Skipping\n"
                )
                continue
            # Team names

            if date not in matchDates:
                matchDates[date] = {}
            if title:
                matchDates[date] = {**matchDates[date], "title": title}
            if subtitle:
                matchDates[date] = {**matchDates[date], "subtitle": subtitle}
            if team1:
                matchDates[date] = {**matchDates[date], "team1": team1}
            if team2:
                matchDates[date] = {**matchDates[date], "team2": team2}
            if location:
                matchDates[date] = {**matchDates[date], "location": location}
    else:
        print("❗ No data avalibale - Existting")

    # If match dates:
    if matchDates:
        for date in matchDates:
            dateStr = str(date)
            dateParts = dateStr.split("، ")
            dateMonth = dateParts[1]
            dateDay = int(dateMonth.split(" ")[0])
            if datetime.now().date().day == dateDay:
                print(f"Founded match today: {date}")

                matchDec = matchDates[date]
                team1 = matchDec["team1"]
                team2 = matchDec["team2"]
                location = matchDec["location"]
                if not team1 == "ريال مدريد":
                    team1 = "ريال مدريد"
                    team2 = team1

                messageText = (
                    f"<b>مباراة اليوم - الساعة {dateParts[2]}</b>\n\n"
                    f"<b>{team1}</b> و <b>{team2}</b> - علي ملعب {location}"
                )

                print("Send to telegram - Sending")
                isSuccessSend = asyncio.run(
                    send_text_message(
                        token=TELEGRAM_TOKEN_REAL_MADRID,
                        chat_id=TELEGRAM_CHAT_ID,
                        text=messageText,
                        source_url=MATCHES_URL,
                        buttonText="الموقع الرسمي لريال مدريد",
                    )
                )
                if not isSuccessSend:
                    print("Faild to send telegram message - Continue")
                    continue
                print("Telegram message sended successfully")
        print("✅ Work ended successfully - Exitting...")
    else:
        print("❗ No data avalibale - Existting")
else:
    print(f"🚫 Request Fail: {response.status_code} - Exitting...")
