from fastapi import FastAPI, UploadFile, File, HTTPException, BackgroundTasks, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import os
import shutil
import uuid
import time
import asyncio
from typing import Dict, Any, Optional

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

# In-memory job store
jobs: Dict[str, Dict[str, Any]] = {}

class PresignedUrlRequest(BaseModel):
    filename: str
    content_type: str = "image/jpeg"

class AnalyzeUrlRequest(BaseModel):
    media_url: str
    filename: Optional[str] = "evidence_file"
    content_type: Optional[str] = None

def cleanup_old_jobs():
    """Remove jobs older than 1 hour to prevent memory growth on free tiers."""
    now = time.time()
    expired = [jid for jid, j in jobs.items() if now - j.get("created_at", now) > 3600]
    for jid in expired:
        jobs.pop(jid, None)

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

def run_analysis_pipeline(job_id: str, file_path: str, media_type: str, content_type: str):
    """Synchronous worker function executed in background thread."""
    start_time = time.time()
    try:
        jobs[job_id]["status"] = "processing"
        jobs[job_id]["stage"] = "Multi-agent vision & critic forensics in progress..."
        jobs[job_id]["progress"] = 30
        jobs[job_id]["updated_at"] = time.time()

        if media_type == "Video":
            jobs[job_id]["stage"] = "Extracting video keyframes and analyzing frame sequences..."
            jobs[job_id]["progress"] = 45
            raw_result = analyze_video(file_path)
        else:
            jobs[job_id]["stage"] = "Vision agent extracting micro-anomalies and critic jury evaluating..."
            jobs[job_id]["progress"] = 50
            raw_result = analyze_media(file_path, content_type, media_type=media_type)

        elapsed = round(time.time() - start_time, 2)

        # Normalize result for consistent frontend consumption
        vote_breakdown = raw_result.get("vote_breakdown", {})
        votes_list = []
        if isinstance(vote_breakdown, dict):
            for model_name, info in vote_breakdown.items():
                if isinstance(info, dict):
                    votes_list.append({
                        "model": model_name,
                        "vote": info.get("classification", "Unknown"),
                        "conf": info.get("confidence", 0.0)
                    })

        formatted_result = {
            "classification": raw_result.get("classification", "Unknown"),
            "confidence": raw_result.get("confidence_score", 0.0),
            "confidence_score": raw_result.get("confidence_score", 0.0),
            "reason": raw_result.get("reason", ""),
            "vision_findings": raw_result.get("vision_findings", ""),
            "votes": votes_list,
            "vote_breakdown": vote_breakdown,
            "consensus": raw_result.get("consensus", "majority"),
            "calibration": raw_result.get("calibration", ""),
            "elapsed_seconds": elapsed,
            "media_type": media_type
        }

        jobs[job_id]["status"] = "completed"
        jobs[job_id]["progress"] = 100
        jobs[job_id]["stage"] = "Analysis complete"
        jobs[job_id]["result"] = formatted_result
        jobs[job_id]["updated_at"] = time.time()

        # Automatically persist to database for analytics dashboard
        try:
            filename = jobs[job_id].get("filename", "evidence_file")
            save_evaluation(
                filename=filename,
                media_type=media_type,
                ai_prediction=formatted_result["classification"],
                confidence=formatted_result["confidence"],
                final_reasoning=formatted_result["reason"],
                vision_findings=formatted_result.get("vision_findings", ""),
                processing_time=elapsed
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
            "submit_url_job": "POST /api/analyze-url",
            "job_status": "GET /api/jobs/{job_id}"
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
        "active_jobs": len([j for j in jobs.values() if j.get("status") in ["queued", "processing"]])
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
