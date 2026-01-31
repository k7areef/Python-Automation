from pymongo.mongo_client import MongoClient
from pymongo.server_api import ServerApi


def get_collection(uri, db_name, collection_name):
    client = MongoClient(uri, server_api=ServerApi("1"))
    db = client.get_database(db_name)
    return db.get_collection(collection_name)


def save_url(collection, url):
    collection.insert_one({"article_url": url})


def url_exists(collection, url):
    return collection.find_one({"article_url": url}) is not None
