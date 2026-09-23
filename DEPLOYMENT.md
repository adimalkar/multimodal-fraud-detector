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
│  - Handles upload UI & poll updates          │
└──────────────┬───────────────────────────────┘
               │
               │ Direct Presigned Upload (Bypasses API memory)
               ▼
┌──────────────────────────────────────────────┐
│  Layer 2: Media Storage (Videos / PDFs)      │
│  Hosted on: CLOUDFLARE R2 or SUPABASE        │
│  - 10 GB Free Storage, $0 Egress fees        │
└──────────────┬───────────────────────────────┘
               │
               │ Triggers analysis job
               ▼
┌──────────────────────────────────────────────┐
│  Layer 3: AI Backend Engine (FastAPI)        │
│  Option A (Recommended): HUGGING FACE SPACES │
│    • 16 GB RAM + 2 vCPU (FREE!)              │
│    • Built for OpenCV, Video, & Python AI    │
│  Option B: Render / Koyeb (API-only)         │
│    • Reserved 100% for Python (No Node.js)   │
└──────────────┬───────────────────────────────┘
               │
               ▼ Async Task / Job Status
┌──────────────────────────────────────────────┐
│  Layer 4: Async Job Processing               │
│  - POST /api/analyze -> returns { job_id }   │
│  - Frontend polls GET /api/jobs/{job_id}     │
│  - Prevents 100s HTTP Gateway Timeouts       │
└──────────────────────────────────────────────┘
```

---

## Layer 1: Deploying the Next.js Frontend to Vercel (Free)

1. Go to [vercel.com](https://vercel.com) and log in with your GitHub account.
2. Click **"Add New..."** → **"Project"**.
3. Select your repository: `adimalkar/multimodal-fraud-detector`.
4. In the project configuration:
   - **Framework Preset**: Next.js
   - **Root Directory**: Click "Edit" and choose `frontend`
   - **Environment Variables**:
     - `NEXT_PUBLIC_API_URL`: Your backend API URL (e.g. `https://multimodal-fraud-detector-1.onrender.com`)
5. Click **"Deploy"**.

**Benefits:**
- 0s cold starts (instant global CDN delivery).
- Does not consume Python server RAM or CPU.
- Automatically rebuilds on git push.

---

## Layer 3: AI Backend Engine (FastAPI)

The backend has been upgraded to a dedicated FastAPI server with non-blocking background task execution:
- `GET /api/health`: Health check (used by keepalive loops).
- `POST /api/analyze`: Non-blocking job submission, returns a `job_id` in <100ms.
- `GET /api/jobs/{job_id}`: Poll endpoint returning live progress percentage, stage, and full multi-agent jury results.
- `POST /analyze_media`: Synchronous endpoint for legacy integrations.

---

## Layer 2: Cloudflare R2 Object Storage (10 GB Free, $0 Egress)

When processing large videos (50MB–200MB), uploading directly to object storage bypasses container RAM limits completely.

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

## Layer 3, Option A: Deploying Backend to Hugging Face Spaces (16 GB RAM Free!)

Hugging Face Spaces offers **16 GB RAM + 2 vCPU** for FREE on Docker spaces — 30x more RAM than Render's 512 MB tier.

1. Go to [huggingface.co/spaces](https://huggingface.co/spaces) and click **"Create new Space"**.
2. Settings:
   - **Space name**: `multimodal-fraud-detector`
   - **License**: MIT
   - **Space SDK**: **Docker** (Blank)
   - **Space hardware**: Free (2 vCPU, 16 GB RAM)
3. Set Space Secrets in **Settings → Variables and Secrets**:
   - `OPENROUTER_API_KEY`: your OpenRouter API key
   - `FEATHERLESS_API_KEY`: your Featherless API key (optional)
4. Push or mirror this repository:
   ```bash
   git remote add space https://huggingface.co/spaces/YOUR_USERNAME/multimodal-fraud-detector
   git push space main
   ```
5. Hugging Face builds the included `Dockerfile` and serves your FastAPI backend on port 7860!

---

### Running Locally:
```bash
# 1. Start Backend API
uvicorn backend.app:app --host 0.0.0.0 --port 8000 --reload

# 2. Start Next.js Frontend
cd frontend
npm run dev
```
Open [http://localhost:3000](http://localhost:3000).
