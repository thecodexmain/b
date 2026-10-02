import json
import requests
import re
from shopify_engine import (
    normalize_url, SEC_CH_UA, USER_AGENT, FALLBACK_PROPOSAL_ID,
    extract_checkout_token, extract_session_token, extract_stable_id,
    extract_commit_sha, extract_identification_signature, patch_payload,
    extract_queue_token
)

site = "https://1441-wc-vip.myshopify.com"
session = requests.Session()

# 1. Cart
r = session.get(site + "/cart.js")
p_resp = session.get(site + "/products.json?limit=1")
products = p_resp.json().get('products', [])
variant_id = products[0]['variants'][0]['id']
var_price = str(products[0]['variants'][0]['price'])

session.post(site + "/cart/add.js", data={'id': variant_id, 'quantity': 1})
checkout_resp = session.get(site + "/checkout", allow_redirects=True)
checkout_url = checkout_resp.url
html_text = checkout_resp.text

checkout_token = extract_checkout_token(checkout_url, html_text)
session_token = extract_session_token(html_text)
stable_id = extract_stable_id(html_text) or "3348fc50-7477-4a60-a4a6-81ec082aba88"
queue_token1 = None

proposal_headers = {
    'accept': 'application/json',
    'content-type': 'application/json',
    'origin': site,
    'referer': checkout_url,
    'user-agent': USER_AGENT,
    'x-shopify-checkout-version': '2026-01-05',
}

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
            "merchandise": {"productVariantReference": {"id": f"gid://shopify/ProductVariantMerchandise/{variant_id}", "variantId": f"gid://shopify/ProductVariant/{variant_id}", "properties": [], "sellingPlanId": None, "sellingPlanDigest": None}},
            "quantity": {"items": {"value": 1}},
            "expectedTotalPrice": {"any": True}, "lineComponentsSource": None, "lineComponents": []
        }]
    },
    "memberships": {"memberships": []},
    "payment": {"totalAmount": {"any": True}, "paymentLines": [], "billingAddress": {"streetAddress": {"address1": "", "city": "", "countryCode": "US", "lastName": "", "phone": ""}}},
    "buyerIdentity": {"customer": {"presentmentCurrency": "USD", "countryCode": "US"}, "phoneCountryCode": "US", "marketingConsent": [], "shopPayOptInPhone": {"countryCode": "US"}, "rememberMe": False},
    "tip": {"tipLines": []}, "poNumber": None,
    "taxes": {"proposedAllocations": None, "proposedTotalAmount": {"any": True}, "proposedTotalIncludedAmount": None, "proposedMixedStateTotalAmount": None, "proposedExemptions": []},
    "note": {"message": None, "customAttributes": []},
    "localizationExtension": {"fields": []}, "nonNegotiableTerms": None,
    "scriptFingerprint": {"signature": None, "signatureUuid": None, "lineItemScriptChanges": [], "paymentScriptChanges": [], "shippingScriptChanges": []},
    "optionalDuties": {"buyerRefusesDuties": False}, "cartMetafields": []
}

p1_resp = session.post(f"{site}/checkouts/c/{checkout_token}/graphql", headers=proposal_headers, json={
    "variables": base_proposal, "operationName": "Proposal", "id": FALLBACK_PROPOSAL_ID
})
p1_data = p1_resp.json()
queue_token2 = extract_queue_token(p1_resp.text) or queue_token1

# Proposal 2
addr = {
    "first_name": "Python", "last_name": "Shelby", "address1": "St 82", "address2": "",
    "city": "Ny", "country_code": "US", "zone_code": "NY", "postal_code": "10010", "phone": "+12125551212"
}
prop2 = dict(base_proposal)
prop2["queueToken"] = queue_token2
prop2["buyerIdentity"]["email"] = "johnwilliams720@gmail.com"
prop2["delivery"]["deliveryLines"][0]["destination"] = {
    "streetAddress": {
        "address1": addr["address1"], "address2": addr["address2"],
        "city": addr["city"], "countryCode": addr["country_code"],
        "postalCode": addr["postal_code"], "firstName": addr["first_name"],
        "lastName": addr["last_name"], "zoneCode": addr["zone_code"],
        "phone": addr["phone"], "oneTimeUse": False
    }
}
prop2["payment"]["billingAddress"] = {
    "streetAddress": {
        "address1": addr["address1"], "address2": addr["address2"],
        "city": addr["city"], "countryCode": addr["country_code"],
        "postalCode": addr["postal_code"], "firstName": addr["first_name"],
        "lastName": addr["last_name"], "zoneCode": addr["zone_code"],
        "phone": addr["phone"]
    }
}
p2_resp = session.post(f"{site}/checkouts/c/{checkout_token}/graphql", headers=proposal_headers, json={
    "variables": prop2, "operationName": "Proposal", "id": FALLBACK_PROPOSAL_ID
})
p2_data = p2_resp.json()
queue_token3 = extract_queue_token(p2_resp.text) or queue_token2

# Proposal 3
prop3 = dict(prop2)
prop3["queueToken"] = queue_token3
p3_resp = session.post(f"{site}/checkouts/c/{checkout_token}/graphql", headers=proposal_headers, json={
    "variables": prop3, "operationName": "Proposal", "id": FALLBACK_PROPOSAL_ID
})
p3_data = p3_resp.json()

with open("p3_sample.json", "w", encoding="utf-8") as f:
    json.dump(p3_data, f, indent=2)

print("Saved p3_sample.json successfully!")
