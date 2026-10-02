import json
import logging
from shopify_engine import run_shopify_checkout, parse_card_string

logging.basicConfig(level=logging.INFO)

# Test site that had delivery changed
site = "113a8f-4f.myshopify.com"
card = "5456150015507529|03|2028|166"
card_num, card_m, card_y, card_cvv = parse_card_string(card)

res = run_shopify_checkout(
    domain=f"https://{site}",
    card_number=card_num,
    card_month=card_m,
    card_year=card_y,
    cvv=card_cvv,
    timeout=30
)

print("\n--- TEST RESULT ---")
print("Status:", res.get("status"))
print("Message:", res.get("message"))
if "details" in res:
    print("Details:", json.dumps(res.get("details"), indent=2)[:2000])
