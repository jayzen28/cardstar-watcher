"""
snkrdunk Discovery Script
探索每個分類的熱門卡片,抓:
- 商品基本資料(從 JSON-LD)
- 30 天成交歷史(從 sales-histories 頁)

輸出純報表,不寫 D1、不推 Telegram
"""

import re
import json
import time
import requests
from bs4 import BeautifulSoup


# 兩個分類的搜尋詞
SEARCHES = [
    {
        "category": "pokemon",
        "label": "寶可夢卡",
        # snkrdunk 的卡牌都在 trading-cards 這個 category
        # keyword 用日文「ポケモンカード」效果最好
        "search_url": "https://snkrdunk.com/search?keyword=%E3%83%9D%E3%82%B1%E3%83%A2%E3%83%B3%E3%82%AB%E3%83%BC%E3%83%89",
    },
    {
        "category": "one_piece",
        "label": "海賊王卡",
        # 「ワンピースカード」
        "search_url": "https://snkrdunk.com/search?keyword=%E3%83%AF%E3%83%B3%E3%83%94%E3%83%BC%E3%82%B9%E3%82%AB%E3%83%BC%E3%83%89",
    },
]

TOP_N = 10  # 每個分類取前 10 張卡

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

# 商品連結 pattern: /apparels/{numeric_id}
APPAREL_LINK_PATTERN = re.compile(r"/apparels/(\d+)(?:\?|$|/|#)")


def fetch(url):
    """簡單包一層 GET,加上錯誤處理"""
    r = requests.get(url, headers=HEADERS, timeout=30, allow_redirects=True)
    r.raise_for_status()
    return r.text


def find_apparel_ids(search_url, limit=TOP_N):
    """從搜尋頁抓出商品 ID,保留出現順序(熱門排序),最多 limit 個"""
    print(f"[search] {search_url}")
    html = fetch(search_url)
    print(f"[search] HTML size: {len(html):,} bytes")

    # 從整個 HTML 用 regex 撈 /apparels/{id}
    # 保留首次出現順序
    seen = []
    for m in APPAREL_LINK_PATTERN.finditer(html):
        aid = m.group(1)
        if aid not in seen:
            seen.append(aid)
        if len(seen) >= limit:
            break

    print(f"[search] 找到 {len(seen)} 個 apparel IDs: {seen}")
    return seen


def parse_jsonld(html):
    """從 HTML 抓所有 <script type='application/ld+json'> 並 parse 成 list of dicts"""
    soup = BeautifulSoup(html, "html.parser")
    results = []
    for tag in soup.find_all("script", attrs={"type": "application/ld+json"}):
        text = tag.string or tag.get_text() or ""
        text = text.strip()
        if not text:
            continue
        try:
            data = json.loads(text)
            results.append(data)
        except json.JSONDecodeError:
            # snkrdunk 有時會有 @graph 用奇怪格式
            continue
    return results


def extract_product_info(jsonld_list):
    """
    從 JSON-LD list 萃取商品資訊
    snkrdunk 通常用 @graph 結構,裡面包含 Organization、Product、BreadcrumbList 等
    我們要的是 Product
    """
    info = {
        "name": None,
        "image": None,
        "low_price": None,
        "high_price": None,
        "currency": None,
        "offer_count": None,
        "aggregate_rating": None,
        "review_count": None,
    }

    for data in jsonld_list:
        # 可能是單一 dict 或 @graph 包多個
        items = []
        if isinstance(data, dict):
            if "@graph" in data:
                items = data["@graph"]
            else:
                items = [data]
        elif isinstance(data, list):
            items = data

        for item in items:
            if not isinstance(item, dict):
                continue
            t = item.get("@type")
            if t == "Product":
                info["name"] = item.get("name") or info["name"]
                # image 可能是 string 或 list
                img = item.get("image")
                if isinstance(img, list) and img:
                    info["image"] = img[0]
                elif isinstance(img, str):
                    info["image"] = img

                # offers 通常是 AggregateOffer
                offers = item.get("offers", {})
                if isinstance(offers, dict):
                    info["low_price"] = offers.get("lowPrice") or info["low_price"]
                    info["high_price"] = offers.get("highPrice") or info["high_price"]
                    info["currency"] = offers.get("priceCurrency") or info["currency"]
                    info["offer_count"] = offers.get("offerCount") or info["offer_count"]

                # 評價 + 評論數
                rating = item.get("aggregateRating", {})
                if isinstance(rating, dict):
                    info["aggregate_rating"] = rating.get("ratingValue") or info["aggregate_rating"]
                    info["review_count"] = rating.get("reviewCount") or info["review_count"]

    return info


def parse_sales_history(html):
    """
    從成交歷史頁抓最近 N 筆成交。
    這個是探索性質 — 我們不知道實際 HTML 結構,所以印出多種可能的線索讓我們判斷。
    """
    soup = BeautifulSoup(html, "html.parser")
    findings = {
        "tables_count": len(soup.find_all("table")),
        "scripts_with_data": 0,
        "raw_price_mentions": 0,
        "sample_text": "",
    }

    # 找 ¥ 出現次數(成交價慣例)
    text = soup.get_text(" ", strip=True)
    findings["raw_price_mentions"] = text.count("¥")

    # 找 __NEXT_DATA__ script(Next.js SSR 會把資料塞這裡)
    for tag in soup.find_all("script"):
        s = tag.get("id") or ""
        if "NEXT_DATA" in s or "__NUXT__" in s:
            findings["scripts_with_data"] += 1

    # 文字 sample,能看到表格結構
    findings["sample_text"] = text[:600]

    return findings


def explore_one_card(apparel_id):
    """對一張卡:打 product page + sales history page,印出能拿到的資料"""
    print(f"\n  ─ apparel {apparel_id} ─")

    # Product page
    try:
        url = f"https://snkrdunk.com/apparels/{apparel_id}"
        html = fetch(url)
        jsonld = parse_jsonld(html)
        info = extract_product_info(jsonld)
        print(f"    📦 {info['name']}")
        print(f"       價格區間: ¥{info['low_price']} - ¥{info['high_price']} ({info['currency']})")
        print(f"       目前掛賣: {info['offer_count']} 件")
        print(f"       評價: {info['aggregate_rating']} ({info['review_count']} 則)")
        print(f"       圖片: {info['image']}")
    except Exception as e:
        print(f"    ✗ Product page 失敗: {type(e).__name__}: {e}")

    time.sleep(1)  # 禮貌間隔

    # Sales history page
    try:
        url = f"https://snkrdunk.com/apparels/{apparel_id}/sales-histories"
        html = fetch(url)
        findings = parse_sales_history(html)
        print(f"    📊 成交歷史頁(原始探勘):")
        print(f"       <table> 數: {findings['tables_count']}")
        print(f"       Next.js data scripts: {findings['scripts_with_data']}")
        print(f"       ¥ 出現次數: {findings['raw_price_mentions']}")
        # 印部分 text 樣本(短)
        sample = findings['sample_text'][:300].replace("\n", " ")
        print(f"       Sample text: {sample}...")
    except Exception as e:
        print(f"    ✗ Sales history 失敗: {type(e).__name__}: {e}")

    time.sleep(1)


def main():
    print("=" * 60)
    print(f"snkrdunk Discovery — {time.strftime('%Y-%m-%d %H:%M')}")
    print(f"目標:每個分類抓前 {TOP_N} 張熱門卡")
    print("=" * 60)

    for cfg in SEARCHES:
        print(f"\n{'#' * 60}")
        print(f"# {cfg['label']} ({cfg['category']})")
        print(f"{'#' * 60}")

        try:
            apparel_ids = find_apparel_ids(cfg["search_url"], limit=TOP_N)
        except Exception as e:
            print(f"✗ 搜尋失敗: {type(e).__name__}: {e}")
            continue

        if not apparel_ids:
            print("✗ 沒撈到任何 apparel ID — 搜尋頁結構可能跟預期不一樣")
            continue

        for aid in apparel_ids:
            try:
                explore_one_card(aid)
            except Exception as e:
                print(f"  ✗ apparel {aid} 整個失敗: {type(e).__name__}: {e}")

    print(f"\n{'=' * 60}")
    print("Done.")
    print("=" * 60)


if __name__ == "__main__":
    main()
