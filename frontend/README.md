# FraudSight frontend

Next.js 14 app for the FraudSight evidence screening engine: the landing page plus the workspace where claims teams screen files, read reports, review history and run claim-level signals.

| Route | Purpose |
| --- | --- |
| `/` | Landing page |
| `/analyze` | Upload one file or a batch |
| `/analyze/job/[id]` | Live progress and the screening report |
| `/analyze/batch/[id]` | Batch progress and results, highest scores first |
| `/analytics` | History, score bands and CSV export |
| `/signals` | Claim-level checks: timing, travel, shared identifiers, signal conflict and past findings |

## Run it

```bash
cp .env.local.example .env.local   # points at http://localhost:8000
npm ci
npm run dev
```

Start the backend from the repository root with `uvicorn backend.app:app --reload`. Without `NEXT_PUBLIC_API_URL`, the app uses the hosted Render API.

## Design rules

- Colour carries meaning: carbon for people and decisions, UV violet for anything the machine observed, yellow tags for exhibits that cross-reference a finding.
- Score bands are ordered, so they share one hue from light to dark. Status colours describe the system, never a claim.
- The interface never presents a score as a verdict. Engine values such as `CRITICAL_FRAUD` are mapped to plain labels in `lib/format.ts`.
- A skipped check must read as skipped, never as passed.
- Don't add stats, logos or testimonials that aren't real.

The bundled `LICENSE` covers the MIT-licensed template this project started from.
