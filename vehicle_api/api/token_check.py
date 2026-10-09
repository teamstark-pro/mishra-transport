"""Vercel function: GET /api/token — Chola login diagnostics.

The file is named token_check.py (not token.py) on purpose: a module named
"token" in the functions directory shadows Python's stdlib `token` module
once this directory is on sys.path, and Flask's import chain
(logging -> traceback -> tokenize -> `from token import *`) then breaks.
vercel.json rewrites /api/token to this function, so the public URL is
unchanged.

Returns {"ok": true} when the Chola login works from this region, or the exact
failure otherwise (e.g. "HTTP 406" means this region's IP is being blocked by
Chola — check the Vercel project's function region is Mumbai).
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # sibling imports

from flask import Flask, jsonify

import chola

app = Flask(__name__)


@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def token(path):
    try:
        chola.get_valid_token()
        return jsonify({"ok": True, "token_age_seconds": int(time.time() - chola.LAST_TOKEN_FETCH)})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 502
