"""
Cloudflare D1 寫入
透過 HTTP API 把 listings 寫入 prices 表
"""

import os
import requests


# D1 query API endpoint
def _endpoint():
    account_id = os.environ["CF_ACCOUNT_ID"]
    database_id = os.environ["CF_D1_DATABASE_ID"]
    return f"https://api.cloudflare.com/client/v4/accounts/{account_id}/d1/database/{database_id}/query"


def _headers():
    token = os.environ["CF_D1_TOKEN"]
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }


# 來源是哪一國的幣別
CURRENCY_BY_SOURCE = {
    "yahoo_tw": "TWD",
    "ruten": "TWD",
    "fb_groups": "TWD",
    # 之後加日本來源就在這加 "hareruya2": "JPY", 等等
}


def write_listings(listings, scraped_at):
    """
    listings: [(card, source_name, listing_dict), ...]
    回傳:成功寫入的筆數
    """
    if not listings:
        return 0

    written = 0
    BATCH = 50  # 每次最多 50 筆,避免單一 query 過大

    for i in range(0, len(listings), BATCH):
        chunk = listings[i:i + BATCH]
        n = _write_batch(chunk, scraped_at)
        written += n

    return written


def _write_batch(chunk, scraped_at):
    placeholders = []
    params = []

    for card, source_name, listing in chunk:
        placeholders.append("(?, ?, ?, ?, ?, ?, ?, ?)")
        currency = CURRENCY_BY_SOURCE.get(source_name, "")
        params.extend([
            card["id"],
            source_name,
            (listing.get("title") or "")[:500],
            int(listing.get("price") or 0),
            currency,
            (listing.get("seller") or "")[:200],
            (listing.get("url") or "")[:500],
            scraped_at,
        ])

    sql = (
        "INSERT INTO prices "
        "(card_id, source, title, price, currency, seller, url, scraped_at) "
        "VALUES " + ", ".join(placeholders)
    )

    payload = {"sql": sql, "params": params}
    r = requests.post(_endpoint(), headers=_headers(), json=payload, timeout=60)

    if r.status_code != 200:
        # 印出錯誤訊息前 500 字幫助 debug
        raise RuntimeError(
            f"D1 API 回 {r.status_code}: {r.text[:500]}"
        )

    result = r.json()
    if not result.get("success"):
        raise RuntimeError(f"D1 success=false: {str(result)[:500]}")

    return len(chunk)
