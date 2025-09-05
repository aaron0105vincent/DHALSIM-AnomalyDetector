import os
import time
import sqlite3
from .db import get_master_time


class DatabaseManager:
    """Manages database connections and operations."""
    
    def __init__(self, db_path="/tmp/monitor_copy.sqlite", poll_interval=1.2, timeout=30):
        """
        Initialize database manager.
        
        Args:
            db_path (str): Path to SQLite database
            poll_interval (float): Polling interval in seconds
            timeout (int): Connection timeout in seconds
        """
        self.db_path = db_path
        self.poll_interval = poll_interval
        self.timeout = timeout
        self.connection = None
    
    def wait_for_database(self):
        """Wait for database file to become available."""
        while not os.path.exists(self.db_path):
            print("Waiting for DB copy to appear...")
            time.sleep(self.poll_interval)
    
    def connect(self):
        """
        Establish database connection.
        
        Returns:
            sqlite3.Connection: Database connection
        """
        print("Opening database connection...")
        self.connection = sqlite3.connect(self.db_path, timeout=self.timeout)
        return self.connection
    
    def wait_for_schema(self):
        """Wait for database schema to be populated."""
        if not self.connection:
            raise RuntimeError("Database connection not established")
        
        while True:
            try:
                self.connection.execute("SELECT 1 FROM plant LIMIT 1")
                print("Database schema is ready.")
                break
            except sqlite3.OperationalError:
                print("Waiting for table 'plant' to exist...")
                time.sleep(self.poll_interval)
    
    def get_current_iteration(self):
        """
        Get current iteration from database.
        
        Returns:
            int: Current iteration number
        """
        if not self.connection:
            raise RuntimeError("Database connection not established")
        
        return get_master_time(self.connection)
    
    def close(self):
        """Close database connection."""
        if self.connection:
            self.connection.close()
            self.connection = None
            print("Database connection closed.")
    
    def setup_database(self):
        """
        Complete database setup: wait for file, connect, and wait for schema.
        
        Returns:
            sqlite3.Connection: Established database connection
        """
        self.wait_for_database()
        self.connect()
        self.wait_for_schema()
        return self.connection


def setup_database_connection(db_path="/tmp/monitor_copy.sqlite", poll_interval=1.2):
    """
    Legacy function to maintain compatibility.
    Set up database connection with waiting for file and schema.
    
    Args:
        db_path (str): Path to SQLite database
        poll_interval (float): Polling interval in seconds
        
    Returns:
        sqlite3.Connection: Database connection
    """
    db_manager = DatabaseManager(db_path, poll_interval)
    return db_manager.setup_database()
