"""/api/analyze-url must only fetch from this deployment's own storage."""
import asyncio

import httpx
import pytest
from starlette.testclient import TestClient

from backend import app as app_module
from backend import storage
from backend.app import app
from backend.guardrails import rate_limiter

ENDPOINT = "https://account.r2.cloudflarestorage.com"
PUBLIC = "https://media.example-storage.test"


@pytest.fixture
def client(monkeypatch):
    rate_limiter._requests.clear()
    monkeypatch.setattr(storage, "S3_ENDPOINT_URL", ENDPOINT)
    monkeypatch.setattr(storage, "S3_PUBLIC_DOMAIN", PUBLIC)
    monkeypatch.setattr(app_module, "missing_model_credentials", lambda: [])
    monkeypatch.setattr(app_module, "verify_provider_authentication",
                        lambda: {"openrouter": {"status": "authenticated", "http_status": 200}})
    fetched = []

    async def fake_pipeline(job_id, media_url, *args):
        fetched.append(media_url)

    monkeypatch.setattr(app_module, "run_analysis_pipeline_from_url", fake_pipeline)
    test_client = TestClient(app)
    test_client.fetched = fetched
    return test_client


def submit(client, url):
    return client.post("/api/analyze-url", json={"media_url": url, "filename": "claim.jpg"})


@pytest.mark.parametrize("url", [
    f"{ENDPOINT}/fraud-evidence/evidence/claim.jpg?X-Amz-Signature=abc",
    f"{PUBLIC}/evidence/claim.jpg",
    "https://ACCOUNT.r2.cloudflarestorage.com/fraud-evidence/claim.jpg",
])
def test_configured_storage_is_allowed(client, url):
    assert submit(client, url).status_code == 200
    assert client.fetched == [url]


@pytest.mark.parametrize("url", [
    "http://169.254.169.254/latest/meta-data/",
    "http://localhost:8000/docs",
    "http://127.0.0.1/admin.jpg",
    "http://[::1]/x.jpg",
    "https://evil.example/claim.jpg",
    "file:///etc/passwd",
    "ftp://account.r2.cloudflarestorage.com/claim.jpg",
    # Same host, wrong scheme or port.
    "http://account.r2.cloudflarestorage.com/claim.jpg",
    "https://account.r2.cloudflarestorage.com:8443/claim.jpg",
    # Lookalikes.
    "https://account.r2.cloudflarestorage.com.evil.example/claim.jpg",
    "https://evil.example/account.r2.cloudflarestorage.com/claim.jpg",
    "https://evil.example#@account.r2.cloudflarestorage.com/claim.jpg",
    # Credentials and parser confusion.
    "https://account.r2.cloudflarestorage.com@evil.example/claim.jpg",
    "https://user:pass@account.r2.cloudflarestorage.com/claim.jpg",
    "https://evil.example\\@account.r2.cloudflarestorage.com/claim.jpg",
    "https://account.r2.cloudflarestorage.com\t.evil.example/claim.jpg",
    "https://account.r2.cloudflarestorage.com:notaport/claim.jpg",
    "not a url",
])
def test_everything_else_is_refused_before_any_fetch(client, url):
    response = submit(client, url)
    assert response.status_code == 403, (url, response.text)
    assert client.fetched == []


def test_unconfigured_storage_refuses_every_url(client, monkeypatch):
    monkeypatch.setattr(storage, "S3_ENDPOINT_URL", None)
    monkeypatch.setattr(storage, "S3_PUBLIC_DOMAIN", None)
    assert submit(client, f"{ENDPOINT}/fraud-evidence/claim.jpg").status_code == 403


def test_durable_mode_still_disables_the_route(client, monkeypatch):
    monkeypatch.setattr(app_module, "DURABLE_JOBS_ENABLED", True)
    monkeypatch.setenv("ANALYSIS_TOKENS_JSON", '{"tenant-a": "' + "t" * 32 + '"}')
    response = client.post("/api/analyze-url", json={"media_url": f"{ENDPOINT}/a.jpg"},
                           headers={"Authorization": "Bearer " + "t" * 32})
    assert response.status_code == 410


def serve(handler, monkeypatch):
    """Run the real downloader against a local transport."""
    real_client = httpx.AsyncClient
    monkeypatch.setattr(storage.httpx, "AsyncClient",
                        lambda **kwargs: real_client(transport=httpx.MockTransport(handler), **kwargs))


def test_redirects_are_not_followed(monkeypatch, tmp_path):
    """An allowed host must not be able to bounce the fetch somewhere else."""
    seen = []

    def handler(request):
        seen.append(str(request.url))
        return httpx.Response(302, headers={"Location": "http://169.254.169.254/latest/meta-data/"})

    serve(handler, monkeypatch)
    with pytest.raises(Exception):
        asyncio.run(storage.download_file_stream(f"{ENDPOINT}/a.jpg", str(tmp_path / "a.jpg")))
    assert seen == [f"{ENDPOINT}/a.jpg"]


def test_failed_fetch_does_not_expose_the_signed_url(monkeypatch, tmp_path):
    serve(lambda request: httpx.Response(403), monkeypatch)
    with pytest.raises(Exception) as caught:
        asyncio.run(storage.download_file_stream(
            f"{ENDPOINT}/a.jpg?X-Amz-Signature=secret", str(tmp_path / "a.jpg")))
    assert "secret" not in str(caught.value)
    assert "403" in str(caught.value)
