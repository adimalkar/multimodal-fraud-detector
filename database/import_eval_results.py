"""
Import teammate's evaluation results from new_evaluation_results.txt into the SQLite database.
Extracts: verdict (ai_prediction), confidence score, and reason (final_reasoning).
Also imports vision findings for complete data.
"""
import os
import re
import sqlite3

# Configuration
RESULTS_FILE = os.environ.get("RESULTS_FILE_PATH") or os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "new_evaluation_results.txt"))
DB_PATH = os.environ.get("DATABASE_PATH") or os.path.join(os.path.dirname(__file__), "fraud_detection.db")

# The results came from this directory on a teammate's machine
SOURCE_DIR = r"D:\Stevens Hackathon\real\Real"


def parse_results(filepath):
    """Parse the evaluation results text file into a list of records."""
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    # Split by the separator that marks each entry
    entries = re.split(r"-{40}", content)
    
    # Actually split by the "--- filename ---" pattern
    # Each block starts with "--- filename ---" and ends with "----...----"
    blocks = re.split(r'\n--- (.+?) ---\n', content)
    
    # blocks[0] is the header, then alternating [filename, content, filename, content, ...]
    records = []
    for i in range(1, len(blocks) - 1, 2):
        filename = blocks[i].strip()
        block_content = blocks[i + 1]

        # Check if this is an error entry
        if block_content.strip().startswith("ERROR:"):
            print(f"  ⚠ Skipping {filename} (API error)")
            continue

        # Extract Verdict
        verdict_match = re.search(r'Verdict:\s*(Real|Fake)', block_content)
        if not verdict_match:
            print(f"  ⚠ Skipping {filename} (no verdict found)")
            continue
        verdict = verdict_match.group(1)

        # Extract Confidence Score (e.g. "83.00%")
        conf_match = re.search(r'Confidence Score:\s*([\d.]+)%', block_content)
        confidence = float(conf_match.group(1)) / 100.0 if conf_match else 0.0

        # Extract Reason (everything between "Reason:" and "Agent 1 Findings:")
        reason_match = re.search(r'Reason:\s*(.*?)(?:\nAgent 1 Findings:|\n-{40})', block_content, re.DOTALL)
        reason = reason_match.group(1).strip() if reason_match else ""

        # Extract Agent 1 Findings (everything after "Agent 1 Findings:")
        findings_match = re.search(r'Agent 1 Findings:\s*(.*?)$', block_content, re.DOTALL)
        vision_findings = findings_match.group(1).strip() if findings_match else ""
        # Clean up trailing dashes
        vision_findings = re.sub(r'\n-{40,}\s*$', '', vision_findings).strip()

        records.append({
            "filename": filename,
            "verdict": verdict,
            "confidence": confidence,
            "reason": reason,
            "vision_findings": vision_findings,
        })

    return records


def import_to_db(records):
    """Insert parsed records into the evidence table."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    inserted = 0
    updated = 0
    skipped = 0

    for rec in records:
        # Check if this filename already exists in the database
        cursor.execute("SELECT id, is_processed FROM evidence WHERE filename = ?", (rec["filename"],))
        existing = cursor.fetchone()

        if existing:
            rec_id, is_processed = existing
            if is_processed:
                print(f"  ⏩ {rec['filename']} already processed, skipping")
                skipped += 1
                continue

            # Update existing unprocessed record
            cursor.execute('''
                UPDATE evidence
                SET ai_prediction = ?,
                    confidence = ?,
                    vision_findings = ?,
                    final_reasoning = ?,
                    is_processed = 1,
                    processed_at = 'imported from teammate'
                WHERE id = ?
            ''', (rec["verdict"], rec["confidence"], rec["vision_findings"], rec["reason"], rec_id))
            updated += 1
            print(f"  ✏️  Updated: {rec['filename']} → {rec['verdict']} ({rec['confidence']*100:.0f}%)")
        else:
            # Insert new record (these images are from the teammate's Real directory)
            cursor.execute('''
                INSERT INTO evidence (filename, file_path, media_type, fraud_category, ground_truth,
                                     ai_prediction, confidence, vision_findings, final_reasoning,
                                     is_processed, processed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 'imported from teammate')
            ''', (
                rec["filename"],
                f"{SOURCE_DIR}\\{rec['filename']}",  # Original path on teammate's machine
                "Image",
                "Vehicle",  # These are all from the Real car accident folder
                "Real",     # Ground truth: from the "real" directory
                rec["verdict"],
                rec["confidence"],
                rec["vision_findings"],
                rec["reason"],
            ))
            inserted += 1
            print(f"  ✅ Inserted: {rec['filename']} → {rec['verdict']} ({rec['confidence']*100:.0f}%)")

    conn.commit()
    conn.close()
    return inserted, updated, skipped


def main():
    print("=" * 60)
    print("IMPORTING TEAMMATE'S EVALUATION RESULTS")
    print("=" * 60)
    print(f"Source: {RESULTS_FILE}")
    print(f"Database: {DB_PATH}\n")

    # Parse the results file
    print("Parsing evaluation results...")
    records = parse_results(RESULTS_FILE)
    print(f"Found {len(records)} valid results (skipped errors)\n")

    # Show summary before import
    fake_count = sum(1 for r in records if r["verdict"] == "Fake")
    real_count = sum(1 for r in records if r["verdict"] == "Real")
    print(f"Breakdown: {fake_count} Fake, {real_count} Real\n")

    # Import to database
    print("Importing to database...")
    inserted, updated, skipped = import_to_db(records)

    print(f"\n{'=' * 60}")
    print(f"IMPORT COMPLETE!")
    print(f"  New records inserted: {inserted}")
    print(f"  Existing records updated: {updated}")
    print(f"  Already processed (skipped): {skipped}")
    print(f"{'=' * 60}")

    # Show final DB stats
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM evidence")
    total = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM evidence WHERE is_processed = 1")
    processed = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM evidence WHERE is_processed = 1 AND ai_prediction = ground_truth")
    correct = cursor.fetchone()[0]
    conn.close()

    accuracy = (correct / processed * 100) if processed > 0 else 0
    print(f"\nDatabase Stats: {total} total records, {processed} processed, {accuracy:.1f}% accuracy")


if __name__ == "__main__":
    main()
