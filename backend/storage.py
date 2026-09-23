import os
import uuid
import httpx
from typing import Optional, Dict, Any

# Environment variables for S3 / Cloudflare R2 / Supabase Storage
S3_ENDPOINT_URL = os.environ.get("S3_ENDPOINT_URL") or os.environ.get("R2_ENDPOINT_URL")
S3_ACCESS_KEY_ID = os.environ.get("S3_ACCESS_KEY_ID") or os.environ.get("R2_ACCESS_KEY_ID")
S3_SECRET_ACCESS_KEY = os.environ.get("S3_SECRET_ACCESS_KEY") or os.environ.get("R2_SECRET_ACCESS_KEY")
S3_BUCKET_NAME = os.environ.get("S3_BUCKET_NAME") or os.environ.get("R2_BUCKET_NAME") or "fraud-evidence"
S3_PUBLIC_DOMAIN = os.environ.get("S3_PUBLIC_DOMAIN")

def is_storage_configured() -> bool:
    """Returns True if object storage credentials are configured."""
    return bool(S3_ACCESS_KEY_ID and S3_SECRET_ACCESS_KEY and S3_ENDPOINT_URL)

def get_s3_client():
    """Lazily initialize and return boto3 S3 client."""
    try:
        import boto3
        from botocore.config import Config
    except ImportError:
        raise RuntimeError("boto3 is required for object storage. Install with 'pip install boto3'")

    return boto3.client(
        "s3",
        endpoint_url=S3_ENDPOINT_URL,
        aws_access_key_id=S3_ACCESS_KEY_ID,
        aws_secret_access_key=S3_SECRET_ACCESS_KEY,
        config=Config(signature_version="s3v4")
    )

def generate_presigned_upload_url(filename: str, content_type: str, expires_in: int = 3600) -> Dict[str, Any]:
    """
    Generates a pre-signed URL allowing frontend client to upload large files directly
    to Cloudflare R2 / S3 without exhausting the web container's RAM.
    """
    unique_key = f"evidence/{uuid.uuid4()}_{os.path.basename(filename)}"

    if not is_storage_configured():
        return {
            "storage_configured": False,
            "key": unique_key,
            "upload_url": None,
            "public_url": None,
            "message": "Storage credentials not set. Use standard multipart upload (/api/analyze) instead."
        }

    s3 = get_s3_client()
    presigned_url = s3.generate_presigned_url(
        ClientMethod="put_object",
        Params={
            "Bucket": S3_BUCKET_NAME,
            "Key": unique_key,
            "ContentType": content_type
        },
        ExpiresIn=expires_in
    )

    if S3_PUBLIC_DOMAIN:
        public_url = f"{S3_PUBLIC_DOMAIN.rstrip('/')}/{unique_key}"
    elif S3_ENDPOINT_URL:
        public_url = f"{S3_ENDPOINT_URL.rstrip('/')}/{S3_BUCKET_NAME}/{unique_key}"
    else:
        public_url = None

    return {
        "storage_configured": True,
        "key": unique_key,
        "upload_url": presigned_url,
        "public_url": public_url,
        "expires_in": expires_in
    }

async def download_file_stream(url: str, destination_path: str, max_size_mb: int = 250):
    """
    Streams a remote file into a local path in chunks to avoid high RAM usage.
    """
    max_bytes = max_size_mb * 1024 * 1024
    downloaded = 0

    async with httpx.AsyncClient(timeout=120.0, follow_redirects=True) as client:
        async with client.stream("GET", url) as response:
            if response.status_code != 200:
                raise Exception(f"Failed to fetch file from {url}: HTTP {response.status_code}")

            with open(destination_path, "wb") as f:
                async for chunk in response.aiter_bytes(chunk_size=1024 * 64):
                    downloaded += len(chunk)
                    if downloaded > max_bytes:
                        raise Exception(f"File exceeds maximum allowed size of {max_size_mb} MB")
                    f.write(chunk)
