import json
from shopify_engine import run_shopify_checkout, parse_card_string

sites = [
    '113a8f-4f.myshopify.com',
    '4ad7f7.myshopify.com',
    'annika-martin.myshopify.com',
    'arccos-golf-uk.myshopify.com',
    'baby-box-llcc.myshopify.com'
]

card = "5456150015507529|03|2028|166"
card_num, card_m, card_y, card_cvv = parse_card_string(card)

for site in sites:
    print(f"\n--- TESTING {site} ---")
    res = run_shopify_checkout(
        domain=f"https://{site}",
        card_number=card_num,
        card_month=card_m,
        card_year=card_y,
        cvv=card_cvv,
        timeout=25
    )
    print("Status:", res.get("status"))
    print("Message:", res.get("message"))
    sr = res.get("details", {}).get("submit_response", {})
    if sr:
        sfc = sr.get("data", {}).get("submitForCompletion", {})
        print("Submit Typename:", sfc.get("__typename"))
        if sfc.get("errors"):
            print("Errors:", [e.get("code") or e.get("message") for e in sfc.get("errors", [])])
    elif "receipt_type" in res.get("details", {}):
        print("Receipt Type:", res["details"]["receipt_type"])
