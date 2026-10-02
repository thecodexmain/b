import json
import logging
from shopify_engine import run_shopify_checkout, parse_card_string

# Let's inspect submit response on 113a8f-4f
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

with open("debug_113_res.json", "w", encoding="utf-8") as f:
    json.dump(res, f, indent=2)

print("Saved debug_113_res.json")
