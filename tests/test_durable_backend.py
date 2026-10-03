"""Restart, ownership and billing-safety checks for the opt-in durable path."""

import hashlib
import io
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from pypdf import PdfWriter

from backend import app as app_module
from backend import db_service
from backend.durable_jobs import DurableJobStore, QueueUnavailable
from backend.durable_worker import (
    build_components,
    delete_private_job,
    prune_expired,
    run_once,
)


def image_bytes(color="white"):
    image = Image.new("RGB", (16, 16), color)
    output = io.BytesIO()
    image.save(output, format="JPEG")
    return output.getvalue()


def pdf_bytes():
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DURABLE_ALLOW_LOCAL", "1")
    monkeypatch.setenv("DURABLE_SQLITE_PATH", str(tmp_path / "jobs.db"))
    monkeypatch.setenv("DURABLE_ARTIFACT_DIR", str(tmp_path / "artifacts"))
    monkeypatch.setenv("DURABLE_ARTIFACT_BACKEND", "local")
    monkeypatch.setenv("ANALYSIS_TOKENS_JSON", json.dumps({
        "tenant-a": "a" * 32, "tenant-b": "b" * 32,
    }))
    monkeypatch.setattr(app_module, "DURABLE_JOBS_ENABLED", True)
    monkeypatch.setattr(app_module, "DURABLE_EXECUTION_MODE", "external")
    monkeypatch.setattr(app_module, "missing_model_credentials", list)
    monkeypatch.setattr(
        app_module, "verify_provider_authentication",
        lambda: {"openrouter": {"status": "authenticated", "http_status": 200}},
    )
    monkeypatch.setattr(db_service, "DATABASE_URL", None)
    monkeypatch.setattr(db_service, "DB_PATH", str(tmp_path / "analytics.db"))
    app_module.durable_components.cache_clear()
    app_module.rate_limiter.reset()
    store, _ = app_module.durable_components()
    store.touch_worker("test-worker")
    with TestClient(app_module.app) as test_client:
        yield test_client
    app_module.durable_components.cache_clear()
    app_module.rate_limiter.reset()


def headers(tenant="a", **extra):
    return {"Authorization": f"Bearer {tenant * 32}", **extra}


def submit(client, data=None, *, extra_headers=None):
    return client.post(
        "/api/analyze", headers=headers(**(extra_headers or {})),
        files={"file": ("claim.jpg", data or image_bytes(), "image/jpeg")},
    )


def test_job_survives_new_store_instance_and_runs_once(client, monkeypatch):
    data = image_bytes()
    submitted = submit(client, data)
    assert submitted.status_code == 200
    job_id = submitted.json()["job_id"]
    assert submitted.json()["status"] == "queued"
    app_module.durable_components.cache_clear()  # Simulate a new web process.
    queued = client.get(f"/api/jobs/{job_id}", headers=headers()).json()
    assert queued["status"] == "queued"
    assert queued["artifact_sha256"] == hashlib.sha256(data).hexdigest()

    calls = []

    def fake_analysis(*args):
        calls.append(args)
        return {
            "classification": "Real", "confidence": 0.8,
            "reason": "Controlled", "vision_findings": "Controlled",
            "elapsed_seconds": 0.1, "model_usage": {"cost": 0.001},
            "multimodal_risk": {"recommended_action": "MANUAL_REVIEW"},
        }

    monkeypatch.setattr(app_module, "execute_agent_analysis", fake_analysis)
    store, artifacts = app_module.durable_components()
    assert run_once(store, artifacts) is True
    assert run_once(store, artifacts) is False
    assert len(calls) == 1
    completed = client.get(f"/api/jobs/{job_id}", headers=headers()).json()
    assert completed["status"] == "completed"
    assert completed["result"]["classification"] == "Real"
    assert completed["pipeline_version"] == "screening-v1"


def test_image_evidence_job_needs_no_provider_or_paid_call(client, monkeypatch):
    monkeypatch.setenv("IMAGE_EVIDENCE_PIPELINE_ENABLED", "1")
    monkeypatch.setattr(app_module, "missing_model_credentials", lambda: ["OPENROUTER_API_KEY"])

    def forbid_model_call(*args):
        raise AssertionError("Image provenance path must not call the model")

    monkeypatch.setattr(app_module, "execute_agent_analysis", forbid_model_call)
    signed = Path(__file__).parent / "fixtures" / "c2pa_valid_untrusted.jpg"
    submitted = submit(client, signed.read_bytes())
    assert submitted.status_code == 200
    assert submitted.json()["status"] == "queued"
    job_id = submitted.json()["job_id"]
    store, artifacts = app_module.durable_components()
    assert store.get(job_id, "tenant-a")["pipeline_version"] == "image-evidence-v1"
    assert store.get(job_id, "tenant-a")["status"] == "queued_image"
    assert client.get(f"/api/jobs/{job_id}", headers=headers()).json()["status"] == "queued"

    assert run_once(store, artifacts)
    job = store.get(job_id, "tenant-a")
    assert job["billing_started"] == 0
    completed = client.get(f"/api/jobs/{job_id}", headers=headers()).json()
    assert completed["status"] == "completed"
    assert completed["pipeline_version"] == "image-evidence-v1"
    assert completed["result"]["model_usage"]["cost"] == 0
    assert completed["result"]["task_results"][0]["state"] == "valid_untrusted"
    assert completed["result"]["task_results"][1]["status"] == "inconclusive"


def test_pdf_evidence_job_is_queued_for_new_worker_and_needs_no_provider(client, monkeypatch):
    monkeypatch.setenv("PDF_EVIDENCE_PIPELINE_ENABLED", "1")
    monkeypatch.setattr(app_module, "missing_model_credentials", lambda: ["OPENROUTER_API_KEY"])

    def forbid_model_call(*args):
        raise AssertionError("PDF structure path must not call the model")

    monkeypatch.setattr(app_module, "execute_agent_analysis", forbid_model_call)
    submitted = client.post(
        "/api/analyze", headers=headers(),
        files={"file": ("invoice.pdf", pdf_bytes(), "application/pdf")},
    )
    assert submitted.status_code == 200
    job_id = submitted.json()["job_id"]
    store, artifacts = app_module.durable_components()
    assert store.get(job_id, "tenant-a")["status"] == "queued_pdf"
    assert store.get(job_id, "tenant-a")["pipeline_version"] == "pdf-evidence-v1"
    assert client.get(f"/api/jobs/{job_id}", headers=headers()).json()["status"] == "queued"

    assert run_once(store, artifacts)
    job = store.get(job_id, "tenant-a")
    assert job["billing_started"] == 0
    completed = client.get(f"/api/jobs/{job_id}", headers=headers()).json()
    assert completed["status"] == "completed"
    assert completed["result"]["model_usage"] == {"cost": 0.0, "calls": 0}
    assert completed["result"]["task_results"][0]["coverage"]["pages_inspected"] == 1
    assert completed["result"]["task_results"][1]["status"] == "inconclusive"


def test_image_pdf_batch_uses_two_evidence_queues_without_model(client, monkeypatch):
    monkeypatch.setenv("IMAGE_EVIDENCE_PIPELINE_ENABLED", "1")
    monkeypatch.setenv("PDF_EVIDENCE_PIPELINE_ENABLED", "1")
    monkeypatch.setattr(app_module, "missing_model_credentials", lambda: ["OPENROUTER_API_KEY"])
    response = client.post(
        "/api/batch/analyze", headers=headers(), files=[
            ("files", ("photo.jpg", image_bytes(), "image/jpeg")),
            ("files", ("invoice.pdf", pdf_bytes(), "application/pdf")),
        ],
    )
    assert response.status_code == 200
    store, _ = app_module.durable_components()
    children = store.children(response.json()["batch_id"], "tenant-a")
    assert {row["status"] for row in children} == {"queued_image", "queued_pdf"}
    assert all(item["status"] == "queued" for item in client.get(
        f"/api/batch/{response.json()['batch_id']}", headers=headers()
    ).json()["items"])


def test_pdf_artifact_retry_stays_in_pdf_queue(client, monkeypatch):
    monkeypatch.setenv("PDF_EVIDENCE_PIPELINE_ENABLED", "1")
    submitted = client.post(
        "/api/analyze", headers=headers(),
        files={"file": ("invoice.pdf", pdf_bytes(), "application/pdf")},
    )
    assert submitted.status_code == 200
    store, artifacts = app_module.durable_components()
    original_materialize = artifacts.materialize
    failures = [True]

    def fail_once(*args):
        if failures:
            failures.clear()
            raise OSError("temporary storage outage")
        return original_materialize(*args)

    monkeypatch.setattr(artifacts, "materialize", fail_once)
    assert run_once(store, artifacts)
    assert store.get(submitted.json()["job_id"], "tenant-a")["status"] == "queued_pdf"
    assert run_once(store, artifacts)
    assert store.get(submitted.json()["job_id"], "tenant-a")["status"] == "completed"


def test_pdf_signature_version_uses_its_own_queue_and_no_provider(client, monkeypatch):
    monkeypatch.setenv("PDF_EVIDENCE_PIPELINE_ENABLED", "1")
    monkeypatch.setenv("PDF_SIGNATURE_PIPELINE_ENABLED", "1")
    monkeypatch.setattr(app_module, "missing_model_credentials", lambda: ["OPENROUTER_API_KEY"])

    def forbid_model_call(*args):
        raise AssertionError("PDF signature path must not call the model")

    monkeypatch.setattr(app_module, "execute_agent_analysis", forbid_model_call)
    data = pdf_bytes()
    files = {"file": ("invoice.pdf", data, "application/pdf")}
    request_headers = headers(**{"Idempotency-Key": "pdf-signature-version"})
    submitted = client.post("/api/analyze", headers=request_headers, files=files)
    assert submitted.status_code == 200
    job_id = submitted.json()["job_id"]
    store, artifacts = app_module.durable_components()
    assert store.get(job_id, "tenant-a")["status"] == "queued_pdf_v2"
    assert store.get(job_id, "tenant-a")["pipeline_version"] == "pdf-evidence-v2"
    assert client.get(f"/api/jobs/{job_id}", headers=headers()).json()["status"] == "queued"

    monkeypatch.setenv("PDF_SIGNATURE_PIPELINE_ENABLED", "0")
    replay = client.post("/api/analyze", headers=request_headers, files=files)
    assert replay.status_code == 409
    assert run_once(store, artifacts)
    completed = client.get(f"/api/jobs/{job_id}", headers=headers()).json()
    assert completed["status"] == "completed"
    assert completed["pipeline_version"] == "pdf-evidence-v2"
    assert completed["result"]["task_results"][1]["state"] == "unsigned"
    assert completed["result"]["model_usage"] == {"cost": 0.0, "calls": 0}
    assert store.get(job_id, "tenant-a")["billing_started"] == 0


def test_pdf_signature_artifact_retry_stays_in_v2_queue(client, monkeypatch):
    monkeypatch.setenv("PDF_EVIDENCE_PIPELINE_ENABLED", "1")
    monkeypatch.setenv("PDF_SIGNATURE_PIPELINE_ENABLED", "1")
    submitted = client.post(
        "/api/analyze", headers=headers(),
        files={"file": ("invoice.pdf", pdf_bytes(), "application/pdf")},
    )
    assert submitted.status_code == 200
    store, artifacts = app_module.durable_components()
    original_materialize = artifacts.materialize
    failures = [True]

    def fail_once(*args):
        if failures:
            failures.clear()
            raise OSError("temporary storage outage")
        return original_materialize(*args)

    monkeypatch.setattr(artifacts, "materialize", fail_once)
    assert run_once(store, artifacts)
    assert store.get(submitted.json()["job_id"], "tenant-a")["status"] == "queued_pdf_v2"
    assert run_once(store, artifacts)
    assert store.get(submitted.json()["job_id"], "tenant-a")["status"] == "completed"


def test_pdf_idempotency_cannot_replay_across_pipeline_versions(client, monkeypatch):
    data = pdf_bytes()
    files = {"file": ("invoice.pdf", data, "application/pdf")}
    request_headers = headers(**{"Idempotency-Key": "pdf-version-change"})
    first = client.post("/api/analyze", headers=request_headers, files=files)
    assert first.status_code == 200
    monkeypatch.setenv("PDF_EVIDENCE_PIPELINE_ENABLED", "1")
    replay = client.post("/api/analyze", headers=request_headers, files=files)
    assert replay.status_code == 409


def test_image_only_batch_skips_provider_but_mixed_batch_requires_it(client, monkeypatch):
    monkeypatch.setenv("IMAGE_EVIDENCE_PIPELINE_ENABLED", "1")
    monkeypatch.setattr(app_module, "missing_model_credentials", lambda: ["OPENROUTER_API_KEY"])
    images = [
        ("files", ("one.jpg", image_bytes("white"), "image/jpeg")),
        ("files", ("two.jpg", image_bytes("black"), "image/jpeg")),
    ]
    accepted = client.post("/api/batch/analyze", headers=headers(), files=images)
    assert accepted.status_code == 200
    batch_id = accepted.json()["batch_id"]
    store, _ = app_module.durable_components()
    assert {row["pipeline_version"] for row in store.children(batch_id, "tenant-a")} == {
        "image-evidence-v1"
    }

    mixed = client.post(
        "/api/batch/analyze", headers=headers(),
        files=[images[0], ("files", ("paper.pdf", b"%PDF-1.4", "application/pdf"))],
    )
    assert mixed.status_code == 503


def test_idempotency_key_cannot_replay_across_image_pipeline_versions(client, monkeypatch):
    data = image_bytes()
    first = submit(client, data, extra_headers={"Idempotency-Key": "version-change"})
    assert first.status_code == 200
    monkeypatch.setenv("IMAGE_EVIDENCE_PIPELINE_ENABLED", "1")
    replay = submit(client, data, extra_headers={"Idempotency-Key": "version-change"})
    assert replay.status_code == 409


def test_unknown_queued_pipeline_version_fails_before_billing(client, monkeypatch):
    store, artifacts = app_module.durable_components()
    key, digest, _ = artifacts.put_upload(io.BytesIO(image_bytes()), "claim.jpg")
    job, _ = store.create(
        "tenant-a", [{
            "filename": "claim.jpg", "media_type": "Image", "content_type": "image/jpeg",
            "artifact_key": key, "artifact_sha256": digest,
            "pipeline_version": "unknown-future-version",
        }], idempotency_key=None, request_fingerprint="unknown-version",
        max_daily_jobs=20, max_daily_reserved_usd=1, reserve_per_job_usd=0.01,
    )

    def forbid_model_call(*args):
        raise AssertionError("Unknown version must not use a paid fallback")

    monkeypatch.setattr(app_module, "execute_agent_analysis", forbid_model_call)
    assert run_once(store, artifacts)
    failed = store.get(job["id"], "tenant-a")
    assert failed["status"] == "failed"
    assert failed["error_code"] == "UNSUPPORTED_PIPELINE_VERSION"
    assert failed["billing_started"] == 0


def test_image_artifact_retry_stays_in_image_queue(client, monkeypatch):
    monkeypatch.setenv("IMAGE_EVIDENCE_PIPELINE_ENABLED", "1")
    job_id = submit(client).json()["job_id"]
    store, artifacts = app_module.durable_components()
    original_materialize = artifacts.materialize
    failures = [True]

    def fail_once(*args):
        if failures:
            failures.clear()
            raise OSError("temporary storage outage")
        return original_materialize(*args)

    monkeypatch.setattr(artifacts, "materialize", fail_once)
    assert run_once(store, artifacts)
    assert store.get(job_id, "tenant-a")["status"] == "queued_image"
    assert run_once(store, artifacts)
    assert store.get(job_id, "tenant-a")["status"] == "completed"


def test_lost_lease_does_not_write_legacy_analytics(client, monkeypatch):
    job_id = submit(client).json()["job_id"]
    store, artifacts = app_module.durable_components()
    monkeypatch.setattr(app_module, "execute_agent_analysis", lambda *args: {
        "classification": "Real", "confidence": 0.8,
        "reason": "Controlled", "vision_findings": "Controlled",
        "elapsed_seconds": 0.1, "model_usage": {"cost": 0.001},
    })
    analytics_writes = []
    monkeypatch.setattr(db_service, "save_evaluation", lambda **kwargs: analytics_writes.append(kwargs))

    def lose_lease(*args):
        raise QueueUnavailable("Job lease was lost")

    monkeypatch.setattr(store, "complete", lose_lease)

    assert run_once(store, artifacts)
    assert analytics_writes == []
    assert store.get(job_id, "tenant-a")["status"] == "failed"


def test_auth_and_tenant_scoped_job_reads(client):
    assert submit(client).status_code == 200
    job_id = submit(client).json()["job_id"]
    assert client.get(f"/api/jobs/{job_id}").status_code == 401
    assert client.get(f"/api/jobs/{job_id}", headers=headers("b")).status_code == 404
    assert client.get(f"/api/jobs/{job_id}", headers=headers()).status_code == 200
    assert client.get("/api/analytics/evaluations", headers=headers()).status_code == 503


def test_batch_items_are_durable_and_owner_scoped(client, monkeypatch):
    response = client.post(
        "/api/batch/analyze", headers=headers(),
        files=[
            ("files", ("one.jpg", image_bytes("white"), "image/jpeg")),
            ("files", ("two.jpg", image_bytes("black"), "image/jpeg")),
        ],
    )
    assert response.status_code == 200
    batch_id = response.json()["batch_id"]
    assert client.get(f"/api/batch/{batch_id}", headers=headers("b")).status_code == 404
    queued = client.get(f"/api/batch/{batch_id}", headers=headers()).json()
    assert queued["total_items"] == 2
    assert all(item["status"] == "queued" for item in queued["items"])

    def fake_analysis(*args):
        return {
            "classification": "Real", "confidence": 0.9, "reason": "Controlled",
            "vision_findings": "Controlled", "elapsed_seconds": 0.1,
            "model_usage": {"cost": 0.001}, "multimodal_risk": {},
        }

    monkeypatch.setattr(app_module, "execute_agent_analysis", fake_analysis)
    store, artifacts = app_module.durable_components()
    assert run_once(store, artifacts)
    assert run_once(store, artifacts)
    completed = client.get(f"/api/batch/{batch_id}", headers=headers()).json()
    assert completed["status"] == "completed"
    assert completed["summary"]["processed"] == 2
    assert completed["progress"] == 100
    assert all(item["result"]["decision"] == "manual_review" for item in completed["items"])


def test_mime_mismatch_rejected_before_enqueue(client):
    response = client.post(
        "/api/analyze", headers=headers(),
        files={"file": ("claim.pdf", image_bytes(), "application/pdf")},
    )
    assert response.status_code == 415
    store, _ = app_module.durable_components()
    assert store.active_counts()["active_jobs"] == 0


def test_missing_worker_rejects_new_work_before_upload(client, monkeypatch, tmp_path):
    store, _ = app_module.durable_components()
    monkeypatch.setattr(store, "worker_recent", lambda *args: False)
    response = submit(client)
    assert response.status_code == 503
    assert list((tmp_path / "artifacts").iterdir()) == []


def test_idempotency_and_quota_do_not_enqueue_extra_jobs(client, monkeypatch, tmp_path):
    monkeypatch.setenv("DURABLE_DAILY_JOBS_PER_TENANT", "1")
    first_data = image_bytes("white")
    first = submit(client, first_data, extra_headers={"Idempotency-Key": "claim-1"})
    assert first.status_code == 200
    repeated = submit(client, first_data, extra_headers={"Idempotency-Key": "claim-1"})
    assert repeated.status_code == 200
    assert repeated.json()["job_id"] == first.json()["job_id"]
    changed = submit(
        client, image_bytes("black"), extra_headers={"Idempotency-Key": "claim-1"}
    )
    assert changed.status_code == 409
    over_quota = submit(client, image_bytes("gray"))
    assert over_quota.status_code == 429
    assert len(list((tmp_path / "artifacts").iterdir())) == 1


def test_recovery_never_requeues_work_after_lease_expires(tmp_path):
    store = DurableJobStore(sqlite_path=str(tmp_path / "jobs.db"))
    store.initialize()
    job, created = store.create(
        "owner", [{
            "filename": "claim.jpg", "media_type": "Image", "content_type": "image/jpeg",
            "artifact_key": "evidence/" + "a" * 32 + ".jpg", "artifact_sha256": "a" * 64,
        }], idempotency_key=None, request_fingerprint="fingerprint",
        max_daily_jobs=2, max_daily_reserved_usd=1, reserve_per_job_usd=0.01,
    )
    assert created
    claimed = store.claim(lease_seconds=-1)
    assert claimed["id"] == job["id"]
    store.mark_billing_started(job["id"], claimed["lease_token"])
    assert store.recover_expired() == 1
    assert store.claim() is None
    assert store.get(job["id"], "owner")["error_code"] == "WORKER_INTERRUPTED_REVIEW_REQUIRED"


def test_two_workers_claim_distinct_jobs(tmp_path):
    first = DurableJobStore(sqlite_path=str(tmp_path / "jobs.db"))
    second = DurableJobStore(sqlite_path=str(tmp_path / "jobs.db"))
    first.initialize()
    for index in range(2):
        first.create(
            "owner", [{
                "filename": f"{index}.jpg", "media_type": "Image", "content_type": "image/jpeg",
                "artifact_key": "evidence/" + str(index) * 32 + ".jpg",
                "artifact_sha256": str(index) * 64,
            }], idempotency_key=None, request_fingerprint=str(index),
            max_daily_jobs=2, max_daily_reserved_usd=1, reserve_per_job_usd=0.01,
        )
    a = first.claim()
    b = second.claim()
    assert a["id"] != b["id"]
    assert first.claim() is None


def test_owner_can_delete_queued_evidence_and_analytics(client, tmp_path):
    submitted = submit(client)
    job_id = submitted.json()["job_id"]
    assert len(list((tmp_path / "artifacts").iterdir())) == 1
    assert client.delete(f"/api/jobs/{job_id}", headers=headers("b")).status_code == 404
    deleted = client.delete(f"/api/jobs/{job_id}", headers=headers())
    assert deleted.status_code == 200
    assert client.get(f"/api/jobs/{job_id}", headers=headers()).status_code == 404
    assert list((tmp_path / "artifacts").iterdir()) == []


def test_failed_delete_is_retried_before_retention_deadline(client, monkeypatch, tmp_path):
    job_id = submit(client).json()["job_id"]
    store, artifacts = app_module.durable_components()
    original_delete = artifacts.delete
    failures = [True]

    def fail_once(key):
        if failures:
            failures.clear()
            raise OSError("storage temporarily unavailable")
        original_delete(key)

    monkeypatch.setattr(artifacts, "delete", fail_once)
    with pytest.raises(OSError, match="storage temporarily unavailable"):
        delete_private_job(store, artifacts, "tenant-a", job_id, "item")
    assert store.get(job_id, "tenant-a")["status"] == "deleting"
    assert len(list((tmp_path / "artifacts").iterdir())) == 1

    prune_expired(store, artifacts)
    assert store.get(job_id, "tenant-a") is None
    assert list((tmp_path / "artifacts").iterdir()) == []


def test_deletion_does_not_reset_daily_quota(client, monkeypatch):
    monkeypatch.setenv("DURABLE_DAILY_JOBS_PER_TENANT", "1")
    job_id = submit(client).json()["job_id"]
    assert client.delete(f"/api/jobs/{job_id}", headers=headers()).status_code == 200
    assert submit(client).status_code == 429


def test_processing_job_cannot_be_deleted(client):
    job_id = submit(client).json()["job_id"]
    store, _ = app_module.durable_components()
    assert store.claim()["id"] == job_id
    assert client.delete(f"/api/jobs/{job_id}", headers=headers()).status_code == 409
    assert store.get(job_id, "tenant-a")["status"] == "processing"


def test_production_mode_rejects_ephemeral_storage(monkeypatch):
    monkeypatch.delenv("DURABLE_ALLOW_LOCAL", raising=False)
    monkeypatch.delenv("DURABLE_DATABASE_URL", raising=False)
    monkeypatch.setenv("DURABLE_ARTIFACT_BACKEND", "local")
    with pytest.raises(RuntimeError, match="requires PostgreSQL and private S3/R2"):
        build_components()
