"""
CARDSTAR Price Watcher v0.1
爬 BigGo 多卡片價格 + Telegram 推播

使用方式：
    1. 設定環境變數 TELEGRAM_TOKEN 和 TELEGRAM_CHAT_ID
    2. python3 watcher.py

需要套件：requests, beautifulsoup4, lxml
"""

import os
import json
import time
import re
import sys
from datetime import datetime
from urllib.parse import quote
import requests
from bs4 import BeautifulSoup

# ===== 設定 =====
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

# 推播門檻：價格分布 = (最高價 - 最低價) / 最低價
# 超過這個百分比才推播,避免雜訊
ALERT_THRESHOLD = 0.10  # 10%

# 每張卡顯示前 N 個最低標價
TOP_N_RESULTS = 5

# 請求間隔（秒），避免被反爬
REQUEST_DELAY = 3

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
}


# ===== BigGo 爬蟲 =====
def search_biggo(keyword, exclude_keywords=None):
    """
    在 BigGo 搜尋商品，回傳 [{title, price, source, url}, ...]

    BigGo 的搜尋頁是 https://biggo.com.tw/s/{keyword}/
    商品結構大致為 .item__container，含標題、價格、賣場
    """
    exclude_keywords = exclude_keywords or []
    url = f"https://biggo.com.tw/s/{quote(keyword)}/"
    results = []

    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
        if r.status_code != 200:
            print(f"  [BigGo] {keyword}: HTTP {r.status_code}")
            return results

        soup = BeautifulSoup(r.text, "lxml")

        # BigGo 的 HTML 結構會變，這裡用多個 selector 嘗試
        # 主要用 itemprops 或 data attributes 來抓
        items = soup.select('[itemprop="itemOffered"]') or \
                soup.select('.item__container') or \
                soup.select('article[data-item]') or \
                soup.select('a[href*="/item/"]')

        for item in items[:30]:  # 取前 30 筆，過濾後再篩
            try:
                # 嘗試多個欄位抓標題
                title_el = item.select_one('[itemprop="name"]') or \
                           item.select_one('.title') or \
                           item.select_one('h3') or \
                           item.select_one('h2')
                title = title_el.get_text(strip=True) if title_el else ""

                if not title:
                    # 從 alt 或 aria-label 抓
                    img = item.select_one('img')
                    if img:
                        title = img.get('alt', '') or img.get('title', '')

                if not title:
                    continue

                # 排除關鍵字過濾
                if any(ex in title for ex in exclude_keywords):
                    continue

                # 抓價格
                price_el = item.select_one('[itemprop="price"]') or \
                           item.select_one('.price') or \
                           item.select_one('[class*="price"]')
                price_text = price_el.get_text(strip=True) if price_el else ""
                # 從 content 屬性抓更準
                if price_el and price_el.get('content'):
                    price_text = price_el.get('content')

                price_match = re.search(r'[\d,]+', price_text.replace(',', ''))
                if not price_match:
                    continue
                price = int(price_match.group().replace(',', ''))
                if price < 10:  # 太低的可能是抓錯
                    continue

                # 抓來源（蝦皮/露天/Ruten/etc）
                source_el = item.select_one('.source') or \
                            item.select_one('[class*="shop"]') or \
                            item.select_one('[class*="store"]')
                source = source_el.get_text(strip=True) if source_el else "BigGo"

                # 抓連結
                link_el = item.select_one('a[href]')
                link = link_el.get('href', '') if link_el else ""
                if link.startswith('/'):
                    link = "https://biggo.com.tw" + link

                results.append({
                    "title": title[:60],
                    "price": price,
                    "source": source[:20],
                    "url": link,
                })

            except Exception as e:
                continue

        # 依價格排序
        results.sort(key=lambda x: x['price'])

    except Exception as e:
        print(f"  [BigGo] {keyword} 爬取失敗: {e}")

    return results


# ===== Telegram 推播 =====
def send_telegram(text):
    """推送訊息到 Telegram"""
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("\n⚠️ 未設定 TELEGRAM_TOKEN 或 TELEGRAM_CHAT_ID,跳過推播")
        print("=== 訊息內容 ===")
        print(text)
        print("================\n")
        return

    api = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    # Telegram 訊息最長 4096 字元,超過要拆
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
    """為單張卡片產生 Telegram 訊息"""
    market_flag = {"TW": "🇹🇼", "HK": "🇭🇰", "JP": "🇯🇵"}.get(
        card.get("primary_market", ""), "🌐"
    )

    if not results:
        return f"{market_flag} <b>{card['name_zh']}</b>\n❌ 本次未抓到資料\n"

    top = results[:TOP_N_RESULTS]
    lowest = top[0]['price']
    highest_in_top = top[-1]['price']
    spread = (highest_in_top - lowest) / lowest if lowest > 0 else 0

    lines = [f"{market_flag} <b>{card['name_zh']}</b>"]
    if card.get('card_no'):
        lines.append(f"<code>{card['card_no']}</code>")
    lines.append(f"前 {len(top)} 個最低標價（價差 {spread:.0%}）：")
    lines.append("")

    for i, item in enumerate(top, 1):
        title = item['title'][:35] + ("…" if len(item['title']) > 35 else "")
        lines.append(
            f"{i}. NT$ {item['price']:,} | {item['source']}\n"
            f"   {title}\n"
            f"   <a href=\"{item['url']}\">→ 查看</a>"
        )
        lines.append("")

    return "\n".join(lines)


# ===== 主流程 =====
def main():
    # 載入卡片清單
    with open(os.path.join(os.path.dirname(__file__), "cards.json"), encoding="utf-8") as f:
        cards = json.load(f)

    print(f"=== CARDSTAR Watcher 開始執行 ===")
    print(f"時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"監控卡片: {len(cards)} 張\n")

    # 訊息開頭
    msg_parts = [
        f"🎴 <b>CARDSTAR 監控報告</b>",
        f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"━━━━━━━━━━━━━━━━",
        ""
    ]

    total_found = 0
    for card in cards:
        print(f"▶ 搜尋: {card['name_zh']}")
        all_results = []

        # 用每個關鍵字搜
        for kw in card['search_keywords']:
            results = search_biggo(kw, card.get('exclude_keywords', []))
            all_results.extend(results)
            print(f"  關鍵字「{kw}」抓到 {len(results)} 筆")
            time.sleep(REQUEST_DELAY)

        # 去重（同 url）
        seen_urls = set()
        unique = []
        for r in all_results:
            if r['url'] not in seen_urls:
                seen_urls.add(r['url'])
                unique.append(r)
        unique.sort(key=lambda x: x['price'])

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
