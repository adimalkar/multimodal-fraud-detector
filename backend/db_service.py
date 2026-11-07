import os
import sqlite3
import csv
import io
import uuid
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

DATABASE_URL = os.environ.get("DATABASE_URL") or os.environ.get("DURABLE_DATABASE_URL")
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

DB_PATH = os.environ.get("DATABASE_PATH") or os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "database", "fraud_detection.db")
)

def is_postgres() -> bool:
    return bool(DATABASE_URL and ("postgresql://" in DATABASE_URL or "postgres://" in DATABASE_URL))

def ensure_columns(conn):
    """Ensures multimodal risk columns exist on existing database tables."""
    new_cols = [
        ("risk_score", "REAL"),
        ("severity_tier", "TEXT"),
        ("recommended_action", "TEXT"),
        ("job_id", "TEXT"),
        ("owner_id", "TEXT"),
    ]
    for col, col_type in new_cols:
        try:
            if is_postgres() and hasattr(conn, "cursor_factory"):
                with conn.cursor() as cur:
                    cur.execute(f"ALTER TABLE evidence ADD COLUMN IF NOT EXISTS {col} {col_type}")
                conn.commit()
            else:
                conn.execute(f"ALTER TABLE evidence ADD COLUMN {col} {col_type}")
        except Exception:
            pass
    try:
        if is_postgres() and hasattr(conn, "cursor_factory"):
            with conn.cursor() as cur:
                cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS evidence_job_id_unique ON evidence(job_id) WHERE job_id IS NOT NULL")
        else:
            conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS evidence_job_id_unique ON evidence(job_id) WHERE job_id IS NOT NULL")
        conn.commit()
    except Exception:
        pass
    usage_table = """
        CREATE TABLE IF NOT EXISTS web_usage (
            owner_id TEXT NOT NULL,
            day TEXT NOT NULL,
            files INTEGER NOT NULL,
            PRIMARY KEY (owner_id, day)
        )
    """
    try:
        if is_postgres() and hasattr(conn, "cursor_factory"):
            with conn.cursor() as cur:
                cur.execute(usage_table)
                cur.execute("CREATE INDEX IF NOT EXISTS evidence_owner_id ON evidence(owner_id)")
        else:
            conn.execute(usage_table)
            conn.execute("CREATE INDEX IF NOT EXISTS evidence_owner_id ON evidence(owner_id)")
        conn.commit()
    except Exception:
        pass

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
                        processed_at TEXT,
                        risk_score REAL,
                        severity_tier TEXT,
                        recommended_action TEXT
                    )
                """)
            conn.commit()
            ensure_columns(conn)
            return conn
        except Exception as e:
            if os.environ.get("DURABLE_JOBS_ENABLED") == "1":
                raise RuntimeError("PostgreSQL is unavailable; analytics cannot fall back to SQLite") from e
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
                processed_at TEXT,
                risk_score REAL,
                severity_tier TEXT,
                recommended_action TEXT
            )
        """)
    ensure_columns(conn)
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
    file_path: Optional[str] = None,
    risk_score: Optional[float] = None,
    severity_tier: Optional[str] = None,
    recommended_action: Optional[str] = None,
    job_id: Optional[str] = None,
    owner_id: Optional[str] = None,
) -> int:
    """Save a completed visual screening record to the database."""
    conn = get_connection()
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    # Adapt placeholder syntax between Postgres (%s) and SQLite (?)
    placeholder = "%s" if is_postgres() and hasattr(conn, "cursor_factory") else "?"

    query = f"""
        INSERT INTO evidence (
            filename, file_path, media_type, fraud_category, ground_truth,
            ai_prediction, confidence, vision_findings, final_reasoning,
            is_processed, processing_time, processed_at,
            risk_score, severity_tier, recommended_action, job_id, owner_id
        ) VALUES ({','.join([placeholder] * 17)}) ON CONFLICT DO NOTHING
    """
    actual_file_path = file_path or f"{filename}_{uuid.uuid4().hex[:8]}"
    params = (
        filename,
        actual_file_path,
        media_type,
        fraud_category,
        "Pending Review",
        ai_prediction,
        float(confidence),
        vision_findings,
        final_reasoning,
        True,  # SQLite stores this as 1; PostgreSQL requires a boolean.
        float(processing_time),
        timestamp,
        float(risk_score) if risk_score is not None else None,
        severity_tier,
        recommended_action,
        job_id,
        owner_id,
    )

    if is_postgres() and hasattr(conn, "cursor_factory"):
        with conn.cursor() as cursor:
            cursor.execute(query + " RETURNING id", params)
            row = cursor.fetchone()
            if row:
                record_id = row[0]
            elif job_id:
                cursor.execute("SELECT id FROM evidence WHERE job_id=%s", (job_id,))
                record_id = cursor.fetchone()[0]
            else:
                raise RuntimeError("Evaluation insert conflicted without job ID")
        conn.commit()
    else:
        with conn:
            cursor = conn.execute(query, params)
            if job_id:
                record_id = conn.execute("SELECT id FROM evidence WHERE job_id=?", (job_id,)).fetchone()[0]
            else:
                record_id = cursor.lastrowid

    conn.close()
    return record_id


def delete_evaluation_by_job_id(job_id: str) -> None:
    """Remove the derived analytics projection when its private source job is deleted."""
    conn = get_connection()
    try:
        placeholder = "%s" if is_postgres() and hasattr(conn, "cursor_factory") else "?"
        cursor = conn.cursor()
        cursor.execute(f"DELETE FROM evidence WHERE job_id={placeholder}", (job_id,))
        conn.commit()
    finally:
        conn.close()

def _owner_scope(conn, owner_id: Optional[str]):
    """SQL filter that limits rows to one signed-in owner, or to everything."""
    if owner_id is None:
        return "1=1", ()
    placeholder = "%s" if is_postgres() and hasattr(conn, "cursor_factory") else "?"
    return f"owner_id = {placeholder}", (owner_id,)


def get_analytics_summary(owner_id: Optional[str] = None) -> Dict[str, Any]:
    """Calculates high-level forensic metrics for the analytics dashboard."""
    conn = get_connection()
    cursor = conn.cursor()
    scope, scope_params = _owner_scope(conn, owner_id)

    def count(condition: str = "1=1"):
        cursor.execute(f"SELECT COUNT(*) FROM evidence WHERE {scope} AND {condition}", scope_params)
        return cursor.fetchone()[0]

    processed = "(is_processed = 1 OR is_processed = TRUE)"

    total_records = count()
    processed_records = count(processed)
    fake_count = count(f"{processed} AND LOWER(ai_prediction) = 'fake'")
    real_count = count(f"{processed} AND LOWER(ai_prediction) = 'real'")
    image_count = count("media_type = 'Image'")
    document_count = count("media_type = 'Document'")
    video_count = count("media_type = 'Video'")

    cursor.execute(f"SELECT AVG(confidence) FROM evidence WHERE {scope} AND {processed} AND confidence IS NOT NULL", scope_params)
    avg_conf_row = cursor.fetchone()[0]
    avg_confidence = round(float(avg_conf_row or 0.0), 3)

    cursor.execute(f"SELECT AVG(processing_time) FROM evidence WHERE {scope} AND {processed} AND processing_time > 0", scope_params)
    avg_time_row = cursor.fetchone()[0]
    avg_latency = round(float(avg_time_row or 0.0), 2)

    flagged_rate = round((fake_count / processed_records * 100), 1) if processed_records > 0 else 0.0

    # Severity tier counts
    critical_count = count("severity_tier = 'CRITICAL_FRAUD'")
    high_risk_count = count("severity_tier = 'HIGH_RISK'")
    suspicious_count = count("severity_tier = 'SUSPICIOUS'")
    low_risk_count = count("severity_tier = 'LOW_RISK'")

    cursor.execute(f"""
        SELECT id, filename, media_type, fraud_category, ai_prediction, confidence,
               risk_score, severity_tier, recommended_action,
               final_reasoning, processing_time, processed_at
        FROM evidence
        WHERE {scope}
        ORDER BY id DESC
        LIMIT 25
    """, scope_params)
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
        "severity_breakdown": {
            "critical_fraud": critical_count,
            "high_risk": high_risk_count,
            "suspicious": suspicious_count,
            "low_risk": low_risk_count
        },
        "recent_evaluations": recent
    }

def get_evaluations_list(limit: int = 50, offset: int = 0, owner_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """Returns paginated evaluations."""
    conn = get_connection()
    cursor = conn.cursor()
    placeholder = "%s" if is_postgres() and hasattr(conn, "cursor_factory") else "?"
    scope, scope_params = _owner_scope(conn, owner_id)
    cursor.execute(f"""
        SELECT id, filename, media_type, fraud_category, ground_truth,
               ai_prediction, confidence, risk_score, severity_tier, recommended_action,
               vision_findings, final_reasoning,
               processing_time, processed_at
        FROM evidence
        WHERE {scope}
        ORDER BY id DESC
        LIMIT {placeholder} OFFSET {placeholder}
    """, (*scope_params, limit, offset))
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows

def export_evaluations_csv(owner_id: Optional[str] = None) -> str:
    """Generates a CSV report string of all processed evaluations."""
    conn = get_connection()
    cursor = conn.cursor()
    scope, scope_params = _owner_scope(conn, owner_id)
    cursor.execute(f"""
        SELECT filename, media_type, fraud_category, ground_truth,
               ai_prediction, confidence, risk_score, severity_tier, recommended_action,
               vision_findings, final_reasoning,
               processing_time, processed_at
        FROM evidence
        WHERE {scope} AND (is_processed = 1 OR is_processed = TRUE)
        ORDER BY id DESC
    """, scope_params)
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
        "Risk Score",
        "Severity Tier",
        "Recommended Action",
        "Visual Findings",
        "Reasoning Output",
        "Latency (sec)",
        "Processed At"
    ])

    for row in rows:
        row_dict = dict(row)
        risk_val = row_dict.get("risk_score")
        writer.writerow([
            row_dict["filename"],
            row_dict["media_type"],
            row_dict["fraud_category"],
            row_dict["ground_truth"],
            row_dict["ai_prediction"],
            f"{float(row_dict['confidence'] or 0.0):.2f}",
            f"{float(risk_val):.2f}" if risk_val is not None else "--",
            row_dict.get("severity_tier") or "N/A",
            row_dict.get("recommended_action") or "MANUAL_REVIEW",
            row_dict["vision_findings"] or "",
            row_dict["final_reasoning"] or "",
            f"{float(row_dict['processing_time'] or 0.0):.2f}",
            row_dict["processed_at"] or ""
        ])

    conn.close()
    return output.getvalue()


def consume_daily_files(owner_id: str, files: int, limit: int) -> bool:
    """Count files against an owner's daily allowance. False means over the limit.

    The check and the increment are one statement, so two uploads at once
    cannot both slip under the limit.
    """
    if files <= 0:
        return True
    if files > limit:
        return False
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    conn = get_connection()
    try:
        postgres = is_postgres() and hasattr(conn, "cursor_factory")
        placeholder = "%s" if postgres else "?"
        query = f"""
            INSERT INTO web_usage (owner_id, day, files) VALUES ({placeholder}, {placeholder}, {placeholder})
            ON CONFLICT (owner_id, day) DO UPDATE SET files = web_usage.files + excluded.files
            WHERE web_usage.files + excluded.files <= {placeholder}
            RETURNING files
        """
        params = (owner_id, day, files, limit)
        if postgres:
            with conn.cursor() as cursor:
                cursor.execute(query, params)
                row = cursor.fetchone()
            conn.commit()
        else:
            with conn:
                row = conn.execute(query, params).fetchone()
        return row is not None
    finally:
        conn.close()
