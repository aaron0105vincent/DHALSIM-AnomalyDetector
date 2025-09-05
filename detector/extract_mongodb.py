import pandas as pd
from pymongo import MongoClient
from modules.mongodb_config import get_mongodb_connection 

# Set up the MongoDB connection
client, db, alerts = get_mongodb_connection()

# Retrieve all data from the collection
data = list(alerts.find())

# If data exists, save it as a CSV file
if data:
    # Convert MongoDB data to DataFrame (pandas)
    df = pd.json_normalize(data)  # This will flatten nested documents if needed

    # Export to CSV
    df.to_csv('alert_mongodb.csv', index=False)  # Replace 'output.csv' with your desired filename
    print("Data exported successfully to 'alert_mongodb.csv'")
else:
    print("No data found in the collection.")