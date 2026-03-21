import os
import asyncio
import requests
from bs4 import BeautifulSoup
from shared.database_service import get_collection, save_to_database, check_database
from shared.telegram_service import send_text_message
from dotenv import load_dotenv
from scripts.freelance.configs.mostql_config import (
    DEVELOPERMENT_URL,
    HEADERS,
    COLLECTION_NAME,
    SOURCE_NAME,
    FORBIDDEN_WORDS,
)

load_dotenv()

# Secret Keys:
TELEGRAM_TOKEN_FREELANCE = os.getenv("TELEGRAM_TOKEN_FREELANCE")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
MONGO_URI = os.getenv("MONGO_URI")
if not all([TELEGRAM_TOKEN_FREELANCE, TELEGRAM_CHAT_ID, MONGO_URI]):
    raise Exception("MISSING EVNIRONMENT VARIABLES")

# Start
response = requests.get(url=DEVELOPERMENT_URL, headers=HEADERS)
statusCode = response.status_code

if statusCode == 200:
    print(f"\n✅ Request Success: {statusCode}\n")
    content = response.content
    soup = BeautifulSoup(content, "html.parser")
    projects = soup.find_all("tr", class_="project-row")
    if projects:
        # Projects Filtered:
        projectsFiltered = []
        # Start Filteration:
        print(f"- Projects Count: {len(projects)} - Start Filtering...")
        for pro in projects:
            proTitleEle = pro.find("h2")
            if not proTitleEle:
                continue
            title = proTitleEle.get_text().strip().lower()

            if not any(word.lower() in title for word in FORBIDDEN_WORDS):
                projectsFiltered.append(pro)
        if projectsFiltered:
            projectsFiltered.reverse()
            # Filteration Count:
            print(f"- Fileration Count: {len(projectsFiltered)}\n")

            # Get Projects From Database:
            print("- Getting Project Urls From Database...")
            projectsUrlsCollection = get_collection(
                uri=MONGO_URI, collection_name=COLLECTION_NAME, db_name="my_db"
            )
            print(f"- Get Project Urls From Database Successfully\n")

            for project in projectsFiltered:
                projectUrlEle = project.find("a", href=True)
                if not projectUrlEle:
                    continue
                projectUrl = projectUrlEle.get("href")
                if check_database(
                    collection=projectsUrlsCollection, data={"project_url": projectUrl}
                ):
                    print("☑️ Url in database - Skipping")
                    continue
                projectResponse = requests.get(url=projectUrl, headers=HEADERS)
                if not projectResponse.status_code == 200:
                    continue
                projectContent = projectResponse.content
                projectSoup = BeautifulSoup(projectContent, "html.parser")

                projectTitle = projectSoup.find("h1").get_text().strip()
                descriptionWrapper = projectSoup.find("div", class_="text-wrapper-div")
                descriptionPTags = descriptionWrapper.find_all("p", string=True)
                projectDescription = ""
                for pTag in descriptionPTags:
                    projectDescription += f"{pTag.get_text().strip()}\n"

                # Project Details:
                metaRowsEle = projectSoup.find("div", class_="meta-rows")
                metaRows = metaRowsEle.find_all("div", class_="meta-row")
                projectBadget = " ".join(
                    metaRows[2].find("div", class_="meta-value").get_text().split()
                )
                projectDeadline = " ".join(
                    metaRows[3].find("div", class_="meta-value").get_text().split()
                )

                # User Details:
                tableMeta = projectSoup.find("table", class_="table-meta")
                tableTrs = tableMeta.find_all("tr")
                signDate = tableTrs[0].find_all("td")[1].get_text(strip=True)
                employmentRate = tableTrs[1].find_all("td")[1].get_text(strip=True)
                openProjects = tableTrs[2].find_all("td")[1].get_text(strip=True)
                progressProjects = tableTrs[3].find_all("td")[1].get_text(strip=True)
                connectionProgress = tableTrs[4].find_all("td")[1].get_text(strip=True)

                message = (
                    f"<b>{projectTitle}</b>\n\n"
                    f"{projectDescription}\n\n"
                    f"الميزانية: <b>{projectBadget}</b>\n"
                    f"مدة التنفيذ: <b>{projectDeadline}</b>\n"
                    f"تاريخ التسجيل: <b>{signDate}</b>\n"
                    f"معدل التوظيف: <b>{employmentRate}</b>\n"
                    f"عدد المشاريع المفتوحة: <b>{openProjects}</b>\n"
                    f"عدد المشاريع المكتملة: <b>{progressProjects}</b>\n"
                    f"التواصلات الجارية: <b>{connectionProgress}</b>\n"
                )

                status = asyncio.run(
                    send_text_message(
                        token=TELEGRAM_TOKEN_FREELANCE,
                        chat_id=TELEGRAM_CHAT_ID,
                        text=message,
                        source_url=projectUrl,
                        buttonText="رابط المشروع علي مستقل",
                    )
                )

                if status:
                    print("☑️ Message Sended Successfully - Saveing to Database...")
                    save_to_database(
                        collection=projectsUrlsCollection,
                        data={"project_url": projectUrl, "source": SOURCE_NAME},
                    )
                    print("☑️ Url Saved to Database\n")
                else:
                    print("❗ Some Error \n")
            print("☑️ Ended Without Errors Succesfully.")
        else:
            print("❗ No projects apply to filteration")
            exit()
    else:
        print("❗ No Avaliable Projects")
        exit()
else:
    print(f"🚫 Request Fail: {statusCode}")
    print("Existing")
    exit()
