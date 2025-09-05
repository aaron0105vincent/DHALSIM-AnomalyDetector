

import json
import os
import argparse
from datetime import datetime
from modules.mongodb_config import get_alerts_collection

def save_alerts_json(alerts_data, output_dir, timestamp):
    """Save alerts to JSON format"""
    filename = f"alerts_{timestamp}.json"
    filepath = os.path.join(output_dir, filename)
    
    try:
        with open(filepath, 'w') as f:
            json.dump(alerts_data, f, indent=2, default=str)
        print(f"JSON alerts saved to: {filepath}")
        return filepath
    except Exception as e:
        print(f"Error saving JSON file: {e}")
        return None

def main():
    parser = argparse.ArgumentParser(description='Save MongoDB alerts to JSON file')
    parser.add_argument('--output-dir', type=str, default='.', 
                        help='Output directory for saved files (default: current directory)')
    
    args = parser.parse_args()
    
    print("MongoDB Alert Saver")
    print("=" * 40)
    
    # Connect to MongoDB
    print("Connecting to MongoDB...")
    alerts_collection = get_alerts_collection()
    
    if alerts_collection is None:
        print("Error: Could not connect to MongoDB")
        print("Make sure MongoDB is running and properly configured.")
        return 1
    
    print("Connected to MongoDB")
    
    # Retrieve all alerts
    print("Retrieving alerts...")
    try:
        alerts_cursor = alerts_collection.find({})
        alerts_data = list(alerts_cursor)
        print(f"Retrieved {len(alerts_data)} alerts")
    except Exception as e:
        print(f"Error retrieving alerts: {e}")
        return 1
    
    if not alerts_data:
        print("\nNo alerts to save.")
        return 0
    
    # Create output directory if it doesn't exist
    os.makedirs(args.output_dir, exist_ok=True)
    
    # Generate timestamp for filenames
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    print(f"\nSaving alerts to: {args.output_dir}")
    
    # Save JSON file
    filepath = save_alerts_json(alerts_data, args.output_dir, timestamp)
    
    if filepath:
        print(f"\nJSON file saved to: {filepath}")

    return 0

if __name__ == "__main__":
    exit(main())
