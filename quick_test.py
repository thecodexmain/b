import json
from shopify_engine import run_shopify_checkout, parse_card_string

# Test with 113a8f-4f
card_num, card_m, card_y, card_cvv = parse_card_string('5456150015507529|03|2028|166')
res = run_shopify_checkout(
    domain='https://113a8f-4f.myshopify.com',
    card_number=card_num,
    card_month=card_m,
    card_year=card_y,
    cvv=card_cvv,
    timeout=25
)
print("Result message:", res.get("message"))
if "errors" in str(res):
    print("Errors found in res!")
