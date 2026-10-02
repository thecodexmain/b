import json
from shopify_engine import run_shopify_checkout

sites = [
    '113a8f-4f.myshopify.com',
    '132461-96.myshopify.com',
    '1441-wc-vip.myshopify.com',
    '1776-industries-llc.myshopify.com',
    '18bhyc-zn.myshopify.com',
    '1ab4ab.myshopify.com',
    '1lss-store.myshopify.com',
    '2d0369-6f.myshopify.com',
    '3duxdesign.myshopify.com'
]

for s in sites:
    res = run_shopify_checkout(site=s, card_number='5456150015507529', card_month=3, card_year=2028, cvv='166', timeout=15)
    print(f"{s:<35} -> {res.get('status')} | {res.get('message')}")
