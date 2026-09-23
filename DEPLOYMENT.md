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

### Running Backend Locally:
```bash
uvicorn backend.app:app --host 0.0.0.0 --port 8000 --reload
```

### Running Frontend Locally:
```bash
cd frontend
npm run dev
```
Open [http://localhost:3000](http://localhost:3000).
