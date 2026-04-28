"""
Yahoo 拍賣台灣 — HTML 爬蟲
URL 格式: https://tw.bid.yahoo.com/search/auction/product?ht={query}
注意:query parameter 是 ht 不是 p
"""

import re
import time
import requests
from bs4 import BeautifulSoup
from urllib.parse import quote


SEARCH_URL = "https://tw.bid.yahoo.com/search/auction/product?ht={query}"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# 商品 URL pattern: https://tw.bid.yahoo.com/item/{numeric_id}
ITEM_URL_PATTERN = re.compile(r"^https?://tw\.bid\.yahoo\.com/item/(\d+)")
# 找價格: $XXX 或 $X,XXX (取第一個出現的,通常就是現價)
PRICE_PATTERN = re.compile(r"\$\s*([\d,]+)")


def search(card):
    """
    回傳: [{"title": ..., "price": int, "seller": ..., "url": ...}, ...]
    """
    queries = card.get("search_keywords") or [card["name_zh"]]
    exclude = card.get("exclude_keywords", [])

    all_items = []
    for q in queries:
        try:
            items = _fetch_query(q, exclude)
            all_items.extend(items)
        except Exception as e:
            print(f"    [yahoo_tw] 查詢 '{q}' 失敗: {type(e).__name__}: {e}")
        # 不同 keyword 之間禮貌停 1 秒,避免被當成爆量
        time.sleep(1)

    # 用 url 去重
    seen = set()
    deduped = []
    for it in all_items:
        if it["url"] not in seen:
            seen.add(it["url"])
            deduped.append(it)

    return deduped


def _fetch_query(query, exclude_keywords):
    url = SEARCH_URL.format(query=quote(query))
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()

    soup = BeautifulSoup(r.text, "html.parser")
    items = []
    seen_ids = set()

    # 找所有指向 /item/{id} 的 <a>
    for a in soup.find_all("a", href=ITEM_URL_PATTERN):
        href = a.get("href", "")
        m = ITEM_URL_PATTERN.match(href)
        if not m:
            continue

        item_id = m.group(1)
        if item_id in seen_ids:
            continue
        seen_ids.add(item_id)

        # 標題:優先 img alt(乾淨),沒有就用文字
        title = ""
        img = a.find("img")
        if img and img.get("alt"):
            title = img["alt"].strip()

        # 整個 <a> 的文字
        text = a.get_text(" ", strip=True)

        # 價格
        price_match = PRICE_PATTERN.search(text)
        if not price_match:
            continue
        try:
            price = int(price_match.group(1).replace(",", ""))
        except ValueError:
            continue
        if price < 1:
            continue

        # 沒有 alt 就用 $ 前的文字當標題
        if not title:
            before_price = text[: price_match.start()].strip()
            # 取最後 100 字以內(避免抓到一堆 seller name)
            title = before_price[-100:].strip() if before_price else ""

        if not title:
            continue

        # 排除關鍵字過濾
        title_lower = title.lower()
        if any(kw and kw.lower() in title_lower for kw in exclude_keywords):
            continue

        items.append({
            "title": title,
            "price": price,
            "seller": "",  # 之後可以再加,先空
            "url": f"https://tw.bid.yahoo.com/item/{item_id}",
        })

    return items
