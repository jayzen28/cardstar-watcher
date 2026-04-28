"""
snkrdunk Inspection
打一次寶可夢搜尋頁,把 HTML 存到 artifact,並印出關鍵線索
"""

import re
import os
import requests


SEARCH_URL = "https://snkrdunk.com/search?keyword=%E3%83%9D%E3%82%B1%E3%83%A2%E3%83%B3%E3%82%AB%E3%83%BC%E3%83%89"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/avif,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Sec-Ch-Ua": '"Chromium";v="120", "Not_A Brand";v="8"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"macOS"',
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Upgrade-Insecure-Requests": "1",
}

# 一些可能的 alternative URL,連續打看哪個是 SSR
ALTERNATIVE_URLS = [
    # 主搜尋頁(已知是 SPA)
    ("search_pokemon", "https://snkrdunk.com/search?keyword=%E3%83%9D%E3%82%B1%E3%83%A2%E3%83%B3%E3%82%AB%E3%83%BC%E3%83%89"),
    # 卡牌專屬 listing 頁(猜的)
    ("trading_cards", "https://snkrdunk.com/trading-cards"),
    # 寶可夢分類首頁(猜的)
    ("category_pokemon", "https://snkrdunk.com/category/pokemon"),
    # ranking 頁(猜的)
    ("ranking", "https://snkrdunk.com/ranking"),
    # 人氣 pokemon 文章頁(從之前搜尋結果出現過,可能是 SSR)
    ("article_pokemon_psa10", "https://snkrdunk.com/articles/30531/"),
]


def main():
    os.makedirs("dumps", exist_ok=True)

    print("=" * 60)
    print("snkrdunk Inspection")
    print("=" * 60)

    for name, url in ALTERNATIVE_URLS:
        print(f"\n--- [{name}] {url}")
        try:
            r = requests.get(url, headers=HEADERS, timeout=30, allow_redirects=True)
            print(f"  Status: {r.status_code}")
            print(f"  Final URL: {r.url}")
            print(f"  Size: {len(r.content):,} bytes")
        except Exception as e:
            print(f"  ERROR: {type(e).__name__}: {e}")
            continue

        if r.status_code != 200:
            continue

        html = r.text
        # dump 完整 HTML
        path = f"dumps/{name}.html"
        with open(path, "w", encoding="utf-8") as f:
            f.write(html)
        print(f"  Saved: {path}")

        # 找線索
        clues(html)


def clues(html):
    """印關鍵線索:apparel 連結數、可能的 API endpoint、Next.js data 是否存在"""
    # 1. apparel 連結
    apparel_count = len(re.findall(r"/apparels/\d+", html))
    print(f"  '/apparels/{{id}}' 連結數: {apparel_count}")

    # 2. 找 __NEXT_DATA__(Next.js 把整個 page state JSON 塞這裡)
    next_data = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL)
    if next_data:
        nd = next_data.group(1)
        print(f"  __NEXT_DATA__ 存在! size: {len(nd):,} bytes")
        # 在 NEXT_DATA 裡找 apparel id
        nd_apparel = len(re.findall(r'"id":\s*\d{5,}', nd))
        print(f"    NEXT_DATA 內 numeric IDs (>=5digits): {nd_apparel}")
    else:
        print("  __NEXT_DATA__ 不存在")

    # 3. 找 API endpoint 線索(/api/...)
    api_endpoints = set(re.findall(r'["\'](/api/[a-z_/\-]+)', html))
    if api_endpoints:
        print(f"  發現 API endpoints({len(api_endpoints)} 個):")
        for ep in sorted(api_endpoints)[:10]:
            print(f"    {ep}")

    # 4. 找完整的 https URL 中的 API
    full_apis = set(re.findall(r'https?://[a-z.]+/api/[a-z_/\-]+', html))
    if full_apis:
        print(f"  發現完整 API URLs({len(full_apis)} 個):")
        for ep in sorted(full_apis)[:5]:
            print(f"    {ep}")


if __name__ == "__main__":
    main()
    print("\n" + "=" * 60)
    print("Inspection 完成。HTML 已存 dumps/ 資料夾,workflow 會上傳 artifact")
    print("=" * 60)
