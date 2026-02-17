import os
import asyncio
import requests
from datetime import datetime
from deep_translator import GoogleTranslator
from shared.database_service import cve_exists, get_collection, save_to_database
from shared.telegram_service import send_text_message
from dotenv import load_dotenv
from scripts.cve.nvd_api_config import (
    API_URL,
    HEADERS,
    COLLECTION_NAME,
    CVE_DETAILS_URL,
)

load_dotenv()

# Secret Keys:
TELEGRAM_TOKEN_CVE = os.getenv("TELEGRAM_TOKEN_CVE")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
MONGO_URI = os.getenv("MONGO_URI")
if not all([TELEGRAM_TOKEN_CVE, TELEGRAM_CHAT_ID, MONGO_URI]):
    raise Exception("Missing environment variables")
translator = GoogleTranslator(source="auto", target="ar")

print("\nScript Starting\n")
now = datetime.now()
year = now.year
month = str(now.month).zfill(2)
day = str(now.day).zfill(2)
params = {
    "pubStartDate": f"{year}-{month}-{day}T00:00:00.000-00:00",
    "pubEndDate": f"{year}-{month}-{day}T23:59:59.999-00:00",
}
response = requests.get(url=API_URL, headers=HEADERS, params=params)
responseCode = response.status_code

if responseCode == 200:

    # Get Data
    print(f"✅ Request Success: {responseCode}\n")
    responseData = response.json()
    if not isinstance(responseData, dict):
        raise Exception("No data avaliable => Exiting")
    vulnerabilities = responseData.get("vulnerabilities")
    if not vulnerabilities:
        raise Exception("❗ Vulnerabilities list is empty => Exiting")
    vulnerabilitiesCount = len(vulnerabilities)
    print(f"- Vulnerabilities count: {vulnerabilitiesCount} (ready to filtering)")

    # Filter Vulnerabilities
    targetVulnerabilities = []
    for vulnerability in vulnerabilities:
        referencesExplioted = []
        description = "No Found Description"
        cve = vulnerability.get("cve")
        if not cve:
            continue
        cveReferences = cve.get("references")
        if not cve.get("references"):
            continue
        cveMetricsDict = cve.get("metrics")
        if not isinstance(cveMetricsDict, dict):
            continue
        cveMetricsVersionsList = list(cveMetricsDict)
        if not cveMetricsVersionsList:
            continue
        cveMetricsList = cve.get("metrics").get(cveMetricsVersionsList[0])
        if not isinstance(cveMetricsList, list):
            continue
        cveMetricsData = cveMetricsList[0]
        if not cveMetricsData:
            continue
        cvssData = cveMetricsData.get("cvssData")
        if not cvssData:
            continue
        baseScore = cvssData.get("baseScore")
        baseSeverity = cvssData.get("baseSeverity")
        if not baseScore >= 7:
            continue

        vulnStatus = cve.get("vulnStatus")
        if not vulnStatus:
            continue
        valid_statuses = ["Analyzed", "Modified"]
        if cve.get("vulnStatus") in valid_statuses:
            for reference in cveReferences:
                referenceTags = reference.get("tags")
                if not referenceTags:
                    continue
                important_tags = [
                    "Third Party Advisory",
                    "Patch",
                    "Exploit",
                    "Vendor Advisory",
                ]
                for tag in referenceTags:
                    if tag in important_tags:
                        referencesExplioted.append(
                            {
                                "url": reference.get("url"),
                                "source": reference.get("source"),
                                "tag": tag,
                            }
                        )
            if referencesExplioted:
                cveId = cve.get("id")
                descriptions = cve.get("descriptions")
                vectorString = cvssData.get("vectorString")
                if isinstance(descriptions, list):
                    firstDescription = descriptions[0]
                    description = firstDescription.get("value")
                targetVulnerabilities.append(
                    {
                        "cve": {
                            "id": cveId,
                            "vectorString": vectorString,
                            "description": description,
                            "references": referencesExplioted,
                            "baseScore": baseScore,
                            "baseSeverity": baseSeverity,
                        }
                    }
                )
    if not targetVulnerabilities:
        print("❗ No vulnerabilities apply to filter\n")
        print("✅ Exiting")
        exit()
    targetVulnerabilitiesCount = len(targetVulnerabilities)
    print(f"- Target vulnerabilities count: ({targetVulnerabilitiesCount} filtered)\n")

    # Get from database
    print("- Get cves stored in database...")
    cvesCollection = get_collection(
        uri=MONGO_URI, collection_name=COLLECTION_NAME, db_name="my_db"
    )
    print("- Get cves stored successfully.\n")

    # Start
    for vulnerability in targetVulnerabilities:
        cve = vulnerability.get("cve")
        cveId = cve.get("id")
        if cve_exists(collection=cvesCollection, cveId=cveId):
            print(f"- {cveId} in database - Skipping\n")
            continue
        description = translator.translate(
            cve.get("description")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace("&&", "&amp;")
        )
        cveReferences = cve.get("references")
        vectorString = cve.get("vectorString")
        baseSeverity = cve.get("baseSeverity")
        baseScore = cve.get("baseScore")

        ref_links = ""

        if cveReferences:
            for refernce in cveReferences:
                url = refernce.get("url")
                source = refernce.get("source")
                tag = refernce.get("tag")
                ref_links += f"- ({tag})\n{url}\n\n"

        formatted_text = (
            f"<b>⚠️ New Vulnerability Detected</b>\n\n"
            f"<b>CVE ID:</b> <code>{cveId}</code>\n"
            f"<b>Severity:</b> {baseSeverity} ( {baseScore} )\n\n"
            f"<b>الوصف:</b>\n{(description[:600] + '...') if len(description) > 600 else description}"
            f"\n\n{ref_links}"
        )

        print(f"- {cveId} - Base Score: {baseScore}")
        print("📩 Sned to telegram...")
        status = asyncio.run(
            send_text_message(
                token=TELEGRAM_TOKEN_CVE,
                chat_id=TELEGRAM_CHAT_ID,
                text=formatted_text,
                source_url=f"{CVE_DETAILS_URL}/{cveId}/",
                buttonText="CVE Details",
            )
        )
        if status == True or status == "TIMEOUT":
            print("☑️ Message sended to telegram successfully.\n")
            print("📊 Save to database...")
            save_to_database(collection=cvesCollection, data={"cve_id": cveId})
            print("☑️ CVE saved to database successfully.\n")
        else:
            print("❗ Faild to send message.\n")

    # End
    print("✅ Script Ended")
else:
    raise Exception(f"🚫 Request Faild: {responseCode} => Exiting")
