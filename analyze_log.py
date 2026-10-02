import re
from collections import Counter

with open('log.txt', 'r', encoding='utf-8', errors='ignore') as f:
    text = f.read()

# Let's find all entries with INVALID_VARIABLE
sites = re.findall(r'--- \[#\d+/\d+\] ([\w\.-]+) ---\nTimestamp: [^\n]+\nStatus: [^\n]+\nDuration: [^\n]+\nMessage: ([^\n]+)', text)

invalid_var_sites = []
delivery_detail_sites = []

for site, msg in sites:
    if 'INVALID_VARIABLE' in msg:
        invalid_var_sites.append(site)
    elif 'Some delivery details may have changed' in msg:
        delivery_detail_sites.append(site)

print(f"Total sites: {len(sites)}")
print(f"INVALID_VARIABLE ({len(invalid_var_sites)}): {invalid_var_sites}")
print(f"DELIVERY_CHANGED ({len(delivery_detail_sites)}): {delivery_detail_sites}")

# Now let's extract the exact error messages for INVALID_VARIABLE
err_msgs = re.findall(r'Variable \$input of type NegotiationInput! was provided invalid value for [^\"]+', text)
print("\nUnique INVALID_VARIABLE errors:")
for m, c in Counter(err_msgs).most_common():
    print(f"[{c}] {m}")
