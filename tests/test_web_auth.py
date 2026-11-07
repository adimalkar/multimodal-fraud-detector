"""Signed-in web visitors: token checks, per-account history and the daily file limit."""
import io
import time

import jwt
import pytest
from PIL import Image
from starlette.testclient import TestClient

from backend import app as app_module
from backend import db_service
from backend.app import app, batches, jobs
from backend.durable_auth import require_tenant
from backend.guardrails import rate_limiter
from backend.web_auth import AUDIENCE, ISSUER, verify_web_token

SECRET = "s" * 48


def token(sub="google:1", secret=SECRET, lifetime=600, **overrides):
    now = int(time.time())
    claims = {"sub": sub, "iss": ISSUER, "aud": AUDIENCE, "iat": now, "exp": now + lifetime}
    claims.update(overrides)
    algorithm = claims.pop("alg", "HS256")
    return jwt.encode(claims, secret, algorithm=algorithm)


def headers(sub="google:1"):
    return {"Authorization": f"Bearer {token(sub)}"}


def jpeg():
    buffer = io.BytesIO()
    Image.new("RGB", (8, 8), "red").save(buffer, "JPEG")
    return buffer.getvalue()


@pytest.fixture
def signed_in(monkeypatch, tmp_path):
    monkeypatch.setenv("WEB_AUTH_SECRET", SECRET)
    monkeypatch.setattr(db_service, "DATABASE_URL", None)
    monkeypatch.setattr(db_service, "DB_PATH", str(tmp_path / "web.db"))
    rate_limiter._requests.clear()
    monkeypatch.setattr(app_module, "missing_model_credentials", lambda: [])
    monkeypatch.setattr(app_module, "verify_provider_authentication",
                        lambda: {"openrouter": {"status": "authenticated", "http_status": 200}})
    monkeypatch.setattr(app_module, "run_analysis_pipeline", lambda *args: None)
    monkeypatch.setattr(app_module, "run_batch_pipeline", lambda *args: None)
    yield TestClient(app)
    jobs.clear()
    batches.clear()


class TestTokenCheck:
    @pytest.fixture(autouse=True)
    def secret(self, monkeypatch):
        monkeypatch.setenv("WEB_AUTH_SECRET", SECRET)

    def test_valid_token_names_the_owner(self):
        assert verify_web_token(token("github:42")) == "web:github:42"

    @pytest.mark.parametrize("bad", [
        lambda: token(secret="x" * 48),
        lambda: token(lifetime=-120),
        lambda: token(lifetime=7200),
        lambda: token(aud="someone-else"),
        lambda: token(iss="someone-else"),
        lambda: token(sub=""),
        lambda: token(sub="x" * 500),
        lambda: token(alg="HS512"),
        lambda: jwt.encode({"sub": "google:1", "iss": ISSUER, "aud": AUDIENCE}, SECRET, algorithm="HS256"),
        lambda: "not-a-token",
        lambda: "",
    ])
    def test_rejects_bad_tokens(self, bad):
        assert verify_web_token(bad()) is None

    def test_unsigned_token_is_rejected(self):
        now = int(time.time())
        unsigned = jwt.encode({"sub": "google:1", "iss": ISSUER, "aud": AUDIENCE, "iat": now, "exp": now + 60},
                              None, algorithm="none")
        assert verify_web_token(unsigned) is None

    def test_short_secret_never_verifies(self, monkeypatch):
        monkeypatch.setenv("WEB_AUTH_SECRET", "short")
        assert verify_web_token(token(secret="short")) is None


def test_engine_stays_open_without_a_secret(monkeypatch, tmp_path):
    monkeypatch.delenv("WEB_AUTH_SECRET", raising=False)
    monkeypatch.setattr(db_service, "DATABASE_URL", None)
    monkeypatch.setattr(db_service, "DB_PATH", str(tmp_path / "open.db"))
    response = TestClient(app).get("/api/analytics/stats")
    assert response.status_code == 200


def test_health_is_public_and_reports_sign_in(signed_in):
    response = signed_in.get("/api/health")
    assert response.status_code == 200
    assert response.json()["web_auth"] == "on"


@pytest.mark.parametrize("method,path", [
    ("post", "/api/analyze"),
    ("post", "/api/batch/analyze"),
    ("post", "/analyze_media"),
    ("get", "/api/analytics/stats"),
    ("get", "/api/analytics/evaluations"),
    ("get", "/api/analytics/export-csv"),
    ("get", "/api/jobs/anything"),
    ("get", "/api/batch/anything"),
])
def test_routes_need_sign_in(signed_in, method, path):
    if method == "post":
        field = "files" if "batch" in path else "file"
        response = signed_in.post(path, files=[(field, ("claim.jpg", jpeg(), "image/jpeg"))])
    else:
        response = signed_in.get(path)
    assert response.status_code == 401
    assert response.json()["detail"] == "Sign in to use the screening engine"


def test_short_secret_fails_closed(signed_in, monkeypatch):
    monkeypatch.setenv("WEB_AUTH_SECRET", "too-short")
    response = signed_in.get("/api/analytics/stats", headers=headers())
    assert response.status_code == 503


def test_jobs_are_private_to_their_owner(signed_in):
    response = signed_in.post("/api/analyze", headers=headers("google:1"),
                              files={"file": ("claim.jpg", jpeg(), "image/jpeg")})
    assert response.status_code == 200, response.text
    job_id = response.json()["job_id"]
    assert jobs[job_id]["owner_id"] == "web:google:1"

    assert signed_in.get(f"/api/jobs/{job_id}", headers=headers("google:1")).status_code == 200
    assert signed_in.get(f"/api/jobs/{job_id}", headers=headers("github:9")).status_code == 404


def test_batches_are_private_to_their_owner(signed_in):
    response = signed_in.post("/api/batch/analyze", headers=headers("google:1"), files=[
        ("files", ("a.jpg", jpeg(), "image/jpeg")),
        ("files", ("b.jpg", jpeg(), "image/jpeg")),
    ])
    assert response.status_code == 200, response.text
    batch_id = response.json()["batch_id"]

    assert signed_in.get(f"/api/batch/{batch_id}", headers=headers("google:1")).status_code == 200
    assert signed_in.get(f"/api/batch/{batch_id}", headers=headers("github:9")).status_code == 404


def test_history_shows_only_your_own_screenings(signed_in):
    for owner, name in [("web:google:1", "mine.jpg"), ("web:github:9", "theirs.jpg"), (None, "legacy.jpg")]:
        db_service.save_evaluation(filename=name, media_type="Image", ai_prediction="Fake",
                                   confidence=0.9, final_reasoning="", owner_id=owner)

    listed = signed_in.get("/api/analytics/evaluations", headers=headers("google:1")).json()["evaluations"]
    assert [row["filename"] for row in listed] == ["mine.jpg"]

    stats = signed_in.get("/api/analytics/stats", headers=headers("google:1")).json()
    assert stats["total_records"] == 1
    assert stats["fake_count"] == 1
    assert [row["filename"] for row in stats["recent_evaluations"]] == ["mine.jpg"]

    csv_text = signed_in.get("/api/analytics/export-csv", headers=headers("google:1")).text
    assert "mine.jpg" in csv_text
    assert "theirs.jpg" not in csv_text and "legacy.jpg" not in csv_text


def test_daily_limit_counts_files_per_account(signed_in, monkeypatch):
    monkeypatch.setenv("WEB_DAILY_FILE_LIMIT", "2")
    upload = {"file": ("claim.jpg", jpeg(), "image/jpeg")}

    assert signed_in.post("/api/analyze", headers=headers("google:1"), files=upload).status_code == 200
    batch = signed_in.post("/api/batch/analyze", headers=headers("google:1"), files=[
        ("files", ("a.jpg", jpeg(), "image/jpeg")),
        ("files", ("b.jpg", jpeg(), "image/jpeg")),
    ])
    assert batch.status_code == 429
    assert "limit of 2 files" in batch.json()["detail"]

    assert signed_in.post("/api/analyze", headers=headers("google:1"), files=upload).status_code == 200
    assert signed_in.post("/api/analyze", headers=headers("google:1"), files=upload).status_code == 429
    assert signed_in.post("/api/analyze", headers=headers("github:9"), files=upload).status_code == 200


def test_rejected_files_do_not_use_the_allowance(signed_in, monkeypatch):
    monkeypatch.setenv("WEB_DAILY_FILE_LIMIT", "1")
    bad = signed_in.post("/api/analyze", headers=headers(),
                         files={"file": ("claim.jpg", b"not an image", "image/jpeg")})
    assert bad.status_code == 415
    good = signed_in.post("/api/analyze", headers=headers(),
                          files={"file": ("claim.jpg", jpeg(), "image/jpeg")})
    assert good.status_code == 200


def test_durable_routes_accept_web_tokens(monkeypatch):
    monkeypatch.setenv("WEB_AUTH_SECRET", SECRET)
    monkeypatch.delenv("ANALYSIS_TOKENS_JSON", raising=False)

    class FakeRequest:
        def __init__(self, value):
            self.headers = {"authorization": value}

    assert require_tenant(FakeRequest(f"Bearer {token('github:42')}")) == "web:github:42"
    with pytest.raises(Exception) as error:
        require_tenant(FakeRequest("Bearer nope"))
    assert getattr(error.value, "status_code", None) == 503
