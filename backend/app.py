from fastapi import FastAPI, UploadFile, File, HTTPException, BackgroundTasks, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import os
import shutil
import uuid
import time
import asyncio
from typing import Dict, Any, Optional, List

try:
    from backend.qwen_agent import analyze_media, analyze_video
except ImportError:
    from qwen_agent import analyze_media, analyze_video

try:
    from backend.storage import (
        generate_presigned_upload_url,
        is_storage_configured,
        download_file_stream
    )
except ImportError:
    from storage import (
        generate_presigned_upload_url,
        is_storage_configured,
        download_file_stream
    )

try:
    from backend.db_service import (
        save_evaluation,
        get_analytics_summary,
        get_evaluations_list,
        export_evaluations_csv
    )
except ImportError:
    from db_service import (
        save_evaluation,
        get_analytics_summary,
        get_evaluations_list,
        export_evaluations_csv
    )

try:
    from backend.risk_scorer import MultimodalRiskScorer
    from backend.metadata_extractor import extract_metadata
except ImportError:
    from risk_scorer import MultimodalRiskScorer
    from metadata_extractor import extract_metadata

risk_scorer_engine = MultimodalRiskScorer()

app = FastAPI(
    title="FraudSight AI Backend API",
    description="Multi-agent multimodal insurance fraud detection API with asynchronous job queuing and object storage support",
    version="2.1.0"
)

# Enable CORS for Next.js frontend (Vercel, localhost, and custom domains)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

TEMP_DIR = os.path.join(os.path.dirname(__file__), "..", "temp_uploads")
os.makedirs(TEMP_DIR, exist_ok=True)

# In-memory job and batch stores
jobs: Dict[str, Dict[str, Any]] = {}
batches: Dict[str, Dict[str, Any]] = {}

class PresignedUrlRequest(BaseModel):
    filename: str
    content_type: str = "image/jpeg"

class AnalyzeUrlRequest(BaseModel):
    media_url: str
    filename: Optional[str] = "evidence_file"
    content_type: Optional[str] = None

def cleanup_old_jobs():
    """Remove jobs and batches older than 1 hour to prevent memory growth on free tiers."""
    now = time.time()
    expired_jobs = [jid for jid, j in jobs.items() if now - j.get("created_at", now) > 3600]
    for jid in expired_jobs:
        jobs.pop(jid, None)
    expired_batches = [bid for bid, b in batches.items() if now - b.get("created_at", now) > 3600]
    for bid in expired_batches:
        batches.pop(bid, None)

def detect_media_type(filename: str, content_type: str) -> tuple[str, str]:
    ext = filename.split(".")[-1].lower() if "." in filename else ""
    if ext == "pdf" or content_type == "application/pdf":
        return "Document", "application/pdf"
    elif ext in ["mp4", "avi", "mov", "mkv", "webm"] or "video" in content_type:
        return "Video", content_type or "video/mp4"
    elif ext in ["png"]:
        return "Image", "image/png"
    else:
        return "Image", content_type or "image/jpeg"

def execute_agent_analysis(file_path: str, media_type: str, content_type: str) -> Dict[str, Any]:
    """Runs multi-agent vision & critic forensics and formats result structure with unified risk scoring."""
    start_time = time.time()

    # 1. Forensic metadata extraction
    meta_info = extract_metadata(file_path, media_type)
    metadata_dict = meta_info.get("metadata", {})
    metadata_flags = meta_info.get("flags", [])
    flags_count = meta_info.get("flags_count", 0)

    # 2. Vision agent & LLM critic jury
    if media_type == "Video":
        raw_result = analyze_video(file_path)
    else:
        raw_result = analyze_media(file_path, content_type, media_type=media_type)

    elapsed = round(time.time() - start_time, 2)

    # 3. Normalize voting breakdown
    vote_breakdown = raw_result.get("vote_breakdown", {})
    votes_list = []
    fake_votes_conf = []
    real_votes_conf = []

    if isinstance(vote_breakdown, dict):
        for model_name, info in vote_breakdown.items():
            if isinstance(info, dict):
                v_vote = info.get("classification", "Unknown")
                v_conf = float(info.get("confidence", 0.0))
                votes_list.append({
                    "model": model_name,
                    "vote": v_vote,
                    "conf": v_conf
                })
                if v_vote.lower() == "fake":
                    fake_votes_conf.append(v_conf)
                elif v_vote.lower() == "real":
                    real_votes_conf.append(v_conf)

    classification = raw_result.get("classification", "Unknown")
    confidence_score = float(raw_result.get("confidence_score", 0.0))

    # 4. Multimodal risk heuristic calculation
    if classification.lower() == "fake":
        visual_score = confidence_score
    elif classification.lower() == "real":
        visual_score = max(0.0, 1.0 - confidence_score)
    else:
        visual_score = 0.5

    if fake_votes_conf:
        text_score = sum(fake_votes_conf) / len(fake_votes_conf)
    elif real_votes_conf:
        text_score = max(0.0, 1.0 - (sum(real_votes_conf) / len(real_votes_conf)))
    else:
        text_score = visual_score

    risk_assessment = risk_scorer_engine.calculate_risk(
        text_score=text_score,
        visual_score=visual_score,
        metadata_flags=flags_count,
        synergy_boost_enabled=True
    )

    return {
        "classification": classification,
        "confidence": confidence_score,
        "confidence_score": confidence_score,
        "reason": raw_result.get("reason", ""),
        "vision_findings": raw_result.get("vision_findings", ""),
        "votes": votes_list,
        "vote_breakdown": vote_breakdown,
        "consensus": raw_result.get("consensus", "majority"),
        "calibration": raw_result.get("calibration", ""),
        "elapsed_seconds": elapsed,
        "media_type": media_type,
        "multimodal_risk": {
            "risk_score": risk_assessment["risk_score"],
            "severity_tier": risk_assessment["severity_tier"],
            "recommended_action": risk_assessment["recommended_action"],
            "cross_modal_synergy_applied": risk_assessment["cross_modal_synergy_applied"],
            "breakdown": risk_assessment["breakdown"],
            "metadata": metadata_dict,
            "metadata_flags": metadata_flags,
            "metadata_flags_count": flags_count
        }
    }

def run_analysis_pipeline(job_id: str, file_path: str, media_type: str, content_type: str):
    """Synchronous worker function executed in background thread."""
    try:
        jobs[job_id]["status"] = "processing"
        jobs[job_id]["stage"] = "Multi-agent vision & critic forensics in progress..."
        jobs[job_id]["progress"] = 30
        jobs[job_id]["updated_at"] = time.time()

        if media_type == "Video":
            jobs[job_id]["stage"] = "Extracting video keyframes and analyzing frame sequences..."
            jobs[job_id]["progress"] = 45
        else:
            jobs[job_id]["stage"] = "Vision agent extracting micro-anomalies and critic jury evaluating..."
            jobs[job_id]["progress"] = 50

        formatted_result = execute_agent_analysis(file_path, media_type, content_type)
        elapsed = formatted_result["elapsed_seconds"]

        jobs[job_id]["status"] = "completed"
        jobs[job_id]["progress"] = 100
        jobs[job_id]["stage"] = "Analysis complete"
        jobs[job_id]["result"] = formatted_result
        jobs[job_id]["updated_at"] = time.time()

        # Automatically persist to database for analytics dashboard
        try:
            filename = jobs[job_id].get("filename", "evidence_file")
            risk_data = formatted_result.get("multimodal_risk", {})
            save_evaluation(
                filename=filename,
                media_type=media_type,
                ai_prediction=formatted_result["classification"],
                confidence=formatted_result["confidence"],
                final_reasoning=formatted_result["reason"],
                vision_findings=formatted_result.get("vision_findings", ""),
                processing_time=elapsed,
                risk_score=risk_data.get("risk_score"),
                severity_tier=risk_data.get("severity_tier"),
                recommended_action=risk_data.get("recommended_action")
            )
        except Exception as db_err:
            print(f"Database save notice: {db_err}")

    except Exception as e:
        jobs[job_id]["status"] = "failed"
        jobs[job_id]["progress"] = 100
        jobs[job_id]["stage"] = "Analysis failed"
        jobs[job_id]["error"] = str(e)
        jobs[job_id]["updated_at"] = time.time()
    finally:
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except Exception:
                pass

def run_batch_pipeline(batch_id: str, file_specs: List[Dict[str, str]]):
    """Processes batch items sequentially to prevent memory spikes on free tiers (512MB RAM)."""
    batch = batches.get(batch_id)
    if not batch:
        return

    batch["status"] = "processing"
    batch["updated_at"] = time.time()

    fake_count = 0
    real_count = 0
    error_count = 0
    total_conf = 0.0
    processed_count = 0
    total = len(file_specs)

    for idx, spec in enumerate(file_specs):
        file_path = spec["file_path"]
        filename = spec["filename"]
        media_type = spec["media_type"]
        content_type = spec["content_type"]

        item_entry = batch["items"][idx]
        item_entry["status"] = "processing"
        batch["stage"] = f"Processing item {idx + 1} of {total}: {filename}"
        batch["progress"] = int((idx / total) * 100)
        batch["updated_at"] = time.time()

        try:
            formatted_result = execute_agent_analysis(file_path, media_type, content_type)
            item_entry["status"] = "completed"
            item_entry["result"] = formatted_result
            classification = formatted_result.get("classification", "Unknown")
            conf = float(formatted_result.get("confidence", 0.0))

            if classification.lower() == "fake":
                fake_count += 1
            elif classification.lower() == "real":
                real_count += 1

            total_conf += conf
            processed_count += 1

            try:
                risk_data = formatted_result.get("multimodal_risk", {})
                save_evaluation(
                    filename=filename,
                    media_type=media_type,
                    ai_prediction=classification,
                    confidence=conf,
                    final_reasoning=formatted_result.get("reason", ""),
                    vision_findings=formatted_result.get("vision_findings", ""),
                    processing_time=formatted_result.get("elapsed_seconds", 0.0),
                    risk_score=risk_data.get("risk_score"),
                    severity_tier=risk_data.get("severity_tier"),
                    recommended_action=risk_data.get("recommended_action")
                )
            except Exception as dbe:
                print(f"Batch db save notice: {dbe}")

        except Exception as e:
            error_count += 1
            item_entry["status"] = "failed"
            item_entry["error"] = str(e)
        finally:
            if os.path.exists(file_path):
                try:
                    os.remove(file_path)
                except Exception:
                    pass

        batch["completed_items"] = idx + 1
        batch["progress"] = int(((idx + 1) / total) * 100)
        batch["summary"] = {
            "total": total,
            "processed": processed_count,
            "fake_count": fake_count,
            "real_count": real_count,
            "error_count": error_count,
            "avg_confidence": round(total_conf / processed_count, 3) if processed_count > 0 else 0.0
        }
        batch["updated_at"] = time.time()

    batch["status"] = "completed"
    batch["stage"] = "Batch analysis complete"
    batch["progress"] = 100
    batch["updated_at"] = time.time()

async def run_analysis_pipeline_from_url(job_id: str, media_url: str, media_type: str, content_type: str, filename: str):
    """Downloads remote file in stream chunks before dispatching to pipeline."""
    safe_filename = f"{job_id}_{os.path.basename(filename)}"
    file_path = os.path.join(TEMP_DIR, safe_filename)

    try:
        jobs[job_id]["stage"] = "Streaming media file into memory-efficient buffer..."
        jobs[job_id]["progress"] = 20
        await download_file_stream(media_url, file_path)

        # Offload CPU-heavy pipeline to thread pool
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, run_analysis_pipeline, job_id, file_path, media_type, content_type)
    except Exception as e:
        jobs[job_id]["status"] = "failed"
        jobs[job_id]["progress"] = 100
        jobs[job_id]["stage"] = "Failed to stream media"
        jobs[job_id]["error"] = str(e)
        jobs[job_id]["updated_at"] = time.time()
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except Exception:
                pass

@app.get("/")
def root():
    return {
        "service": "FraudSight AI Engine",
        "version": "2.1.0",
        "status": "online",
        "docs": "/docs",
        "storage": {
            "configured": is_storage_configured(),
            "presigned_upload": "POST /api/storage/presigned-url"
        },
        "endpoints": {
            "health": "/api/health",
            "submit_upload_job": "POST /api/analyze",
            "submit_batch_job": "POST /api/batch/analyze",
            "submit_url_job": "POST /api/analyze-url",
            "job_status": "GET /api/jobs/{job_id}",
            "batch_status": "GET /api/batch/{batch_id}"
        }
    }

@app.get("/health")
@app.get("/api/health")
def health_check():
    cleanup_old_jobs()
    return {
        "status": "healthy",
        "service": "FraudSight AI API",
        "storage_configured": is_storage_configured(),
        "active_jobs": len([j for j in jobs.values() if j.get("status") in ["queued", "processing"]]),
        "active_batches": len([b for b in batches.values() if b.get("status") in ["queued", "processing"]])
    }

@app.post("/api/storage/presigned-url")
def request_presigned_url(req: PresignedUrlRequest):
    """
    Generates a pre-signed URL for direct browser uploads to Cloudflare R2 / S3.
    Bypasses API server RAM completely.
    """
    return generate_presigned_upload_url(req.filename, req.content_type)

@app.get("/api/storage/status")
def storage_status():
    return {
        "configured": is_storage_configured(),
        "endpoint": os.environ.get("S3_ENDPOINT_URL") or os.environ.get("R2_ENDPOINT_URL"),
        "bucket": os.environ.get("S3_BUCKET_NAME") or os.environ.get("R2_BUCKET_NAME")
    }

@app.post("/api/analyze")
async def create_analysis_job(background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    """Accepts direct multipart file upload and enqueues background evaluation."""
    if not file or not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")

    cleanup_old_jobs()
    job_id = str(uuid.uuid4())
    safe_filename = f"{job_id}_{os.path.basename(file.filename)}"
    file_path = os.path.join(TEMP_DIR, safe_filename)

    try:
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save upload: {e}")

    media_type, content_type = detect_media_type(file.filename, file.content_type or "")

    jobs[job_id] = {
        "job_id": job_id,
        "filename": file.filename,
        "media_type": media_type,
        "content_type": content_type,
        "status": "queued",
        "progress": 10,
        "stage": f"Queued for {media_type.lower()} forensics...",
        "created_at": time.time(),
        "updated_at": time.time(),
        "result": None,
        "error": None
    }

    background_tasks.add_task(run_analysis_pipeline, job_id, file_path, media_type, content_type)

    return {
        "job_id": job_id,
        "status": "queued",
        "media_type": media_type,
        "filename": file.filename,
        "message": "Analysis started in background. Poll /api/jobs/{job_id} for progress."
    }

@app.post("/api/analyze-url")
async def create_analysis_job_from_url_endpoint(background_tasks: BackgroundTasks, req: AnalyzeUrlRequest):
    """
    Initiates analysis on a media file stored in Cloudflare R2 / S3 / Supabase.
    Buffers the file in chunks without crashing 512MB RAM containers.
    """
    if not req.media_url:
        raise HTTPException(status_code=400, detail="media_url is required")

    cleanup_old_jobs()
    job_id = str(uuid.uuid4())
    media_type, content_type = detect_media_type(req.filename or "file", req.content_type or "")

    jobs[job_id] = {
        "job_id": job_id,
        "filename": req.filename,
        "media_url": req.media_url,
        "media_type": media_type,
        "content_type": content_type,
        "status": "queued",
        "progress": 10,
        "stage": f"Queued for {media_type.lower()} forensics from cloud storage...",
        "created_at": time.time(),
        "updated_at": time.time(),
        "result": None,
        "error": None
    }

    background_tasks.add_task(run_analysis_pipeline_from_url, job_id, req.media_url, media_type, content_type, req.filename or "file")

    return {
        "job_id": job_id,
        "status": "queued",
        "media_type": media_type,
        "filename": req.filename,
        "message": "Analysis started from cloud storage URL. Poll /api/jobs/{job_id} for progress."
    }

@app.get("/api/jobs/{job_id}")
def get_job_status(job_id: str):
    cleanup_old_jobs()
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found or expired")

    now = time.time()
    elapsed = round(now - job.get("created_at", now), 1)

    return {
        "job_id": job_id,
        "status": job["status"],
        "progress": job.get("progress", 0),
        "stage": job.get("stage", ""),
        "elapsed_seconds": elapsed,
        "result": job.get("result"),
        "error": job.get("error")
    }

@app.post("/api/batch/analyze")
async def create_batch_job(background_tasks: BackgroundTasks, files: List[UploadFile] = File(...)):
    """Accepts multiple evidence files and processes them sequentially in background without OOM."""
    if not files:
        raise HTTPException(status_code=400, detail="No files provided")

    valid_files = [f for f in files if f.filename and len(f.filename.strip()) > 0]
    if not valid_files:
        raise HTTPException(status_code=400, detail="No valid files provided")

    cleanup_old_jobs()
    batch_id = str(uuid.uuid4())
    file_specs = []
    items = []

    for i, file in enumerate(valid_files):
        safe_filename = f"batch_{batch_id}_{i}_{os.path.basename(file.filename)}"
        file_path = os.path.join(TEMP_DIR, safe_filename)

        try:
            with open(file_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to save upload '{file.filename}': {e}")

        media_type, content_type = detect_media_type(file.filename, file.content_type or "")

        file_specs.append({
            "file_path": file_path,
            "filename": file.filename,
            "media_type": media_type,
            "content_type": content_type
        })

        items.append({
            "item_id": i,
            "filename": file.filename,
            "media_type": media_type,
            "status": "queued",
            "result": None,
            "error": None
        })

    batches[batch_id] = {
        "batch_id": batch_id,
        "status": "queued",
        "stage": f"Queued {len(valid_files)} evidence files for batch evaluation...",
        "total_items": len(valid_files),
        "completed_items": 0,
        "progress": 0,
        "created_at": time.time(),
        "updated_at": time.time(),
        "summary": {
            "total": len(valid_files),
            "processed": 0,
            "fake_count": 0,
            "real_count": 0,
            "error_count": 0,
            "avg_confidence": 0.0
        },
        "items": items
    }

    background_tasks.add_task(run_batch_pipeline, batch_id, file_specs)

    return {
        "batch_id": batch_id,
        "status": "queued",
        "total_files": len(valid_files),
        "message": f"Batch analysis of {len(valid_files)} items started in background. Poll /api/batch/{batch_id} for progress."
    }

@app.get("/api/batch/{batch_id}")
def get_batch_status(batch_id: str):
    cleanup_old_jobs()
    batch = batches.get(batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found or expired")

    now = time.time()
    elapsed = round(now - batch.get("created_at", now), 1)

    return {
        "batch_id": batch_id,
        "status": batch["status"],
        "stage": batch.get("stage", ""),
        "total_items": batch["total_items"],
        "completed_items": batch["completed_items"],
        "progress": batch["progress"],
        "elapsed_seconds": elapsed,
        "summary": batch["summary"],
        "items": batch["items"]
    }

# Backward compatible synchronous endpoint
@app.post("/analyze_media")
async def analyze_media_sync(file: UploadFile = File(...)):
    if not file or not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")

    file_id = str(uuid.uuid4())
    file_path = os.path.join(TEMP_DIR, f"sync_{file_id}_{file.filename}")
    try:
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        media_type, content_type = detect_media_type(file.filename, file.content_type or "")
        if media_type == "Video":
            return analyze_video(file_path)
        else:
            return analyze_media(file_path, content_type, media_type=media_type)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except Exception:
                pass

# Analytics & Reporting endpoints
@app.get("/api/analytics/stats")
def get_analytics_stats():
    cleanup_old_jobs()
    return get_analytics_summary()

@app.get("/api/analytics/evaluations")
def get_evaluations(limit: int = 50, offset: int = 0):
    cleanup_old_jobs()
    return {
        "evaluations": get_evaluations_list(limit=limit, offset=offset),
        "limit": limit,
        "offset": offset
    }

@app.get("/api/analytics/export-csv")
def download_evaluations_csv():
    csv_data = export_evaluations_csv()
    return Response(
        content=csv_data,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=fraud_detection_report.csv"}
    )

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("backend.app:app", host="0.0.0.0", port=port, reload=True)
