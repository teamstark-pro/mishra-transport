"""Parivahan (Vahan) linked-mobile lookup for the Vercel function.

Vahan (vahan.parivahan.gov.in) is unreachable or slow from US datacenter IPs
(the Render backend used to burn its timeouts here), so the lookup runs from
the Mumbai region alongside the Chola relay.

The lookup is best-effort: any failure returns {"success": False, ...} and the
caller degrades the mobile number to NOT_FOUND. fetch_mobile_number is wrapped
in a daemon thread with a hard cap so a stalled Vahan connection can never
consume the whole /api/fetch function budget (maxDuration 60s).
"""
import re
import threading
import time

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

HOMEPAGE_URL = "https://vahan.parivahan.gov.in/vahanservice/vahan/ui/statevalidation/homepage.xhtml?statecd=Mzc2MzM2MzAzNjY0MzIzODM3NjIzNjY0MzY2MjM3NDQ0Yw=="
HOMEPAGE_BASE = "https://vahan.parivahan.gov.in/vahanservice/vahan/ui/statevalidation/homepage.xhtml"
LOGIN_URL = "https://vahan.parivahan.gov.in/vahanservice/vahan/ui/usermgmt/login.xhtml"
FORM_URL = "https://vahan.parivahan.gov.in/vahanservice/vahan/ui/balanceservice/form_reschedule_fitness.xhtml"

CALL_TIMEOUT = 10


def _create_session():
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


def _extract_viewstate(html):
    soup = BeautifulSoup(html, 'html.parser')
    vs = soup.find('input', {'name': 'javax.faces.ViewState'})
    return vs.get('value') if vs else None


def _extract_viewstate_from_ajax(text):
    m = re.search(r'<update id="j_id1:javax.faces.ViewState:0"><!\[CDATA\[(.*?)\]\]></update>', text)
    return m.group(1) if m else None


def _find_checkbox_id(html):
    m = re.search(r'<div[^>]*id="(j_idt\d+)"[^>]*class="[^"]*ui-chkbox', html)
    if not m:
        m = re.search(r'PrimeFaces\.cw\("SelectBooleanCheckbox"[^}]*id:"(j_idt\d+)"', html)
    return m.group(1) if m else "j_idt193"


def _lookup(vehicle_number, chassis_last_5):
    session = _create_session()
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
            r1 = session.get(HOMEPAGE_URL, timeout=CALL_TIMEOUT)
            if r1.status_code != 200:
                continue
            viewstate = _extract_viewstate(r1.text)
            if not viewstate:
                continue
            checkbox_id = _find_checkbox_id(r1.text)

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
            }, headers=ajax_headers, timeout=CALL_TIMEOUT)
            viewstate = _extract_viewstate_from_ajax(r2.text) or viewstate

            r3 = session.post(HOMEPAGE_BASE, data={
                'javax.faces.partial.ajax': 'true',
                'javax.faces.source': checkbox_id,
                'javax.faces.partial.execute': checkbox_id,
                'javax.faces.partial.render': 'proccedHomeButtonId',
                'javax.faces.behavior.event': 'change',
                'homepageformid': 'homepageformid',
                f'{checkbox_id}_input': 'on',
                'javax.faces.ViewState': viewstate,
            }, headers=ajax_headers, timeout=CALL_TIMEOUT)
            viewstate = _extract_viewstate_from_ajax(r3.text) or viewstate

            r4 = session.post(HOMEPAGE_BASE, data={
                'javax.faces.partial.ajax': 'true',
                'javax.faces.source': 'proccedHomeButtonId',
                'javax.faces.partial.execute': '@all',
                'proccedHomeButtonId': 'proccedHomeButtonId',
                'homepageformid': 'homepageformid',
                f'{checkbox_id}_input': 'on',
                'javax.faces.ViewState': viewstate,
            }, headers=ajax_headers, timeout=CALL_TIMEOUT)
            viewstate = _extract_viewstate_from_ajax(r4.text) or viewstate

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
            }, headers=ajax_headers, timeout=CALL_TIMEOUT)
            viewstate = _extract_viewstate_from_ajax(r5.text) or viewstate

            r6 = session.get(LOGIN_URL + "?faces-redirect=true", timeout=CALL_TIMEOUT, allow_redirects=True)
            viewstate = _extract_viewstate(r6.text)
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
            }, headers={**session.headers, 'Content-Type': 'application/x-www-form-urlencoded', 'Origin': 'https://vahan.parivahan.gov.in', 'Referer': LOGIN_URL + "?faces-redirect=true"}, timeout=CALL_TIMEOUT, allow_redirects=True)

            r8 = session.get(FORM_URL, headers={**session.headers, 'Referer': LOGIN_URL + "?faces-redirect=true"}, timeout=CALL_TIMEOUT)
            viewstate = _extract_viewstate(r8.text)
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
            }, headers=ajax_headers, timeout=CALL_TIMEOUT)

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


def fetch_mobile_number(vehicle_number, chassis_last_5, timeout_seconds=35):
    """Hard-capped wrapper: the caller never waits past timeout_seconds."""
    result = {}

    def run():
        try:
            result["value"] = _lookup(vehicle_number, chassis_last_5)
        except Exception as e:
            result["value"] = {"success": False, "error": str(e)}

    t = threading.Thread(target=run, daemon=True)
    t.start()
    t.join(timeout_seconds)
    if "value" not in result:
        return {"success": False, "error": f"parivahan lookup exceeded {timeout_seconds}s"}
    return result["value"]
