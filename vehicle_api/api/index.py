"""Vercel Flask application for the vehicle_api service (Mumbai region).

A single Flask app — Vercel's Flask backend support expects exactly one
entrypoint (pinned in pyproject.toml; previously the build failed because
api/fetch.py and api/token_check.py both exported `app`).

- GET /api/fetch?vehicle_number=UP43BA2007 — raw Chola profile
  (bike->car fallback included) with a best-effort "parivahan_mobile"
  (linked mobile) lookup attached. Called by the Render backend.
- GET /api/token — Chola login diagnostics: {"ok": true} or the exact
  failure (e.g. "HTTP 406" means the function region is not Mumbai).
"""
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # sibling imports

from flask import Flask, jsonify, request

import chola
import parivahan

app = Flask(__name__)


@app.route("/")
def index():
    return jsonify({
        "status": "ok",
        "service": "vehicle_api",
        "endpoints": ["/api/fetch?vehicle_number=...", "/api/token"],
    })


@app.route("/api/fetch")
def api_fetch():
    vehicle_number = (request.args.get("vehicle_number") or request.args.get("number") or "").strip().upper()
    vehicle_number = re.sub(r"[^A-Z0-9]", "", vehicle_number)
    if not vehicle_number or len(vehicle_number) < 6 or len(vehicle_number) > 12:
        return jsonify({"code": 400, "error": "Invalid vehicle number format"}), 400
    try:
        profile = chola.fetch_profile(vehicle_number)
    except Exception as e:
        return jsonify({"code": 502, "error": str(e)}), 502

    # Best-effort linked mobile from this (Indian) IP, hard-capped well under
    # the 60s function limit. The key is ALWAYS present in relay responses so
    # the Render backend knows the lookup was already attempted and does not
    # retry it from its blocked US IP.
    mobile = None
    try:
        chassis = (((profile.get("data") or {}).get("result") or {}).get("chassis") or "")
        chassis = chassis.replace(" ", "").upper()
        if len(chassis) >= 5:
            mobile = parivahan.fetch_mobile_number(vehicle_number, chassis[-5:])
    except Exception as e:
        print(f"[-] parivahan mobile lookup failed: {e}")
    if not isinstance(mobile, dict):
        mobile = {"success": False, "error": "unavailable"}

    out = dict(profile)
    out["parivahan_mobile"] = mobile
    return jsonify(out)


@app.route("/api/token")
def api_token():
    try:
        chola.get_valid_token()
        return jsonify({"ok": True, "token_age_seconds": int(time.time() - chola.LAST_TOKEN_FETCH)})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 502
