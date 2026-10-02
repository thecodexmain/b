import re
import json
import html
import random
import string
import urllib.parse
import time
import uuid
import secrets
from typing import List, Optional, Tuple, Dict, Any
import requests

FALLBACK_BUILD_ID = "9d599a0bc38671e85522f332198ada49b9bc8a9f"
FALLBACK_PROPOSAL_ID = "cd1c759d6c8ca754f501a6b4e91684ad8ba1553095acc86b54bb3aa840587dae"
FALLBACK_SUBMIT_ID = "51ea6a6dd873dd6e77892cb78b9f9574626169f1f664e3914f21b280f80ac4d9"
FALLBACK_POLL_ID = "658bb809ab07c0463243990c0c79fd8f2eacb112e7ea5c8f2cef6bc7b109127a"

KNOWN_BUILD_OPERATIONS: Dict[str, Dict[str, str]] = {
    "9d599a0bc38671e85522f332198ada49b9bc8a9f": {
        "proposal_id": "cd1c759d6c8ca754f501a6b4e91684ad8ba1553095acc86b54bb3aa840587dae",
        "submit_id": "51ea6a6dd873dd6e77892cb78b9f9574626169f1f664e3914f21b280f80ac4d9",
        "poll_id": "658bb809ab07c0463243990c0c79fd8f2eacb112e7ea5c8f2cef6bc7b109127a"
    }
}

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36"
SEC_CH_UA = '"Chromium";v="142", "Google Chrome";v="142", "Not_A Brand";v="99"'

def normalize_url(url: str) -> str:
    if not url:
        return ""
    url = str(url).strip().strip("'\"")
    url = re.sub(r'^[@\s]+', '', url)
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url
    return url.rstrip('/')

def format_proxy(proxy_str: Optional[str]) -> Optional[str]:
    """
    Normalizes any proxy format into a standard URL for requests:
      - ip:port:user:pass      -> http://user:pass@ip:port
      - user:pass:ip:port      -> http://user:pass@ip:port
      - user:pass@ip:port      -> http://user:pass@ip:port
      - ip:port                -> http://ip:port
      - http://... / socks5:// -> preserved
    """
    if not proxy_str:
        return None
    
    proxy_str = str(proxy_str).strip().strip("'\"")
    if not proxy_str:
        return None

    scheme = "http"
    if "://" in proxy_str:
        scheme, proxy_str = proxy_str.split("://", 1)

    if "@" in proxy_str:
        return f"{scheme}://{proxy_str}"

    parts = proxy_str.split(":")
    if len(parts) == 4:
        # Check if parts[1] is numeric port (ip:port:user:pass)
        if parts[1].isdigit():
            ip, port, user, password = parts[0], parts[1], parts[2], parts[3]
            return f"{scheme}://{user}:{password}@{ip}:{port}"
        # Check if parts[3] is numeric port (user:pass:ip:port)
        elif parts[3].isdigit():
            user, password, ip, port = parts[0], parts[1], parts[2], parts[3]
            return f"{scheme}://{user}:{password}@{ip}:{port}"
        else:
            return f"{scheme}://{parts[2]}:{parts[3]}@{parts[0]}:{parts[1]}"
    elif len(parts) == 2:
        return f"{scheme}://{parts[0]}:{parts[1]}"
    elif len(parts) == 3 and parts[1].isdigit():
        return f"{scheme}://{parts[0]}:{parts[1]}"

    return f"{scheme}://{proxy_str}"

def extract_checkout_token(url: str, html_text: str = "") -> str:
    token_patterns = [
        r'/checkouts/cn/([^/?#]+)',
        r'/checkouts/([^/?#]+)',
        r'/cart/c/([^/?#]+)',
        r'checkouts/cn/([a-zA-Z0-9_-]+)',
        r'checkout_token=([a-zA-Z0-9_-]+)',
        r'key=([a-zA-Z0-9_-]+)',
    ]
    for p in token_patterns:
        m = re.search(p, url)
        if m:
            val = m.group(1)
            if val and len(val) > 4 and val not in ('cn', 'cart', 'checkouts'):
                return val
    if html_text:
        m = re.search(r'name=["\']serialized-checkoutToken["\']\s+content=["\']([^"\']+)["\']', html_text)
        if m:
            return html.unescape(m.group(1)).strip('"\'')
        m2 = re.search(r'"checkoutToken"\s*:\s*"([^"]+)"', html_text)
        if m2:
            return m2.group(1)
    return ""

def extract_session_token(html_text: str) -> str:
    if not html_text:
        return ""
    # 1. Raw meta tag search (preserves &quot; entity before outer quote stripping)
    raw_meta = re.findall(r'<meta[^>]+name=["\'](?:serialized-sessionToken|serialized-checkoutSessionIdentifier)["\'][^>]+content=["\']([^"\']+)["\']', html_text, re.I)
    raw_meta += re.findall(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+name=["\'](?:serialized-sessionToken|serialized-checkoutSessionIdentifier)["\']', html_text, re.I)
    for rm in raw_meta:
        cleaned = html.unescape(rm).strip('"\'&quot;')
        if cleaned and len(cleaned) > 8:
            return cleaned

    unescaped = html.unescape(html_text)
    patterns = [
        r'(?:serialized-sessionToken|sessionToken|checkoutSessionToken|checkoutSessionIdentifier)["\']?\s*[:=]\s*["\']?([a-zA-Z0-9_\-\.]+)',
        r'"sessionToken"\s*:\s*"([^"]+)"',
        r'"checkoutSessionIdentifier"\s*:\s*"([^"]+)"',
        r'"checkoutSessionToken"\s*:\s*"([^"]+)"',
        r'sessionToken["\']\s*:\s*["\']([^"\']+)',
        r'checkoutSessionToken["\']\s*:\s*["\']([^"\']+)',
        r'checkoutSessionIdentifier["\']\s*:\s*["\']([^"\']+)',
    ]
    for p in patterns:
        m = re.search(p, unescaped)
        if m:
            val = m.group(1).strip('"\'')
            if val and len(val) > 8:
                return val
    return ""

def extract_stable_id(html_text: str) -> str:
    if not html_text:
        return ""
    unescaped = html.unescape(html_text)
    patterns = [
        r'stableId["\']?\s*[:=]\s*["\']?([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})',
        r'merchandiseLine["\']?\s*[:=]\s*["\']?([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})',
        r'([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})'
    ]
    for p in patterns:
        match = re.search(p, unescaped)
        if match:
            val = match.group(1)
            if not val.startswith("00000000"):
                return val
    return ""

def extract_commit_sha(html_text: str) -> str:
    if not html_text:
        return ""
    unescaped = html.unescape(html_text)
    patterns = [
        r'commitSha["\']?\s*[:=]\s*["\']?([a-f0-9]{40})',
        r'/checkout-web/assets/c1/[^"\']*([a-f0-9]{40})',
        r'"environment"\s*:\s*\{[^}]*"commitSha"\s*:\s*"([a-f0-9]{40})"',
    ]
    for p in patterns:
        match = re.search(p, unescaped)
        if match:
            return match.group(1)
    for p in patterns:
        match = re.search(p, html_text)
        if match:
            return match.group(1)
    return ""

def extract_source_token(html_text: str) -> str:
    m = re.search(r'name=["\']serialized-sourceToken["\']\s+content=["\']([^"\']+)["\']', html_text)
    if m:
        return html.unescape(m.group(1)).strip('"\'')
    unescaped = html.unescape(html_text)
    re_pattern = re.compile(r'<meta\s+name="serialized-sourceToken"\s+content="([^"]*)"')
    m = re_pattern.search(unescaped)
    if m:
        return m.group(1).strip('"\'')
    return ""

def extract_identification_signature(html_text: str) -> str:
    unescaped = html.unescape(html_text)
    patterns = [
        r'checkoutCardsinkCallerIdentificationSignature":"([^"]+)"',
        r'callerIdentificationSignature["\s:]+([^"}\s,]+)',
        r'checkoutCardsinkCallerIdentificationSignature&quot;:&quot;([^&"]+)&quot;',
        r'identificationSignature["\s:]+([^"}\s,]+)',
    ]
    for p in patterns:
        m = re.search(p, unescaped)
        if m:
            return m.group(1).strip('"')
    for p in patterns:
        m = re.search(p, html_text)
        if m:
            return html.unescape(m.group(1)).strip('"')
    return ""

def extract_private_access_token_id(html_text: str) -> str:
    unescaped = html.unescape(html_text)
    re_pattern = re.compile(r'"checkoutSessionIdentifier"\s*:\s*"([a-f0-9]+)"')
    match = re_pattern.search(unescaped)
    if match:
        return match.group(1)
    return ""

def extract_actions_js_url(html_text: str, shop_url: str) -> str:
    patterns = [
        r'["\']((?:https?:)?//[^"\']*/cdn/shopifycloud/checkout-web/assets/c1/actions[A-Za-z0-9_-]*\.[A-Za-z0-9_-]+\.js)["\']',
        r'["\']((?:https?:)?//[^"\']*/cdn/shopifycloud/checkout-web/assets/[^"\']*actions[^"\']*\.js)["\']',
        r'(/cdn/shopifycloud/checkout-web/assets/c1/actions[A-Za-z0-9_-]*\.[A-Za-z0-9_-]+\.js)',
        r'(/cdn/shopifycloud/checkout-web/assets/[^"\']*actions[^"\']*\.js)',
    ]
    for p in patterns:
        match = re.search(p, html_text)
        if match:
            url = match.group(1)
            if url.startswith('//'):
                return 'https:' + url
            elif url.startswith('http'):
                return url
            return shop_url + url
    return ""

def extract_processing_js_url(html_text: str, shop_url: str) -> str:
    patterns = [
        r'["\']((?:https?:)?//[^"\']*/cdn/shopifycloud/checkout-web/assets/c1/useHasOrdersFromMultipleShops[A-Za-z0-9_.-]*\.js)["\']',
        r'["\']((?:https?:)?//[^"\']*/cdn/shopifycloud/checkout-web/assets/[A-Za-z0-9_/.-]*useHasOrdersFromMultipleShops[A-Za-z0-9_.-]*\.js)["\']',
        r'["\']((?:https?:)?//[^"\']*/cdn/shopifycloud/checkout-web/assets/[A-Za-z0-9_/.-]*[Pp]rocessing[A-Za-z0-9_.-]*\.js)["\']',
        r'["\']((?:https?:)?//[^"\']*/cdn/shopifycloud/checkout-web/assets/[A-Za-z0-9_/.-]*[Rr]eceipt[A-Za-z0-9_.-]*\.js)["\']',
        r'(/cdn/shopifycloud/checkout-web/assets/c1/useHasOrdersFromMultipleShops[A-Za-z0-9_.-]*\.js)',
        r'(/cdn/shopifycloud/checkout-web/assets/[A-Za-z0-9_/.-]*useHasOrdersFromMultipleShops[A-Za-z0-9_.-]*\.js)',
        r'(/cdn/shopifycloud/checkout-web/assets/[A-Za-z0-9_/.-]*[Pp]rocessing[A-Za-z0-9_.-]*\.js)',
        r'(/cdn/shopifycloud/checkout-web/assets/[A-Za-z0-9_/.-]*[Rr]eceipt[A-Za-z0-9_.-]*\.js)',
    ]
    for p in patterns:
        match = re.search(p, html_text)
        if match:
            url = match.group(1)
            if url.startswith('//'):
                return 'https:' + url
            elif url.startswith('http'):
                return url
            return shop_url + url
    return ""

def extract_events_js_url(html_text: str, shop_url: str) -> str:
    patterns = [
        r'["\']((?:https?:)?//[^"\']*/cdn/shopifycloud/checkout-web/assets/c1/events-shared[^"\']+\.js)["\']',
        r'["\']((?:https?:)?//[^"\']*/cdn/shopifycloud/checkout-web/assets/[^"\']*events[^"\']*\.js)["\']',
        r'(/cdn/shopifycloud/checkout-web/assets/c1/events-shared[^"]+\.js)',
        r'(/cdn/shopifycloud/checkout-web/assets/[^"]*events-shared[^"]*\.js)',
        r'(/cdn/shopifycloud/checkout-web/assets/[^"]*events[^"]*\.js)',
    ]
    for p in patterns:
        match = re.search(p, html_text)
        if match:
            url = match.group(1)
            if url.startswith('//'):
                return 'https:' + url
            elif url.startswith('http'):
                return url
            return shop_url + url
    script_events = re.findall(r'<script[^>]+src=["\']([^"\']+events[^"\']+\.js)["\']', html_text)
    if script_events:
        for s in script_events:
            if s.startswith('//'):
                return 'https:' + s
            elif not s.startswith('http'):
                return shop_url + s
            return s
    return ""

def fetch_js(session_obj: requests.Session, js_url: str, shop_url: str, referer: str, timeout: int = 15) -> str:
    if js_url.startswith('//'):
        js_url = 'https:' + js_url

    headers = {
        "accept": "*/*",
        "accept-language": "en-US,en;q=0.9",
        "origin": shop_url,
        "referer": referer,
        "sec-ch-ua": SEC_CH_UA,
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "sec-fetch-dest": "script",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin",
        "user-agent": USER_AGENT
    }
    resp = session_obj.get(js_url, headers=headers, timeout=timeout)
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
        r'name:\s*[\'"]Proposal[\'"].*?id:\s*[\'"]([a-f0-9]{64})[\'"]',
        r'id:\s*[\'"]([a-f0-9]{64})[\'"].*?name:\s*[\'"]Proposal[\'"]',
        r'id:[\'"]([a-f0-9]{64})[\'"],type:[\'"]query[\'"],name:[\'"]Proposal[\'"]',
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
        r'name:\s*[\'"]SubmitForCompletion[\'"].*?id:\s*[\'"]([a-f0-9]{64})[\'"]',
        r'id:\s*[\'"]([a-f0-9]{64})[\'"].*?name:\s*[\'"]SubmitForCompletion[\'"]',
        r'id:[\'"]([a-f0-9]{64})[\'"],type:[\'"]mutation[\'"],name:[\'"]SubmitForCompletion[\'"]',
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
        r'name:\s*[\'"]PollForReceipt[\'"].*?id:\s*[\'"]([a-f0-9]{64})[\'"]',
        r'id:\s*[\'"]([a-f0-9]{64})[\'"].*?name:\s*[\'"]PollForReceipt[\'"]',
        r'id:[\'"]([a-f0-9]{64})[\'"],type:[\'"]query[\'"],name:[\'"]PollForReceipt[\'"]',
        r'PollForReceipt.{0,300}?([a-f0-9]{64})',
        r'([a-f0-9]{64}).{0,300}?PollForReceipt',
    ]
    for p in patterns:
        match = re.search(p, js_body)
        if match:
            return match.group(1)
    return ""

def extract_operations_from_js_chunks(session_obj: requests.Session, shop_url: str, html_text: str, referer: str, timeout: int = 8) -> Tuple[str, str, str]:
    """
    Scans preloaded c1 JS chunks from the checkout HTML in parallel to extract Proposal, SubmitForCompletion, and PollForReceipt IDs.
    """
    from concurrent.futures import ThreadPoolExecutor
    links = re.findall(r'href=["\']((?:https?:)?//[^"\']*/cdn/shopifycloud/checkout-web/assets/c1/[^"\']+\.js|/cdn/shopifycloud/checkout-web/assets/c1/[^"\']+\.js)["\']', html_text)
    scripts = re.findall(r'src=["\']((?:https?:)?//[^"\']*/cdn/shopifycloud/checkout-web/assets/c1/[^"\']+\.js|/cdn/shopifycloud/checkout-web/assets/c1/[^"\']+\.js)["\']', html_text)
    importmap_matches = re.findall(r'["\']((?:https?:)?//[^"\']*/cdn/shopifycloud/checkout-web/assets/c1/[^"\']+\.js|/cdn/shopifycloud/checkout-web/assets/c1/[^"\']+\.js)["\']', html_text)
    all_chunks = list(dict.fromkeys(links + scripts + importmap_matches))

    if not all_chunks:
        return "", "", ""

    proposal_id, submit_id, poll_id = "", "", ""

    def check_chunk(rel_url: str):
        if rel_url.startswith('//'):
            full_url = 'https:' + rel_url
        elif rel_url.startswith('http'):
            full_url = rel_url
        else:
            full_url = shop_url + rel_url
        try:
            txt = fetch_js(session_obj, full_url, shop_url, referer, timeout=timeout)
            p = extract_proposal_id(txt)
            s = extract_submit_for_completion_id(txt)
            po = extract_poll_for_receipt_id(txt)
            return (p, s, po)
        except Exception:
            return ("", "", "")

    # Check chunks in parallel (scanning up to 40 chunks)
    with ThreadPoolExecutor(max_workers=15) as executor:
        for p, s, po in executor.map(check_chunk, all_chunks[:40]):
            if p and not proposal_id:
                proposal_id = p
            if s and not submit_id:
                submit_id = s
            if po and not poll_id:
                poll_id = po
            if proposal_id and submit_id and poll_id:
                break

    return proposal_id, submit_id, poll_id

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

def extract_queue_token(response_body: str) -> str:
    re_pattern = re.compile(r'"queueToken"\s*:\s*"([^"]+)"')
    m = re_pattern.search(response_body)
    if m:
        return m.group(1)
    return ""

def check_graphql_captcha(data: Any) -> bool:
    if not isinstance(data, dict):
        return False
    data_dict = data.get('data', {})
    if isinstance(data_dict, dict):
        for key in ['proposal', 'submitForCompletion']:
            obj = data_dict.get(key)
            if isinstance(obj, dict):
                # Only if captcha is present and NOT null
                if obj.get('captcha') is not None:
                    return True
                res_obj = obj.get('result', {})
                if isinstance(res_obj, dict) and res_obj.get('captcha') is not None:
                    return True

    # Check top-level GraphQL errors
    errors = data.get('errors', [])
    if isinstance(errors, list):
        for err in errors:
            code = str(err.get('code', '')).upper()
            msg = str(err.get('message', '')).upper()
            if 'CAPTCHA_REQUIRED' in code or 'CHECKOUT_BLOCKED_BY_CHALLENGE' in code:
                return True
            if 'CAPTCHA' in msg or 'CHALLENGE' in msg:
                return True

    # Check submit rejected errors
    submit_obj = data.get('data', {}).get('submitForCompletion', {})
    if isinstance(submit_obj, dict):
        result_obj = submit_obj.get('result', {})
        if isinstance(result_obj, dict):
            sub_errors = result_obj.get('errors', [])
            if isinstance(sub_errors, list):
                for err in sub_errors:
                    code = str(err.get('code', '')).upper()
                    msg = str(err.get('localizedMessage', '')).upper()
                    if 'CAPTCHA' in code or 'CHALLENGE' in code:
                        return True
                    if 'CAPTCHA' in msg or 'CHALLENGE' in msg:
                        return True

    return False

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
    if currency and currency != "USD":
        payload = payload.replace('"currencyCode": "USD"', f'"currencyCode": "{currency}"')
        payload = payload.replace('"presentmentCurrency": "USD"', f'"presentmentCurrency": "{currency}"')
    if country and country != "US":
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
            price_str = str(cart_data['items'][0]['price'])
            match = re.match(r'^[^\d]*', price_str)
            if match and match.group(0):
                return match.group(0)
    return "USD"

def extract_pci_session_id(pci_body: str) -> str:
    re_pattern = re.compile(r'"id"\s*:\s*"([^"]+)"')
    match = re_pattern.search(pci_body)
    if match:
        return match.group(1)
    return ""

def parse_card_string(cc_input: str) -> Tuple[str, int, int, str]:
    """
    Parses a card string formatted like:
      - '5456 1500 1550 7529|03|2028|166'
      - '5456150015507529:03:28:166'
      - '5456150015507529/03/2028/166'
      - '5456 1500 1550 7529 03 28 166'
    """
    cleaned = re.sub(r'[\r\n\t]+', '', cc_input.strip())
    
    # Check if a non-space delimiter is used (pipe, colon, or slash)
    delimiter = None
    for d in ['|', ':', '/']:
        if d in cleaned and cleaned.count(d) >= 3:
            delimiter = d
            break
            
    if delimiter:
        parts = [p.strip() for p in cleaned.split(delimiter) if p.strip()]
        if len(parts) >= 4:
            number = re.sub(r'[\s\-]+', '', parts[0])
            m = int(parts[1])
            y_str = parts[2]
            y = int('20' + y_str) if len(y_str) == 2 else int(y_str)
            cvv = re.sub(r'\D+', '', parts[3])
            if m > 12 and 1 <= y <= 12:
                m, y = y, m
            return number, m, y, cvv

    # If no delimiter or space-separated
    tokens = [t.strip() for t in re.split(r'[\s]+', cleaned) if t.strip()]
    if len(tokens) >= 4:
        cvv = re.sub(r'\D+', '', tokens[-1])
        y_str = tokens[-2]
        y = int('20' + y_str) if len(y_str) == 2 else int(y_str)
        m = int(tokens[-3])
        number = ''.join(tokens[:-3]).replace('-', '').replace(' ', '')
        if m > 12 and 1 <= y <= 12:
            m, y = y, m
        return number, m, y, cvv

    raise ValueError("Card input must contain number, month, year, and cvv separated by '|', ':', '/', or spaces")

def run_shopify_checkout(
    domain: Optional[str] = None,
    site: Optional[str] = None,
    card_number: str = "",
    card_month: int = 1,
    card_year: int = 2028,
    cvv: str = "",
    card_name: Optional[str] = None,
    address: Optional[Dict[str, str]] = None,
    email: Optional[str] = None,
    variant_id: Optional[int] = None,
    proxy: Optional[str] = None,
    timeout: int = 25
) -> Dict[str, Any]:
    start_time = time.time()
    store_url = domain or site or "https://us.mercihandy.com"
    domain = normalize_url(store_url)
    formatted_proxy = format_proxy(proxy)

    # Sanitize and validate card credentials
    card_number = re.sub(r'[\s\-]+', '', str(card_number))
    cvv = re.sub(r'\D+', '', str(cvv))
    try:
        card_month = int(card_month)
    except (ValueError, TypeError):
        card_month = 1
    try:
        card_year = int(card_year)
    except (ValueError, TypeError):
        card_year = 2028

    if card_year < 100:
        card_year = 2000 + card_year
    if card_month > 12 and 1 <= card_year <= 12:
        card_month, card_year = card_year, card_month
    
    session = requests.Session()
    if formatted_proxy:
        session.proxies = {
            "http": formatted_proxy,
            "https": formatted_proxy
        }
    
    # Default Address
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
    if address:
        addr.update({k: v for k, v in address.items() if v is not None})
    
    if not card_name:
        card_name = f"{addr['first_name']} {addr['last_name']}"
        
    if not email:
        email_domains = ["gmail.com", "yahoo.com", "outlook.com"]
        first_names = ["james", "john", "robert", "michael", "william"]
        last_names = ["smith", "johnson", "williams", "brown", "jones"]
        email = f"{random.choice(first_names)}{random.choice(last_names)}{random.randint(1, 999)}@{random.choice(email_domains)}"

    home_headers = {
        'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
        'accept-language': 'en-US,en;q=0.9',
        'cache-control': 'max-age=0',
        'priority': 'u=0, i',
        'sec-ch-ua': SEC_CH_UA,
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-platform': '"Windows"',
        'sec-fetch-dest': 'document',
        'sec-fetch-mode': 'navigate',
        'sec-fetch-site': 'none',
        'sec-fetch-user': '?1',
        'upgrade-insecure-requests': '1',
        'user-agent': USER_AGENT,
    }

    home_resp = None
    try:
        home_resp = session.get(domain + '/', headers=home_headers, timeout=timeout, allow_redirects=True)
        # Automatically follow canonical domain redirect (e.g. store.myshopify.com -> store.com)
        if home_resp.url:
            parsed = urllib.parse.urlparse(home_resp.url)
            if parsed.scheme in ('http', 'https') and parsed.netloc:
                domain = f"{parsed.scheme}://{parsed.netloc}".rstrip('/')
    except Exception as e:
        return {
            "success": False,
            "status": "ERROR",
            "message": f"Failed to connect to store domain: {str(e)}",
            "time_taken": round(time.time() - start_time, 2)
        }

    if home_resp is not None:
        if '/password' in home_resp.url or '<title>Opening Soon' in home_resp.text or 'store-password' in home_resp.text:
            return {
                "success": False,
                "status": "STORE_LOCKED",
                "message": "Store is password protected or in development mode.",
                "time_taken": round(time.time() - start_time, 2)
            }
        if home_resp.status_code == 430 or '/challenge' in home_resp.url or 'challenge-platform' in home_resp.text or 'shopify-challenge' in home_resp.text:
            return {
                "success": False,
                "status": "CAPTCHA_REQUIRED",
                "message": "Store homepage protected by Cloudflare/Shopify challenge.",
                "time_taken": round(time.time() - start_time, 2)
            }

    # Fetch products
    products_headers = {
        'accept': 'application/json, text/javascript, */*; q=0.01',
        'accept-language': 'en-US,en;q=0.9',
        'referer': domain + '/',
        'sec-ch-ua': SEC_CH_UA,
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-platform': '"Windows"',
        'sec-fetch-dest': 'empty',
        'sec-fetch-mode': 'cors',
        'sec-fetch-site': 'same-origin',
        'user-agent': USER_AGENT,
        'x-requested-with': 'XMLHttpRequest',
    }

    selected_product = None
    selected_variant = None

    if variant_id:
        selected_variant = {'id': variant_id, 'price': '10.00'}
        selected_product = {'handle': 'custom-product', 'title': 'Custom Product', 'variants': [selected_variant]}
    else:
        products = []
        endpoints = [
            f"{domain}/products.json?limit=250",
            f"{domain}/products.json?limit=50&page=1",
            f"{domain}/collections/all/products.json?limit=50",
            f"{domain}/products.json?limit=10"
        ]
        for ep in endpoints:
            try:
                products_resp = session.get(ep, headers=products_headers, timeout=timeout)
                if products_resp.status_code == 200:
                    data = products_resp.json()
                    p_list = data.get('products', [])
                    if p_list:
                        products = p_list
                        break
            except Exception:
                continue

        # If JSON endpoints returned nothing, scrape product handles from homepage HTML
        if not products and home_resp and home_resp.text:
            try:
                found_handles = re.findall(r'/products/([a-zA-Z0-9_\-]+)', home_resp.text)
                for h in dict.fromkeys(found_handles)[:6]:
                    if h in ('all', 'search', 'collections', 'cart', 'checkout'):
                        continue
                    p_js = session.get(f"{domain}/products/{h}.js", headers=products_headers, timeout=timeout)
                    if p_js.status_code == 200:
                        prod_obj = p_js.json()
                        if prod_obj and prod_obj.get('variants'):
                            products = [prod_obj]
                            break
            except Exception:
                pass

        if not products:
            return {
                "success": False,
                "status": "NO_PRODUCTS",
                "message": f"No purchasable products found on store {domain}. Pass 'variant_id' directly to test a specific product.",
                "time_taken": round(time.time() - start_time, 2)
            }

        # Select first available variant with lowest price
        min_price = float('inf')
        for product in products:
            for variant in product.get('variants', []):
                if variant.get('available') and variant.get('price'):
                    try:
                        price = float(variant['price'])
                        if 0 < price < min_price:
                            min_price = price
                            selected_product = product
                            selected_variant = variant
                    except (ValueError, TypeError):
                        pass

        if not selected_product:
            for product in products:
                for variant in product.get('variants', []):
                    if variant.get('available') and variant.get('price'):
                        try:
                            price = float(variant['price'])
                            if price < min_price:
                                min_price = price
                                selected_product = product
                                selected_variant = variant
                        except (ValueError, TypeError):
                            pass

        if not selected_product:
            selected_product = products[0]
            selected_variant = selected_product['variants'][0]

    # Add to cart
    add_headers = {
        'accept': 'application/javascript',
        'accept-language': 'en-US,en;q=0.9',
        'content-type': 'application/x-www-form-urlencoded',
        'origin': domain,
        'referer': f"{domain}/products/{selected_product['handle']}?variant={selected_variant['id']}",
        'sec-ch-ua': SEC_CH_UA,
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-platform': '"Windows"',
        'sec-fetch-dest': 'empty',
        'sec-fetch-mode': 'cors',
        'sec-fetch-site': 'same-origin',
        'user-agent': USER_AGENT,
        'x-requested-with': 'XMLHttpRequest',
    }

    add_data = {
        'id': str(selected_variant['id']),
        'quantity': '1',
        'form_type': 'product',
        'utf8': '✓',
    }

    try:
        add_resp = session.post(domain + '/cart/add', headers=add_headers, data=add_data, timeout=timeout)
        if add_resp.status_code == 430 or '/challenge' in add_resp.url or 'challenge-platform' in add_resp.text or 'shopify-challenge' in add_resp.text:
            return {
                "success": False,
                "status": "CAPTCHA_REQUIRED",
                "message": "Store cart add protected by Cloudflare/Shopify challenge.",
                "time_taken": round(time.time() - start_time, 2)
            }
    except Exception as e:
        return {
            "success": False,
            "status": "ERROR",
            "message": f"Failed to add item to cart: {str(e)}",
            "time_taken": round(time.time() - start_time, 2)
        }

    # Fetch Cart
    cart_headers = {
        'accept': 'application/json, text/javascript, */*; q=0.01',
        'accept-language': 'en-US,en;q=0.9',
        'referer': f"{domain}/products/{selected_product['handle']}?variant={selected_variant['id']}",
        'sec-ch-ua': SEC_CH_UA,
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-platform': '"Windows"',
        'sec-fetch-dest': 'empty',
        'sec-fetch-mode': 'cors',
        'sec-fetch-site': 'same-origin',
        'user-agent': USER_AGENT,
        'x-requested-with': 'XMLHttpRequest',
    }

    try:
        cart_resp = session.get(domain + '/cart.js', headers=cart_headers, timeout=timeout)
        if cart_resp.status_code == 430 or '/challenge' in cart_resp.url or 'challenge-platform' in cart_resp.text or 'shopify-challenge' in cart_resp.text:
            return {
                "success": False,
                "status": "CAPTCHA_REQUIRED",
                "message": "Store cart protected by Cloudflare/Shopify challenge.",
                "time_taken": round(time.time() - start_time, 2)
            }
        cart_data = cart_resp.json()
        cart_token = cart_data.get('token', '')
        clean_token = cart_token.split('?')[0] if cart_token else ""
        key = cart_token.split('?key=')[1] if '?key=' in cart_token else None
        currency = extract_currency_from_cart(cart_data)
        country = "US"
    except Exception as e:
        return {
            "success": False,
            "status": "ERROR",
            "message": f"Failed to fetch cart.js: {str(e)}",
            "time_taken": round(time.time() - start_time, 2)
        }

    # Checkout
    checkout_headers = {
        'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
        'accept-language': 'en-US,en;q=0.9',
        'priority': 'u=0, i',
        'referer': f"{domain}/products/{selected_product['handle']}?variant={selected_variant['id']}",
        'sec-ch-ua': SEC_CH_UA,
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-platform': '"Windows"',
        'sec-fetch-dest': 'document',
        'sec-fetch-mode': 'navigate',
        'sec-fetch-site': 'same-origin',
        'sec-fetch-user': '?1',
        'upgrade-insecure-requests': '1',
        'user-agent': USER_AGENT,
    }

    checkout_params = {}
    if key:
        checkout_params['key'] = key
    checkout_params['skip_shop_pay'] = 'true'

    checkout_url = f"{domain}/cart/c/{clean_token}"
    try:
        checkout_resp = session.get(checkout_url, params=checkout_params, headers=checkout_headers, allow_redirects=True, timeout=timeout)
        # If redirected back to /cart, use /checkout directly
        if '/checkouts/' not in checkout_resp.url and '/cart' in checkout_resp.url:
            checkout_resp = session.get(f"{domain}/checkout", headers=checkout_headers, allow_redirects=True, timeout=timeout)
        checkout_url_final = checkout_resp.url
        html_text = checkout_resp.text
    except Exception as e:
        return {
            "success": False,
            "status": "ERROR",
            "message": f"Failed to initiate checkout: {str(e)}",
            "time_taken": round(time.time() - start_time, 2)
        }

    unescaped = html.unescape(html_text)

    # Detect locked or protected stores
    if '/password' in checkout_url_final or '<title>Opening Soon' in html_text or 'store-password' in html_text:
        return {
            "success": False,
            "status": "STORE_LOCKED",
            "message": "Store is password protected or in development mode.",
            "time_taken": round(time.time() - start_time, 2)
        }

    captcha_indicators = [
        checkout_resp.status_code == 430,
        '/challenge' in checkout_url_final,
        'challenge-platform' in html_text,
        'shopify-challenge' in html_text,
        'g-recaptcha' in html_text,
        'h-captcha' in html_text,
        'cf-turnstile' in html_text,
        'hcaptcha.com' in html_text,
        'google.com/recaptcha' in html_text,
        'recaptcha/api.js' in html_text,
    ]
    if any(captcha_indicators):
        return {
            "success": False,
            "status": "CAPTCHA_REQUIRED",
            "message": "Store checkout protected by Cloudflare/Shopify challenge.",
            "time_taken": round(time.time() - start_time, 2)
        }

    # Extract or automatically generate/fallback every checkout token
    checkout_token = extract_checkout_token(checkout_url_final, html_text) or clean_token or secrets.token_hex(16)
    session_token = extract_session_token(html_text)
    stable_id = extract_stable_id(unescaped) or extract_stable_id(html_text)
    build_id = extract_commit_sha(unescaped) or extract_commit_sha(html_text)
    source_token = extract_source_token(html_text) or checkout_token
    ident_sig = extract_identification_signature(unescaped) or extract_identification_signature(html_text)

    # Automatic fallback for session token from cookies or derived identifiers
    if not session_token:
        session_token = (
            session.cookies.get('checkout_session_token')
            or session.cookies.get('_shopify_s')
            or session.cookies.get('cart_sig')
            or ""
        )
    if not session_token:
        alt_token_re = re.compile(r'"checkoutSessionIdentifier"\s*:\s*"([a-f0-9]+)"')
        m_alt = alt_token_re.search(unescaped)
        if m_alt:
            session_token = m_alt.group(1)
    if not session_token:
        session_token = checkout_token or clean_token or secrets.token_hex(16)

    # Automatic fallback for stableId (RFC 4122 client UUID expected by Shopify)
    if not stable_id:
        stable_id = str(uuid.uuid4())

    # Automatic fallback for buildId (known production build)
    if not build_id:
        build_id = FALLBACK_BUILD_ID

    if not source_token:
        source_token = checkout_token

    proposal_id = ""
    submit_id = ""
    poll_id = ""

    # Check known build operations cache first
    if build_id and build_id in KNOWN_BUILD_OPERATIONS:
        known_ops = KNOWN_BUILD_OPERATIONS[build_id]
        proposal_id = known_ops.get("proposal_id", "")
        submit_id = known_ops.get("submit_id", "")
        poll_id = known_ops.get("poll_id", "")

    actions_url = extract_actions_js_url(html_text, domain)
    processing_url = extract_processing_js_url(html_text, domain)
    events_js_url = extract_events_js_url(html_text, domain)

    if not actions_url:
        all_scripts = re.findall(r'<script[^>]+src=["\']([^"\']+\.js)["\']', html_text)
        for script in all_scripts:
            if 'actions' in script.lower():
                if not script.startswith('http'):
                    actions_url = domain + script
                else:
                    actions_url = script
                break

    js_body = ""
    if actions_url and (not proposal_id or not submit_id):
        try:
            js_body = fetch_js(session, actions_url, domain, checkout_url_final, timeout=timeout)
            if not proposal_id:
                proposal_id = extract_proposal_id(js_body)
            if not submit_id:
                submit_id = extract_submit_for_completion_id(js_body)
        except Exception:
            pass

    if not poll_id:
        for source_js in [events_js_url, processing_url]:
            if source_js and not poll_id:
                try:
                    js = fetch_js(session, source_js, domain, checkout_url_final, timeout=timeout)
                    poll_id = extract_poll_for_receipt_id(js)
                except Exception:
                    pass

    if not poll_id and js_body:
        poll_id = extract_poll_for_receipt_id(js_body)

    # Dynamic parallel scan of c1 module chunks if any operation ID is still missing
    if not proposal_id or not submit_id or not poll_id:
        dyn_p, dyn_s, dyn_po = extract_operations_from_js_chunks(session, domain, html_text, checkout_url_final, timeout=8)
        if not proposal_id and dyn_p:
            proposal_id = dyn_p
        if not submit_id and dyn_s:
            submit_id = dyn_s
        if not poll_id and dyn_po:
            poll_id = dyn_po
        if build_id and (proposal_id or submit_id or poll_id):
            KNOWN_BUILD_OPERATIONS[build_id] = {
                "proposal_id": proposal_id or FALLBACK_PROPOSAL_ID,
                "submit_id": submit_id or FALLBACK_SUBMIT_ID,
                "poll_id": poll_id or FALLBACK_POLL_ID
            }

    # Safe fallback defaults to guarantee pipeline never halts
    if not proposal_id:
        proposal_id = FALLBACK_PROPOSAL_ID
    if not submit_id:
        submit_id = FALLBACK_SUBMIT_ID
    if not poll_id:
        poll_id = FALLBACK_POLL_ID


    # Proposal 1
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
        'sec-ch-ua': SEC_CH_UA,
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-platform': '"Windows"',
        'sec-fetch-dest': 'empty',
        'sec-fetch-mode': 'cors',
        'sec-fetch-site': 'same-origin',
        'shopify-checkout-client': 'checkout-web/1.0',
        'shopify-checkout-source': f'id="{checkout_token}", type="cn"',
        'user-agent': USER_AGENT,
        'x-checkout-one-session-token': session_token,
        'x-checkout-web-build-id': build_id,
        'x-checkout-web-deploy-stage': 'production',
        'x-checkout-web-source-id': source_token,
    }

    try:
        proposal_resp = session.post(
            f"{domain}/checkouts/internal/graphql/persisted",
            params={'operationName': 'Proposal'},
            headers=proposal_headers,
            data=proposal_gql,
            timeout=timeout
        )
        proposal_data = proposal_resp.json()
        if check_graphql_captcha(proposal_data):
            return {
                "success": False,
                "status": "CAPTCHA_REQUIRED",
                "message": "Store checkout requires Captcha verification on proposal.",
                "details": {"graphql_response": proposal_data},
                "time_taken": round(time.time() - start_time, 2)
            }
        queue_token = extract_queue_token(json.dumps(proposal_data))
    except Exception as e:
        return {
            "success": False,
            "status": "ERROR",
            "message": f"Proposal 1 failed: {str(e)}",
            "time_taken": round(time.time() - start_time, 2)
        }

    # Proposal 2
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

    try:
        proposal2_resp = session.post(
            f"{domain}/checkouts/internal/graphql/persisted",
            params={'operationName': 'Proposal'},
            headers=proposal_headers,
            data=proposal2_gql,
            timeout=timeout
        )
        proposal2_data = proposal2_resp.json()
        if check_graphql_captcha(proposal2_data):
            return {
                "success": False,
                "status": "CAPTCHA_REQUIRED",
                "message": "Store checkout requires Captcha verification on proposal 2.",
                "details": {"graphql_response": proposal2_data},
                "time_taken": round(time.time() - start_time, 2)
            }
        queue_token2 = extract_queue_token(json.dumps(proposal2_data))
    except Exception as e:
        return {
            "success": False,
            "status": "ERROR",
            "message": f"Proposal 2 failed: {str(e)}",
            "time_taken": round(time.time() - start_time, 2)
        }

    # Proposal 3
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

    try:
        proposal3_resp = session.post(
            f"{domain}/checkouts/internal/graphql/persisted",
            params={'operationName': 'Proposal'},
            headers=proposal_headers,
            data=proposal3_gql,
            timeout=timeout
        )
        proposal3_data = proposal3_resp.json()
        if check_graphql_captcha(proposal3_data):
            return {
                "success": False,
                "status": "CAPTCHA_REQUIRED",
                "message": "Store checkout requires Captcha verification on proposal 3.",
                "details": {"graphql_response": proposal3_data},
                "time_taken": round(time.time() - start_time, 2)
            }
        queue_token3 = extract_queue_token(json.dumps(proposal3_data))
    except Exception as e:
        return {
            "success": False,
            "status": "ERROR",
            "message": f"Proposal 3 failed: {str(e)}",
            "time_taken": round(time.time() - start_time, 2)
        }

    proposal3_str = json.dumps(proposal3_data)
    
    # Extract exact negotiated terms from Proposal 3 result
    neg_result = proposal3_data.get('data', {}).get('session', {}).get('negotiate', {}).get('result', {})
    seller_prop = neg_result.get('sellerProposal', {}) or neg_result.get('buyerProposal', {})

    merchandise_price = str(selected_variant['price'])
    total_amount = ""
    is_shipping_required = True
    delivery_handle = ""
    shipping_amount = "0.00"
    has_dest_address = True

    if seller_prop:
        is_shipping_required = seller_prop.get('isShippingRequired', True)
        
        # 1. Total and Currency
        for k in ['total', 'checkoutTotal', 'runningTotal', 'subtotalBeforeTaxesAndShipping', 'subtotalBeforeReductions']:
            v = seller_prop.get(k, {})
            if isinstance(v, dict):
                val = v.get('value', {})
                if isinstance(val, dict) and val.get('amount'):
                    total_amount = val['amount']
                    if val.get('currencyCode'):
                        currency = val['currencyCode']
                    break

        cust_curr = seller_prop.get('buyerIdentity', {}).get('customer', {}).get('presentmentCurrency')
        if cust_curr:
            currency = cust_curr

        # 2. Merchandise lines and stableId
        merch_lines = seller_prop.get('merchandise', {}).get('merchandiseLines', [])
        if merch_lines:
            if merch_lines[0].get('stableId'):
                stable_id = merch_lines[0]['stableId']
            total_amt_obj = merch_lines[0].get('totalAmount', {}).get('value', {})
            if total_amt_obj.get('amount'):
                merchandise_price = total_amt_obj['amount']

        # 3. Delivery Strategy & Shipping
        deliv = seller_prop.get('delivery', {})
        deliv_lines = deliv.get('deliveryLines', [])
        if deliv_lines:
            first_dl = deliv_lines[0]
            if first_dl.get('destinationAddress') is None and not is_shipping_required:
                has_dest_address = False
            strat = first_dl.get('selectedDeliveryStrategy', {})
            if strat.get('handle'):
                delivery_handle = strat['handle']
            
            # Find exact string amount in availableDeliveryStrategies
            avail_strats = first_dl.get('availableDeliveryStrategies', [])
            if not delivery_handle and avail_strats:
                delivery_handle = avail_strats[0].get('handle', '')
            
            for s in avail_strats:
                if s.get('handle') == delivery_handle:
                    if s.get('amount', {}).get('value', {}).get('amount'):
                        shipping_amount = s['amount']['value']['amount']
                    elif s.get('deliveryStrategyBreakdown'):
                        bk = s['deliveryStrategyBreakdown']
                        if isinstance(bk, list) and bk and bk[0].get('amount', {}).get('value', {}).get('amount'):
                            shipping_amount = bk[0]['amount']['value']['amount']
                    break

    # Fallback extractions if not found in dictionary
    if not delivery_handle:
        delivery_handle = extract_delivery_handle(proposal3_str)
    signed_handles = extract_signed_handles(proposal3_str)
    if not total_amount:
        total_amount = extract_checkout_total(proposal3_str) or extract_seller_total(proposal3_str) or merchandise_price
    if not shipping_amount:
        ext_ship = extract_shipping_amount(proposal3_str)
        if ext_ship:
            shipping_amount = ext_ship
        elif total_amount and merchandise_price:
            try:
                diff = round(float(total_amount) - float(merchandise_price), 2)
                if diff >= 0:
                    shipping_amount = f"{diff:.2f}"
            except Exception:
                pass

    if not currency or currency == "USD":
        extracted_currency = extract_seller_currency(proposal3_str)
        if extracted_currency:
            currency = extracted_currency
    if country == "US":
        extracted_country = extract_seller_country(proposal3_str)
        if extracted_country:
            country = extracted_country

    # Shopify PCI Session
    shop_domain = domain.replace("https://", "").replace("http://", "").split("/")[0]
    payment_scope = shop_domain

    pci_headers = {
        'accept': 'application/json',
        'accept-language': 'en-US,en;q=0.9',
        'content-type': 'application/json',
        'origin': 'https://checkout.pci.shopifyinc.com',
        'referer': 'https://checkout.pci.shopifyinc.com/build/a8e4a94/number-ltr.html?identifier=&locationURL=',
        'sec-ch-ua': SEC_CH_UA,
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-platform': '"Windows"',
        'sec-fetch-dest': 'empty',
        'sec-fetch-mode': 'cors',
        'sec-fetch-site': 'same-origin',
        'shopify-identification-signature': ident_sig,
        'user-agent': USER_AGENT,
    }

    pci_json = {
        'credit_card': {
            'number': str(card_number),
            'month': int(card_month),
            'year': int(card_year),
            'verification_value': str(cvv),
            'start_month': None,
            'start_year': None,
            'issue_number': '',
            'name': card_name,
        },
        'payment_session_scope': payment_scope,
    }

    pci_session = requests.Session()
    if formatted_proxy:
        pci_session.proxies = {"http": formatted_proxy, "https": formatted_proxy}

    try:
        pci_resp = pci_session.post(
            'https://checkout.pci.shopifyinc.com/sessions',
            headers=pci_headers,
            json=pci_json,
            timeout=timeout
        )
        pci_session_id = extract_pci_session_id(pci_resp.text)
    except Exception as e:
        return {
            "success": False,
            "status": "ERROR",
            "message": f"PCI session request failed: {str(e)}",
            "time_taken": round(time.time() - start_time, 2)
        }

    if not pci_session_id:
        error_msg = extract_any_error(pci_resp.text) or pci_resp.text
        return {
            "success": False,
            "status": "DECLINED",
            "message": f"Card rejected by PCI service: {error_msg}",
            "details": {
                "pci_status_code": pci_resp.status_code,
                "pci_response": pci_resp.text
            },
            "time_taken": round(time.time() - start_time, 2)
        }

    attempt_token = generate_attempt_token(checkout_token)
    page_id = generate_page_id()
    signed_handles_list = [{"signedHandle": h} for h in signed_handles] if signed_handles else []

    destination_dict = {
        "streetAddress": {
            "address1": addr["address1"], "address2": addr["address2"],
            "city": addr["city"], "countryCode": addr["country_code"],
            "postalCode": addr["postal_code"], "firstName": addr["first_name"],
            "lastName": addr["last_name"], "zoneCode": addr["zone_code"],
            "phone": addr["phone"], "oneTimeUse": False
        }
    }

    if not deliv_lines or deliv.get('__typename') == 'UnavailableTerms':
        delivery_section = {
            "deliveryLines": [],
            "noDeliveryRequired": [],
            "useProgressiveRates": False,
            "prefetchShippingRatesStrategy": None,
            "supportsSplitShipping": False
        }
    else:
        dl_dict = {
            "selectedDeliveryStrategy": {
                "deliveryStrategyByHandle": {"handle": delivery_handle, "customDeliveryRate": False},
                "options": {}
            },
            "targetMerchandiseLines": {"lines": [{"stableId": stable_id}]},
            "deliveryMethodTypes": ["SHIPPING"],
            "expectedTotalPrice": {"value": {"amount": shipping_amount, "currencyCode": currency}},
            "destinationChanged": False
        }
        if has_dest_address:
            dl_dict["destination"] = destination_dict

        delivery_section = {
            "deliveryLines": [dl_dict],
            "noDeliveryRequired": [], "useProgressiveRates": False,
            "prefetchShippingRatesStrategy": None, "supportsSplitShipping": True
        }

    submit_variables = {
        "input": {
            "sessionInput": {"sessionToken": session_token},
            "queueToken": queue_token3,
            "discounts": {"lines": [], "acceptUnexpectedDiscounts": True},
            "delivery": delivery_section,
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
                    "expectedTotalPrice": {"value": {"amount": merchandise_price, "currencyCode": currency}},
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
        'sec-ch-ua': SEC_CH_UA,
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-platform': '"Windows"',
        'sec-fetch-dest': 'empty',
        'sec-fetch-mode': 'cors',
        'sec-fetch-site': 'same-origin',
        'shopify-checkout-client': 'checkout-web/1.0',
        'shopify-checkout-source': f'id="{checkout_token}", type="cn"',
        'user-agent': USER_AGENT,
        'x-checkout-one-session-token': session_token,
        'x-checkout-web-build-id': build_id,
        'x-checkout-web-deploy-stage': 'production',
        'x-checkout-web-source-id': source_token,
    }

    try:
        submit_resp = session.post(
            f"{domain}/checkouts/internal/graphql/persisted",
            params={'operationName': 'SubmitForCompletion'},
            headers=submit_headers,
            data=submit_gql,
            timeout=timeout
        )
        submit_data = submit_resp.json()
        if check_graphql_captcha(submit_data):
            return {
                "success": False,
                "status": "CAPTCHA_REQUIRED",
                "message": "Store checkout requires Captcha verification on submit.",
                "details": {"graphql_response": submit_data},
                "time_taken": round(time.time() - start_time, 2)
            }
    except Exception as e:
        return {
            "success": False,
            "status": "ERROR",
            "message": f"Submit request failed: {str(e)}",
            "time_taken": round(time.time() - start_time, 2)
        }

    receipt_id = ""
    receipt_session_token = ""
    submit_for_completion = submit_data.get('data', {}).get('submitForCompletion', {})

    # Auto-reconcile with sellerProposal if Shopify returns SubmitRejected (ConfirmChangeViolation)
    if submit_for_completion.get('__typename') == 'SubmitRejected':
        rej_sp = submit_for_completion.get('sellerProposal')
        if rej_sp:
            for k in ['total', 'checkoutTotal', 'runningTotal', 'subtotalBeforeTaxesAndShipping', 'subtotalBeforeReductions']:
                v = rej_sp.get(k, {})
                if isinstance(v, dict):
                    val = v.get('value', {})
                    if isinstance(val, dict) and val.get('amount'):
                        total_amount = val['amount']
                        if val.get('currencyCode'):
                            currency = val['currencyCode']
                        break

            rej_cust = rej_sp.get('buyerIdentity', {}).get('customer', {})
            if rej_cust.get('presentmentCurrency'):
                currency = rej_cust['presentmentCurrency']

            rej_merch = rej_sp.get('merchandise', {}).get('merchandiseLines', [])
            if rej_merch:
                if rej_merch[0].get('stableId'):
                    stable_id = rej_merch[0]['stableId']
                if rej_merch[0].get('totalAmount', {}).get('value', {}).get('amount'):
                    merchandise_price = rej_merch[0]['totalAmount']['value']['amount']

            rej_deliv = rej_sp.get('delivery', {})
            rej_deliv_lines = rej_deliv.get('deliveryLines', []) if isinstance(rej_deliv, dict) else []
            if not rej_deliv_lines or (isinstance(rej_deliv, dict) and rej_deliv.get('__typename') == 'UnavailableTerms'):
                submit_variables["input"]["delivery"] = {
                    "deliveryLines": [],
                    "noDeliveryRequired": [],
                    "useProgressiveRates": False,
                    "prefetchShippingRatesStrategy": None,
                    "supportsSplitShipping": False
                }
            else:
                first_line = rej_deliv_lines[0]
                strat = first_line.get('selectedDeliveryStrategy', {})
                if strat.get('handle'):
                    delivery_handle = strat['handle']
                avail_strats = first_line.get('availableDeliveryStrategies', [])
                if not delivery_handle and avail_strats:
                    delivery_handle = avail_strats[0].get('handle', '')
                for s in avail_strats:
                    if s.get('handle') == delivery_handle:
                        if s.get('amount', {}).get('value', {}).get('amount'):
                            shipping_amount = s['amount']['value']['amount']
                        elif s.get('deliveryStrategyBreakdown'):
                            bk = s['deliveryStrategyBreakdown']
                            if isinstance(bk, list) and bk and bk[0].get('amount', {}).get('value', {}).get('amount'):
                                shipping_amount = bk[0]['amount']['value']['amount']
                        break

                rej_dl_dict = {
                    "selectedDeliveryStrategy": {
                        "deliveryStrategyByHandle": {"handle": delivery_handle, "customDeliveryRate": False},
                        "options": {}
                    },
                    "targetMerchandiseLines": {"lines": [{"stableId": stable_id}]},
                    "deliveryMethodTypes": ["SHIPPING"],
                    "expectedTotalPrice": {"value": {"amount": shipping_amount, "currencyCode": currency}},
                    "destinationChanged": False
                }
                if first_line.get("destinationAddress") is not None:
                    rej_dl_dict["destination"] = destination_dict

                submit_variables["input"]["delivery"] = {
                    "deliveryLines": [rej_dl_dict],
                    "noDeliveryRequired": [],
                    "useProgressiveRates": False,
                    "prefetchShippingRatesStrategy": None,
                    "supportsSplitShipping": True
                }

            submit_variables["input"]["merchandise"]["merchandiseLines"][0]["stableId"] = stable_id
            submit_variables["input"]["merchandise"]["merchandiseLines"][0]["expectedTotalPrice"]["value"]["amount"] = merchandise_price
            submit_variables["input"]["merchandise"]["merchandiseLines"][0]["expectedTotalPrice"]["value"]["currencyCode"] = currency

            submit_variables["input"]["payment"]["totalAmount"]["value"]["amount"] = total_amount
            submit_variables["input"]["payment"]["totalAmount"]["value"]["currencyCode"] = currency
            submit_variables["input"]["payment"]["paymentLines"][0]["amount"]["value"]["amount"] = total_amount
            submit_variables["input"]["payment"]["paymentLines"][0]["amount"]["value"]["currencyCode"] = currency
            submit_variables["input"]["buyerIdentity"]["customer"]["presentmentCurrency"] = currency

            try:
                # Update queueToken if returned in first submit
                new_qtoken = extract_queue_token(submit_resp.text)
                if new_qtoken:
                    submit_variables["input"]["queueToken"] = new_qtoken

                submit_gql_reconciled = json.dumps({
                    "variables": submit_variables,
                    "operationName": "SubmitForCompletion",
                    "id": submit_id
                })

                submit_resp = session.post(
                    f"{domain}/checkouts/internal/graphql/persisted",
                    params={'operationName': 'SubmitForCompletion'},
                    headers=submit_headers,
                    data=submit_gql_reconciled,
                    timeout=timeout
                )
                submit_data = submit_resp.json()
                submit_for_completion = submit_data.get('data', {}).get('submitForCompletion', {})
            except Exception:
                pass

    receipt = submit_for_completion.get('receipt', {})

    if receipt:
        receipt_id = receipt.get('id', '')
        purchase_order = receipt.get('purchaseOrder', {})
        if purchase_order:
            receipt_session_token = purchase_order.get('sessionToken', '')
        receipt_type = receipt.get('__typename', '')
        
        if receipt_type == 'ProcessedReceipt':
            return {
                "success": True,
                "status": "APPROVED",
                "message": "Order placed successfully",
                "details": {
                    "receipt_id": receipt_id,
                    "receipt_type": receipt_type,
                    "amount": total_amount,
                    "currency": currency,
                    "product": selected_product.get('title'),
                    "variant_id": selected_variant.get('id')
                },
                "time_taken": round(time.time() - start_time, 2)
            }
        elif receipt_type == 'FailedReceipt':
            err = receipt.get('processingError', {})
            return {
                "success": False,
                "status": "DECLINED",
                "message": err.get('message', 'Payment processing failed'),
                "details": {
                    "receipt_id": receipt_id,
                    "receipt_type": receipt_type,
                    "error_code": err.get('code'),
                    "error_details": err
                },
                "time_taken": round(time.time() - start_time, 2)
            }
        elif receipt_type == 'ActionRequiredReceipt':
            return {
                "success": False,
                "status": "3DS_REQUIRED",
                "message": "3DS authentication required",
                "details": {
                    "receipt_id": receipt_id,
                    "receipt_type": receipt_type
                },
                "time_taken": round(time.time() - start_time, 2)
            }

    if not receipt_id:
        receipt_id = extract_receipt_id(submit_resp.text)
    if not receipt_session_token:
        receipt_session_token = extract_receipt_session_token(submit_resp.text)

    # Poll if needed
    if receipt_id and receipt_session_token and poll_id:
        for poll_num in range(1, 6):
            time.sleep(1)
            poll_headers = {
                'accept': 'application/json',
                'accept-language': 'en-US,en;q=0.9',
                'content-type': 'application/json',
                'priority': 'u=1, i',
                'referer': checkout_url_final,
                'sec-ch-ua': SEC_CH_UA,
                'sec-ch-ua-mobile': '?0',
                'sec-ch-ua-platform': '"Windows"',
                'sec-fetch-dest': 'empty',
                'sec-fetch-mode': 'cors',
                'sec-fetch-site': 'same-origin',
                'shopify-checkout-client': 'checkout-web/1.0',
                'shopify-checkout-source': f'id="{checkout_token}", type="cn"',
                'user-agent': USER_AGENT,
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

            try:
                poll_resp = session.get(
                    f"{domain}/checkouts/internal/graphql/persisted",
                    params=poll_params,
                    headers=poll_headers,
                    timeout=timeout
                )
                poll_json = poll_resp.json()
                receipt_data = poll_json.get('data', {}).get('receipt', {})
                if receipt_data:
                    typename = receipt_data.get('__typename', '')
                    if typename == 'ProcessedReceipt':
                        return {
                            "success": True,
                            "status": "APPROVED",
                            "message": "Order placed successfully",
                            "details": {
                                "receipt_id": receipt_id,
                                "receipt_type": typename,
                                "amount": total_amount,
                                "currency": currency,
                                "polls_needed": poll_num
                            },
                            "time_taken": round(time.time() - start_time, 2)
                        }
                    elif typename == 'FailedReceipt':
                        error = receipt_data.get('processingError', {})
                        return {
                            "success": False,
                            "status": "DECLINED",
                            "message": error.get('message', 'Payment failed'),
                            "details": {
                                "receipt_id": receipt_id,
                                "receipt_type": typename,
                                "error_code": error.get('code'),
                                "error_details": error,
                                "polls_needed": poll_num
                            },
                            "time_taken": round(time.time() - start_time, 2)
                        }
                    elif typename == 'ActionRequiredReceipt':
                        return {
                            "success": False,
                            "status": "3DS_REQUIRED",
                            "message": "3DS authentication required",
                            "details": {
                                "receipt_id": receipt_id,
                                "receipt_type": typename,
                                "polls_needed": poll_num
                            },
                            "time_taken": round(time.time() - start_time, 2)
                        }
            except Exception:
                continue

    # Fallback error detection
    error_msg = extract_submit_error(submit_resp.text) or extract_any_error(submit_resp.text)
    if not error_msg:
        errors_list = submit_data.get('errors', [])
        if errors_list and isinstance(errors_list, list):
            error_msg = errors_list[0].get('message', 'Unknown GraphQL error')

    if error_msg:
        status_code = "DECLINED"
        if "3d" in error_msg.lower() or "action_required" in error_msg.lower():
            status_code = "3DS_REQUIRED"
        elif "captcha" in error_msg.lower() or "challenge" in error_msg.lower():
            status_code = "CAPTCHA_REQUIRED"
        return {
            "success": False,
            "status": status_code,
            "message": error_msg,
            "details": {
                "submit_response": submit_data
            },
            "time_taken": round(time.time() - start_time, 2)
        }

    return {
        "success": False,
        "status": "DECLINED",
        "message": "Transaction declined or receipt status could not be finalized",
        "details": {
            "receipt_id": receipt_id,
            "submit_response": submit_data
        },
        "time_taken": round(time.time() - start_time, 2)
    }
