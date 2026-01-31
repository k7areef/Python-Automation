import os
import re
import asyncio
import requests
from datetime import datetime
from shared.database_service import cve_exists, get_collection, save_cve
from shared.telegram_service import send_text_message
from dotenv import load_dotenv
from scripts.cve.nvd_api_config import (
    API_URL,
    HEADERS,
    COLLECTION_NAME,
)

load_dotenv()

# Secret Keys:
TELEGRAM_TOKEN_CVE = os.getenv("TELEGRAM_TOKEN_CVE")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
MONGO_URI = os.getenv("MONGO_URI")
NVD_API_KEY = os.getenv("NVD_API_KEY")
if not all([TELEGRAM_TOKEN_CVE, TELEGRAM_CHAT_ID, MONGO_URI, NVD_API_KEY]):
    raise Exception("Missing environment variables")


# Generate Report:
def generate_report(vector_string):
    mapping = {
        "AV": {
            "N": "NETWORK",
            "A": "ADJACENT",
            "L": "LOCAL",
            "P": "PHYSICAL",
        },
        "PR": {
            "N": "NONE",
            "L": "LOW",
            "H": "HIGH",
        },
        "AC": {"L": "LOW", "H": "HIGH"},
        "E": {
            "X": "NOT_DEFINED",
            "U": "UNPROVEN",
            "P": "PROOF_OF_CONCEPT",
            "A": "ATTACKED",
        },
        "VC": {"H": "HIGH", "L": "LOW", "N": "NONE"},
        "VI": {"H": "HIGH", "L": "LOW", "N": "NONE"},
        "VA": {"H": "HIGH", "L": "LOW", "N": "NONE"},
    }

    parts = {
        p.split(":")[0]: p.split(":")[1] for p in vector_string.split("/") if ":" in p
    }

    report = {
        "authRequired": mapping["PR"].get(parts.get("PR"), "Unknown"),
        "attackVector": mapping["AV"].get(parts.get("AV"), "Unknown"),
        "complexity": mapping["AC"].get(parts.get("AC"), "Unknown"),
        "exploitState": mapping["E"].get(parts.get("E"), "Unknown"),
        "confidentiality": mapping["VC"].get(parts.get("VC"), "Unknown"),
        "integrity": mapping["VI"].get(parts.get("VI"), "Unknown"),
        "availability": mapping["VA"].get(parts.get("VA"), "Unknown"),
    }

    return report


print("nvd_api Script Running:\n")

try:
    # Constants:
    now = datetime.now()
    startTimeParam = now.strftime("%Y-%m-%dT00:00:00.000")
    endTimeParam = now.strftime("%Y-%m-%dT23:59:59.999")

    api = API_URL
    headers = {"apiKey": NVD_API_KEY, **HEADERS}
    params = {
        "pubStartDate": startTimeParam,
        "pubEndDate": endTimeParam,
    }
    apiResponse = requests.get(api, headers=headers, params=params)
    responseCode = apiResponse.status_code
    if responseCode == 200:

        print("Getting CVE ids from database...")
        cveIdsCollection = get_collection(
            uri=MONGO_URI, collection_name=COLLECTION_NAME, db_name="my_db"
        )
        print(f"Get CVE ids from database successfully\n")

        print(f"Request Success - CODE IS: {responseCode}\n")
        apiResponseJson = apiResponse.json()
        vulnerabilitiesList = apiResponseJson.get("vulnerabilities")
        print(f"CVEs Count: {len(vulnerabilitiesList)}\n")

        if vulnerabilitiesList:
            for vulneItem in vulnerabilitiesList:
                cve = vulneItem.get("cve", {})

                cveId = cve.get("id", None)
                if not cveId:
                    print(f"CVE id not avaliable - Skipping\n")
                    continue

                isInDatabase = cve_exists(collection=cveIdsCollection, cveId=cveId)
                if isInDatabase:
                    print(f"- {cveId} in database - Skipping\n")
                    continue

                print(f"- {cveId} Not in database - Working...")
                isMetricsDict = cve.get("metrics")
                if not isMetricsDict:
                    print("No metrics avaliable! - Skiping\n")
                    continue

                metricsDict = cve.get("metrics")[list(cve.get("metrics"))[0]]
                cvssDataDict = metricsDict[0].get("cvssData")
                baseScore = cvssDataDict.get("baseScore")
                if baseScore < 7:
                    print("Base Score Under 7 - Canceling\n")
                    continue

                descriptions = cve.get("descriptions", None)
                weaknesses = cve.get("weaknesses", None)
                references = cve.get("references", None)

                if not all([descriptions, weaknesses, references]):
                    print("Some data missing! - Skipping\n")
                    continue

                description = descriptions[0].get("value")
                clean_description = re.sub(r"\n{3,}", "\n\n", description).strip()
                descriptionLen = len(clean_description)
                print(f" - Description is: {clean_description[:20]}...")

                weaknesse = cve.get("weaknesses")[0].get("description")[0].get("value")
                print(f" - Weaknesse is: {weaknesse}")

                referenceUrl = cve.get("references")[0].get("url")
                referenceSouce = cve.get("references")[0].get("source")
                print(f" - Reference Url is: {referenceUrl}")
                print(f" - Reference Souce is: {referenceSouce}")

                publishedDate = datetime.strptime(
                    cve.get("published"), "%Y-%m-%dT%H:%M:%S.%f"
                )
                messageTitle = "CRITICAL" if baseScore >= 9 else "HIGH" " ALERT"
                reportDict = generate_report(cvssDataDict.get("vectorString"))
                authRequired = reportDict.get("authRequired", "UNKNOWN")
                attackVector = reportDict.get("attackVector", "UNKNOWN")
                complexity = reportDict.get("complexity", "UNKNOWN")
                exploitState = reportDict.get("exploitState", "UNKNOWN")
                confidentiality = reportDict.get("confidentiality", "UNKNOWN")
                integrity = reportDict.get("integrity", "UNKNOWN")
                availability = reportDict.get("availability", "UNKNOWN")

                message = (
                    f"<b>{messageTitle} - <code>{cveId}</code>  - <code>{weaknesse}</code></b>\n\n"
                    f"<b>{clean_description[:2000]}{'...' if descriptionLen > 2000 else ''}</b>\n\n"
                    f"CVSS Details:\n"
                    f"- <b>Auth Required:</b> {authRequired}\n"
                    f"- <b>Attack Vector:</b> {attackVector}\n"
                    f"- <b>Complexity:</b> {complexity}\n"
                    f"- <b>Exploit State:</b> {exploitState}\n"
                    f"- <b>Confidentiality:</b> {confidentiality}\n"
                    f"- <b>Integrity:</b> {integrity}\n"
                    f"- <b>Availability:</b> {availability}\n"
                    f"- <b>Base Score:</b> {baseScore}\n\n"
                    f"Published at: {publishedDate.strftime('%I:%M %p, %A, %d-%m-%Y')}"
                )

                # Send to telegram:
                print("Send message to telegram - Sending")
                asyncio.run(
                    send_text_message(
                        token=TELEGRAM_TOKEN_CVE,
                        chat_id=TELEGRAM_CHAT_ID,
                        text=message,
                        source_url=f"https://www.cvedetails.com/cve/{cveId}",
                    )
                )
                print("Message sended to telegram successfully")

                print("Save CVE to database:")
                save_cve(collection=cveIdsCollection, cve_data={"cve_id": cveId})
                print("CVE saved to database successfully - Continue \n")

            print("✅ All Done - Exsitting")
    else:
        print(f"Faild to get data from api! - CODE IS: {responseCode}")
except Exception as e:
    print(e)
