# ⚡ Multi-Site Stripe Auth / SetupIntent API Gateway

High-Performance 0$ Stripe Authorization and Card Verification API built with Python, Flask, and Async HTTPX.

## 🌟 Supported Gateways
1. **Bombouche** (`bombouche.com`)
2. **Pathos Ceramiche** (`pathosceramiche.com`)
3. **Freestone Shooting Complex** (`freestoneshootingcomplex.com`)
4. **Odin Water Polo** (`odinwaterpolo.com`)
5. **Noble Rot Newsstand** (`noble-rot.newsstand.co.uk`)

---

## 📡 API Endpoints

### 1. Card Verification (Stripe Auth)
`GET /check?cc=NUM|MM|YY|CVV`
`GET /stripe?cc=NUM|MM|YY|CVV`
`GET /auth?cc=NUM|MM|YY|CVV`

**Optional Parameters:**
- `site`: Select specific gateway (`bombouche`, `pathos`, `freestone`, `odin`, `noblerot` or `1`..`5`)
- `proxy`: Custom proxy (`ip:port:user:pass` or `http://...`)
- `format`: `json` (default) or `text`

#### Example Requests:
```bash
# Auto-Rotation mode
curl "https://<your-render-url>/check?cc=4000001234567890|12|28|123"

# Specific Gateway mode
curl "https://<your-render-url>/check?cc=4000001234567890|12|28|123&site=bombouche"

# Plaintext response
curl "https://<your-render-url>/check?cc=4000001234567890|12|28|123&format=text"
```

---

### 2. Configured Sites Status
`GET /sites`

Returns active gateways list and current live configurations.

---

### 3. Health Check
`GET /health`
