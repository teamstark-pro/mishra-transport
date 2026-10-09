import json
import os
import re
import time
from datetime import datetime
from bs4 import BeautifulSoup
from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

app = Flask(__name__)
CORS(app)  # allow frontend (Vercel / localhost) to call this API

# Local persistent cache (falls back to /tmp if write fails)
CACHE_FILE = os.environ.get("CACHE_FILE", "/tmp/vehicle_cache.json")

CURRENT_TOKEN = None
LAST_TOKEN_FETCH = 0
LAST_TOKEN_ERROR = ""
TOKEN_EXPIRY_TIMEOUT = 1200  # 20 minutes

BASE_HEADERS = {
    'Accept': 'application/json, text/plain, */*',
    'Accept-Language': 'en-US,en;q=0.9',
    'Content-Type': 'application/json',
    'Origin': 'https://digital.cholainsurance.com',
    'Referer': 'https://digital.cholainsurance.com/cscportal/',
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36',
}

CHOLA_API_URL = "https://digital.cholainsurance.com/api/v1/masterdata/vehicle_class_validation"
CHASSIS_API_URL = "https://vehicle2chassis.profilework239.workers.dev/?plate={}"

# Chola (digital.cholainsurance.com) returns HTTP 406 to US datacenter IPs, so this
# backend (Render, US) cannot call it directly. VEHICLE_API_URL points at the Vercel
# vehicle_api deployed from the vehicle_api/ folder in the MUMBAI region, which relays
# all Chola lookups from an Indian IP. When unset, this backend calls Chola directly
# (local development from an unblocked IP).
VEHICLE_API_URL = os.environ.get("VEHICLE_API_URL", "").rstrip("/")

# Optional persistent cache. When MONGODB_URI is set (e.g. MongoDB Atlas), lookups
# are cached in MongoDB instead of the ephemeral /tmp file. Unset -> file cache.
MONGODB_URI = os.environ.get("MONGODB_URI", "")
MONGODB_DB = os.environ.get("MONGODB_DB", "mishra_transport")

HOMEPAGE_URL = "https://vahan.parivahan.gov.in/vahanservice/vahan/ui/statevalidation/homepage.xhtml?statecd=Mzc2MzM2MzAzNjY0MzIzODM3NjIzNjY0MzY2MjM3NDQ0Yw=="
HOMEPAGE_BASE = "https://vahan.parivahan.gov.in/vahanservice/vahan/ui/statevalidation/homepage.xhtml"
LOGIN_URL = "https://vahan.parivahan.gov.in/vahanservice/vahan/ui/usermgmt/login.xhtml"
FORM_URL = "https://vahan.parivahan.gov.in/vahanservice/vahan/ui/balanceservice/form_reschedule_fitness.xhtml"


# ==================== CACHE ====================

def load_cache():
    try:
        if os.path.exists(CACHE_FILE):
            with open(CACHE_FILE, 'r') as f:
                return json.load(f)
    except Exception:
        return {}
    return {}


def save_cache(cache):
    try:
        with open(CACHE_FILE, 'w') as f:
            json.dump(cache, f, indent=2)
    except Exception:
        pass


_MONGO_COLL = None


def _mongo_collection():
    """Lazily connect to MongoDB when MONGODB_URI is configured."""
    global _MONGO_COLL
    if _MONGO_COLL is None:
        import pymongo  # lazy: only needed when MongoDB is configured
        client = pymongo.MongoClient(MONGODB_URI, serverSelectionTimeoutMS=5000)
        _MONGO_COLL = client[MONGODB_DB]["vehicle_cache"]
    return _MONGO_COLL


def get_from_cache(vehicle_number):
    if MONGODB_URI:
        try:
            doc = _mongo_collection().find_one({"_id": vehicle_number})
            if doc:
                return {"data": doc["data"], "cached_at": doc["cached_at"]}
            return None
        except Exception as e:
            print(f"[-] MongoDB cache read failed, using file cache: {e}")
    return load_cache().get(vehicle_number)


def save_to_cache(vehicle_number, data):
    if MONGODB_URI:
        try:
            _mongo_collection().update_one(
                {"_id": vehicle_number},
                {"$set": {"data": data, "cached_at": datetime.now().isoformat()}},
                upsert=True,
            )
            return
        except Exception as e:
            print(f"[-] MongoDB cache write failed, using file cache: {e}")
    cache = load_cache()
    cache[vehicle_number] = {"data": data, "cached_at": datetime.now().isoformat()}
    save_cache(cache)


# ==================== TOKEN (SERVERLESS-SAFE) ====================

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


# ==================== CHOLA API ====================

def fetch_chola_raw(vehicle_number, source, max_attempts=3):
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
        token = get_valid_token()
        headers = BASE_HEADERS.copy()
        headers['In-Auth-Token'] = token

        r = requests.post(CHOLA_API_URL, headers=headers, json=payload, timeout=20)
        try:
            data = r.json()
        except ValueError:
            snippet = r.text[:120].replace("\n", " ")
            raise Exception(f"Chola API returned non-JSON (HTTP {r.status_code}, likely WAF/IP block): {snippet}")
        last_txt = (data.get('txt') or '') + (data.get('data', {}) or {}).get('txt', '') if isinstance(data.get('data'), dict) else (data.get('txt') or '')

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


def fetch_vehicle_profile(vehicle_number):
    """Chola vehicle profile for a vehicle number.

    Via the Vercel vehicle_api (Mumbai region) when VEHICLE_API_URL is set —
    Chola blocks this host's US IP with HTTP 406 — or direct to Chola
    otherwise (local development).
    """
    if VEHICLE_API_URL:
        r = requests.get(
            f"{VEHICLE_API_URL}/api/fetch",
            params={"vehicle_number": vehicle_number},
            timeout=65,  # the Vercel function is capped at 60s (maxDuration)
        )
        if r.status_code != 200:
            raise Exception(f"vehicle_api returned HTTP {r.status_code}: {r.text[:120]}")
        return r.json()

    bike_res = fetch_chola_raw(vehicle_number, 'bike')
    inner = bike_res.get('data')
    bike_txt = inner.get('txt') if isinstance(inner, dict) else None
    bike_txt = bike_txt or bike_res.get('txt') or ''
    if bike_res.get('status') == -1 or "not an two wheeler" in bike_txt.lower():
        return fetch_chola_raw(vehicle_number, 'car')
    return bike_res


# ==================== PARIVAHAN ====================

def create_parivahan_session():
    session = requests.Session()
    retry = Retry(total=2, backoff_factor=2, status_forcelist=[500, 502, 503, 504])
    adapter = HTTPAdapter(max_retries=retry, pool_connections=10, pool_maxsize=10)
    session.mount('https://', adapter)
    session.mount('http://', adapter)
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
        'Connection': 'keep-alive',
    })
    return session


def extract_viewstate(html):
    soup = BeautifulSoup(html, 'html.parser')
    vs = soup.find('input', {'name': 'javax.faces.ViewState'})
    return vs.get('value') if vs else None


def extract_viewstate_from_ajax(text):
    m = re.search(r'<update id="j_id1:javax.faces.ViewState:0"><!\[CDATA\[(.*?)\]\]></update>', text)
    return m.group(1) if m else None


def find_checkbox_id(html):
    m = re.search(r'<div[^>]*id="(j_idt\d+)"[^>]*class="[^"]*ui-chkbox', html)
    if not m:
        m = re.search(r'PrimeFaces\.cw\("SelectBooleanCheckbox"[^}]*id:"(j_idt\d+)"', html)
    return m.group(1) if m else "j_idt193"


def fetch_mobile_number(vehicle_number, chassis_last_5):
    session = create_parivahan_session()
    ajax_headers = {
        'Accept': 'application/xml, text/xml, */*; q=0.01',
        'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
        'Faces-Request': 'partial/ajax',
        'X-Requested-With': 'XMLHttpRequest',
        'Origin': 'https://vahan.parivahan.gov.in',
    }

    for attempt in range(2):
        try:
            time.sleep(1)
            r1 = session.get(HOMEPAGE_URL, timeout=15)
            if r1.status_code != 200:
                continue
            viewstate = extract_viewstate(r1.text)
            if not viewstate:
                continue
            checkbox_id = find_checkbox_id(r1.text)

            ajax_headers['Referer'] = HOMEPAGE_URL
            r2 = session.post(HOMEPAGE_BASE, data={
                'javax.faces.partial.ajax': 'true',
                'javax.faces.source': 'fit_c_office_to',
                'javax.faces.partial.execute': 'fit_c_office_to',
                'javax.faces.behavior.event': 'change',
                'javax.faces.partial.event': 'change',
                'homepageformid': 'homepageformid',
                'fit_c_office_to_input': '1',
                'javax.faces.ViewState': viewstate,
            }, headers=ajax_headers, timeout=15)
            viewstate = extract_viewstate_from_ajax(r2.text) or viewstate

            r3 = session.post(HOMEPAGE_BASE, data={
                'javax.faces.partial.ajax': 'true',
                'javax.faces.source': checkbox_id,
                'javax.faces.partial.execute': checkbox_id,
                'javax.faces.partial.render': 'proccedHomeButtonId',
                'javax.faces.behavior.event': 'change',
                'homepageformid': 'homepageformid',
                f'{checkbox_id}_input': 'on',
                'javax.faces.ViewState': viewstate,
            }, headers=ajax_headers, timeout=15)
            viewstate = extract_viewstate_from_ajax(r3.text) or viewstate

            r4 = session.post(HOMEPAGE_BASE, data={
                'javax.faces.partial.ajax': 'true',
                'javax.faces.source': 'proccedHomeButtonId',
                'javax.faces.partial.execute': '@all',
                'proccedHomeButtonId': 'proccedHomeButtonId',
                'homepageformid': 'homepageformid',
                f'{checkbox_id}_input': 'on',
                'javax.faces.ViewState': viewstate,
            }, headers=ajax_headers, timeout=15)
            viewstate = extract_viewstate_from_ajax(r4.text) or viewstate

            dialog_match = re.search(r'id="(j_idt\d+)"[^>]*class="[^"]*ui-button', r4.text)
            dialog_btn = dialog_match.group(1) if dialog_match else "j_idt536"
            r5 = session.post(HOMEPAGE_BASE, data={
                'javax.faces.partial.ajax': 'true',
                'javax.faces.source': dialog_btn,
                'javax.faces.partial.execute': '@all',
                f'{dialog_btn}': dialog_btn,
                'homepageformid': 'homepageformid',
                f'{checkbox_id}_input': 'on',
                'javax.faces.ViewState': viewstate,
            }, headers=ajax_headers, timeout=15)
            viewstate = extract_viewstate_from_ajax(r5.text) or viewstate

            r6 = session.get(LOGIN_URL + "?faces-redirect=true", timeout=15, allow_redirects=True)
            viewstate = extract_viewstate(r6.text)
            if not viewstate:
                continue

            fit_match = re.search(r'id="(j_idt\d+)"[^>]*name="\1"[^>]*type="submit"', r6.text)
            fit_btn = fit_match.group(1) if fit_match else "j_idt506"
            r7 = session.post(LOGIN_URL, data={
                'loginForm': 'loginForm',
                f'{fit_btn}': fit_btn,
                'javax.faces.ViewState': viewstate,
                'fitbalcTest': 'fitbalcTest',
                'pur_cd': '86',
            }, headers={**session.headers, 'Content-Type': 'application/x-www-form-urlencoded', 'Origin': 'https://vahan.parivahan.gov.in', 'Referer': LOGIN_URL + "?faces-redirect=true"}, timeout=15, allow_redirects=True)

            r8 = session.get(FORM_URL, headers={**session.headers, 'Referer': LOGIN_URL + "?faces-redirect=true"}, timeout=15)
            viewstate = extract_viewstate(r8.text)
            if not viewstate:
                continue

            ajax_headers['Referer'] = FORM_URL
            r9 = session.post(FORM_URL, data={
                'javax.faces.partial.ajax': 'true',
                'javax.faces.source': 'balanceFeesFine:validate_dtls',
                'javax.faces.partial.execute': '@all',
                'javax.faces.partial.render': 'balanceFeesFine:auth_panel',
                'balanceFeesFine:validate_dtls': 'balanceFeesFine:validate_dtls',
                'balanceFeesFine': 'balanceFeesFine',
                'balanceFeesFine:tf_reg_no': vehicle_number,
                'balanceFeesFine:tf_chasis_no': chassis_last_5,
                'javax.faces.ViewState': viewstate,
            }, headers=ajax_headers, timeout=15)

            text = r9.text
            for pat in [r'id="balanceFeesFine:tf_mobile"[^>]*value="(\d{10})"',
                        r'value="(\d{10})"[^>]*id="balanceFeesFine:tf_mobile"',
                        r'balanceFeesFine:tf_mobile[^>]*value="(\d{10})"']:
                m = re.search(pat, text, re.DOTALL)
                if m and m.group(1)[0] in '6789':
                    return {"success": True, "mobile_number": m.group(1)}

            fallback = re.findall(r'\b[6-9]\d{9}\b', text)
            if fallback:
                return {"success": True, "mobile_number": fallback[0]}

        except Exception as e:
            print(f"[-] Parivahan attempt {attempt+1} failed: {e}")
        if attempt == 0:
            time.sleep(3)

    return {"success": False, "error": "Mobile number extraction failed"}


# ==================== ROUTES ====================

@app.route("/")
def home():
    return jsonify({
        "status": "ok",
        "service": "v2num",
        "vehicle_api": VEHICLE_API_URL or "direct",
        "cache": "mongodb" if MONGODB_URI else "file",
        "token_ready": bool(CURRENT_TOKEN),
        "token_last_error": LAST_TOKEN_ERROR or None,
    })


@app.route("/token")
def token_debug():
    """Diagnostics: verifies the upstream Chola path works from this host."""
    if VEHICLE_API_URL:
        try:
            r = requests.get(f"{VEHICLE_API_URL}/api/token", timeout=60)
            try:
                body = r.json()
            except ValueError:
                body = {"ok": False, "error": f"non-JSON response (HTTP {r.status_code}): {r.text[:120]}"}
            return jsonify({"vehicle_api": body}), (200 if r.status_code == 200 else 502)
        except Exception as e:
            return jsonify({"vehicle_api": {"ok": False, "error": str(e)}}), 502
    try:
        get_valid_token()
        return jsonify({"ok": True, "token_age_seconds": int(time.time() - LAST_TOKEN_FETCH)})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 502


@app.route("/fetch", methods=["GET"])
@app.route("/v2num/vehicle", methods=["GET"])
def fetch_combined_data():
    vehicle_number = request.args.get("vehicle_number") or request.args.get("number") or ""
    vehicle_number = vehicle_number.strip().upper()
    vehicle_number = re.sub(r'[^A-Z0-9]', '', vehicle_number)

    if not vehicle_number or len(vehicle_number) < 6 or len(vehicle_number) > 12:
        return jsonify({"code": 400, "error": "Invalid vehicle number format"}), 400

    cached = get_from_cache(vehicle_number)
    if cached:
        data = cached["data"]
        # older cache entries stored the full payload nested under "data" — unwrap
        if isinstance(data.get("data"), dict) and "result" in data["data"]:
            data = data["data"]
        # normalize to the same shape as a fresh fetch: {code, data:{...}}
        if "result" in data and "data" not in data:
            data = {
                "code": 200,
                "data": {
                    "masterData": data.get("masterData", []),
                    "result": data.get("result", {}),
                    "source": "DB",
                    "parivahan_linked_mobile": data.get("parivahan_linked_mobile", ""),
                },
                "status": 0,
                "txt": "",
            }
        return jsonify({**data, "source": "cache"})

    full_chassis = None
    registry_details = {}
    master_data = []
    engine_success = False
    last_upstream_error = None

    try:
        raw_profile = fetch_vehicle_profile(vehicle_number)

        if raw_profile and 'data' in raw_profile and raw_profile['data']:
            inner_data = raw_profile['data']
            master_data = inner_data.get('cholaMasterData', [])
            if 'result' in inner_data:
                registry_details = inner_data['result']
            elif 'raw_data' in inner_data and inner_data['raw_data'] and 'result' in inner_data['raw_data']:
                registry_details = inner_data['raw_data']['result']
            full_chassis = registry_details.get("chassis", "").replace(" ", "").upper()
            if full_chassis and len(full_chassis) >= 5:
                engine_success = True
            if not engine_success and isinstance(inner_data, dict):
                msg = inner_data.get('txt')
                if msg and 'too many' not in msg.lower():
                    last_upstream_error = msg
    except Exception as e:
        print(f"[-] vehicle_api lookup failed: {e}")
        last_upstream_error = str(e)

    if not engine_success:
        try:
            resp = requests.get(CHASSIS_API_URL.format(vehicle_number), timeout=20)
            if resp.status_code == 200:
                full_chassis = resp.json().get("chassis", "").replace(" ", "").upper()
            else:
                print(f"[-] Fallback worker HTTP {resp.status_code}")
        except Exception as e:
            print(f"[-] Fallback error: {e}")

    if not full_chassis or len(full_chassis) < 5:
        msg = last_upstream_error or "Vehicle details could not be resolved from upstream providers"
        return jsonify({"code": 404, "error": msg}), 404

    chassis_last_5 = full_chassis[-5:]
    try:
        mobile_profile = fetch_mobile_number(vehicle_number, chassis_last_5)
        linked_phone = mobile_profile["mobile_number"] if mobile_profile.get("success") else "NOT_FOUND"
    except Exception as e:
        print(f"[-] Parivahan mobile lookup failed: {e}")
        linked_phone = "NOT_FOUND"

    if 'mappings' in registry_details and isinstance(registry_details['mappings'], dict):
        if 'signzyID' in registry_details['mappings']:
            registry_details['mappings']['signzyID'] = 'MASTER_PROVIDER'

    cleaned_master_data = []
    for block in master_data:
        cleaned_block = {}
        for key, val in block.items():
            new_key = key.replace('chola', 'master').replace('sigzy', 'master').replace('signzy', 'master')
            cleaned_block[new_key] = val
        cleaned_master_data.append(cleaned_block)

    payload = {
        "code": 200,
        "data": {
            "masterData": cleaned_master_data,
            "result": registry_details,
            "source": "DB",
            "parivahan_linked_mobile": linked_phone
        },
        "status": 0,
        "txt": ""
    }
    save_to_cache(vehicle_number, payload)
    return jsonify(payload)


# ==================== LOCAL RUN ====================

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=False)
