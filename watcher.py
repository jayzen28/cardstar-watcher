"""
CARDSTAR Watcher v0.3
主程式:讀 cards.json → 對每張卡跑各個 source → 寫 D1 → 找套利機會 → 推 Telegram
"""

import json
import time
import statistics
import sys

from sources import yahoo_tw, ruten, fb_groups
from storage import telegram, d1


# 啟用的 source 清單。要加新的就在 sources/ 開新檔案,然後加進這裡
SOURCES = {
    "yahoo_tw": yahoo_tw,
    "ruten": ruten,
    "fb_groups": fb_groups,
}

# 套利門檻:標價 < 中位數 * THRESHOLD = 套利候選
# 0.7 = 比中位數便宜 30% 才算
# 之後資料夠多,可以調更激進(0.85 = 便宜 15%)
ARBITRAGE_THRESHOLD = 0.7

# 中位數至少需要這麼多筆資料才計算(避免 2-3 筆算中位數沒意義)
MIN_LISTINGS_FOR_MEDIAN = 3


def main():
    print("=" * 50)
    print(f"CARDSTAR Watcher v0.3")
    print(f"Started at {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 50)

    # 讀卡片清單
    with open("cards.json", "r", encoding="utf-8") as f:
        cards = json.load(f)
    print(f"Loaded {len(cards)} cards from cards.json")

    scraped_at = int(time.time())

    # 每個 (card, source) 各自抓
    # all_listings 結構:[(card, source_name, listing_dict), ...]
    all_listings = []

    for card in cards:
        print(f"\n--- {card['name_zh']} ({card['id']}) ---")

        for source_name, source_module in SOURCES.items():
            try:
                listings = source_module.search(card)
                print(f"  [{source_name}] {len(listings)} 筆")
                for listing in listings:
                    all_listings.append((card, source_name, listing))
            except NotImplementedError as e:
                print(f"  [{source_name}] 未啟用: {e}")
            except Exception as e:
                print(f"  [{source_name}] 失敗: {type(e).__name__}: {e}")

    print(f"\n{'=' * 50}")
    print(f"總計抓到 {len(all_listings)} 筆")
    print("=" * 50)

    # 寫進 D1
    d1_written = 0
    if all_listings:
        try:
            d1_written = d1.write_listings(all_listings, scraped_at)
            print(f"✓ D1 寫入 {d1_written} 筆")
        except Exception as e:
            print(f"✗ D1 寫入失敗: {type(e).__name__}: {e}")

    # 算套利機會
    opportunities = find_opportunities(all_listings)
    print(f"✓ 套利候選 {len(opportunities)} 筆")

    # 推 Telegram
    report = build_report(cards, all_listings, opportunities, d1_written)
    try:
        telegram.send(report)
        print(f"✓ Telegram 已送出")
    except Exception as e:
        print(f"✗ Telegram 失敗: {type(e).__name__}: {e}")

    print(f"\nDone at {time.strftime('%Y-%m-%d %H:%M:%S')}")


def find_opportunities(all_listings):
    """
    對每張卡計算 listings 的中位數,找出 < 中位數 * THRESHOLD 的標的
    回傳 [(card, source_name, listing, median), ...]
    """
    by_card = {}
    for card, source_name, listing in all_listings:
        by_card.setdefault(card["id"], []).append((card, source_name, listing))

    opportunities = []
    for card_id, entries in by_card.items():
        prices = [e[2]["price"] for e in entries if e[2]["price"] > 0]
        if len(prices) < MIN_LISTINGS_FOR_MEDIAN:
            continue
        median = statistics.median(prices)
        for card, source_name, listing in entries:
            if listing["price"] < median * ARBITRAGE_THRESHOLD:
                opportunities.append((card, source_name, listing, median))

    # 從折扣最大的排到最小
    opportunities.sort(key=lambda o: o[2]["price"] / o[3])
    return opportunities


def build_report(cards, all_listings, opportunities, d1_written):
    lines = []
    lines.append("🃏 CARDSTAR Watcher v0.3")
    lines.append(time.strftime("%Y-%m-%d %H:%M"))
    lines.append("")

    # 每張卡抓到幾筆
    by_card = {}
    for card, source_name, listing in all_listings:
        by_card.setdefault(card["id"], 0)
        by_card[card["id"]] += 1

    lines.append("📊 抓取結果:")
    for card in cards:
        count = by_card.get(card["id"], 0)
        flag = "✅" if count > 0 else "⚠️"
        lines.append(f"{flag} {card['name_zh']}: {count} 筆")

    lines.append("")
    lines.append(f"💾 D1 寫入: {d1_written} 筆")
    lines.append("")

    if opportunities:
        lines.append(f"🔥 套利候選 {len(opportunities)} 筆:")
        # 最多列 8 個,Telegram 訊息不要太長
        for card, source_name, listing, median in opportunities[:8]:
            discount = (1 - listing["price"] / median) * 100
            title = listing["title"][:50]
            lines.append("")
            lines.append(f"💰 {card['name_zh']} -{discount:.0f}%")
            lines.append(f"   {title}")
            lines.append(f"   ${listing['price']:,} (中位數 ${median:,.0f})")
            lines.append(f"   {listing['url']}")
    else:
        lines.append("📊 暫無顯著套利機會")
        lines.append("(資料累積中,7 天後比對歷史中位數會更準)")

    return "\n".join(lines)


if __name__ == "__main__":
    main()


if __name__ == "__main__":
    main()
