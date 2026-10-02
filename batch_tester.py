import sys
import re
import json
import time
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

# Direct engine import as high-reliability backend
from shopify_engine import run_shopify_checkout, parse_card_string

if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

SITES_FILE = "sample_sites.txt"
LOG_FILE = "log.txt"
API_URL = "http://127.0.0.1:8000/api/checkout"
TEST_CC = "5456150015507529|03|2028|166"
MAX_WORKERS = 6
TIMEOUT = 30

def extract_sites(file_path: str):
    sites = []
    with open(file_path, "r", encoding="utf-8") as f:
        for line in f:
            m = re.search(r'⭐\s*\d+\.\s*([a-zA-Z0-9\.\-_]+)', line)
            if m:
                sites.append(m.group(1).strip())
    return sites

def test_site(site: str, index: int, total: int):
    start = time.time()
    payload = {
        "site": site,
        "cc": TEST_CC,
        "timeout": 20
    }
    
    data = None
    method_used = "API"

    # Try local API first
    try:
        resp = requests.post(API_URL, json=payload, timeout=TIMEOUT)
        if resp.status_code == 200:
            data = resp.json()
    except Exception:
        pass

    # Fallback to direct engine call if API is busy or offline
    if not data:
        method_used = "DIRECT"
        try:
            card_num, card_m, card_y, card_cvv = parse_card_string(TEST_CC)
            data = run_shopify_checkout(
                domain=site,
                card_number=card_num,
                card_month=card_m,
                card_year=card_y,
                cvv=card_cvv,
                timeout=20
            )
        except Exception as e:
            duration = round(time.time() - start, 2)
            return {
                "index": index,
                "site": site,
                "status": "ERROR",
                "duration": duration,
                "message": str(e),
                "success": False,
                "method": method_used,
                "response": {"error": str(e)}
            }

    duration = round(time.time() - start, 2)
    status = data.get("status", "UNKNOWN")
    msg = data.get("message", "")
    return {
        "index": index,
        "site": site,
        "status": status,
        "duration": duration,
        "message": msg,
        "success": data.get("success", False),
        "method": method_used,
        "response": data
    }

def main():
    sites = extract_sites(SITES_FILE)
    total = len(sites)
    print(f"Loaded {total} sites to test.")
    print(f"Engine/API: {API_URL} (with fallback to direct engine)")
    print(f"Writing live results to {LOG_FILE}\n")

    with open(LOG_FILE, "w", encoding="utf-8") as log_f:
        log_f.write("="*65 + "\n")
        log_f.write("SHOPIFY BATCH SITE & CAPTCHA TEST RUN\n")
        log_f.write(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        log_f.write(f"Total Sites: {total}\n")
        log_f.write(f"Test Card: {TEST_CC}\n")
        log_f.write(f"Concurrency: {MAX_WORKERS} workers\n")
        log_f.write("="*65 + "\n\n")

    results = []
    captcha_sites = []
    locked_sites = []
    declined_sites = []
    no_product_sites = []
    error_sites = []
    
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_site = {
            executor.submit(test_site, site, idx + 1, total): (idx + 1, site)
            for idx, site in enumerate(sites)
        }
        
        completed_count = 0
        for future in as_completed(future_to_site):
            idx, site = future_to_site[future]
            try:
                res = future.result()
            except Exception as e:
                res = {
                    "index": idx,
                    "site": site,
                    "status": "EXCEPTION",
                    "duration": 0,
                    "message": str(e),
                    "success": False,
                    "method": "DIRECT",
                    "response": {"error": str(e)}
                }

            results.append(res)
            completed_count += 1
            status = res["status"]
            is_captcha = (status == "CAPTCHA_REQUIRED") or ("captcha" in res["message"].lower()) or ("challenge" in res["message"].lower())
            
            if is_captcha:
                captcha_sites.append(site)
                tag = "[CAPTCHA DETECTED]"
            elif status == "STORE_LOCKED":
                locked_sites.append(site)
                tag = "[STORE LOCKED]"
            elif status == "DECLINED":
                declined_sites.append(site)
                tag = "[DECLINED / REACHED GATEWAY]"
            elif status == "APPROVED":
                tag = "[APPROVED]"
            elif status == "NO_PRODUCTS":
                no_product_sites.append(site)
                tag = "[NO PRODUCTS]"
            else:
                error_sites.append(site)
                tag = f"[{status}]"

            print(f"[{completed_count:02d}/{total:02d}] #{res['index']:02d} {res['site']:<38} -> {tag:<28} ({res['duration']}s)")

            # Append to log.txt immediately
            with open(LOG_FILE, "a", encoding="utf-8") as log_f:
                log_f.write(f"--- [#{res['index']:02d}/{total:02d}] {res['site']} ---\n")
                log_f.write(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                log_f.write(f"Status: {res['status']}\n")
                log_f.write(f"Duration: {res['duration']}s\n")
                log_f.write(f"Message: {res['message']}\n")
                log_f.write(f"Captcha Detected: {'YES' if is_captcha else 'NO'}\n")
                log_f.write("Full Response:\n")
                log_f.write(json.dumps(res["response"], indent=2) + "\n\n")

    # Final summary in log
    with open(LOG_FILE, "a", encoding="utf-8") as log_f:
        log_f.write("\n" + "="*65 + "\n")
        log_f.write("FINAL SUMMARY OF RESULTS\n")
        log_f.write("="*65 + "\n")
        log_f.write(f"Total Sites Tested: {total}\n")
        log_f.write(f"Captcha Sites: {len(captcha_sites)}\n")
        log_f.write(f"Store Locked / Password: {len(locked_sites)}\n")
        log_f.write(f"Reached Gateway / Declined: {len(declined_sites)}\n")
        log_f.write(f"No Products Found: {len(no_product_sites)}\n")
        log_f.write(f"Other Errors: {len(error_sites)}\n\n")
        
        log_f.write("--- SITES REQUIRING CAPTCHA ---\n")
        if captcha_sites:
            for s in sorted(captcha_sites):
                log_f.write(f"  * {s}\n")
        else:
            log_f.write("  None\n")

        log_f.write("\n--- SITES PASSWORD PROTECTED / LOCKED ---\n")
        for s in sorted(locked_sites):
            log_f.write(f"  * {s}\n")

        log_f.write("\n--- SITES REACHED GATEWAY / PROCESSED ---\n")
        for s in sorted(declined_sites):
            log_f.write(f"  * {s}\n")
            
        log_f.write("="*65 + "\n")

    print("\n" + "="*50)
    print("BATCH RUN COMPLETE")
    print(f"Total Tested: {total}")
    print(f"Sites with CAPTCHA: {len(captcha_sites)}")
    for s in sorted(captcha_sites):
        print(f"  * {s}")
    print(f"Locked Stores: {len(locked_sites)}")
    print(f"Reached Gateway: {len(declined_sites)}")
    print(f"No Products Found: {len(no_product_sites)}")
    print(f"All full responses saved in {LOG_FILE}")

if __name__ == "__main__":
    main()
