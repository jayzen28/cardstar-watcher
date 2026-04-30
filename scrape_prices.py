"""
CARDSTAR v0.4 — snkrdunk Price Scraper
1. 搜 snkrdunk 找 SV-P 商品 → 自動對應 card_uid
2. 抓每張卡的 JSON-LD 價格資料
3. 全部寫進 D1
"""

import requests
from bs4 import BeautifulSoup
import json
import re
import os
import time

# ── D1 設定 ──────────────────────────────────
CF_ACCOUNT_ID = os.environ["CF_ACCOUNT_ID"]
CF_D1_DATABASE_ID = os.environ["CF_D1_DATABASE_ID"]
CF_D1_TOKEN = os.environ["CF_D1_TOKEN"]
D1_API = f"https://api.cloudflare.com/client/v4/accounts/{CF_ACCOUNT_ID}/d1/database/{CF_D1_DATABASE_ID}/query"

HEADERS_D1 = {
    "Authorization": f"Bearer {CF_D1_TOKEN}",
    "Content-Type": "application/json",
}

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

TYPE_MAP = {
    "Grass": "草", "Fire": "火", "Water": "水",
    "Lightning": "雷", "Psychic": "超", "Fighting": "鬥",
    "Darkness": "惡", "Metal": "鋼", "Dragon": "龍",
    "Colorless": "無", "Fairy": "妖",
}


def d1(sql, params=None):
    body = {"sql": sql}
    if params:
        body["params"] = params
    r = requests.post(D1_API, headers=HEADERS_D1, json=body)
    data = r.json()
    if not data.get("success"):
        print(f"  D1 ERROR: {data.get('errors', data)}")
    return data


# ── Step 1: 建表 ─────────────────────────────
def migrate():
    print("[1/5] 建表（清除舊表重建）...")

    d1("DROP TABLE IF EXISTS source_mappings")
    d1("DROP TABLE IF EXISTS prices")

    d1("""CREATE TABLE source_mappings (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        card_uid    TEXT NOT NULL,
        source      TEXT NOT NULL,
        source_id   TEXT NOT NULL,
        source_name TEXT,
        source_url  TEXT,
        created_at  INTEGER DEFAULT (strftime('%s','now')),
        UNIQUE(card_uid, source, source_id)
    )""")

    d1("""CREATE TABLE prices (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        card_uid    TEXT NOT NULL,
        source      TEXT NOT NULL,
        price       INTEGER,
        currency    TEXT DEFAULT 'JPY',
        price_type  TEXT DEFAULT 'low',
        offer_count INTEGER,
        scraped_at  INTEGER DEFAULT (strftime('%s','now'))
    )""")

    d1("CREATE INDEX idx_sm_card ON source_mappings(card_uid)")
    d1("CREATE INDEX idx_prices_card ON prices(card_uid, scraped_at)")

    print("  OK")


# ── Step 2: 搜 snkrdunk 找 SV-P 商品 ────────
def discover_snkrdunk():
    """搜尋 snkrdunk，從 productTile 抽出 apparel ID + SV-P 卡號"""
    print("[2/5] 搜尋 snkrdunk SV-P 商品...")

    mappings = {}

    keywords = ["SV-P プロモ", "SV-P ピカチュウ", "SV-P イーブイ",
                "SV-P ポケモン", "SV-P トレーナーズ"]

    for kw in keywords:
        url = f"https://snkrdunk.com/search?keyword={requests.utils.quote(kw)}"
        print(f"  搜尋: {kw}")

        try:
            r = requests.get(url, headers={"User-Agent": UA}, timeout=30)
            if r.status_code != 200:
                print(f"    HTTP {r.status_code}")
                continue

            pattern = re.compile(
                r'<a\s+[^>]*href="[^"]*?/apparels/(\d+)"[^>]*'
                r'aria-label="([^"]*?)"',
                re.DOTALL
            )

            found = 0
            for m in pattern.finditer(r.text):
                apparel_id = m.group(1)
                label = m.group(2)

                svp_m = re.search(r'\[(?:SV-P\s*)?(\d{3})(?:/SV-P)?\]', label)
                if not svp_m:
                    continue

                card_no = svp_m.group(1)
                card_uid = f"SV-P_{card_no}"

                if card_uid not in mappings:
                    mappings[card_uid] = {
                        "apparel_id": apparel_id,
                        "name": label.split(" - ")[0].strip() if " - " in label else label,
                    }
                    found += 1

            print(f"    找到 {found} 個新對應")

        except Exception as e:
            print(f"    錯誤: {e}")

        time.sleep(2)

    print(f"  搜尋結果: {len(mappings)} 張卡")

    # 如果搜尋結果太少，加上已知的 mapping
    known = {
        "SV-P_001": {"apparel_id": "104784", "name": "ピカチュウ: プロモ [001/SV-P]"},
        "SV-P_074": {"apparel_id": "132896", "name": "ピカチュウ: プロモ [SV-P 074]"},
        "SV-P_098": {"apparel_id": "135232", "name": "名探偵ピカチュウ: プロモ [SV-P 098]"},
        "SV-P_120": {"apparel_id": "134393", "name": "ピカチュウ: プロモ [SV-P 120]"},
        "SV-P_197": {"apparel_id": "475194", "name": "ピカチュウ P [SV-P 197]"},
        "SV-P_218": {"apparel_id": "332798", "name": "ピカチュウ P [SV-P 218]"},
        "SV-P_242": {"apparel_id": "518774", "name": "ピカチュウ [SV-P 242]"},
        "SV-P_057": {"apparel_id": "520383", "name": "ピカチュウ P [SV-P 057] 中国語版"},
        "SV-P_062": {"apparel_id": "126655", "name": "イーブイ [SV-P 062]"},
    }

    for uid, info in known.items():
        if uid not in mappings:
            mappings[uid] = info

    print(f"  加上已知 mapping 後: {len(mappings)} 張卡")
    return mappings


# ── Step 3: 抓 JSON-LD 價格 ──────────────────
def fetch_price(apparel_id):
    """從 snkrdunk 商品頁的 JSON-LD 抓價格"""
    url = f"https://snkrdunk.com/apparels/{apparel_id}"

    try:
        r = requests.get(url, headers={"User-Agent": UA}, timeout=30)
        print(f"    HTTP {r.status_code}, {len(r.text)} bytes")

        if r.status_code != 200:
            return None

        soup = BeautifulSoup(r.text, "html.parser")

        # 找所有 JSON-LD
        scripts = soup.find_all("script", type="application/ld+json")
        print(f"    JSON-LD 數量: {len(scripts)}")

        for script in scripts:
            try:
                data = json.loads(script.string)

                # 有時候是 list
                if isinstance(data, list):
                    for item in data:
                        if item.get("@type") == "Product":
                            data = item
                            break
                    else:
                        continue

                if data.get("@type") == "Product":
                    offers = data.get("offers", {})
                    low = 0
                    high = 0
                    count = 0
                    currency = "JPY"

                    if isinstance(offers, dict):
                        low = int(offers.get("lowPrice", 0) or 0)
                        high = int(offers.get("highPrice", 0) or 0)
                        count = int(offers.get("offerCount", 0) or 0)
                        currency = offers.get("priceCurrency", "JPY")
                    elif isinstance(offers, list):
                        prices = []
                        for o in offers:
                            p = int(o.get("price", 0) or 0)
                            if p > 0:
                                prices.append(p)
                        if prices:
                            low = min(prices)
                            high = max(prices)
                            count = len(prices)

                    print(f"    JSON-LD: ¥{low:,} ~ ¥{high:,}, {count} offers")

                    return {
                        "low_price": low,
                        "high_price": high,
                        "currency": currency,
                        "offer_count": count,
                        "name_ja": data.get("name", ""),
                    }

            except (json.JSONDecodeError, ValueError, TypeError) as e:
                print(f"    JSON parse error: {e}")
                continue

        # 沒找到 JSON-LD Product，試著從 HTML 找價格
        print("    沒找到 JSON-LD Product，嘗試 HTML...")
        price_m = re.search(r'¥([\d,]+)', r.text)
        if price_m:
            price = int(price_m.group(1).replace(',', ''))
            print(f"    HTML 價格: ¥{price:,}")
            return {
                "low_price": price,
                "high_price": price,
                "currency": "JPY",
                "offer_count": 0,
                "name_ja": "",
            }

    except Exception as e:
        print(f"    fetch 錯誤 {apparel_id}: {e}")

    return None


# ── Step 4: 寫入 D1 ──────────────────────────
def save_mappings(mappings):
    print(f"\n[3/5] 寫入 {len(mappings)} 筆 source_mappings...")
    new = 0

    for card_uid, info in mappings.items():
        result = d1(
            """INSERT OR IGNORE INTO source_mappings
               (card_uid, source, source_id, source_name, source_url)
               VALUES (?, 'snkrdunk', ?, ?, ?)""",
            [card_uid, info["apparel_id"], info["name"],
             f"https://snkrdunk.com/apparels/{info['apparel_id']}"]
        )
        if result.get("success"):
            try:
                if result["result"][0]["meta"]["changes"] > 0:
                    new += 1
            except (KeyError, IndexError):
                pass

    print(f"  新增: {new}")


def save_prices(price_records):
    print(f"\n[5/5] 寫入 {len(price_records)} 筆價格...")
    new = 0
    err = 0

    for i, p in enumerate(price_records):
        result = d1(
            """INSERT INTO prices
               (card_uid, source, price, currency, price_type, offer_count)
               VALUES (?, 'snkrdunk', ?, ?, ?, ?)""",
            [p["card_uid"], p["price"], p["currency"], p["price_type"],
             p["offer_count"]]
        )
        if result.get("success"):
            new += 1
        else:
            err += 1

    print(f"  新增: {new}, 錯誤: {err}")


# ── Main ─────────────────────────────────────
def main():
    print("=" * 50)
    print("CARDSTAR v0.4 — snkrdunk Price Scraper")
    print("=" * 50)

    migrate()
    mappings = discover_snkrdunk()

    if not mappings:
        print("\nERROR: 沒有任何 mapping")
        return

    save_mappings(mappings)

    # 抓價格
    print(f"\n[4/5] 抓取 {len(mappings)} 張卡的價格...")
    price_records = []

    for i, (card_uid, info) in enumerate(mappings.items()):
        apparel_id = info["apparel_id"]
        print(f"  {card_uid} (apparel {apparel_id})...")
        price_data = fetch_price(apparel_id)

        if price_data:
            if price_data["low_price"] > 0:
                price_records.append({
                    "card_uid": card_uid,
                    "price": price_data["low_price"],
                    "currency": price_data["currency"],
                    "price_type": "low",
                    "offer_count": price_data["offer_count"],
                })
            if price_data["high_price"] > 0:
                price_records.append({
                    "card_uid": card_uid,
                    "price": price_data["high_price"],
                    "currency": price_data["currency"],
                    "price_type": "high",
                    "offer_count": price_data["offer_count"],
                })

            if price_data.get("name_ja"):
                d1("UPDATE cards SET name_ja = ? WHERE card_uid = ?",
                   [price_data["name_ja"], card_uid])
        else:
            print(f"    失敗")

        if (i + 1) % 5 == 0:
            time.sleep(2)
        else:
            time.sleep(1)

    if price_records:
        save_prices(price_records)

    # 驗證
    print("\n" + "=" * 50)
    print("驗證結果:")

    result = d1("SELECT COUNT(*) as cnt FROM source_mappings WHERE source = 'snkrdunk'")
    if result.get("success"):
        try:
            cnt = result["result"][0]["results"][0]["cnt"]
            print(f"  source_mappings: {cnt} 筆")
        except (KeyError, IndexError):
            pass

    result = d1("SELECT COUNT(*) as cnt FROM prices WHERE source = 'snkrdunk'")
    if result.get("success"):
        try:
            cnt = result["result"][0]["results"][0]["cnt"]
            print(f"  prices: {cnt} 筆")
        except (KeyError, IndexError):
            pass

    result = d1("""SELECT p.card_uid, p.price, p.price_type
                   FROM prices p
                   WHERE p.price_type = 'low'
                   ORDER BY p.price DESC LIMIT 10""")
    if result.get("success"):
        try:
            rows = result["result"][0]["results"]
            print("\n  最貴 10 張 (最低價):")
            for row in rows:
                print(f"    {row['card_uid']}: ¥{row['price']:,}")
        except (KeyError, IndexError):
            pass

    print("\n完成!")


if __name__ == "__main__":
    main()
