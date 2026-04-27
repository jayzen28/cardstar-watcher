"""
CARDSTAR Price Watcher v0.2
直接打露天 API（穩定、回傳 JSON）+ Telegram 推播

v0.2 變更:
- 移除 BigGo HTML 爬取（動態載入抓不到）
- 改用露天 (Ruten) 公開搜尋 API,直接拿 JSON
- 商品 ID 列表 → 商品詳情批次查詢
- 更精準的價格、賣家資訊

使用方式:
    1. 設環境變數 TELEGRAM_TOKEN 和 TELEGRAM_CHAT_ID
    2. python3 watcher.py
"""

import os
import json
import time
import sys
from datetime import datetime
from urllib.parse import quote
import requests

# ===== 設定 =====
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

# 每張卡顯示前 N 個最低標價
TOP_N_RESULTS = 5

# 每個關鍵字最多抓 N 個商品 (露天 API 最多 100)
MAX_PER_KEYWORD = 50

# 請求間隔（秒）
REQUEST_DELAY = 2

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-TW,zh;q=0.9",
    "Origin": "https://www.ruten.com.tw",
    "Referer": "https://www.ruten.com.tw/",
}


# ===== 露天 API =====
def search_ruten(keyword, exclude_keywords=None, limit=MAX_PER_KEYWORD):
    """
    用露天 API 搜尋商品

    流程:
    1. /search/v3/index.php/core/prod 拿到符合的商品 ID 列表
    2. /search/v3/index.php/core/seller 批次查詢這些 ID 的詳情

    回傳: [{title, price, source, url, seller}, ...]
    """
    exclude_keywords = exclude_keywords or []
    results = []

    # ===== 階段 1: 搜商品 ID =====
    search_url = "https://rtapi.ruten.com.tw/api/search/v3/index.php/core/prod"
    search_params = {
        "q": keyword,
        "type": "direct",
        "sort": "prc/ac",  # 價格由低到高
        "limit": limit,
        "offset": 1,
    }

    try:
        r = requests.get(search_url, params=search_params, headers=HEADERS, timeout=20)
        if r.status_code != 200:
            print(f"  [Ruten search] {keyword}: HTTP {r.status_code}")
            return results

        data = r.json()
        items = data.get("Rows", [])
        if not items:
            return results

        item_ids = [item["Id"] for item in items if item.get("Id")]
        if not item_ids:
            return results

    except Exception as e:
        print(f"  [Ruten search] {keyword} 失敗: {e}")
        return results

    # ===== 階段 2: 批次查詢商品詳情 =====
    # 露天 API 一次最多 50 個 ID
    BATCH_SIZE = 50
    detail_url = "https://rtapi.ruten.com.tw/api/items/v2/list"

    all_details = []
    for i in range(0, len(item_ids), BATCH_SIZE):
        batch = item_ids[i:i+BATCH_SIZE]
        try:
            r = requests.get(
                detail_url,
                params={"gno": ",".join(batch)},
                headers=HEADERS,
                timeout=20
            )
            if r.status_code != 200:
                print(f"  [Ruten detail] batch {i}: HTTP {r.status_code}")
                continue

            details = r.json()
            if isinstance(details, list):
                all_details.extend(details)
            time.sleep(0.5)
        except Exception as e:
            print(f"  [Ruten detail] batch {i} 失敗: {e}")
            continue

    # ===== 階段 3: 整理結果 =====
    for item in all_details:
        try:
            title = item.get("ProdName", "")
            if not title:
                continue

            # 排除關鍵字過濾
            if any(ex in title for ex in exclude_keywords):
                continue

            # 取直購價（PriceRange 的最低值），沒有就用 OpeningPrice
            price = None
            price_range = item.get("PriceRange", [])
            if price_range and isinstance(price_range, list):
                price = price_range[0]
            if not price:
                price = item.get("DirectPrice") or item.get("OpeningPrice")
            if not price:
                continue

            try:
                price = int(price)
            except (TypeError, ValueError):
                continue

            if price < 10:
                continue

            seller = item.get("UserId") or item.get("SellerNick") or "未知"
            item_id = item.get("ProdId") or item.get("Id", "")
            url = f"https://www.ruten.com.tw/item/show?{item_id}"

            results.append({
                "title": title[:60],
                "price": price,
                "source": "露天",
                "seller": seller,
                "url": url,
            })

        except Exception:
            continue

    results.sort(key=lambda x: x["price"])
    return results


# ===== Telegram 推播 =====
def send_telegram(text):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("\n⚠️ 未設定 TELEGRAM_TOKEN 或 TELEGRAM_CHAT_ID,跳過推播")
        print("=== 訊息內容 ===")
        print(text)
        print("================\n")
        return

    api = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    chunks = [text[i:i+4000] for i in range(0, len(text), 4000)]

    for chunk in chunks:
        try:
            r = requests.post(api, json={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": chunk,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            }, timeout=15)
            if r.status_code != 200:
                print(f"Telegram 推送失敗: {r.status_code} {r.text[:200]}")
        except Exception as e:
            print(f"Telegram 推送異常: {e}")
        time.sleep(0.5)


# ===== 報告產生 =====
def format_report(card, results):
    market_flag = {"TW": "🇹🇼", "HK": "🇭🇰", "JP": "🇯🇵"}.get(
        card.get("primary_market", ""), "🌐"
    )

    if not results:
        return f"{market_flag} <b>{card['name_zh']}</b>\n❌ 本次未抓到資料\n"

    top = results[:TOP_N_RESULTS]
    lowest = top[0]["price"]
    highest = top[-1]["price"]
    spread = (highest - lowest) / lowest if lowest > 0 else 0

    lines = [f"{market_flag} <b>{card['name_zh']}</b>"]
    if card.get("card_no"):
        lines.append(f"<code>{card['card_no']}</code>")
    lines.append(f"露天前 {len(top)} 個最低標價（價差 {spread:.0%}）：")
    lines.append("")

    for i, item in enumerate(top, 1):
        title = item["title"][:35] + ("…" if len(item["title"]) > 35 else "")
        lines.append(
            f"<b>{i}. NT$ {item['price']:,}</b>\n"
            f"   {title}\n"
            f"   賣家: {item['seller']}\n"
            f"   <a href=\"{item['url']}\">→ 查看</a>"
        )
        lines.append("")

    return "\n".join(lines)


# ===== 主流程 =====
def main():
    cards_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cards.json")
    with open(cards_file, encoding="utf-8") as f:
        cards = json.load(f)

    print(f"=== CARDSTAR Watcher v0.2 開始執行 ===")
    print(f"時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"監控卡片: {len(cards)} 張")
    print(f"資料來源: 露天 (Ruten) API\n")

    msg_parts = [
        f"🎴 <b>CARDSTAR 監控報告 v0.2</b>",
        f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"📡 來源: 露天 Ruten",
        f"━━━━━━━━━━━━━━━━",
        ""
    ]

    total_found = 0
    for card in cards:
        print(f"▶ 搜尋: {card['name_zh']}")
        all_results = []

        for kw in card["search_keywords"]:
            results = search_ruten(kw, card.get("exclude_keywords", []))
            all_results.extend(results)
            print(f"  關鍵字「{kw}」抓到 {len(results)} 筆")
            time.sleep(REQUEST_DELAY)

        # 用商品 URL 去重
        seen = set()
        unique = []
        for r in all_results:
            if r["url"] not in seen:
                seen.add(r["url"])
                unique.append(r)
        unique.sort(key=lambda x: x["price"])

        total_found += len(unique)
        msg_parts.append(format_report(card, unique))
        msg_parts.append("━━━━━━━━━━━━━━━━")

    msg_parts.append(f"\n✅ 共抓到 {total_found} 筆")
    full_message = "\n".join(msg_parts)

    print(f"\n=== 抓取完成,共 {total_found} 筆 ===")
    print("正在推送到 Telegram...")
    send_telegram(full_message)
    print("✅ 完成")


if __name__ == "__main__":
    main()
