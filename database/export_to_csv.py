import sqlite3
import csv
import os

DB_PATH = os.environ.get("DATABASE_PATH") or os.path.join(os.path.dirname(__file__), "fraud_detection.db")
CSV_PATH = os.environ.get("CSV_REPORT_PATH") or os.path.join(os.path.dirname(__file__), "fraud_detection_report.csv")

def export_to_csv():
    # 1. Connect to the SQLite Database
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # 2. Select everything except id and file paths (to keep it clean for stakeholders)
    cursor.execute("""
        SELECT 
            filename, 
            media_type, 
            fraud_category, 
            ground_truth, 
            ai_prediction, 
            confidence, 
            vision_findings, 
            final_reasoning,
            processing_time,
            processed_at
        FROM evidence
        WHERE is_processed = 1
    """)
    rows = cursor.fetchall()
    
    # 3. Define the column headers for the CSV
    headers = [
        "File Name", 
        "Media Type", 
        "Fraud Category", 
        "Actual Label (Ground Truth)", 
        "AI Analysis Outcome", 
        "AI Confidence Score", 
        "Raw Visual Anomalies Detected", 
        "Final Reasoning Output",
        "API Latency (seconds)",
        "Processed At"
    ]
    
    # 4. Open the CSV file and write the data
    with open(CSV_PATH, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(headers) # Write the header row
        writer.writerows(rows)  # Write all the data rows
        
    print(f"✅ Successfully exported {len(rows)} processed records to: {CSV_PATH}")
    conn.close()

if __name__ == "__main__":
    export_to_csv()
