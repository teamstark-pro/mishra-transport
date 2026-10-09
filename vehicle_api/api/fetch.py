"""Vercel function: GET /api/fetch?vehicle_number=UP43BA2007

Returns the raw Chola vehicle profile (bike -> car fallback included).
Called by the Render backend (set VEHICLE_API_URL there).
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # sibling imports

from flask import Flask, jsonify, request

import chola

app = Flask(__name__)


@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def fetch(path):
    # Path-agnostic: Vercel may route this function under /api/fetch or /api/index.
    vehicle_number = (request.args.get("vehicle_number") or request.args.get("number") or "").strip().upper()
    vehicle_number = re.sub(r"[^A-Z0-9]", "", vehicle_number)
    if not vehicle_number or len(vehicle_number) < 6 or len(vehicle_number) > 12:
        return jsonify({"code": 400, "error": "Invalid vehicle number format"}), 400
    try:
        return jsonify(chola.fetch_profile(vehicle_number))
    except Exception as e:
        return jsonify({"code": 502, "error": str(e)}), 502
