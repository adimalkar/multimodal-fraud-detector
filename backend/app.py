from fastapi import FastAPI, UploadFile, File, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
import os
import shutil
import uuid
import time
import asyncio
from typing import Dict, Any

try:
    from backend.qwen_agent import analyze_media, analyze_video
except ImportError:
    from qwen_agent import analyze_media, analyze_video

app = FastAPI(
    title="FraudSight AI Backend API",
    description="Multi-agent multimodal insurance fraud detection API with asynchronous job queuing",
    version="2.0.0"
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

@app.get("/")
def root():
    return {
        "service": "FraudSight AI Engine",
        "version": "2.0.0",
        "status": "online",
        "docs": "/docs",
        "endpoints": {
            "health": "/api/health",
            "submit_job": "POST /api/analyze",
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
        "active_jobs": len([j for j in jobs.values() if j.get("status") in ["queued", "processing"]])
    }

@app.post("/api/analyze")
async def create_analysis_job(background_tasks: BackgroundTasks, file: UploadFile = File(...)):
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

    # Execute in background thread so request returns immediately (<100ms)
    background_tasks.add_task(run_analysis_pipeline, job_id, file_path, media_type, content_type)

    return {
        "job_id": job_id,
        "status": "queued",
        "media_type": media_type,
        "filename": file.filename,
        "message": "Analysis started in background. Poll /api/jobs/{job_id} for progress."
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

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("backend.app:app", host="0.0.0.0", port=port, reload=True)
