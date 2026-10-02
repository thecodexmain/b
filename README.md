# Shopify Checkout & Card Gateway API (Railway Hostable)

A production-ready, asynchronous REST API built with **FastAPI** to execute Shopify GraphQL checkout flows and test payment gateway responses. Fully pre-configured for **Railway** deployment.

---

## 🚀 Features

- **Ready for Railway**: Includes `Procfile`, `railway.json`, `Dockerfile`, and `requirements.txt`.
- **FastAPI Powered**: Fast, auto-threaded execution of external requests so concurrent requests do not block the event loop.
- **Auto OpenAPI / Swagger Docs**: Interactive API documentation automatically available at `/docs`.
- **Built-in Web Dashboard**: Sleek dark-mode tester interface at `/` for quick browser testing.
- **Multiple Input Formats**: Accepts formatted card string (`cc|mm|yy|cvv` with `/`, `:`, `|`, or space delimiters) or separate JSON fields.
- **Proxy Support**: Optional residential/datacenter proxy routing (`http://user:pass@host:port`) to bypass Shopify datacenter rate limits.
- **Optional API Key Auth**: Secure your API on Railway using the `API_KEY` environment variable.

---

## 📁 Project Structure

```
├── main.py            # FastAPI REST API, endpoints, models & web dashboard
├── shopify_engine.py  # Core Shopify GraphQL checkout & token extraction engine
├── requirements.txt   # Python dependencies
├── Procfile           # Railway / Heroku process declaration
├── railway.json       # Railway deployment & health check configuration
├── Dockerfile         # Docker container definition (alternative Railway builder)
├── .dockerignore      # Docker ignore rules
└── .gitignore         # Git ignore rules
```

---

## 🛠️ Deploying to Railway

### Method 1: Deploy via GitHub (Recommended)
1. Push this folder to a GitHub repository:
   ```bash
   git init
   git add .
   git commit -m "Initial commit - Shopify Checkout API"
   git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO.git
   git push -u origin main
   ```
2. Go to [Railway.app](https://railway.app/) and click **New Project** > **Deploy from GitHub repo**.
3. Select your repository. Railway will automatically detect `railway.json` and `Procfile` / `requirements.txt`.
4. In Railway dashboard, go to **Settings** > **Networking** > click **Generate Domain** to get your public URL (e.g. `https://your-app.up.railway.app`).

### Method 2: Deploy using Railway CLI
```bash
npm install -g @railway/cli
railway login
railway init
railway up
```

---

## ⚙️ Environment Variables (Optional)

You can set these in the Railway dashboard under **Variables**:

| Variable | Default | Description |
|---|---|---|
| `PORT` | `8000` | Injected automatically by Railway |
| `DEFAULT_STORE_DOMAIN` | `https://us.mercihandy.com` | Default Shopify store if none is specified in request |
| `DEFAULT_PROXY` | `None` | Default HTTP/HTTPS proxy for all outbound requests |
| `API_KEY` | `None` | If set, requires `X-API-Key` header or `?key=` query param |

---

## 📡 API Endpoints

### 1. Interactive Web Dashboard
- **URL**: `GET /`
- **Description**: Open in any browser for a UI to test card checkouts in real-time.

### 2. Interactive Swagger Docs
- **URL**: `GET /docs`
- **Description**: Full OpenAPI specification and interactive test runner.

### 3. Health Check
- **URL**: `GET /health`
- **Response**:
  ```json
  {
    "status": "healthy",
    "timestamp": 1711234567.89,
    "default_domain": "https://us.mercihandy.com",
    "proxy_configured": false
  }
  ```

---

### 4. POST `/api/checkout` or POST `/api/check` (Main Endpoint)

Send a JSON payload with card details, optional site, and optional proxy in any format.

#### Request Body (Option A - Using Site & Proxy in Any Format):
```json
{
  "site": "so.com",
  "proxy": "1.2.3.4:8080:username:password",
  "cc": "5456150015507529|03|2028|166"
}
```

#### Request Body (Option B - Split Fields & Custom Address):
```json
{
  "site": "https://us.mercihandy.com",
  "proxy": "username:password@1.2.3.4:8080",
  "card_number": "5456 1500 1550 7529",
  "card_month": 3,
  "card_year": 2028,
  "cvv": "166",
  "card_name": "John Doe",
  "address": {
    "first_name": "John",
    "last_name": "Doe",
    "address1": "742 Evergreen Terrace",
    "city": "Springfield",
    "country_code": "US",
    "zone_code": "OR",
    "postal_code": "97477",
    "phone": "+15551234567"
  }
}
```

---

### 5. GET `/api/check` or GET `/api/checkout` (Query Parameter API)

Designed for easy integration with Telegram bots, discord bots, cURL, or browser requests.

Supports `site` (or `domain`), `proxy` in any format, and `cc`.

#### Example 1: With Custom Site and Proxy (`ip:port:user:pass`)
```bash
curl -X GET "https://your-railway-url.up.railway.app/api/check?site=so.com&proxy=1.2.3.4:8080:usr:pwd&cc=5456150015507529|03|2028|166"
```

#### Example 2: With Standard URL Proxy
```bash
curl -X GET "https://your-railway-url.up.railway.app/api/check?site=us.mercihandy.com&proxy=http://usr:pwd@1.2.3.4:8080&cc=5456150015507529|03|2028|166"
```

#### Supported Proxy Formats:
- `ip:port:user:pass` (e.g., `1.2.3.4:8080:usr:pwd`)
- `user:pass:ip:port` (e.g., `usr:pwd:1.2.3.4:8080`)
- `user:pass@ip:port` (e.g., `usr:pwd@1.2.3.4:8080`)
- `ip:port` (e.g., `1.2.3.4:8080`)
- Standard URLs (e.g., `http://usr:pwd@1.2.3.4:8080`, `socks5://usr:pwd@1.2.3.4:8080`)

---

## 💻 Running Locally

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
2. Start the local server:
   ```bash
   python main.py
   ```
   Or with hot-reload:
   ```bash
   uvicorn main:app --reload --port 8000
   ```
3. Open `http://localhost:8000` in your browser.
