# Mishra Transport Agency — Insurance expiry tracker

A simple tool for the agency to track insurance expiry on every vehicle. Enter a vehicle number, and the API fetches the insurance company, policy number, owner and expiry from Chola/Vahan. The site reminds you 30 days before anything lapses.

No fake data. Every number on screen is either entered by the agency or returned by the live API.

## What it is

- **Frontend** — a Next.js app, statically exported to `out/`. Drag-and-drop `out/` to Vercel or Netlify.
- **Backend** — a small Python Flask service (`backend/vehicle_api.py`) that sits on Render. It calls Chola/Vahan to enrich a vehicle lookup, caches results, and is wired to accept a MongoDB Atlas URI later (via the `MONGODB_URI` env var on Render).
- **chola.py** — the Chola/Vahan logic lives in `vehicle_api.py`. If you host a separate `chola.py` on Vercel as a serverless API, point the backend at its endpoint with the `CHOLA_API_URL` env var.

## Run locally

### Frontend (Next.js)

```bash
npm install
npm run dev               # http://localhost:3003 (or next free port)
```

The frontend reads `NEXT_PUBLIC_VEHICLE_API` from `.env.local`. For local testing the backend should run on `:5001` and the frontend on its own port.

To test the static export the same way Vercel/Netlify will serve it:

```bash
npm run build            # produces out/
# then serve out/ with any static server, e.g.
npx serve out
```

### Backend (Render-style)

```bash
cd backend
pip install -r requirements.txt
python vehicle_api.py          # or gunicorn vehicle_api:app --bind 0.0.0.0:$PORT
```

The backend listens on `PORT` (Render sets this). Default listens on `0.0.0.0:$PORT`.

## Deploy

### Backend → Render

1. Push this repo to `teamstark-pro/mishra-transport` on GitHub.
2. On Render, create a **New → Web Service**, connect the repo, and use:
   - **Build Command:** `cd backend && pip install -r requirements.txt`
   - **Start Command:** `cd backend && gunicorn vehicle_api:app --bind 0.0.0.0:$PORT`
   - Or drop the `render.yaml` into the repo root and Render will pick it up.
3. Set these **Environment Variables** on Render:
   - `FLASK_ENV = production`
   - `CACHE_FILE = /tmp/vehicle_cache.json`
   - `CHOLA_API_URL` = the Chola endpoint the backend should hit (default is the built-in Chola URL; change this if you host `chola.py` on Vercel as a serverless API and want the backend to call that Vercel endpoint instead).
   - `MONGODB_URI` = your MongoDB Atlas connection string (optional). When set, vehicle data lives in MongoDB. When not set, the backend uses the local `/tmp` cache.
4. Deploy.

### Frontend → Vercel (drag-and-drop)

1. Run `npm run build` locally. This creates `out/`.
2. Drag the `out/` folder onto https://vercel.com/drop.
3. In the Vercel project dashboard, add this Environment Variable **before** the first deploy or redeploy:
   - `NEXT_PUBLIC_VEHICLE_API = https://<your-render-backend-url>` (for example `https://mishra-transport-backend.onrender.com`).
4. Redeploy / the site restarts with that variable.

### Frontend → Netlify (drag-and-drop)

1. Run `npm run build` locally. This creates `out/`.
2. Drag the `out/` folder onto https://app.netlify.com/drop.
3. In the Netlify site dashboard, add this Environment Variable:
   - `NEXT_PUBLIC_VEHICLE_API = https://<your-render-backend-url>`.
4. Redeploy / the site restarts with that variable.

Important: for drag-drop deploys you cannot bake the Render backend URL at build time easily. Set `NEXT_PUBLIC_VEHICLE_API` in the platform dashboard and redeploy so the build picks it up. If you ever want the URL to be fixed at build time, run `NEXT_PUBLIC_VEHICLE_API=https://<your-render-backend-url> npm run build` and then drag that new `out/` to the platform.

### Git

Pushed to `https://github.com/teamstark-pro/mishra-transport` on branch `main`.

The repo is kept clean:
- No virtualenv (`backend/venv/`) committed.
- No cache or artifacts (`backend/__pycache__/`, `backend/requests`, `out-vercel/`, `out-netlify/`) committed.
- Environment files (`.env*`) are gitignored — set secrets on the platform dashboards instead.

### Git

Pushed to `https://github.com/teamstark-pro/mishra-transport` on branch `main`.

The repo is kept clean:
- No virtualenv (`backend/venv/`) committed.
- No cache or artifacts (`backend/__pycache__/`, `backend/requests`, `out-vercel/`, `out-netlify/`) committed.
- Environment files (`.env*`) are gitignored — set secrets on the platform dashboards instead.

## Environment variables

| Variable | Where | Notes |
|---|---|---|
| `NEXT_PUBLIC_VEHICLE_API` | Frontend (`.env.local` for local; Vercel/Netlify dashboard for deploys) | Base URL of the backend, e.g. `http://localhost:5001` locally, or `https://mishra-transport-backend.onrender.com` in production. |
| `PORT` | Backend (Render sets this) | The port the Flask app binds to. |
| `CHOLA_API_URL` | Backend env var | Override the Chola endpoint if you host `chola.py` on Vercel and want the backend to call that serverless endpoint. |
| `MONGODB_URI` | Backend env var (optional) | MongoDB Atlas connection string. Enables persistent vehicle storage across Render restarts. |
| `CACHE_FILE` | Backend env var | Path for the local cache when MongoDB isn’t set. `/tmp/vehicle_cache.json` on Render is fine. |
| `FLASK_ENV` | Backend env var | `production` on Render. |

## How the lookup works

1. Agency enters a vehicle number on the frontend.
2. Frontend calls the backend `/fetch?vehicle_number=…`.
3. Backend checks its cache (MongoDB if `MONGODB_URI` is set, otherwise `/tmp` cache).
4. If not cached, the backend calls Chola (and a secondary chassis lookup as fallback), then Vahan to grab the linked mobile number, caches the result, and returns the enriched data.
5. Frontend displays insurer, policy number, owner, chassis, expiry and linked mobile from that real response. Nothing is invented.

## Files

- `app/` — Next.js frontend (App Router), statically exported.
- `backend/vehicle_api.py` — Flask backend: Chola/Vahan lookup + cache/MongoDB-ready storage.
- `backend/requirements.txt` — Python deps (flask, flask-cors, requests, beautifulsoup4, urllib3, gunicorn).
- `render.yaml` — Render service definition (backend web service).
- `Procfile` — process declaration for Render (`gunicorn vehicle_api:app`).
- `out/` — built static frontend (after `npm run build`; gitignored).
- `out-vercel/` and `out-netlify/` — local copies of the static export for drag-drop (gitignored).

## Notes

- Keep the backend reachable from wherever the frontend is served. If the frontend is on Vercel and the backend on Render, set `NEXT_PUBLIC_VEHICLE_API` to the Render backend URL.
- If you later want MongoDB persistence, paste the Atlas URI into the Render environment variable `MONGODB_URI`. No code change needed — the backend is already wired to use it when present.
