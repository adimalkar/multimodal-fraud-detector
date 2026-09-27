from fastapi import FastAPI, UploadFile, File, HTTPException, BackgroundTasks, Response, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import os
import shutil
import uuid
import time
import asyncio
import hashlib
import json
from functools import lru_cache
from typing import Dict, Any, Optional, List

from backend.durable_auth import configured_tokens, require_tenant
from backend.durable_jobs import SCHEMA_VERSION, IdempotencyConflict, JobBusy, QuotaExceeded
from backend.durable_worker import build_components, delete_private_job, run_once
from backend.image_evidence import IMAGE_PIPELINE_VERSION

try:
    from backend.guardrails import (
        enforce_rate_limit,
        validate_file_extension,
        validate_file_size,
        validate_batch_size,
        rate_limiter,
        MAX_FILE_SIZE_MB,
        MAX_BATCH_SIZE,
        ALLOWED_EXTENSIONS,
    )
except ImportError:
    from guardrails import (
        enforce_rate_limit,
        validate_file_extension,
        validate_file_size,
        validate_batch_size,
        rate_limiter,
        MAX_FILE_SIZE_MB,
        MAX_BATCH_SIZE,
        ALLOWED_EXTENSIONS,
    )

try:
    from backend.qwen_agent import analyze_media, analyze_video, missing_model_credentials
except ImportError:
    from qwen_agent import analyze_media, analyze_video, missing_model_credentials

try:
    from backend.provider_readiness import verify_provider_authentication
except ImportError:
    from provider_readiness import verify_provider_authentication

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
single_model_risk_scorer = MultimodalRiskScorer(
    text_weight=0.0, visual_weight=1.0, metadata_weight=0.0
)

app = FastAPI(
    title="FraudSight AI Backend API",
    description="Visual evidence screening API with asynchronous jobs and object storage support",
    version="2.2.0"
)

# Durable mode only accepts explicitly configured frontend origins.
cors_origins = (
    [origin.strip() for origin in os.getenv("CORS_ALLOWED_ORIGINS", "").split(",") if origin.strip()]
    if os.getenv("DURABLE_JOBS_ENABLED", "0") == "1" else ["*"]
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=cors_origins != ["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

TEMP_DIR = os.path.join(os.path.dirname(__file__), "..", "temp_uploads")
os.makedirs(TEMP_DIR, exist_ok=True)

# In-memory job and batch stores
jobs: Dict[str, Dict[str, Any]] = {}
batches: Dict[str, Dict[str, Any]] = {}

DURABLE_JOBS_ENABLED = os.getenv("DURABLE_JOBS_ENABLED", "0") == "1"
DURABLE_EXECUTION_MODE = os.getenv("DURABLE_EXECUTION_MODE", "external")


def image_evidence_mode(file: UploadFile) -> bool:
    if os.getenv("IMAGE_EVIDENCE_PIPELINE_ENABLED", "0") != "1":
        return False
    media_type, _ = detect_media_type(file.filename, file.content_type or "")
    return media_type == "Image"


@lru_cache(maxsize=1)
def durable_components():
    try:
        return build_components()
    except Exception as error:
        raise HTTPException(status_code=503, detail="Durable analysis storage is unavailable") from error


def durable_quota():
    return {
        "max_daily_jobs": int(os.getenv("DURABLE_DAILY_JOBS_PER_TENANT", "20")),
        "max_daily_reserved_usd": float(os.getenv("DURABLE_DAILY_RESERVED_USD", "0.50")),
        "reserve_per_job_usd": float(os.getenv("DURABLE_RESERVE_PER_JOB_USD", "0.01")),
    }


def durable_idempotency_key(request: Request):
    key = request.headers.get("idempotency-key")
    if key and (len(key) > 128 or not key.strip()):
        raise HTTPException(status_code=400, detail="Invalid Idempotency-Key")
    return key


def durable_enqueue(background_tasks, request, owner_id, uploads):
    store, artifacts = durable_components()
    specs = []
    keys = []
    try:
        if DURABLE_EXECUTION_MODE == "external" and not store.worker_recent():
            raise HTTPException(status_code=503, detail="Analysis worker is unavailable")
        for file in uploads:
            media_type, content_type = detect_media_type(file.filename, file.content_type or "")
            key, digest, size = artifacts.put_upload(file.file, file.filename)
            keys.append(key)
            specs.append({
                "filename": file.filename,
                "media_type": media_type,
                "content_type": content_type,
                "artifact_key": key,
                "artifact_sha256": digest,
                "size": size,
                "pipeline_version": (
                    IMAGE_PIPELINE_VERSION if image_evidence_mode(file) else SCHEMA_VERSION
                ),
            })
        if sum(spec["size"] for spec in specs) > int(os.getenv("DURABLE_MAX_BATCH_BYTES", "104857600")):
            raise HTTPException(status_code=413, detail="Batch exceeds total size limit")
        fingerprint = hashlib.sha256(json.dumps(
            [
                (
                    spec["filename"], spec["artifact_sha256"], spec["pipeline_version"]
                ) if spec["pipeline_version"] != SCHEMA_VERSION else (
                    spec["filename"], spec["artifact_sha256"]
                )
                for spec in specs
            ],
            separators=(",", ":"),
        ).encode()).hexdigest()
        primary, created = store.create(
            owner_id, specs, idempotency_key=durable_idempotency_key(request),
            request_fingerprint=fingerprint, **durable_quota(),
        )
    except HTTPException:
        raise
    except QuotaExceeded as error:
        raise HTTPException(status_code=429, detail=str(error)) from error
    except IdempotencyConflict as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(status_code=503, detail="Durable analysis storage is unavailable") from error
    finally:
        # Stored objects for a duplicate/failed submission are not owned by a job.
        if "created" not in locals() or not created:
            for key in keys:
                try:
                    artifacts.delete(key)
                except Exception:
                    pass
    if created and DURABLE_EXECUTION_MODE == "inline":
        background_tasks.add_task(durable_process_pending, len(specs))
    return primary


def durable_process_pending(max_items: int):
    store, artifacts = durable_components()
    for _ in range(max_items):
        if not run_once(store, artifacts):
            break


def durable_item_response(job):
    return {
        "job_id": job["id"],
        "status": "queued" if job["status"] == "queued_image" else job["status"],
        "progress": job["progress"], "stage": job["stage"],
        "elapsed_seconds": round(time.time() - job["created_at"], 1),
        "result": json.loads(job["result_json"]) if job["result_json"] else None,
        "error": job["error_message"],
        "error_code": job["error_code"],
        "pipeline_version": job["pipeline_version"],
        "artifact_sha256": job["artifact_sha256"],
    }


def durable_batch_response(parent, children):
    completed = [row for row in children if row["status"] == "completed"]
    failed = [row for row in children if row["status"] == "failed"]
    done = len(completed) + len(failed)
    total = len(children)
    status = (
        "failed" if done == total and not completed else
        "completed" if done == total else
        "processing" if any(row["status"] == "processing" for row in children) or done else
        "queued"
    )
    results = [json.loads(row["result_json"]) for row in completed]
    confidences = [float(result.get("confidence", 0)) for result in results]
    summary = {
        "total": total, "processed": len(completed),
        "fake_count": sum(result.get("classification", "").lower() == "fake" for result in results),
        "real_count": sum(result.get("classification", "").lower() == "real" for result in results),
        "error_count": len(failed),
        "avg_confidence": round(sum(confidences) / len(confidences), 3) if confidences else 0.0,
    }
    return {
        "batch_id": parent["id"], "status": status,
        "stage": "Batch analysis complete" if done == total else "Batch analysis in progress",
        "total_items": total, "completed_items": done,
        "progress": int(done / total * 100) if total else 0,
        "elapsed_seconds": round(time.time() - parent["created_at"], 1),
        "summary": summary,
        "error": "All batch items failed analysis" if status == "failed" else None,
        "items": [
            {
                "item_id": row["item_index"], "filename": row["filename"],
                "media_type": row["media_type"],
                "status": "queued" if row["status"] == "queued_image" else row["status"],
                "result": json.loads(row["result_json"]) if row["result_json"] else None,
                "error": row["error_message"],
            }
            for row in children
        ],
    }


def ensure_analysis_available():
    """Reject analysis requests before staging files when providers are unconfigured."""
    missing = missing_model_credentials()
    if missing:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "MODEL_PROVIDERS_UNCONFIGURED",
                "message": "Analysis is unavailable until model provider credentials are configured.",
                "missing_credentials": missing,
            },
        )
    providers = verify_provider_authentication()
    if any(provider["status"] != "authenticated" for provider in providers.values()):
        raise HTTPException(
            status_code=503,
            detail={
                "code": "MODEL_PROVIDERS_UNAVAILABLE",
                "message": "Analysis is unavailable because model providers could not be authenticated.",
                "providers": providers,
            },
        )

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
    if ext == "pdf":
        return "Document", "application/pdf"
    if ext in {"mp4", "avi", "mov", "mkv", "webm"}:
        mime = {
            "mp4": "video/mp4", "avi": "video/x-msvideo", "mov": "video/quicktime",
            "mkv": "video/x-matroska", "webm": "video/webm",
        }
        return "Video", mime[ext]
    if ext == "png":
        return "Image", "image/png"
    if ext == "webp":
        return "Image", "image/webp"
    return "Image", "image/jpeg"

def execute_agent_analysis(file_path: str, media_type: str, content_type: str) -> Dict[str, Any]:
    """Run visual screening and format its provisional result with metadata signals."""
    start_time = time.time()

    # 1. Forensic metadata extraction
    meta_info = extract_metadata(file_path, media_type)
    metadata_dict = meta_info.get("metadata", {})
    metadata_flags = meta_info.get("flags", [])
    flags_count = meta_info.get("flags_count", 0)

    # 2. One bounded vision request
    if media_type == "Video":
        raw_result = analyze_video(file_path)
    else:
        raw_result = analyze_media(file_path, content_type, media_type=media_type)

    elapsed = round(time.time() - start_time, 2)

    # 3. Keep model attribution in the existing response shape
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
    if classification.lower() not in {"real", "fake"}:
        raise RuntimeError("Analysis did not return a valid Real or Fake verdict.")

    # 4. Compute a provisional visual score, never an automatic decision.
    # Unverified metadata observations have no evidence-backed weight.
    if classification.lower() == "fake":
        visual_score = confidence_score
    elif classification.lower() == "real":
        visual_score = max(0.0, 1.0 - confidence_score)
    else:
        visual_score = 0.5

    single_visual_model = raw_result.get("consensus", "").endswith("single_model")
    if single_visual_model:
        text_score = 0.0
    elif fake_votes_conf:
        text_score = sum(fake_votes_conf) / len(fake_votes_conf)
    elif real_votes_conf:
        text_score = max(0.0, 1.0 - (sum(real_votes_conf) / len(real_votes_conf)))
    else:
        text_score = visual_score

    scorer = single_model_risk_scorer if single_visual_model else risk_scorer_engine
    risk_assessment = scorer.calculate_risk(
        text_score=text_score,
        visual_score=visual_score,
        metadata_flags=flags_count,
        synergy_boost_enabled=not single_visual_model
    )
    if single_visual_model:
        risk_assessment["recommended_action"] = "MANUAL_REVIEW"

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
        "risk_calibration": "Visual-only screening score; not a calibrated fraud probability. Metadata is context only.",
        "model_usage": raw_result.get("model_usage", {}),
        "needs_review": raw_result.get("needs_review", single_visual_model),
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
        jobs[job_id]["stage"] = "Preparing visual evidence for screening..."
        jobs[job_id]["progress"] = 30
        jobs[job_id]["updated_at"] = time.time()

        if media_type == "Video":
            jobs[job_id]["stage"] = "Sampling video frames for visual screening..."
            jobs[job_id]["progress"] = 45
        else:
            jobs[job_id]["stage"] = "Visual screening in progress..."
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

    if processed_count == 0:
        batch["status"] = "failed"
        batch["stage"] = "All batch items failed analysis"
        batch["error"] = "All batch items failed analysis. See item errors for details."
    else:
        batch["status"] = "completed"
        batch["stage"] = (
            f"Batch analysis complete with {error_count} failed item(s)"
            if error_count else "Batch analysis complete"
        )
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
        "version": "2.2.0",
        "status": "online",
        "docs": "/docs",
        "guardrails": {
            "max_file_size_mb": MAX_FILE_SIZE_MB,
            "max_batch_size": MAX_BATCH_SIZE,
            "allowed_extensions": sorted(list(ALLOWED_EXTENSIONS))
        },
        "storage": {
            "configured": is_storage_configured(),
            "presigned_upload": "POST /api/storage/presigned-url"
        },
        "endpoints": {
            "health": "/api/health",
            "readiness": "/api/ready",
            "submit_upload_job": "POST /api/analyze",
            "submit_batch_job": "POST /api/batch/analyze",
            "submit_url_job": "POST /api/analyze-url",
            "job_status": "GET /api/jobs/{job_id}",
            "batch_status": "GET /api/batch/{batch_id}",
            "analytics_stats": "GET /api/analytics/stats",
            "analytics_evaluations": "GET /api/analytics/evaluations",
            "analytics_export_csv": "GET /api/analytics/export-csv"
        }
    }

@app.get("/health")
@app.get("/api/health")
def health_check():
    if DURABLE_JOBS_ENABLED:
        store, _ = durable_components()
        try:
            counts = store.active_counts()
            worker_available = store.worker_recent() if DURABLE_EXECUTION_MODE == "external" else True
        except Exception as error:
            raise HTTPException(status_code=503, detail="Durable job database is unavailable") from error
        return {
            "status": "healthy", "service": "FraudSight AI API",
            "providers_configured": not missing_model_credentials(),
            "storage_configured": True,
            **counts,
            "job_backend": "durable",
            "auth_configured": configured_tokens() is not None,
            "worker_available": worker_available,
        }
    cleanup_old_jobs()
    return {
        "status": "healthy",
        "service": "FraudSight AI API",
        "providers_configured": not missing_model_credentials(),
        "storage_configured": is_storage_configured(),
        "active_jobs": len([j for j in jobs.values() if j.get("status") in ["queued", "processing"]]),
        "active_batches": len([b for b in batches.values() if b.get("status") in ["queued", "processing"]])
    }


@app.get("/api/ready")
def readiness_check():
    """Check provider authentication before accepting analysis work."""
    ensure_analysis_available()
    if DURABLE_JOBS_ENABLED:
        store, _ = durable_components()
        if configured_tokens() is None:
            raise HTTPException(status_code=503, detail="Analysis authentication is not configured")
        if DURABLE_EXECUTION_MODE == "external":
            try:
                worker_available = store.worker_recent()
            except Exception as error:
                raise HTTPException(status_code=503, detail="Durable job database is unavailable") from error
            if not worker_available:
                raise HTTPException(status_code=503, detail="Analysis worker is unavailable")
    return {"status": "ready", "analysis_ready": True}

@app.post("/api/storage/presigned-url")
def request_presigned_url(req: PresignedUrlRequest, request: Request):
    """
    Generates a pre-signed URL for direct browser uploads to Cloudflare R2 / S3.
    Bypasses API server RAM completely.
    """
    if DURABLE_JOBS_ENABLED:
        require_tenant(request)
        raise HTTPException(status_code=410, detail="Use authenticated direct upload")
    enforce_rate_limit(request)
    validate_file_extension(req.filename)
    return generate_presigned_upload_url(req.filename, req.content_type)

@app.get("/api/storage/status")
def storage_status():
    return {
        "configured": is_storage_configured(),
        "endpoint": os.environ.get("S3_ENDPOINT_URL") or os.environ.get("R2_ENDPOINT_URL"),
        "bucket": os.environ.get("S3_BUCKET_NAME") or os.environ.get("R2_BUCKET_NAME")
    }

@app.post("/api/analyze")
async def create_analysis_job(background_tasks: BackgroundTasks, request: Request, file: UploadFile = File(...)):
    """Accepts direct multipart file upload and enqueues background evaluation."""
    if DURABLE_JOBS_ENABLED:
        owner_id = require_tenant(request)
        enforce_rate_limit(request)
        if not file or not file.filename:
            raise HTTPException(status_code=400, detail="No file provided")
        validate_file_extension(file.filename)
        validate_file_size(file)
        if not image_evidence_mode(file):
            await asyncio.to_thread(ensure_analysis_available)
        job = await asyncio.to_thread(durable_enqueue, background_tasks, request, owner_id, [file])
        return {
            "job_id": job["id"],
            "status": "queued" if job["status"] == "queued_image" else job["status"],
            "media_type": job["media_type"], "filename": job["filename"],
            "message": "Analysis queued. Poll /api/jobs/{job_id} for progress.",
        }
    enforce_rate_limit(request)
    if not file or not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")

    validate_file_extension(file.filename)
    validate_file_size(file)
    ensure_analysis_available()

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
async def create_analysis_job_from_url_endpoint(background_tasks: BackgroundTasks, req: AnalyzeUrlRequest, request: Request):
    """
    Initiates analysis on a media file stored in Cloudflare R2 / S3 / Supabase.
    Buffers the file in chunks without crashing 512MB RAM containers.
    """
    if DURABLE_JOBS_ENABLED:
        require_tenant(request)
        raise HTTPException(status_code=410, detail="Arbitrary URL ingestion is disabled; use direct upload")
    enforce_rate_limit(request)
    if not req.media_url:
        raise HTTPException(status_code=400, detail="media_url is required")

    validate_file_extension(req.filename or "evidence.jpg")
    ensure_analysis_available()

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
def get_job_status(job_id: str, request: Request):
    if DURABLE_JOBS_ENABLED:
        owner_id = require_tenant(request)
        store, _ = durable_components()
        job = store.get(job_id, owner_id)
        if not job or job["kind"] != "item":
            raise HTTPException(status_code=404, detail="Job not found")
        return durable_item_response(job)
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


@app.delete("/api/jobs/{job_id}")
def delete_job(job_id: str, request: Request):
    if not DURABLE_JOBS_ENABLED:
        raise HTTPException(status_code=404, detail="Durable job deletion is unavailable")
    owner_id = require_tenant(request)
    store, artifacts = durable_components()
    try:
        deleted = delete_private_job(store, artifacts, owner_id, job_id, "item")
    except JobBusy as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(status_code=503, detail="Evidence deletion is incomplete; retry later") from error
    if not deleted:
        raise HTTPException(status_code=404, detail="Job not found")
    return {"deleted": True, "job_id": job_id}

@app.post("/api/batch/analyze")
async def create_batch_job(background_tasks: BackgroundTasks, request: Request, files: List[UploadFile] = File(...)):
    """Accepts multiple evidence files and processes them sequentially in background without OOM."""
    if DURABLE_JOBS_ENABLED:
        owner_id = require_tenant(request)
        enforce_rate_limit(request)
        validate_batch_size(files)
        if any(not file.filename for file in files):
            raise HTTPException(status_code=400, detail="All batch files need filenames")
        for file in files:
            validate_file_extension(file.filename)
            validate_file_size(file)
        if not all(image_evidence_mode(file) for file in files):
            await asyncio.to_thread(ensure_analysis_available)
        if len(files) == 1:
            raise HTTPException(status_code=400, detail="Use /api/analyze for one file")
        batch = await asyncio.to_thread(durable_enqueue, background_tasks, request, owner_id, files)
        return {
            "batch_id": batch["id"], "status": batch["status"],
            "total_files": len(files),
            "message": "Batch submission accepted. Poll /api/batch/{batch_id} for progress.",
        }
    enforce_rate_limit(request)
    validate_batch_size(files)

    valid_files = [f for f in files if f.filename and len(f.filename.strip()) > 0]
    if not valid_files:
        raise HTTPException(status_code=400, detail="No valid files provided")

    for f in valid_files:
        validate_file_extension(f.filename)
        validate_file_size(f)
    ensure_analysis_available()

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
        "error": None,
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
def get_batch_status(batch_id: str, request: Request):
    if DURABLE_JOBS_ENABLED:
        owner_id = require_tenant(request)
        store, _ = durable_components()
        parent = store.get(batch_id, owner_id)
        if not parent or parent["kind"] != "batch":
            raise HTTPException(status_code=404, detail="Batch not found")
        return durable_batch_response(parent, store.children(batch_id, owner_id))
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
        "error": batch.get("error"),
        "items": batch["items"]
    }


@app.delete("/api/batch/{batch_id}")
def delete_batch(batch_id: str, request: Request):
    if not DURABLE_JOBS_ENABLED:
        raise HTTPException(status_code=404, detail="Durable batch deletion is unavailable")
    owner_id = require_tenant(request)
    store, artifacts = durable_components()
    try:
        deleted = delete_private_job(store, artifacts, owner_id, batch_id, "batch")
    except JobBusy as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(status_code=503, detail="Evidence deletion is incomplete; retry later") from error
    if not deleted:
        raise HTTPException(status_code=404, detail="Batch not found")
    return {"deleted": True, "batch_id": batch_id}

# Backward compatible synchronous endpoint
@app.post("/analyze_media")
async def analyze_media_sync(request: Request, file: UploadFile = File(...)):
    if DURABLE_JOBS_ENABLED:
        require_tenant(request)
        raise HTTPException(status_code=410, detail="Use the asynchronous analysis API")
    enforce_rate_limit(request)
    if not file or not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")

    validate_file_extension(file.filename)
    validate_file_size(file)
    ensure_analysis_available()

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
def get_analytics_stats(request: Request):
    if DURABLE_JOBS_ENABLED:
        require_tenant(request)
        raise HTTPException(status_code=503, detail="Tenant-scoped analytics are not available yet")
    cleanup_old_jobs()
    return get_analytics_summary()

@app.get("/api/analytics/evaluations")
def get_evaluations(request: Request, limit: int = 50, offset: int = 0):
    if DURABLE_JOBS_ENABLED:
        require_tenant(request)
        raise HTTPException(status_code=503, detail="Tenant-scoped analytics are not available yet")
    cleanup_old_jobs()
    return {
        "evaluations": get_evaluations_list(limit=limit, offset=offset),
        "limit": limit,
        "offset": offset
    }

@app.get("/api/analytics/export-csv")
def download_evaluations_csv(request: Request):
    if DURABLE_JOBS_ENABLED:
        require_tenant(request)
        raise HTTPException(status_code=503, detail="Tenant-scoped analytics are not available yet")
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
