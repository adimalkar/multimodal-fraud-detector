"""Run durable queued analyses in a separate process: python -m backend.durable_worker."""

from __future__ import annotations

import argparse
import logging
import os
import threading
import time
import uuid

from backend.durable_jobs import SCHEMA_VERSION, DurableJobStore, QueueUnavailable
from backend.evidence_artifacts import EvidenceArtifactStore
from backend.image_evidence import IMAGE_PIPELINE_VERSION
from backend.pdf_evidence import PDF_PIPELINE_VERSION

LOGGER = logging.getLogger(__name__)
WORKER_ID = uuid.uuid4().hex


class UnsupportedPipelineVersion(ValueError):
    pass


def build_components():
    allow_local = os.getenv("DURABLE_ALLOW_LOCAL", "0") == "1"
    database_url = os.getenv("DURABLE_DATABASE_URL")
    artifact_backend = os.getenv("DURABLE_ARTIFACT_BACKEND", "local")
    execution_mode = os.getenv("DURABLE_EXECUTION_MODE", "external")
    if execution_mode not in {"inline", "external"}:
        raise RuntimeError("DURABLE_EXECUTION_MODE must be inline or external")
    if not allow_local and (not database_url or artifact_backend != "s3"):
        raise RuntimeError("Durable production mode requires PostgreSQL and private S3/R2 storage")
    if not allow_local and execution_mode != "external":
        raise RuntimeError("Durable production mode requires a separate worker")
    store = DurableJobStore(database_url=database_url)
    store.initialize()
    artifacts = EvidenceArtifactStore(backend=artifact_backend)
    return store, artifacts


def run_once(store: DurableJobStore, artifacts: EvidenceArtifactStore) -> bool:
    store.touch_worker(WORKER_ID)
    store.recover_expired()
    job = store.claim()
    if not job:
        return False
    token = job["lease_token"]
    materialized = None
    billed = False
    stop_heartbeat = threading.Event()

    def keep_lease():
        while not stop_heartbeat.wait(60):
            try:
                if not store.heartbeat(job["id"], token):
                    return
                store.touch_worker(WORKER_ID)
            except Exception as error:  # noqa: BLE001 - transient worker boundary
                # The next heartbeat may recover from a transient DB outage.
                LOGGER.warning("Job lease heartbeat failed: %s", type(error).__name__)

    heartbeat_thread = threading.Thread(target=keep_lease, daemon=True)
    heartbeat_thread.start()
    try:
        materialized = artifacts.materialize(job["artifact_key"], job["artifact_sha256"])
        if job["pipeline_version"] == IMAGE_PIPELINE_VERSION:
            from backend.image_evidence import analyze_image_evidence

            result = analyze_image_evidence(
                str(materialized), job["content_type"], job["artifact_sha256"]
            )
        elif job["pipeline_version"] == PDF_PIPELINE_VERSION:
            from backend.pdf_evidence import analyze_pdf_evidence

            result = analyze_pdf_evidence(
                str(materialized), job["content_type"], job["artifact_sha256"]
            )
        elif job["pipeline_version"] == SCHEMA_VERSION:
            store.mark_billing_started(job["id"], token)
            billed = True
            # Import here to avoid an app/worker import cycle and reuse the current baseline.
            from backend.app import execute_agent_analysis

            result = execute_agent_analysis(
                str(materialized), job["media_type"], job["content_type"]
            )
            task = {
                "Image": "synthetic_image_screening",
                "Video": "sampled_video_screening",
                "Document": "rendered_pdf_screening",
            }[job["media_type"]]
            result["pipeline_version"] = SCHEMA_VERSION
            result["decision"] = "manual_review"
            result["task_results"] = [{
                "task": task,
                "status": "inconclusive",
                "model_observation": result.get("classification"),
                "calibrated_score": None,
                "limitations": "Single unvalidated vision model; specialist checks have not run.",
            }]
        else:
            raise UnsupportedPipelineVersion("Unsupported queued pipeline version")
        # Keep the durable result as the only persisted analysis record. Writing a
        # second database here can race with lease loss or evidence deletion and
        # leave a private result behind after its job has disappeared.
        store.complete(job["id"], token, result)
    except Exception as error:  # noqa: BLE001 - per-job failure isolation
        retry = not billed and job["attempts"] < 2 and isinstance(error, OSError)
        code = (
            "UNSUPPORTED_PIPELINE_VERSION" if isinstance(error, UnsupportedPipelineVersion)
            else "ARTIFACT_UNAVAILABLE" if retry else "ANALYSIS_FAILED"
        )
        message = (
            "Evidence storage temporarily unavailable" if retry
            else "Analysis failed; review before retrying"
        )
        try:
            store.fail(
                job["id"], token, code, message, retry=retry,
                retry_status=(
                    "queued_image" if job["pipeline_version"] == IMAGE_PIPELINE_VERSION
                    else "queued_pdf" if job["pipeline_version"] == PDF_PIPELINE_VERSION
                    else "queued"
                ),
            )
        except QueueUnavailable:
            # Expired lease recovery already placed the job into manual review.
            pass
    finally:
        stop_heartbeat.set()
        heartbeat_thread.join(timeout=1)
        if materialized is not None:
            artifacts.release_materialized(materialized)
    return True


def delete_private_job(store, artifacts, owner_id: str, job_id: str, kind: str) -> bool:
    rows = store.begin_delete(job_id, owner_id, kind)
    if rows is None:
        return False
    from backend.db_service import delete_evaluation_by_job_id

    for row in rows:
        if row["artifact_key"]:
            artifacts.delete(row["artifact_key"])
        if row["kind"] == "item":
            delete_evaluation_by_job_id(row["id"])
    store.finalize_delete(job_id, owner_id)
    return True


def prune_expired(store, artifacts):
    retention_days = int(os.getenv("DURABLE_RETENTION_DAYS", "7"))
    usage_retention_days = int(os.getenv("DURABLE_USAGE_RETENTION_DAYS", "90"))
    if retention_days < 1:
        raise ValueError("DURABLE_RETENTION_DAYS must be at least 1")
    if usage_retention_days < 2:
        raise ValueError("DURABLE_USAGE_RETENTION_DAYS must be at least 2")
    from backend.durable_jobs import JobBusy

    for root in store.expired_roots(retention_days * 86400):
        try:
            delete_private_job(store, artifacts, root["owner_id"], root["id"], root["kind"])
        except JobBusy:
            continue
        except Exception as error:  # noqa: BLE001 - retry deletion next pass
            # A failed deletion remains in `deleting` and is retried next pass.
            LOGGER.warning("Evidence retention cleanup failed: %s", type(error).__name__)
            continue
    store.prune_usage(usage_retention_days * 86400)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--poll-seconds", type=float, default=2.0)
    args = parser.parse_args()
    if args.poll_seconds <= 0:
        parser.error("--poll-seconds must be positive")
    store, artifacts = build_components()
    if args.once:
        prune_expired(store, artifacts)
        run_once(store, artifacts)
        return
    last_prune = 0.0
    while True:
        if time.time() - last_prune >= 3600:
            prune_expired(store, artifacts)
            last_prune = time.time()
        if not run_once(store, artifacts):
            time.sleep(args.poll_seconds)


if __name__ == "__main__":
    main()
