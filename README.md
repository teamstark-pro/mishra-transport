# Mishra Transport Agency — Insurance expiry tracker

A simple tool for the agency to track insurance expiry on every vehicle. Enter a vehicle number, and the API fetches the insurer, policy number and expiry from Chola/Vahan. The site reminds you 30 days before anything lapses.

No fake data. Every number on screen is either entered by the agency or returned by the live API.

## Repo layout

- `backend/` — Python/Flask API that does the Chola/Vahan vehicle lookup and caches results. Deployed on **Render**.
- `frontend/` — Next.js app (static export). Deployed on **Vercel**.

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

## Deploy

### Backend → Render

`render.yaml` at the repo root defines the service:

- Build command: `cd backend && pip install -r requirements.txt`
- Start command: `cd backend && gunicorn vehicle_api:app --bind 0.0.0.0:$PORT`
- Environment: `FLASK_ENV=production`, `CACHE_FILE=/tmp/vehicle_cache.json` (`PORT` is set by Render)

Create it as **New → Web Service**, connect this GitHub repo, and Render picks up `render.yaml`. If the service already exists with these commands, nothing changes on redeploy.

### Frontend → Vercel

1. Import this GitHub repo as a new project on Vercel.
2. Set **Root Directory** to `frontend`.
3. Add the environment variable `NEXT_PUBLIC_VEHICLE_API=https://<your-render-backend-url>` (e.g. `https://mishra-transport-backend.onrender.com`) **before** the first deploy — the value is baked in at build time.
4. Deploy. Vercel runs `npm run build`, which static-exports the site to `out/`.

## Environment variables

| Variable | Where | Value |
|---|---|---|
| `NEXT_PUBLIC_VEHICLE_API` | Vercel (frontend) · `frontend/.env.local` (local) | Base URL of the backend. `http://localhost:5001` locally, `https://mishra-transport-backend.onrender.com` in production. |
| `PORT` | Render (backend) | Set automatically by Render. Locally, run the backend with `PORT=5001` to match the frontend default. |
| `FLASK_ENV` | Render (backend) | `production` |
| `CACHE_FILE` | Render (backend) | `/tmp/vehicle_cache.json` — where the backend keeps its lookup cache. |

Secrets belong in the Render/Vercel dashboards, never in git. All `.env*` files are gitignored; only the `*.example` files are committed.

## How the lookup works

1. The agency enters a vehicle number on the frontend.
2. The frontend calls the backend `/fetch?vehicle_number=…`.
3. The backend checks its JSON cache (`CACHE_FILE`).
4. If not cached, the backend calls Chola (with a secondary chassis lookup as fallback), then Vahan for the linked mobile number, caches the result and returns the enriched data.
5. The frontend displays insurer, policy number, chassis, expiry and linked mobile from that real response. Nothing is invented.
