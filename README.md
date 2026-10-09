# Mishra Transport Agency — Insurance expiry tracker

A simple tool for the agency to track insurance expiry on every vehicle. Enter a vehicle number, and the API fetches the insurer, policy number and expiry from Chola/Vahan. The site reminds you 30 days before anything lapses.

No fake data. Every number on screen is either entered by the agency or returned by the live API.

## Repo layout

- `backend/` — Python/Flask API that orchestrates the lookups and caches results. Deployed on **Render**.
- `frontend/` — Next.js app (static export). Deployed on **Vercel**.
- `vehicle_api/` — Serverless Chola relay (Vercel functions, **Mumbai region**). Chola blocks US datacenter IPs, so the Render backend routes all Chola traffic through this service. Deployed on **Vercel** as a separate project.

## Run locally

### Frontend (Next.js)

```bash
cd frontend
npm install
cp .env.local.example .env.local   # points the app at your local backend
npm run dev                        # http://localhost:3000 (next free port if busy)
```

### Backend (Flask)

```bash
cd backend
pip install -r requirements.txt
PORT=5001 python vehicle_api.py    # matches the frontend's default local API URL
```

Locally (unblocked IP) the backend talks to Chola directly — no `VEHICLE_API_URL` needed.

## Deploy

### 1. vehicle_api → Vercel (Mumbai region) — do this first

Chola (`digital.cholainsurance.com`) rejects requests from US datacenter IPs with **HTTP 406**, so the token login fails on Render ("Token refresh failed") even though the same code works from an Indian/residential connection. The `vehicle_api/` folder is a tiny serverless relay that runs on Vercel's **Mumbai (bom1)** region and forwards Chola lookups from an Indian IP.

1. On Vercel: **Add New → Project**, import this GitHub repo.
2. Set **Root Directory** to `vehicle_api`.
3. Deploy. The region is pinned to Mumbai in `vehicle_api/vercel.json`, but verify after the first deploy: **Settings → Functions → Function Region = Mumbai**.
4. Sanity check: open `https://<vehicle-api>.vercel.app/api/token` — `{"ok": true}` means Chola accepts the Mumbai IP. If you see an HTTP 406 error, the region is wrong.

No environment variables are needed on this project.

### 2. Backend → Render

`render.yaml` at the repo root defines the service:

- Build command: `cd backend && pip install -r requirements.txt`
- Start command: `cd backend && gunicorn vehicle_api:app --bind 0.0.0.0:$PORT --workers 2 --threads 8 --timeout 120` (concurrent + long-timeout so slow first-time lookups are not killed; existing Render services must set this in the dashboard)
- Environment: `FLASK_ENV=production`, `VEHICLE_API_URL` (from step 1), optionally `MONGODB_URI`/`MONGODB_DB` (`PORT` is set by Render)

Create it as **New → Web Service**, connect this GitHub repo, and Render picks up `render.yaml`. If the service already exists, just set `VEHICLE_API_URL` in the dashboard and redeploy.

After redeploy, open `https://<backend>/token` — `{"vehicle_api": {"ok": true}}` confirms the relay works.

### 3. Frontend → Vercel

1. Import this GitHub repo as a **second, separate** Vercel project.
2. Set **Root Directory** to `frontend`.
3. Add the environment variable `NEXT_PUBLIC_VEHICLE_API=https://<your-render-backend-url>` (e.g. `https://mishra-transport.onrender.com`) **before** the first deploy — the value is baked in at build time.
4. Deploy. Vercel runs `npm run build`, which static-exports the site to `out/`.

## Environment variables

| Variable | Where | Value |
|---|---|---|
| `NEXT_PUBLIC_VEHICLE_API` | Vercel (frontend) · `frontend/.env.local` (local) | Base URL of the backend. `http://localhost:5001` locally, `https://mishra-transport.onrender.com` in production. |
| `PORT` | Render (backend) | Set automatically by Render. Locally, run the backend with `PORT=5001` to match the frontend default. |
| `FLASK_ENV` | Render (backend) | `production` |
| `CACHE_FILE` | Render (backend) | `/tmp/vehicle_cache.json` — fallback cache file when MongoDB is not configured. |
| `VEHICLE_API_URL` | Render (backend) | **Required on Render.** URL of the vehicle_api project on Vercel (Mumbai region), e.g. `https://mishra-transport-vehicle-api.vercel.app`. Routes all Chola traffic around the datacenter-IP block. Unset → direct Chola calls (local dev). |
| `MONGODB_URI` | Render (backend) | Optional. MongoDB (Atlas) connection string for a persistent lookup cache that survives redeploys. Unset → file cache. |
| `MONGODB_DB` | Render (backend) | Optional. Database name for the MongoDB cache. Defaults to `mishra_transport`. |

Secrets belong in the Render/Vercel dashboards, never in git. All `.env*` files are gitignored; only the `*.example` files are committed.

## How the lookup works

1. The agency enters a vehicle number on the frontend.
2. The frontend calls the backend `/fetch?vehicle_number=…`.
3. The backend checks its cache (MongoDB when `MONGODB_URI` is set, otherwise the JSON file cache).
4. If not cached, the backend asks the vehicle_api (Vercel, Mumbai) for the Chola vehicle profile **and** the Vahan linked mobile number — with a secondary chassis lookup as fallback — caches the result and returns the enriched data.
5. The frontend displays insurer, policy number, chassis, expiry and linked mobile from that real response. Nothing is invented.
