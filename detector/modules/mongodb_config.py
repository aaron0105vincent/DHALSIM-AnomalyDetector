from pymongo import MongoClient
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def get_mongodb_connection():
    """
    Get MongoDB connection with error handling
    Returns: tuple (mongo_client, mongo_db, alerts_collection)
    """
    try:
        mongo_client = MongoClient("mongodb://localhost:27017/")
        mongo_db = mongo_client["dhalsim"]
        alerts_collection = mongo_db["alerts"]
        
        # Test connection
        mongo_client.admin.command('ping')
        logger.info("MongoDB connection established successfully")
        
        return mongo_client, mongo_db, alerts_collection
    
    except Exception as e:
        logger.error(f"Failed to connect to MongoDB: {e}")
        return None, None, None

# Global instances (lazy initialization)
_mongo_client = None
_mongo_db = None
_alerts_collection = None

def get_alerts_collection():
    """Get alerts collection with lazy initialization"""
    global _mongo_client, _mongo_db, _alerts_collection
    
    if _alerts_collection is None:
        _mongo_client, _mongo_db, _alerts_collection = get_mongodb_connection()
    
    return _alerts_collection

def get_mongo_db():
    """Get MongoDB database with lazy initialization"""
    global _mongo_client, _mongo_db, _alerts_collection
    
    if _mongo_db is None:
        _mongo_client, _mongo_db, _alerts_collection = get_mongodb_connection()
    
    return _mongo_db

def get_mongo_client():
    """Get MongoDB client with lazy initialization"""
    global _mongo_client, _mongo_db, _alerts_collection
    
    if _mongo_client is None:
        _mongo_client, _mongo_db, _alerts_collection = get_mongodb_connection()
    
    return _mongo_client
