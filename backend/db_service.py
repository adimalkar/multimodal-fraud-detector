import os
import sqlite3
import csv
import io
from datetime import datetime
from typing import Dict, Any, List, Optional

DATABASE_URL = os.environ.get("DATABASE_URL")
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

DB_PATH = os.environ.get("DATABASE_PATH") or os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "database", "fraud_detection.db")
)

def is_postgres() -> bool:
    return bool(DATABASE_URL and ("postgresql://" in DATABASE_URL or "postgres://" in DATABASE_URL))

def get_connection():
    """Returns a database connection (PostgreSQL if DATABASE_URL is set, else SQLite)."""
    if is_postgres():
        try:
            import psycopg2
            import psycopg2.extras
            conn = psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.DictCursor)
            with conn.cursor() as cursor:
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS evidence (
                        id SERIAL PRIMARY KEY,
                        filename TEXT NOT NULL,
                        file_path TEXT,
                        media_type TEXT NOT NULL,
                        fraud_category TEXT DEFAULT 'General Claim',
                        ground_truth TEXT DEFAULT 'Pending Review',
                        ai_prediction TEXT,
                        confidence REAL,
                        vision_findings TEXT,
                        final_reasoning TEXT,
                        is_processed BOOLEAN DEFAULT TRUE,
                        processing_time REAL,
                        processed_at TEXT
                    )
                """)
            conn.commit()
            return conn
        except Exception as e:
            print(f"PostgreSQL connection warning ({e}), falling back to SQLite: {DB_PATH}")

    # Fallback to local SQLite
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=15)
    conn.row_factory = sqlite3.Row
    with conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS evidence (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                filename TEXT NOT NULL,
                file_path TEXT,
                media_type TEXT NOT NULL,
                fraud_category TEXT DEFAULT 'General Claim',
                ground_truth TEXT DEFAULT 'Pending Review',
                ai_prediction TEXT,
                confidence REAL,
                vision_findings TEXT,
                final_reasoning TEXT,
                is_processed BOOLEAN DEFAULT 1,
                processing_time REAL,
                processed_at TEXT
            )
        """)
    return conn

def save_evaluation(
    filename: str,
    media_type: str,
    ai_prediction: str,
    confidence: float,
    final_reasoning: str,
    vision_findings: str = "",
    fraud_category: str = "General Claim",
    processing_time: float = 0.0,
    file_path: Optional[str] = None
) -> int:
    """Saves a completed multi-agent analysis record to the database."""
    conn = get_connection()
    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

    # Adapt placeholder syntax between Postgres (%s) and SQLite (?)
    placeholder = "%s" if is_postgres() and hasattr(conn, "cursor_factory") else "?"

    query = f"""
        INSERT INTO evidence (
            filename, file_path, media_type, fraud_category, ground_truth,
            ai_prediction, confidence, vision_findings, final_reasoning,
            is_processed, processing_time, processed_at
        ) VALUES ({','.join([placeholder] * 11)})
    """
    params = (
        filename,
        file_path or filename,
        media_type,
        fraud_category,
        "Pending Review",
        ai_prediction,
        float(confidence),
        vision_findings,
        final_reasoning,
        float(processing_time),
        timestamp
    )

    if is_postgres() and hasattr(conn, "cursor_factory"):
        with conn.cursor() as cursor:
            cursor.execute(query + " RETURNING id", params)
            record_id = cursor.fetchone()[0]
        conn.commit()
    else:
        with conn:
            cursor = conn.execute(query, params)
            record_id = cursor.lastrowid

    conn.close()
    return record_id

def get_analytics_summary() -> Dict[str, Any]:
    """Calculates high-level forensic metrics for the analytics dashboard."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM evidence")
    total_records = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM evidence WHERE is_processed = 1 OR is_processed = TRUE")
    processed_records = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM evidence WHERE (is_processed = 1 OR is_processed = TRUE) AND LOWER(ai_prediction) = 'fake'")
    fake_count = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM evidence WHERE (is_processed = 1 OR is_processed = TRUE) AND LOWER(ai_prediction) = 'real'")
    real_count = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM evidence WHERE media_type = 'Image'")
    image_count = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM evidence WHERE media_type = 'Document'")
    document_count = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM evidence WHERE media_type = 'Video'")
    video_count = cursor.fetchone()[0]

    cursor.execute("SELECT AVG(confidence) FROM evidence WHERE (is_processed = 1 OR is_processed = TRUE) AND confidence IS NOT NULL")
    avg_conf_row = cursor.fetchone()[0]
    avg_confidence = round(float(avg_conf_row or 0.0), 3)

    cursor.execute("SELECT AVG(processing_time) FROM evidence WHERE (is_processed = 1 OR is_processed = TRUE) AND processing_time > 0")
    avg_time_row = cursor.fetchone()[0]
    avg_latency = round(float(avg_time_row or 0.0), 2)

    flagged_rate = round((fake_count / processed_records * 100), 1) if processed_records > 0 else 0.0

    cursor.execute("""
        SELECT id, filename, media_type, fraud_category, ai_prediction, confidence,
               final_reasoning, processing_time, processed_at
        FROM evidence
        ORDER BY id DESC
        LIMIT 25
    """)
    recent = [dict(row) for row in cursor.fetchall()]
    conn.close()

    return {
        "total_records": total_records,
        "processed_records": processed_records,
        "fake_count": fake_count,
        "real_count": real_count,
        "flagged_rate_percentage": flagged_rate,
        "avg_confidence": avg_confidence,
        "avg_processing_time_sec": avg_latency,
        "database_engine": "PostgreSQL" if is_postgres() else "SQLite",
        "media_counts": {
            "images": image_count,
            "documents": document_count,
            "videos": video_count
        },
        "recent_evaluations": recent
    }

def get_evaluations_list(limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
    """Returns paginated evaluations."""
    conn = get_connection()
    cursor = conn.cursor()
    placeholder = "%s" if is_postgres() and hasattr(conn, "cursor_factory") else "?"
    cursor.execute(f"""
        SELECT id, filename, media_type, fraud_category, ground_truth,
               ai_prediction, confidence, vision_findings, final_reasoning,
               processing_time, processed_at
        FROM evidence
        ORDER BY id DESC
        LIMIT {placeholder} OFFSET {placeholder}
    """, (limit, offset))
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows

def export_evaluations_csv() -> str:
    """Generates a CSV report string of all processed evaluations."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT filename, media_type, fraud_category, ground_truth,
               ai_prediction, confidence, vision_findings, final_reasoning,
               processing_time, processed_at
        FROM evidence
        WHERE is_processed = 1 OR is_processed = TRUE
        ORDER BY id DESC
    """)
    rows = cursor.fetchall()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "File Name",
        "Media Type",
        "Fraud Category",
        "Ground Truth",
        "AI Prediction",
        "Confidence Score",
        "Visual Findings",
        "Reasoning Output",
        "Latency (sec)",
        "Processed At"
    ])

    for row in rows:
        writer.writerow([
            row["filename"],
            row["media_type"],
            row["fraud_category"],
            row["ground_truth"],
            row["ai_prediction"],
            f"{float(row['confidence'] or 0.0):.2f}",
            row["vision_findings"] or "",
            row["final_reasoning"] or "",
            f"{float(row['processing_time'] or 0.0):.2f}",
            row["processed_at"] or ""
        ])

    conn.close()
    return output.getvalue()
