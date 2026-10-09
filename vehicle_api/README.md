# vehicle_api — Chola lookup on Vercel (Mumbai region)

Chola (`digital.cholainsurance.com`) returns **HTTP 406** to requests from US
datacenter IPs (Render runs in the US), which used to break the backend's token
login with "Token refresh failed". This Flask app runs on Vercel's **Mumbai
region** and relays the Chola lookups from an Indian IP.

The Render backend calls this service (env var `VEHICLE_API_URL`) instead of
talking to Chola directly.

Single Flask app in `api/index.py` (Vercel auto-detects Flask; the entrypoint
is pinned in `pyproject.toml`). `api/chola.py` holds the shared login/lookup
logic. No environment variables needed.

## Endpoints

- `GET /api/fetch?vehicle_number=UP43BA2007` — raw Chola profile (bike→car fallback included)
- `GET /api/token` — diagnostics: `{"ok": true, ...}` or the exact Chola failure

## Deploy (Vercel, ~3 minutes)

1. Vercel → **Add New → Project** → import this GitHub repo.
2. Set **Root Directory** to `vehicle_api`. Framework preset: **Flask** (auto-detected). Deploy.
3. Open **Settings → Functions → Region** and make sure it is **Mumbai (bom1)** —
   that is the entire point of this service (`vercel.json` also requests `bom1`).
4. Test: open `https://<project>.vercel.app/api/token` — `{"ok": true}` means
   Chola accepts requests from this region. If it says HTTP 406, the function is
   not running from Mumbai — fix the region setting and redeploy.
5. On Render (the `mishra-transport` backend) → Environment, add:

   ```
   VEHICLE_API_URL = https://<project>.vercel.app
   ```

   (and `MONGODB_URI` if you want persistent caching) → Save → redeploy.
6. Verify end-to-end: `https://mishra-transport.onrender.com/token` should show
   `{"vehicle_api": {"ok": true, ...}}`, then try `/fetch?vehicle_number=...`.
