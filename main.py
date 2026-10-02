import os
import time
from typing import Optional, Dict, Any
from fastapi import FastAPI, HTTPException, Query, Header, Depends, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field
import uvicorn

from shopify_engine import run_shopify_checkout, parse_card_string, format_proxy

app = FastAPI(
    title="Shopify Checkout & Card Gateway API",
    description="Railway-ready high-performance REST API for Shopify checkout and GraphQL payment testing with flexible proxy and site handling.",
    version="1.1.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# Enable CORS for external web clients
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DEFAULT_STORE_DOMAIN = os.environ.get("DEFAULT_STORE_DOMAIN", "https://us.mercihandy.com")
DEFAULT_PROXY = os.environ.get("DEFAULT_PROXY", None)
API_SECRET_KEY = os.environ.get("API_KEY", None)

def verify_api_key(
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    api_key_query: Optional[str] = Query(None, alias="key")
):
    """
    If API_KEY environment variable is set on Railway, enforce authentication.
    Otherwise, allow public access.
    """
    if not API_SECRET_KEY:
        return True
    key = x_api_key or api_key_query
    if not key or key != API_SECRET_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API Key. Pass 'X-API-Key' in headers or '?key=' in query."
        )
    return True


class AddressModel(BaseModel):
    first_name: Optional[str] = "Python"
    last_name: Optional[str] = "Shelby"
    address1: Optional[str] = "St 82"
    address2: Optional[str] = ""
    city: Optional[str] = "Ny"
    country_code: Optional[str] = "US"
    zone_code: Optional[str] = "NY"
    postal_code: Optional[str] = "10010"
    phone: Optional[str] = "+12125551212"


class CheckoutRequest(BaseModel):
    site: Optional[str] = Field(default=None, description="Shopify store domain / URL (e.g., site=so.com or https://so.com)")
    domain: Optional[str] = Field(default=None, description="Alias for site (e.g., domain=us.mercihandy.com)")
    cc: Optional[str] = Field(default=None, description="Card string formatted as 'number|month|year|cvv'")
    card_number: Optional[str] = Field(default=None, description="Credit card number")
    card_month: Optional[int] = Field(default=None, description="Expiry month (1-12)")
    card_year: Optional[int] = Field(default=None, description="Expiry year (2 or 4 digits, e.g. 28 or 2028)")
    cvv: Optional[str] = Field(default=None, description="Card CVV/CVC code")
    card_name: Optional[str] = Field(default=None, description="Cardholder name")
    address: Optional[AddressModel] = Field(default=None, description="Billing/shipping address")
    email: Optional[str] = Field(default=None, description="Customer email (auto-generated if omitted)")
    variant_id: Optional[int] = Field(default=None, description="Optional Shopify product variant ID to checkout")
    proxy: Optional[str] = Field(default=None, description="Proxy in any format (e.g. ip:port:user:pass, user:pass:ip:port, user:pass@ip:port, or ip:port)")
    timeout: Optional[int] = Field(default=25, description="Timeout in seconds for external requests")


def _execute_checkout_from_request(req: CheckoutRequest):
    card_num = req.card_number
    card_m = req.card_month
    card_y = req.card_year
    card_cvv = req.cvv

    if req.cc:
        try:
            parsed_num, parsed_m, parsed_y, parsed_cvv = parse_card_string(req.cc)
            card_num = card_num or parsed_num
            card_m = card_m or parsed_m
            card_y = card_y or parsed_y
            card_cvv = card_cvv or parsed_cvv
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid 'cc' format: {str(e)}")

    if not card_num or not card_m or not card_y or not card_cvv:
        raise HTTPException(
            status_code=400,
            detail="Missing card credentials. Provide either 'cc' formatted string or individual card fields."
        )

    store_domain = req.site or req.domain or DEFAULT_STORE_DOMAIN
    used_proxy = req.proxy or DEFAULT_PROXY
    addr_dict = req.address.model_dump() if req.address else None

    result = run_shopify_checkout(
        domain=store_domain,
        card_number=card_num,
        card_month=card_m,
        card_year=card_y,
        cvv=card_cvv,
        card_name=req.card_name,
        address=addr_dict,
        email=req.email,
        variant_id=req.variant_id,
        proxy=used_proxy,
        timeout=req.timeout or 25
    )

    return result


def _execute_checkout_from_query(
    cc: str,
    site: Optional[str],
    domain: Optional[str],
    proxy: Optional[str],
    variant_id: Optional[int]
):
    try:
        card_num, card_m, card_y, card_cvv = parse_card_string(cc)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid card format: {str(e)}")

    store_domain = site or domain or DEFAULT_STORE_DOMAIN
    used_proxy = proxy or DEFAULT_PROXY

    result = run_shopify_checkout(
        domain=store_domain,
        card_number=card_num,
        card_month=card_m,
        card_year=card_y,
        cvv=card_cvv,
        variant_id=variant_id,
        proxy=used_proxy
    )

    return result


@app.get("/health", tags=["System"])
def health_check():
    """Railway health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": time.time(),
        "default_domain": DEFAULT_STORE_DOMAIN,
        "default_proxy_configured": bool(DEFAULT_PROXY)
    }


# POST Endpoints (accepts site, proxy, cc in JSON body)
@app.post("/api/checkout", tags=["Shopify Checkout"])
def api_checkout_post(req: CheckoutRequest, authenticated: bool = Depends(verify_api_key)):
    """
    Main checkout execution endpoint via JSON POST.
    Accepts:
      - site / domain (e.g. 'so.com' or 'https://us.mercihandy.com')
      - proxy (any format: 'ip:port:user:pass', 'user:pass:ip:port', 'user:pass@ip:port', 'ip:port', or 'http/socks5')
      - cc ('number|mm|yyyy|cvv') or individual card fields
    """
    return _execute_checkout_from_request(req)


@app.post("/api/check", tags=["Shopify Checkout"])
def api_check_post(req: CheckoutRequest, authenticated: bool = Depends(verify_api_key)):
    """Alias for POST /api/checkout"""
    return _execute_checkout_from_request(req)


# GET Endpoints (accepts ?site=so.com&proxy=...&cc=...)
@app.get("/api/check", tags=["Shopify Checkout"])
def api_check_get(
    cc: str = Query(..., description="Card details formatted as 'number|month|year|cvv'"),
    site: Optional[str] = Query(None, description="Shopify store site/domain (e.g. site=so.com)"),
    domain: Optional[str] = Query(None, description="Alias for site"),
    proxy: Optional[str] = Query(None, description="Proxy in any format (e.g. ip:port:user:pass, user:pass:ip:port, user:pass@ip:port, or ip:port)"),
    variant_id: Optional[int] = Query(None, description="Shopify variant ID (optional)"),
    authenticated: bool = Depends(verify_api_key)
):
    """
    Convenient GET endpoint for Telegram bots, webhooks, or browser testing.
    Example: `/api/check?site=so.com&proxy=1.2.3.4:8080:usr:pwd&cc=5456150015507529|03|2028|166`
    """
    return _execute_checkout_from_query(cc, site, domain, proxy, variant_id)


@app.get("/api/checkout", tags=["Shopify Checkout"])
def api_checkout_get(
    cc: str = Query(..., description="Card details formatted as 'number|month|year|cvv'"),
    site: Optional[str] = Query(None, description="Shopify store site/domain (e.g. site=so.com)"),
    domain: Optional[str] = Query(None, description="Alias for site"),
    proxy: Optional[str] = Query(None, description="Proxy in any format (e.g. ip:port:user:pass, user:pass@ip:port, or ip:port)"),
    variant_id: Optional[int] = Query(None, description="Shopify variant ID (optional)"),
    authenticated: bool = Depends(verify_api_key)
):
    """Alias for GET /api/check"""
    return _execute_checkout_from_query(cc, site, domain, proxy, variant_id)


# Root alias endpoints
@app.post("/checkout", tags=["Shopify Checkout"], include_in_schema=False)
def checkout_post_alias(req: CheckoutRequest, authenticated: bool = Depends(verify_api_key)):
    return _execute_checkout_from_request(req)

@app.post("/check", tags=["Shopify Checkout"], include_in_schema=False)
def check_post_alias(req: CheckoutRequest, authenticated: bool = Depends(verify_api_key)):
    return _execute_checkout_from_request(req)

@app.get("/checkout", tags=["Shopify Checkout"], include_in_schema=False)
def checkout_get_alias(
    cc: str = Query(...),
    site: Optional[str] = Query(None),
    domain: Optional[str] = Query(None),
    proxy: Optional[str] = Query(None),
    variant_id: Optional[int] = Query(None),
    authenticated: bool = Depends(verify_api_key)
):
    return _execute_checkout_from_query(cc, site, domain, proxy, variant_id)

@app.get("/check", tags=["Shopify Checkout"], include_in_schema=False)
def check_get_alias(
    cc: str = Query(...),
    site: Optional[str] = Query(None),
    domain: Optional[str] = Query(None),
    proxy: Optional[str] = Query(None),
    variant_id: Optional[int] = Query(None),
    authenticated: bool = Depends(verify_api_key)
):
    return _execute_checkout_from_query(cc, site, domain, proxy, variant_id)


@app.get("/", response_class=HTMLResponse, tags=["Dashboard"])
def web_dashboard():
    """
    Sleek interactive web tester UI for easy browser testing.
    """
    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Shopify Checkout API Dashboard</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
  <style>
    :root {{
      --bg: #090d16;
      --card-bg: rgba(18, 24, 38, 0.75);
      --card-border: rgba(255, 255, 255, 0.08);
      --accent: #6366f1;
      --accent-glow: rgba(99, 102, 241, 0.35);
      --text: #f3f4f6;
      --text-muted: #94a3b8;
      --success: #10b981;
      --danger: #ef4444;
      --warning: #f59e0b;
    }}
    * {{
      box-sizing: border-box;
      margin: 0;
      padding: 0;
    }}
    body {{
      font-family: 'Plus Jakarta Sans', sans-serif;
      background-color: var(--bg);
      color: var(--text);
      min-height: 100vh;
      display: flex;
      flex-direction: column;
      align-items: center;
      padding: 40px 20px;
      background-image: 
        radial-gradient(circle at 15% 15%, rgba(99, 102, 241, 0.15) 0%, transparent 40%),
        radial-gradient(circle at 85% 85%, rgba(16, 185, 129, 0.12) 0%, transparent 40%);
    }}
    .container {{
      max-width: 960px;
      width: 100%;
    }}
    header {{
      text-align: center;
      margin-bottom: 30px;
    }}
    .badge {{
      display: inline-block;
      padding: 6px 14px;
      font-size: 0.75rem;
      font-weight: 700;
      letter-spacing: 0.05em;
      text-transform: uppercase;
      background: rgba(99, 102, 241, 0.15);
      border: 1px solid rgba(99, 102, 241, 0.4);
      color: #818cf8;
      border-radius: 9999px;
      margin-bottom: 12px;
    }}
    h1 {{
      font-size: 2.3rem;
      font-weight: 800;
      letter-spacing: -0.03em;
      background: linear-gradient(135deg, #ffffff 0%, #cbd5e1 100%);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
      margin-bottom: 8px;
    }}
    p.subtitle {{
      color: var(--text-muted);
      font-size: 0.95rem;
    }}
    .hint-bar {{
      margin-top: 14px;
      padding: 10px 16px;
      background: rgba(99, 102, 241, 0.08);
      border: 1px solid rgba(99, 102, 241, 0.2);
      border-radius: 10px;
      font-family: 'JetBrains Mono', monospace;
      font-size: 0.8rem;
      color: #cbd5e1;
      text-align: center;
    }}
    .hint-bar span {{
      color: #818cf8;
      font-weight: 600;
    }}
    .grid {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 24px;
      margin-top: 24px;
    }}
    @media (max-width: 768px) {{
      .grid {{
        grid-template-columns: 1fr;
      }}
    }}
    .card {{
      background: var(--card-bg);
      backdrop-filter: blur(16px);
      -webkit-backdrop-filter: blur(16px);
      border: 1px solid var(--card-border);
      border-radius: 20px;
      padding: 26px;
      box-shadow: 0 20px 40px rgba(0, 0, 0, 0.4);
    }}
    .form-group {{
      margin-bottom: 16px;
    }}
    label {{
      display: block;
      font-size: 0.78rem;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      color: var(--text-muted);
      margin-bottom: 6px;
    }}
    .label-hint {{
      text-transform: none;
      font-weight: 400;
      color: #64748b;
      font-size: 0.72rem;
    }}
    input, select, textarea {{
      width: 100%;
      padding: 11px 14px;
      background: rgba(10, 15, 26, 0.8);
      border: 1px solid rgba(255, 255, 255, 0.1);
      border-radius: 10px;
      color: #fff;
      font-size: 0.9rem;
      font-family: inherit;
      outline: none;
      transition: all 0.2s;
    }}
    input:focus, textarea:focus {{
      border-color: var(--accent);
      box-shadow: 0 0 0 3px var(--accent-glow);
    }}
    .btn {{
      width: 100%;
      padding: 13px;
      background: linear-gradient(135deg, #6366f1 0%, #4f46e5 100%);
      border: none;
      border-radius: 12px;
      color: #fff;
      font-weight: 700;
      font-size: 0.95rem;
      cursor: pointer;
      box-shadow: 0 8px 20px rgba(99, 102, 241, 0.4);
      transition: all 0.2s;
      display: flex;
      justify-content: center;
      align-items: center;
      gap: 8px;
      margin-top: 10px;
    }}
    .btn:hover {{
      transform: translateY(-2px);
      box-shadow: 0 12px 24px rgba(99, 102, 241, 0.5);
    }}
    .btn:disabled {{
      opacity: 0.6;
      cursor: not-allowed;
      transform: none;
    }}
    pre {{
      font-family: 'JetBrains Mono', monospace;
      font-size: 0.82rem;
      background: rgba(6, 9, 16, 0.9);
      border: 1px solid rgba(255, 255, 255, 0.05);
      border-radius: 12px;
      padding: 16px;
      color: #e2e8f0;
      overflow-x: auto;
      max-height: 480px;
      min-height: 380px;
      white-space: pre-wrap;
    }}
    .links {{
      margin-top: 24px;
      display: flex;
      gap: 20px;
      justify-content: center;
    }}
    .links a {{
      color: #818cf8;
      font-size: 0.85rem;
      text-decoration: none;
      font-weight: 600;
    }}
    .links a:hover {{
      text-decoration: underline;
    }}
  </style>
</head>
<body>
  <div class="container">
    <header>
      <div class="badge">Railway Ready API v1.1</div>
      <h1>Shopify Checkout Gateway</h1>
      <p class="subtitle">Complete GraphQL checkout flow &amp; payment verification</p>
      <div class="hint-bar">
        API Query: <span>/api/check?site=so.com&amp;proxy=ip:port:user:pass&amp;cc=number|mm|yy|cvv</span>
      </div>
    </header>

    <div class="grid">
      <div class="card">
        <form id="checkForm">
          <div class="form-group">
            <label for="site">Site / Store URL <span class="label-hint">(e.g. so.com or https://us.mercihandy.com)</span></label>
            <input type="text" id="site" value="{DEFAULT_STORE_DOMAIN}" placeholder="e.g. so.com or https://store.myshopify.com" required>
          </div>
          <div class="form-group">
            <label for="proxy">Proxy <span class="label-hint">(Any format: ip:port:user:pass, user:pass@ip:port, or ip:port)</span></label>
            <input type="text" id="proxy" placeholder="1.2.3.4:8080:username:password">
          </div>
          <div class="form-group">
            <label for="cc">Card String <span class="label-hint">(cc|mm|yy|cvv)</span></label>
            <input type="text" id="cc" value="5456 1500 1550 7529|03|2028|166" placeholder="4111111111111111|12|28|123" required>
          </div>
          <div class="form-group">
            <label for="variantId">Product Variant ID <span class="label-hint">(Optional, auto-cheapest if empty)</span></label>
            <input type="text" id="variantId" placeholder="Leave empty for cheapest item">
          </div>
          <button type="submit" class="btn" id="submitBtn">
            <span id="btnText">Execute Checkout Test</span>
          </button>
        </form>
      </div>

      <div class="card">
        <label>Response Output</label>
        <pre id="responseJson">// Click "Execute Checkout Test" to run the pipeline</pre>
      </div>
    </div>

    <div class="links">
      <a href="/docs" target="_blank">Interactive Swagger OpenAPI Docs</a>
      <a href="/health" target="_blank">Health Check Endpoint</a>
    </div>
  </div>

  <script>
    const form = document.getElementById('checkForm');
    const submitBtn = document.getElementById('submitBtn');
    const btnText = document.getElementById('btnText');
    const output = document.getElementById('responseJson');

    form.addEventListener('submit', async (e) => {{
      e.preventDefault();
      submitBtn.disabled = true;
      btnText.textContent = 'Processing Checkout...';
      output.textContent = '// Sending request to Shopify GraphQL checkout pipeline...';

      const payload = {{
        site: document.getElementById('site').value.trim(),
        proxy: document.getElementById('proxy').value.trim() || null,
        cc: document.getElementById('cc').value.trim(),
        variant_id: document.getElementById('variantId').value.trim() || null
      }};

      try {{
        const res = await fetch('/api/checkout', {{
          method: 'POST',
          headers: {{ 'Content-Type': 'application/json' }},
          body: JSON.stringify(payload)
        }});
        const data = await res.json();
        output.textContent = JSON.stringify(data, null, 2);
      }} catch (err) {{
        output.textContent = JSON.stringify({{ error: err.message }}, null, 2);
      }} finally {{
        submitBtn.disabled = false;
        btnText.textContent = 'Execute Checkout Test';
      }}
    }});
  </script>
</body>
</html>"""
    return HTMLResponse(content=html_content)


if __name__ == "__main__":
    # In Railway, PORT is provided as an environment variable (e.g., $PORT)
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
