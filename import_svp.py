"""
CARDSTAR v0.4 — SV-P Promo Card Importer
從 pokeboon.com 抓日版 SV-P 卡片清單，寫進 D1。
"""

import requests
from bs4 import BeautifulSoup
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
    print("[1/3] 建表...")

    d1("""CREATE TABLE IF NOT EXISTS sets (
        set_code     TEXT PRIMARY KEY,
        name_ja      TEXT,
        name_zh      TEXT,
        era          TEXT NOT NULL,
        set_type     TEXT NOT NULL,
        release_date TEXT,
        total_cards  INTEGER,
        status       TEXT DEFAULT 'active'
    )""")

    d1("""CREATE TABLE IF NOT EXISTS cards (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        card_uid        TEXT UNIQUE NOT NULL,
        set_code        TEXT NOT NULL,
        card_no         TEXT NOT NULL,
        card_no_display TEXT NOT NULL,
        name_ja         TEXT,
        name_zh         TEXT,
        rarity          TEXT,
        pokemon_no      INTEGER,
        hp              INTEGER,
        card_type       TEXT,
        energy_type     TEXT,
        stage           TEXT,
        illustrator     TEXT,
        image_url       TEXT,
        official_id_ja  INTEGER,
        official_id_zh  INTEGER,
        track_price     INTEGER DEFAULT 0,
        status          TEXT DEFAULT 'active',
        created_at      INTEGER DEFAULT (strftime('%s','now')),
        updated_at      INTEGER DEFAULT (strftime('%s','now')),
        FOREIGN KEY (set_code) REFERENCES sets(set_code)
    )""")

    d1("CREATE UNIQUE INDEX IF NOT EXISTS idx_card_uid ON cards(card_uid)")
    d1("CREATE INDEX IF NOT EXISTS idx_cards_set_code ON cards(set_code)")
    d1("CREATE INDEX IF NOT EXISTS idx_cards_track ON cards(track_price)")

    # 寫入 SV-P 系列
    d1("""INSERT OR IGNORE INTO sets (set_code, name_ja, name_zh, era, set_type, release_date)
          VALUES ('SV-P',
                  'プロモーションカード スカーレット&バイオレット',
                  '特典卡 朱&紫',
                  'SV', 'promo', '2022-11-18')""")

    print("  OK")


# ── Step 2: 抓卡片清單 ───────────────────────
def scrape_pokeboon():
    """從 pokeboon.com 抓 SV-P 完整清單"""
    print("[2/3] 從 pokeboon.com 抓 SV-P 卡片...")

    url = "https://pokeboon.com/jp/category/sv-p/"
    ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    r = requests.get(url, headers={"User-Agent": ua}, timeout=60)
    r.raise_for_status()
    print(f"  HTTP {r.status_code}, {len(r.text)} bytes")

    soup = BeautifulSoup(r.text, "html.parser")
    cards = []

    # pokeboon 用 <table> 列出所有卡片
    for row in soup.find_all("tr"):
        cells = row.find_all("td")
        if len(cells) < 2:
            continue

        first = cells[0].get_text(strip=True)
        m = re.match(r"(\d{3})/SV-P", first)
        if not m:
            continue

        card_no = m.group(1)

        # 卡名（第二欄，可能有超連結）
        link = cells[1].find("a")
        name_ja = link.get_text(strip=True) if link else cells[1].get_text(strip=True)

        cards.append({
            "card_uid": f"SV-P_{card_no}",
            "set_code": "SV-P",
            "card_no": card_no,
            "card_no_display": f"{card_no}/SV-P",
            "name_ja": name_ja,
            "rarity": "P",
        })

    print(f"  找到 {len(cards)} 張卡")

    if cards:
        print(f"  第一張: {cards[0]['card_uid']} {cards[0]['name_ja']}")
        print(f"  最後一張: {cards[-1]['card_uid']} {cards[-1]['name_ja']}")

    return cards


# ── Step 3: 寫入 D1 ──────────────────────────
def write_to_d1(cards):
    """逐筆寫入，安全不爆 D1 variable 限制"""
    print(f"[3/3] 寫入 {len(cards)} 張卡到 D1...")

    new = 0
    exist = 0
    err = 0

    for i, c in enumerate(cards):
        sql = """INSERT OR IGNORE INTO cards
                 (card_uid, set_code, card_no, card_no_display, name_ja, rarity)
                 VALUES (?, ?, ?, ?, ?, ?)"""
        params = [
            c["card_uid"], c["set_code"], c["card_no"],
            c["card_no_display"], c["name_ja"], c["rarity"],
        ]

        result = d1(sql, params)
        if result.get("success"):
            changes = 0
            try:
                changes = result["result"][0]["meta"]["changes"]
            except (KeyError, IndexError):
                pass
            if changes > 0:
                new += 1
            else:
                exist += 1
        else:
            err += 1

        # 每 30 筆暫停一下（D1 免費版 rate limit）
        if (i + 1) % 30 == 0:
            print(f"  進度: {i+1}/{len(cards)}")
            time.sleep(1)

    print(f"  新增: {new}, 已存在: {exist}, 錯誤: {err}")
    return new


# ── 驗證 ─────────────────────────────────────
def verify():
    result = d1("SELECT COUNT(*) as cnt FROM cards WHERE set_code = 'SV-P'")
    if result.get("success"):
        try:
            cnt = result["result"][0]["results"][0]["cnt"]
            print(f"\n  D1 裡 SV-P 卡片總數: {cnt}")
        except (KeyError, IndexError):
            print("  無法讀取數量")

    # 印出前 5 張
    result = d1("SELECT card_uid, name_ja FROM cards WHERE set_code = 'SV-P' ORDER BY card_no LIMIT 5")
    if result.get("success"):
        try:
            rows = result["result"][0]["results"]
            print("  前 5 張:")
            for row in rows:
                print(f"    {row['card_uid']}: {row['name_ja']}")
        except (KeyError, IndexError):
            pass


# ── Main ─────────────────────────────────────
def main():
    print("=" * 50)
    print("CARDSTAR v0.4 — SV-P Promo Card Import")
    print("=" * 50)

    migrate()
    cards = scrape_pokeboon()

    if not cards:
        print("\nERROR: 沒抓到任何卡片。pokeboon.com 結構可能有變。")
        print("請截圖 log 給 Claude。")
        return

    write_to_d1(cards)
    verify()

    print("\n" + "=" * 50)
    print("完成！")


if __name__ == "__main__":
    main()
