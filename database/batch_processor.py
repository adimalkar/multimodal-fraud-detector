import os
import sqlite3
import time
import json
import sys

# Ensure backend modules can be imported
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
from backend.qwen_agent import analyze_media

DB_PATH = os.environ.get("DATABASE_PATH") or os.path.join(os.path.dirname(__file__), "fraud_detection.db")

def process_batch():
    # Connect to the database
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Query for all unprocessed records (images + documents)
    cursor.execute("SELECT id, filename, file_path, fraud_category, ground_truth, media_type FROM evidence WHERE is_processed = 0")
    unprocessed_records = cursor.fetchall()
    
    if not unprocessed_records:
        print("🎉 All records in the database have already been processed!")
        conn.close()
        return

    print(f"🔍 Found {len(unprocessed_records)} unprocessed records. Beginning Batch Inference...\n")
    print(f"Using pipeline: Qwen-VL-Plus (Vision) -> Voting(Qwen, DeepSeek V3.2, GLM 4.6)\n")
    
    processed_count = 0
    
    for record in unprocessed_records:
        rec_id, filename, file_path, fraud_category, ground_truth, media_type = record
        type_label = f"📄 Document" if media_type == "Document" else f"🖼️ Image"
        print(f"[{processed_count+1}/{len(unprocessed_records)}] Analyzing ({type_label}): {filename} (Ground Truth: {ground_truth})")
        
        # Determine content type for the API
        ext = filename.split('.')[-1].lower()
        content_type = "image/jpeg"
        if ext == "png":
            content_type = "image/png"
        elif ext == "pdf":
            content_type = "application/pdf"
        
        start_time = time.time()
        
        try:
            # Send to the appropriate pipeline
            if media_type == "Video":
                from backend.qwen_agent import analyze_video
                result = analyze_video(file_path)
            else:
                result = analyze_media(file_path, content_type, media_type=media_type)
            
            # Extract results
            ai_prediction = result.get("classification", "Error")
            confidence = result.get("confidence_score", 0.0)
            vision_findings = result.get("vision_findings", "")
            final_reasoning = result.get("reason", "")
            
            # Convert voting breakdown to JSON string for storage if needed, though we just store final reasoning
            if "vote_breakdown" in result:
                final_reasoning += f"\n\nVotes: {json.dumps(result['vote_breakdown'])}"
                
        except Exception as e:
            print(f"❌ Error processing {filename}: {e}")
            ai_prediction = "Error"
            confidence = 0.0
            vision_findings = f"Failed: {str(e)}"
            final_reasoning = ""
            
        processing_time = round(time.time() - start_time, 2)
        processed_at = time.strftime('%Y-%m-%d %H:%M:%S')
        
        # Update the database
        cursor.execute('''
            UPDATE evidence 
            SET ai_prediction = ?, 
                confidence = ?, 
                vision_findings = ?, 
                final_reasoning = ?, 
                is_processed = 1, 
                processing_time = ?, 
                processed_at = ?
            WHERE id = ?
        ''', (ai_prediction, confidence, vision_findings, final_reasoning, processing_time, processed_at, rec_id))
        
        conn.commit()
        
        match_str = "✅ Correct" if ai_prediction == ground_truth else "❌ False Prediction"
        if ai_prediction == "Error": match_str = "⚠️ Error"
        
        print(f"   -> AI Says: {ai_prediction} ({confidence*100:.1f}%) | Time: {processing_time}s | {match_str}\n")
        processed_count += 1
        
        # Add a small delay so we don't accidentally get rate-limited by OpenRouter/Featherless
        time.sleep(1.5)

    conn.close()
    print(f"\n✅ Batch Processing Complete! Successfully processed {processed_count} files.")

if __name__ == "__main__":
    process_batch()
