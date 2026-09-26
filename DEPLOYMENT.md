# Production Infrastructure & Deployment Guide (100% Free Tier)

This guide documents the decoupled, production-grade architecture for **FraudSight AI**.

```
[ User Browser ]
       │
       ▼ (Instant, 0s cold start)
┌──────────────────────────────────────────────┐
│  Layer 1: Frontend (Next.js 14 + Tailwind)   │
│  Hosted on: VERCEL (Free Tier)               │
│  - Unlimited global edge CDN & assets        │
│  - Instant page load, zero cold start        │
│  - Staging UI, single & batch analysis       │
│  - Real-time analytics dashboard             │
└──────────────┬───────────────────────────────┘
               │
               │ Direct Presigned Upload (Bypasses API memory)
               ▼
┌──────────────────────────────────────────────┐
│  Layer 2: Media Storage (Videos / PDFs)      │
│  Hosted on: CLOUDFLARE R2 or S3              │
│  - 10 GB Free Storage, $0 Egress fees        │
└──────────────┬───────────────────────────────┘
               │
               │ Triggers asynchronous analysis job
               ▼
┌──────────────────────────────────────────────┐
│  Layer 3: AI Backend Engine (FastAPI)        │
│  Option A (Recommended): HUGGING FACE SPACES │
│    • 16 GB RAM + 2 vCPU (FREE!)              │
│    • Built for OpenCV, Video, & Python AI    │
│  Option B: Render / Koyeb (API-only)         │
│    • Reserved 100% for Python (No Node.js)   │
│  - In-memory rate limiting & file validation │
│  - Multi-agent jury (Qwen-VL + LLM critics)  │
│  - Multimodal risk scoring engine            │
└──────────────┬───────────────────────────────┘
               │
               ▼
┌──────────────────────────────────────────────┐
│  Layer 4: Database Persistence               │
│  Hosted on: SUPABASE / NEON (PostgreSQL)     │
│  Fallback: Local SQLite file                 │
│  - Permanent claim & audit trail history     │
│  - Aggregated risk statistics & metrics      │
│  - CSV export for SIU fraud investigators    │
└──────────────────────────────────────────────┘
```

---

## Layer 1: Deploying Next.js Frontend to Vercel (Free)

1. Go to [vercel.com](https://vercel.com) and log in with your GitHub account.
2. Click **"Add New..."** → **"Project"**.
3. Select your repository: `adimalkar/multimodal-fraud-detector`.
4. In the project configuration:
   - **Framework Preset**: Next.js
   - **Root Directory**: Click "Edit" and choose `frontend`
   - **Environment Variables**:
     - `NEXT_PUBLIC_API_URL`: Your backend API URL (e.g. `https://multimodal-fraud-detector-1.onrender.com` or your Hugging Face Space URL)
5. Click **"Deploy"**.

**Benefits:**
- 0s cold starts (instant global CDN delivery).
- Zero consumption of Python server RAM or CPU.
- Automatically rebuilds on git push.

---

## Layer 2: Cloudflare R2 Object Storage (10 GB Free, $0 Egress)

When processing large videos (50MB–200MB) or PDFs, uploading directly to object storage bypasses container RAM limits completely.

1. Create a free account at [cloudflare.com](https://dash.cloudflare.com) and navigate to **R2**.
2. Click **"Create Bucket"** and name it (e.g. `fraud-evidence`).
3. Under **"Manage R2 API Tokens"**, create an API token with *Object Read & Write* permissions.
4. Add these environment variables to your backend:
   ```bash
   R2_ACCOUNT_ID="your_account_id"
   R2_ACCESS_KEY_ID="your_access_key"
   R2_SECRET_ACCESS_KEY="your_secret_key"
   R2_BUCKET_NAME="fraud-evidence"
   R2_ENDPOINT_URL="https://<account_id>.r2.cloudflarestorage.com"
   ```
5. The backend automatically exposes:
   - `POST /api/storage/presigned-url`: Generates a direct presigned PUT upload URL.
   - `POST /api/analyze-url`: Takes the public/presigned file URL and streams it in chunks.

*Note: If R2 is not configured, the backend automatically falls back to direct multipart upload via `POST /api/analyze`.*

---

## Layer 3: AI Backend Engine (FastAPI)

### Option A (Recommended): Deploying Backend to Hugging Face Spaces (16 GB RAM Free!)

Hugging Face Spaces offers **16 GB RAM + 2 vCPU** for FREE on Docker spaces — 30x more RAM than Render's 512 MB tier.

1. Go to [huggingface.co/spaces](https://huggingface.co/spaces) and click **"Create new Space"**.
2. Settings:
   - **Space name**: `multimodal-fraud-detector`
   - **License**: MIT
   - **Space SDK**: **Docker** (Blank)
   - **Space hardware**: Free (2 vCPU, 16 GB RAM)
3. Set Space Secrets in **Settings → Variables and Secrets**:
   - `OPENROUTER_API_KEY`: your OpenRouter API key
   - `FEATHERLESS_API_KEY`: your Featherless API key (required for the current analysis pipeline)
   - `DATABASE_URL`: your Supabase/Neon PostgreSQL URL (optional)
4. Push or mirror this repository:
   ```bash
   git remote add space https://huggingface.co/spaces/YOUR_USERNAME/multimodal-fraud-detector
   git push space main
   ```
5. Hugging Face builds the included `Dockerfile` and serves your FastAPI backend on port 8000!

---

### Option B: Deploying Backend to Render (Free Web Service)

The repo includes `render.yaml` for a Python FastAPI web service:
1. Connect your repository on [dashboard.render.com](https://dashboard.render.com).
2. Sync the Blueprint, or configure an existing **Web Service** to use the Python runtime, `pip install -r requirements.txt && python database/init_db.py` build command, `uvicorn backend.app:app --host 0.0.0.0 --port $PORT` start command, and `/api/health` health check path. Verify the existing service's linked repository and branch in the Render dashboard; a repository YAML change alone does not update a manually configured service.
3. Set both model provider keys (`OPENROUTER_API_KEY` and `FEATHERLESS_API_KEY`) as Render secrets, plus any optional database and storage settings. Never commit the key values.
4. Run `python scripts/check_backend.py https://YOUR-BACKEND-URL` from a checkout after deployment. This checks JSON health and readiness responses and the OpenAPI route list; an unrelated app returning HTTP 200 will fail the check.
5. Run `python scripts/check_media_pipeline.py --preprocess-only` to check local image, PDF, and video preprocessing. With a ready backend and provider keys, run `python scripts/check_media_pipeline.py https://YOUR-BACKEND-URL` to submit synthetic evidence in all three formats and poll each job. This checks execution and result shape, not fraud detection accuracy. The full run makes paid provider calls and stores three synthetic evaluations.

The `Verify deployed backend` GitHub Actions workflow checks the configured Render URL daily and can be run manually with a different backend URL. It fails when the URL serves Streamlit HTML or the API is unconfigured. GitHub Actions secrets are not needed for this read-only deployment check. The manual `run_media_pipeline` option runs the synthetic three-format check against a ready backend and uses provider credits.

---

## Layer 4: Cloud PostgreSQL Database (Supabase / Neon Free Tier)

FraudSight AI supports both cloud PostgreSQL and local SQLite:
- If `DATABASE_URL` is set, the system uses PostgreSQL. Connections are opened per operation; pooling has not been added yet.
- If `DATABASE_URL` is omitted, it gracefully falls back to local SQLite at `database/fraud_detection.db`.

### Supabase Setup (Free Tier):
1. Sign up at [supabase.com](https://supabase.com) and create a free project.
2. In **Project Settings → Database**, copy the **URI** connection string.
3. Replace `[YOUR-PASSWORD]` with your database password:
   ```bash
   DATABASE_URL="postgresql://postgres:[PASSWORD]@db.[PROJECT_REF].supabase.co:5432/postgres"
   ```
4. Add `DATABASE_URL` to your backend environment variables. FraudSight AI will automatically create all tables and schema migrations on startup.

---

## Layer 5: Production Guardrails & Free-Tier Protections

To protect free-tier servers from container crashes (Exit 137 OOM) and API quota exhaustion:

1. **In-Memory Rate Limiting**:
   - Implements a sliding-window algorithm per client IP.
   - Configurable via `RATE_LIMIT_PER_MINUTE` (default: 60 requests/minute).
   - Returns standard `HTTP 429 Too Many Requests` with `Retry-After` header.

2. **File Size & Type Validation**:
   - Configurable max file size via `MAX_FILE_SIZE_MB` (default: 50MB). Returns `HTTP 413 Payload Too Large`.
   - Permitted extensions: `jpg`, `jpeg`, `png`, `webp`, `pdf`, `mp4`, `avi`, `mov`, `mkv`, `webm`. Returns `HTTP 415 Unsupported Media Type` for unallowed files.

3. **Sequential Zero-OOM Batch Processing**:
   - Capped at `MAX_BATCH_SIZE` (default: 10 items) per batch submission.
   - Files are evaluated sequentially in the background thread pool, immediately freeing file handles and disk buffers in `finally:` blocks.

---

## Local Development Quickstart

```bash
# 1. Clone repository
git clone https://github.com/adimalkar/multimodal-fraud-detector.git
cd multimodal-fraud-detector

# 2. Setup Python virtual environment
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 3. Configure environment
cp .env.example .env
# Edit .env with both OPENROUTER_API_KEY and FEATHERLESS_API_KEY

# 4. Start Backend API
uvicorn backend.app:app --host 0.0.0.0 --port 8000 --reload

# 5. Start Next.js Frontend (in a second terminal)
cd frontend
cp .env.local.example .env.local
npm install
npm run dev
```

Visit [http://localhost:3000](http://localhost:3000) for the frontend and [http://localhost:8000/docs](http://localhost:8000/docs) for the interactive Swagger API documentation.
