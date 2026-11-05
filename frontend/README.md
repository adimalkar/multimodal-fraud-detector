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

- Colour carries meaning: `ink` for people and decisions, `uv` for anything the machine observed, `fluoro` for the scanning light, yellow tags for exhibits that cross-reference a finding.
- Score bands are ordered, so they share one hue that brightens as the score rises. Status colours describe the system, never a claim.
- The interface never presents a score as a verdict. Engine values such as `CRITICAL_FRAUD` are mapped to plain labels in `lib/format.ts`.
- A skipped check must read as skipped, never as passed.
- Don't add stats, logos or testimonials that aren't real.

## 3D scene

The landing page's scene is in `components/landing/three` and uses [three.js](https://github.com/mrdoob/three.js), [react-three-fiber](https://github.com/pmndrs/react-three-fiber) and [drei](https://github.com/pmndrs/drei), all MIT. It loads on demand, so workspace pages don't pay for it. Without WebGL, `StaticStack` is shown instead. With reduced motion on, the idle movement stops and the layers still open with scroll.

The `.beam` style in `styles/globals.css` is adapted from [Magic UI](https://github.com/magicuidesign/magicui)'s BorderBeam (MIT, Copyright (c) Magic UI).

The bundled `LICENSE` covers the MIT-licensed template this project started from.
