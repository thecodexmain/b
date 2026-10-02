import requests
import re

r = requests.get('https://4ad7f7.myshopify.com/checkout')
urls = re.findall(r'https?://[^\'"]+actions[^\'"]+\.js', r.text)
if urls:
    print("Fetching:", urls[0])
    js = requests.get(urls[0]).text
    matches = re.findall(r'paymentMethodIdentifier[^\}]{0,100}', js)
    print("Matches for paymentMethodIdentifier:", len(matches))
    for m in matches[:5]:
        print(" ", m)

    matches2 = re.findall(r'directPaymentMethod[^\}]{0,100}', js)
    print("Matches for directPaymentMethod:", len(matches2))
    for m in matches2[:5]:
        print(" ", m)
