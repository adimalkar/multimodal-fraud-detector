import os
import sqlite3
import glob
from datetime import datetime

# Configuration
DB_PATH = "/home/aditya/Downloads/Hackathon/database/fraud_detection.db"
DATA_DIR = "/home/aditya/Downloads/Hackathon/Chubb_Data"

def init_db():
    print(f"Initializing database at: {DB_PATH}")
    
    # Connect (this creates the file if it doesn't exist)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Create the Evidence table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS evidence (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT NOT NULL,
            file_path TEXT NOT NULL UNIQUE,
            media_type TEXT NOT NULL,
            fraud_category TEXT NOT NULL,
            ground_truth TEXT NOT NULL,
            ai_prediction TEXT,
            confidence REAL,
            vision_findings TEXT,
            final_reasoning TEXT,
            is_processed BOOLEAN DEFAULT 0,
            processing_time REAL,
            processed_at TEXT
        )
    ''')
    
    print("Table 'evidence' created successfully.")
    
    # Scan the local directory for images/videos and populate the DB
    supported_extensions = ['*.jpg', '*.jpeg', '*.png', '*.mp4']
    
    files_found = []
    for ext in supported_extensions:
        # Search recursively in the Chubb_Data directory
        search_pattern = os.path.join(DATA_DIR, '**', ext)
        files_found.extend(glob.glob(search_pattern, recursive=True))
        
    inserted_count = 0
    
    for file_path in files_found:
        filename = os.path.basename(file_path)
        
        # Determine media type
        if filename.lower().endswith('.mp4'):
            media_type = 'Video'
        else:
            media_type = 'Image'
            
        # Determine Ground Truth based on directory name
        if 'fake' in file_path.lower() or 'generated' in file_path.lower():
            ground_truth = 'Fake'
        elif 'real' in file_path.lower():
            ground_truth = 'Real'
        else:
            ground_truth = 'Unknown'
            
        # Since images are not segregated, default to Mixed category
        # The AI can theoretically classify the category later if we want
        fraud_category = 'Mixed (Vehicle/Property)'
            
        try:
            cursor.execute('''
                INSERT INTO evidence (filename, file_path, media_type, fraud_category, ground_truth)
                VALUES (?, ?, ?, ?, ?)
            ''', (filename, file_path, media_type, fraud_category, ground_truth))
            inserted_count += 1
        except sqlite3.IntegrityError:
            # Skip if file_path already exists (due to UNIQUE constraint)
            pass

    conn.commit()
    conn.close()
    
    print(f"Database initialization complete! Inserted {inserted_count} new records out of {len(files_found)} files found.")

if __name__ == "__main__":
    init_db()
