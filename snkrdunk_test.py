"""
snkrdunk Connectivity Test
驗證 GitHub Actions 的 Python requests 能不能打進 snkrdunk
不寫 D1、不推 Telegram、不解析。只看 status code 跟回傳 size
"""

import requests
import sys


# 試 4 個 URL,涵蓋首頁、商品頁、成交歷史頁、搜尋頁
TARGETS = [
    ("homepage", "https://snkrdunk.com/"),
    ("product", "https://snkrdunk.com/apparels/618442"),
    ("sales_history", "https://snkrdunk.com/apparels/618442/sales-histories"),
    ("search", "https://snkrdunk.com/search?keyword=%E3%83%94%E3%82%AB%E3%83%81%E3%83%A5%E3%82%A6"),
]

# 完整瀏覽器 headers,盡量擬真
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
    "Accept-Language": "ja,en-US;q=0.9,en;q=0.8,zh-TW;q=0.7",
    "Accept-Encoding": "gzip, deflate, br",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
    "Sec-Ch-Ua": '"Chromium";v="120", "Not_A Brand";v="8"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"macOS"',
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
}


def main():
    print("=" * 60)
    print("snkrdunk Connectivity Test")
    print("=" * 60)
    print()

    results = []
    for name, url in TARGETS:
        print(f"--- Testing {name} ---")
        print(f"URL: {url}")
        try:
            r = requests.get(url, headers=HEADERS, timeout=30, allow_redirects=True)
            print(f"Status: {r.status_code}")
            print(f"Final URL: {r.url}")
            print(f"Content size: {len(r.content):,} bytes")
            print(f"Content-Type: {r.headers.get('Content-Type', 'N/A')}")

            # 看回傳前 500 字元,判斷是 HTML、JSON、還是擋人頁
            preview = r.text[:500].replace("\n", " ")
            print(f"Preview: {preview}")

            results.append({
                "name": name,
                "status": r.status_code,
                "size": len(r.content),
            })
        except Exception as e:
            print(f"ERROR: {type(e).__name__}: {e}")
            results.append({
                "name": name,
                "status": "ERROR",
                "size": 0,
            })
        print()

    # 總結
    print("=" * 60)
    print("Summary")
    print("=" * 60)
    for r in results:
        flag = "✅" if r["status"] == 200 else "❌"
        print(f"{flag} {r['name']}: status={r['status']}, size={r['size']:,}")

    # 判斷
    print()
    success_count = sum(1 for r in results if r["status"] == 200)
    if success_count == len(TARGETS):
        print(f"🎉 全部 {len(TARGETS)} 個 endpoint 都通!可以繼續做爬蟲")
    elif success_count > 0:
        print(f"⚠️  部分通({success_count}/{len(TARGETS)})— 看哪些通的決定下一步")
    else:
        print("❌ 全部擋掉。需要換策略(playwright / 其他網站)")


if __name__ == "__main__":
    main()
