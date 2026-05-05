"""One-shot debug: fetch a snkrdunk page and dump all image-related data"""
import requests
from bs4 import BeautifulSoup
import json, re

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

# Test with a known card
url = "https://snkrdunk.com/apparels/104784"
print(f"Fetching {url}")
r = requests.get(url, headers={"User-Agent": UA}, timeout=30)
print(f"HTTP {r.status_code}, {len(r.text)} bytes")

soup = BeautifulSoup(r.text, "html.parser")

# 1. All meta tags with image
print("\n=== META TAGS ===")
for meta in soup.find_all("meta"):
    p = meta.get("property", "") or meta.get("name", "")
    c = meta.get("content", "")
    if "image" in p.lower() or "image" in c.lower() or "og:" in p:
        print(f"  {p}: {c[:200]}")

# 2. All JSON-LD
print("\n=== JSON-LD ===")
for script in soup.find_all("script", type="application/ld+json"):
    try:
        jd = json.loads(script.string)
        print(json.dumps(jd, indent=2, ensure_ascii=False)[:1000])
    except:
        print(f"  (parse error) {script.string[:200]}")

# 3. All img tags
print("\n=== IMG TAGS (first 20) ===")
for img in soup.find_all("img")[:20]:
    src = img.get("src", "")
    alt = img.get("alt", "")
    print(f"  src={src[:150]}")
    if alt:
        print(f"  alt={alt[:100]}")

# 4. CDN URLs in full text
print("\n=== CDN URLS ===")
for m in re.finditer(r'(https?://cdn[.\w]+/[^\s"\'<>]+)', r.text):
    print(f"  {m.group(1)[:200]}")

# 5. Any background-image in styles
print("\n=== BACKGROUND IMAGES ===")
for m in re.finditer(r'background-image:\s*url\(([^)]+)\)', r.text):
    print(f"  {m.group(1)[:200]}")
