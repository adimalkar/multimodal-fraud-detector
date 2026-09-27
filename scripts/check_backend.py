"""Verify that a URL serves this FastAPI backend and can accept analysis jobs."""

import argparse
import json
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def get_json(url):
    request = Request(url, headers={"Accept": "application/json"})
    try:
        response = urlopen(request, timeout=15)
    except HTTPError as error:
        response = error

    with response:
        status = response.status
        content_type = response.headers.get("Content-Type", "")
        if "application/json" not in content_type:
            raise ValueError(f"{url} returned HTTP {status} with {content_type or 'no content type'}")
        try:
            body = json.load(response)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError(f"{url} returned invalid JSON") from error
    return status, body


def check_backend(base_url, allow_unconfigured=False):
    base_url = base_url.rstrip("/")
    health_status, health = get_json(base_url + "/api/health")
    if health_status != 200 or health.get("service") != "FraudSight AI API":
        raise ValueError("/api/health is not the expected FastAPI backend")

    schema_status, schema = get_json(base_url + "/openapi.json")
    if schema_status != 200 or "/api/analyze" not in schema.get("paths", {}):
        raise ValueError("/openapi.json does not describe the analysis API")

    ready_status, readiness = get_json(base_url + "/api/ready")
    if ready_status == 200 and readiness.get("analysis_ready") is True:
        print(f"Backend verified and analysis ready: {base_url}")
        return

    detail = readiness.get("detail", {})
    if ready_status == 503 and detail.get("code") == "MODEL_PROVIDERS_UNCONFIGURED":
        if allow_unconfigured:
            print(f"Backend verified; model providers are unconfigured: {base_url}")
            return
        raise ValueError("Backend is running, but model providers are unconfigured")

    raise ValueError(f"/api/ready returned an unexpected response: HTTP {ready_status}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base_url", help="Backend origin, for example http://127.0.0.1:8000")
    parser.add_argument(
        "--allow-unconfigured",
        action="store_true",
        help="Accept a local backend that has no model provider credentials",
    )
    args = parser.parse_args()
    try:
        check_backend(args.base_url, allow_unconfigured=args.allow_unconfigured)
    except (ValueError, URLError, TimeoutError) as error:
        print(f"Backend check failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
