from pymongo.mongo_client import MongoClient
from pymongo.server_api import ServerApi


def get_collection(uri, db_name, collection_name):
    client = MongoClient(uri, server_api=ServerApi("1"))
    db = client.get_database(db_name)
    return db.get_collection(collection_name)


def save_to_database(collection, data):
    collection.insert_one(data)


def url_exists(collection, url):
    return collection.find_one({"article_url": url}) is not None


def check_database(collection, data):
    return collection.find_one(data) is not None


# -------- CVE helpers --------
def cve_exists(collection, cveId):
    return collection.find_one({"cve_id": cveId}) is not None
