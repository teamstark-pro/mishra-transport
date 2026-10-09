"""Vercel Flask application for the vehicle_api service (Mumbai region).

A single Flask app — Vercel's Flask backend support expects exactly one
entrypoint (pinned in pyproject.toml; previously the build failed because
api/fetch.py and api/token_check.py both exported `app`).

- GET /api/fetch?vehicle_number=UP43BA2007 — raw Chola profile
  (bike->car fallback included). Called by the Render backend.
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
        return jsonify(chola.fetch_profile(vehicle_number))
    except Exception as e:
        return jsonify({"code": 502, "error": str(e)}), 502


@app.route("/api/token")
def api_token():
    try:
        chola.get_valid_token()
        return jsonify({"ok": True, "token_age_seconds": int(time.time() - chola.LAST_TOKEN_FETCH)})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 502
