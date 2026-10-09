"""Chola vehicle-lookup logic — shared by the Vercel serverless functions.

Chola (digital.cholainsurance.com) blocks non-Indian/datacenter IPs (HTTP 406),
which is why these functions deploy to Vercel's Mumbai region. The Render
backend calls them (env var VEHICLE_API_URL) instead of talking to Chola
directly.
"""
import json
import time

import requests

CURRENT_TOKEN = None
LAST_TOKEN_FETCH = 0
LAST_TOKEN_ERROR = ""
TOKEN_EXPIRY_TIMEOUT = 1200  # 20 minutes (per warm instance)

BASE_HEADERS = {
    'Accept': 'application/json, text/plain, */*',
    'Accept-Language': 'en-US,en;q=0.9',
    'Content-Type': 'application/json',
    'Origin': 'https://digital.cholainsurance.com',
    'Referer': 'https://digital.cholainsurance.com/cscportal/',
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36',
}

CHOLA_API_URL = "https://digital.cholainsurance.com/api/v1/masterdata/vehicle_class_validation"
PC_LOGIN_PAGE = "https://digital.cholainsurance.com/pc/"
LOGIN_ENDPOINT = "https://digital.cholainsurance.com/api/v1/wrapper_service/auth_d2c/login"
LOGIN_RETRIES = 3
LOGIN_BACKOFF_SECONDS = 3

HANDSHAKE_PAYLOAD = {
    "encryptedKey": "lYZObBhUdQ1JiyUkNxFZt1ePevKHf+yxxoND+RMNS15vcto6Y1BsFULfpoCzkl0OaL7hwnu+J/fvUp02j4MuYCeXYHkB6G2MJuhIzA6gPzgfXg0YXBdBMh82zf23yHNWGHWPrm95sEHat+HBx7e5KJ03Spx4Hf76ZyWct5E2PcO/OfR+BT3gRz0qotQV63pHt2/zH+wfs9vVErIm3x0HvmTr6NMUpNGB9TOgSrd1bgncnTJGiBbG6kEadevWuYuzu/opruvveQuxIIAh2sySL39W/2hlYesoMl17Nx3OuTtNFK5Y0WJ7JzfojUCQvrtWflHEtwvlqqcCoG4ZupegriHF1Rde4ucxYEBW4d6vBeh9UUpKsX8govt0rQehxCwnClWMYfJYW+s/+G8kOx887h3BuZDttoLvJCrl5HaXII3/2iGI6KquVXhNi7xVc5oIEs5PcWC9R9KbCAn6kL3ooSoekTucgCRQYpk50VX8SphrGupQNWsQ5kPhnvbotoMQg+7yKiM9THsJKzuPUtkVIesWEadHUSDIxtFR64PdtejM0gAa+xrtavllMKKJo7l765gvP2LtpR/YPU2hUHFG32ONM7KX3Ieiefaq30Ndxi2CGVXf2+oMQ8Zo9HHqDDPtuNjusC2tCwDfqaXyFQN09trj47ndZ+G14mToFy3Wcb8=",
    "iv": "8yfm3VbcW1dIelFc",
    "encryptedData": "zP9u1jktIWtrIUVlWkF7HZ+FeCG6mWUmvPZYxX2zhG3X1mOVTztFINFcbpkDzY0wb6A8h1CbVwMQZ/OQYwKqew/TrIjxnYzaQMv2Ic07YMd2fAl/U2azGkZPQqbvvg0WUttAD78GTwMQYNGrc3xB+AEVWnW3sk93YdRNSlYFGgkYh7p1AhkXES936Mud1S2+B+AHAYyGZcnHkmmd44uw",
    "authTag": "m0a3akMVGxoPpIHrHgWmCw=="
}


def _attempt_chola_login():
    """One login attempt. Returns the token, or raises with a precise reason."""
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
    })

    session.get(PC_LOGIN_PAGE, timeout=15)

    r = session.post(LOGIN_ENDPOINT, json=HANDSHAKE_PAYLOAD, headers={
        'Accept': 'application/json, text/plain, */*',
        'Content-Type': 'application/json',
        'Origin': 'https://digital.cholainsurance.com',
        'Referer': PC_LOGIN_PAGE
    }, timeout=15)

    if r.status_code != 200:
        raise RuntimeError(f"Chola login returned HTTP {r.status_code}")
    try:
        res_json = r.json()
    except ValueError:
        snippet = r.text[:120].replace("\n", " ")
        raise RuntimeError(
            f"Chola login returned non-JSON (HTTP {r.status_code}, likely WAF/IP block): {snippet}"
        )
    if "serviceResp" not in res_json:
        raise RuntimeError(f"Chola login response missing serviceResp: {str(res_json)[:120]}")
    inner = json.loads(res_json["serviceResp"])
    token = (inner.get("data") or {}).get("token")
    if not token:
        raise RuntimeError(f"Chola login response missing token: {str(inner)[:120]}")
    return token


def force_refresh_session_token():
    global CURRENT_TOKEN, LAST_TOKEN_FETCH, LAST_TOKEN_ERROR
    for attempt in range(1, LOGIN_RETRIES + 1):
        try:
            CURRENT_TOKEN = _attempt_chola_login()
            LAST_TOKEN_FETCH = time.time()
            LAST_TOKEN_ERROR = ""
            return True
        except Exception as e:
            LAST_TOKEN_ERROR = str(e)
            print(f"[-] Token login attempt {attempt}/{LOGIN_RETRIES} failed: {e}")
            if attempt < LOGIN_RETRIES:
                time.sleep(LOGIN_BACKOFF_SECONDS * attempt)
    return False


def get_valid_token():
    global CURRENT_TOKEN, LAST_TOKEN_FETCH
    if not CURRENT_TOKEN or (time.time() - LAST_TOKEN_FETCH > TOKEN_EXPIRY_TIMEOUT):
        if not force_refresh_session_token():
            raise Exception(f"Token refresh failed ({LAST_TOKEN_ERROR})")
    return CURRENT_TOKEN


def inner_txt(d):
    inner = d.get('data')
    if isinstance(inner, dict):
        return inner.get('txt') or d.get('txt') or ''
    return d.get('txt') or ''


def fetch_chola_raw(vehicle_number, source, max_attempts=3):
    """One Chola vehicle_class_validation lookup ('bike' or 'car' product)."""
    payload = {
        'journeyChannel': 'CSC',
        'partnerShortCode': '',
        'productName': 'Two Wheeler' if source == 'bike' else 'Private Car',
        'signzyState': 'UTTAR PRADESH STATE OFFICE',
        'signzySelPolicytype': 'Liability' if source == 'bike' else 'Comprehensive',
        'vehicleNumber': vehicle_number
    }

    last_txt = ""
    refreshed_for_expiry = False
    for attempt in range(max_attempts):
        headers = BASE_HEADERS.copy()
        headers['In-Auth-Token'] = get_valid_token()

        r = requests.post(CHOLA_API_URL, headers=headers, json=payload, timeout=20)
        try:
            data = r.json()
        except ValueError:
            snippet = r.text[:120].replace("\n", " ")
            raise Exception(f"Chola API returned non-JSON (HTTP {r.status_code}, likely WAF/IP block): {snippet}")
        last_txt = inner_txt(data)

        # Rate-limited: back off and retry
        if 'too many requests' in last_txt.lower():
            wait = 8 * (attempt + 1)
            print(f"[*] Chola rate-limited, waiting {wait}s (attempt {attempt + 1}/{max_attempts})")
            time.sleep(wait)
            continue

        # Token expired/invalid: refresh once and retry the lookup with the new token
        if data.get('status') == -106 or "expired" in last_txt.lower():
            if not refreshed_for_expiry:
                refreshed_for_expiry = True
                print("[*] Chola reported expired/invalid token — refreshing and retrying")
                if not force_refresh_session_token():
                    raise Exception(f"Token refresh failed ({LAST_TOKEN_ERROR})")
                continue
            raise Exception(f"Chola rejected the token even after refresh (status {data.get('status')}, txt: {last_txt[:120]})")

        return data

    raise Exception(f"Chola rate-limited after {max_attempts} attempts")


def fetch_profile(vehicle_number):
    """Chola profile with the bike -> car fallback (same order the backend used)."""
    bike_res = fetch_chola_raw(vehicle_number, 'bike')
    if bike_res.get('status') == -1 or "not an two wheeler" in inner_txt(bike_res).lower():
        return fetch_chola_raw(vehicle_number, 'car')
    return bike_res
