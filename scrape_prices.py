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
    print("[1/5] 建表...")

    d1("""CREATE TABLE IF NOT EXISTS source_mappings (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        card_uid    TEXT NOT NULL,
        source      TEXT NOT NULL,
        source_id   TEXT NOT NULL,
        source_name TEXT,
        source_url  TEXT,
        created_at  INTEGER DEFAULT (strftime('%s','now')),
        UNIQUE(card_uid, source, source_id)
    )""")

    d1("""CREATE TABLE IF NOT EXISTS prices (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        card_uid    TEXT NOT NULL,
        source      TEXT NOT NULL,
        price       INTEGER,
        currency    TEXT DEFAULT 'JPY',
        price_type  TEXT DEFAULT 'low',
        offer_count INTEGER,
        scraped_at  INTEGER DEFAULT (strftime('%s','now'))
    )""")

    d1("CREATE INDEX IF NOT EXISTS idx_sm_card ON source_mappings(card_uid)")
    d1("CREATE INDEX IF NOT EXISTS idx_prices_card ON prices(card_uid, scraped_at)")

    print("  OK")


# ── Step 2: 搜 snkrdunk 找 SV-P 商品 ────────
def discover_snkrdunk():
    """搜尋 snkrdunk，從 productTile 抽出 apparel ID + SV-P 卡號"""
    print("[2/5] 搜尋 snkrdunk SV-P 商品...")

    mappings = {}  # card_uid → {apparel_id, name}

    # 搜多個關鍵字確保覆蓋面
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

            # 找 productTile 的 <a> 連結
            # 格式: <a href=".../apparels/XXXXX" ... aria-label="商品名 - ¥價格" ...productTile...>
            pattern = re.compile(
                r'<a\s+[^>]*href="[^"]*?/apparels/(\d+)"[^>]*'
                r'aria-label="([^"]*?)"',
                re.DOTALL
            )

            found = 0
            for m in pattern.finditer(r.text):
                apparel_id = m.group(1)
                label = m.group(2)

                # 從 label 抽 SV-P 卡號
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

        time.sleep(2)  # 禮貌等待

    # 也可以直接用已知的 mapping（搜尋可能不會涵蓋所有）
    # 之後可以擴充這個列表
    print(f"  總共對應: {len(mappings)} 張卡")
    return mappings


# ── Step 3: 抓 JSON-LD 價格 ──────────────────
def fetch_price(apparel_id):
    """從 snkrdunk 商品頁的 JSON-LD 抓價格"""
    url = f"https://snkrdunk.com/apparels/{apparel_id}"

    try:
        r = requests.get(url, headers={"User-Agent": UA}, timeout=30)
        if r.status_code != 200:
            return None

        soup = BeautifulSoup(r.text, "html.parser")

        # 找 JSON-LD
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string)
                if data.get("@type") == "Product":
                    offers = data.get("offers", {})
                    return {
                        "low_price": int(offers.get("lowPrice", 0)),
                        "high_price": int(offers.get("highPrice", 0)),
                        "currency": offers.get("priceCurrency", "JPY"),
                        "offer_count": int(offers.get("offerCount", 0)),
                        "name_ja": data.get("name", ""),
                    }
            except (json.JSONDecodeError, ValueError):
                continue

    except Exception as e:
        print(f"    fetch 錯誤 {apparel_id}: {e}")

    return None


# ── Step 4: 寫入 D1 ──────────────────────────
def save_mappings(mappings):
    """寫入 source_mappings"""
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
    return new


def save_prices(price_records):
    """寫入 prices"""
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

        if (i + 1) % 20 == 0:
            print(f"  進度: {i+1}/{len(price_records)}")
            time.sleep(0.5)

    print(f"  新增: {new}, 錯誤: {err}")


# ── Main ─────────────────────────────────────
def main():
    print("=" * 50)
    print("CARDSTAR v0.4 — snkrdunk Price Scraper")
    print("=" * 50)

    migrate()

    # 探勘 snkrdunk
    mappings = discover_snkrdunk()

    if not mappings:
        print("\n搜尋頁沒找到 productTile。")
        print("改用已知 mapping 測試...")

        # Fallback: 用搜尋結果已確認的幾張卡
        mappings = {
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
        print(f"  使用 {len(mappings)} 筆已知 mapping")

    # 儲存 mapping
    save_mappings(mappings)

    # 抓價格
    print(f"\n[4/5] 抓取 {len(mappings)} 張卡的價格...")
    price_records = []

    for i, (card_uid, info) in enumerate(mappings.items()):
        apparel_id = info["apparel_id"]
        price_data = fetch_price(apparel_id)

        if price_data:
            # 記錄最低價
            if price_data["low_price"] > 0:
                price_records.append({
                    "card_uid": card_uid,
                    "price": price_data["low_price"],
                    "currency": price_data["currency"],
                    "price_type": "low",
                    "offer_count": price_data["offer_count"],
                })
            # 記錄最高價
            if price_data["high_price"] > 0:
                price_records.append({
                    "card_uid": card_uid,
                    "price": price_data["high_price"],
                    "currency": price_data["currency"],
                    "price_type": "high",
                    "offer_count": price_data["offer_count"],
                })

            print(f"  {card_uid}: ¥{price_data['low_price']:,} ~ ¥{price_data['high_price']:,} ({price_data['offer_count']} offers)")

            # 同時更新 cards 表的日文名
            if price_data.get("name_ja"):
                d1("UPDATE cards SET name_ja = ? WHERE card_uid = ?",
                   [price_data["name_ja"], card_uid])
        else:
            print(f"  {card_uid}: 無法取得價格")

        if (i + 1) % 5 == 0:
            time.sleep(2)  # 每 5 張暫停 2 秒
        else:
            time.sleep(1)

    # 儲存價格
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

    result = d1("""SELECT c.card_uid, c.name_en, c.name_ja, p.price, p.price_type
                   FROM cards c
                   JOIN prices p ON c.card_uid = p.card_uid
                   WHERE p.price_type = 'low'
                   ORDER BY p.price DESC LIMIT 10""")
    if result.get("success"):
        try:
            rows = result["result"][0]["results"]
            print("\n  最貴 10 張 (最低價):")
            for row in rows:
                name = row.get('name_ja') or row.get('name_en') or row['card_uid']
                print(f"    {row['card_uid']}: ¥{row['price']:,} - {name}")
        except (KeyError, IndexError):
            pass

    print("\n完成!")


if __name__ == "__main__":
    main()
