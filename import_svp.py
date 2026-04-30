"""
CARDSTAR v0.4 — Card Importer (v3 Final)
從 Bulbapedia 抓日版 SV-P 卡片清單，寫進 D1。

解析邏輯已在 Claude 環境內用 BeautifulSoup + 模擬 HTML 測試通過。
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

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

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
    print("[1/4] 建表（清除舊表重建）...")

    d1("DROP TABLE IF EXISTS cards")
    d1("DROP TABLE IF EXISTS sets")

    d1("""CREATE TABLE IF NOT EXISTS sets (
        set_code     TEXT PRIMARY KEY,
        name_ja      TEXT,
        name_zh      TEXT,
        name_en      TEXT,
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
        name_en         TEXT,
        rarity          TEXT,
        card_type       TEXT,
        energy_type     TEXT,
        mark            TEXT,
        promotion       TEXT,
        image_url       TEXT,
        track_price     INTEGER DEFAULT 0,
        status          TEXT DEFAULT 'active',
        created_at      INTEGER DEFAULT (strftime('%s','now')),
        updated_at      INTEGER DEFAULT (strftime('%s','now')),
        FOREIGN KEY (set_code) REFERENCES sets(set_code)
    )""")

    d1("CREATE UNIQUE INDEX IF NOT EXISTS idx_card_uid ON cards(card_uid)")
    d1("CREATE INDEX IF NOT EXISTS idx_cards_set_code ON cards(set_code)")
    d1("CREATE INDEX IF NOT EXISTS idx_cards_track ON cards(track_price)")

    d1("""INSERT OR IGNORE INTO sets
          (set_code, name_ja, name_zh, name_en, era, set_type, release_date)
          VALUES ('SV-P',
                  'プロモーションカード スカーレット&バイオレット',
                  '特典卡 朱&紫',
                  'SV-P Promotional cards',
                  'SV', 'promo', '2022-11-18')""")
    print("  OK")


# ── Step 2: 從 Bulbapedia 抓卡片清單 ────────
def parse_card_row(tr):
    """解析 Bulbapedia HTML 表格的一行 <tr>。已用模擬 HTML 測試通過。"""
    cells = tr.find_all("td")
    if len(cells) < 5:
        return None

    # Cell 0: 卡號 "001/SV-P"
    cell0 = cells[0].get_text(strip=True)
    no_m = re.match(r"(\d{3})/SV-P", cell0)
    if not no_m:
        return None
    card_no = no_m.group(1)

    # Cell 1: Mark (regulation)
    mark = cells[1].get_text(strip=True)
    if mark == "—" or mark == "":
        mark = None

    # Cell 2: 英文卡名
    name_cell = cells[2]
    links = name_cell.find_all("a")
    if not links:
        return None
    name_en = links[0].get_text(strip=True)

    # ex / GX / EX 後綴（獨立 link）
    if len(links) > 1:
        suffix = links[1].get_text(strip=True)
        if suffix == "ex" and not name_en.endswith(" ex"):
            name_en += " ex"
        elif suffix in ("GX", "-GX") and "-GX" not in name_en:
            name_en += "-GX"
        elif suffix in ("EX", "-EX") and "-EX" not in name_en:
            name_en += "-EX"

    # 粗體副標題 [Professor Sada] 等
    bold = name_cell.find("b")
    if bold:
        name_en += f" {bold.get_text(strip=True)}"

    # Cell 3: 屬性
    typ_text = cells[3].get_text(strip=True)

    if typ_text in ("I", "PT", "Su", "St"):
        card_type = "Trainer"
        energy = None
    elif typ_text.endswith("E"):
        card_type = "Energy"
        typ_base = typ_text.replace("E", "").strip()
        energy = TYPE_MAP.get(typ_base)
    elif typ_text in TYPE_MAP:
        card_type = "Pokemon"
        energy = TYPE_MAP.get(typ_text)
    else:
        # 從 link href 推斷
        link_in_type = cells[3].find("a")
        card_type = "Pokemon"
        energy = None
        if link_in_type:
            href = link_in_type.get("href", "")
            for eng, zh in TYPE_MAP.items():
                if eng.lower() in href.lower():
                    energy = zh
                    break

    # Cell 4: 稀有度
    rarity = cells[4].get_text(strip=True)
    if rarity == "—":
        rarity = None

    # Cell 5: 入手方式
    promotion = cells[5].get_text(strip=True) if len(cells) > 5 else None
    # 截斷太長的 promotion 文字
    if promotion and len(promotion) > 200:
        promotion = promotion[:200] + "..."

    return {
        "card_uid": f"SV-P_{card_no}",
        "set_code": "SV-P",
        "card_no": card_no,
        "card_no_display": f"{card_no}/SV-P",
        "name_en": name_en,
        "card_type": card_type,
        "energy_type": energy,
        "mark": mark,
        "promotion": promotion,
        "rarity": rarity,
    }


def fetch_bulbapedia():
    """從 Bulbapedia 抓 SV-P 完整清單"""
    print("[2/4] 從 Bulbapedia 抓 SV-P 卡片...")

    url = "https://bulbapedia.bulbagarden.net/wiki/SV-P_Promotional_cards_(TCG)"
    r = requests.get(url, headers={"User-Agent": UA}, timeout=60)
    r.raise_for_status()
    print(f"  HTTP {r.status_code}, {len(r.text)} bytes")

    soup = BeautifulSoup(r.text, "html.parser")

    cards = []
    for tr in soup.find_all("tr"):
        cell0 = tr.find("td")
        if not cell0:
            continue
        if not re.search(r"\d{3}/SV-P", cell0.get_text()):
            continue

        card = parse_card_row(tr)
        if card:
            cards.append(card)

    print(f"  解析成功: {len(cards)} 張卡")
    if cards:
        print(f"  第一張: {cards[0]['card_uid']} {cards[0]['name_en']}")
        print(f"  最後一張: {cards[-1]['card_uid']} {cards[-1]['name_en']}")

    return cards


# ── Step 3: 寫入 D1 ──────────────────────────
def write_to_d1(cards):
    print(f"\n[3/4] 寫入 {len(cards)} 張卡到 D1...")
    new = 0
    exist = 0
    err = 0

    for i, c in enumerate(cards):
        sql = """INSERT OR IGNORE INTO cards
                 (card_uid, set_code, card_no, card_no_display,
                  name_en, card_type, energy_type, mark, promotion, rarity)
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"""
        params = [
            c["card_uid"], c["set_code"], c["card_no"], c["card_no_display"],
            c["name_en"], c.get("card_type"), c.get("energy_type"),
            c.get("mark"), c.get("promotion"), c.get("rarity"),
        ]

        result = d1(sql, params)
        if result.get("success"):
            try:
                changes = result["result"][0]["meta"]["changes"]
            except (KeyError, IndexError):
                changes = 0
            if changes > 0:
                new += 1
            else:
                exist += 1
        else:
            err += 1

        if (i + 1) % 30 == 0:
            print(f"  進度: {i+1}/{len(cards)} (新增: {new})")
            time.sleep(1)

    print(f"  完成! 新增: {new}, 已存在: {exist}, 錯誤: {err}")


# ── Step 4: 驗證 ─────────────────────────────
def verify():
    print("\n[4/4] 驗證...")

    result = d1("SELECT COUNT(*) as cnt FROM cards WHERE set_code = 'SV-P'")
    if result.get("success"):
        try:
            cnt = result["result"][0]["results"][0]["cnt"]
            print(f"  D1 SV-P 總數: {cnt}")
        except (KeyError, IndexError):
            print("  無法讀取")

    result = d1("""SELECT card_uid, name_en, card_type
                   FROM cards WHERE set_code='SV-P'
                   ORDER BY card_no LIMIT 5""")
    if result.get("success"):
        try:
            rows = result["result"][0]["results"]
            print("  前 5 張:")
            for row in rows:
                print(f"    {row['card_uid']}: {row['name_en']} ({row['card_type']})")
        except (KeyError, IndexError):
            pass

    result = d1("""SELECT card_uid, name_en, card_type
                   FROM cards WHERE set_code='SV-P'
                   ORDER BY card_no DESC LIMIT 3""")
    if result.get("success"):
        try:
            rows = result["result"][0]["results"]
            print("  最後 3 張:")
            for row in rows:
                print(f"    {row['card_uid']}: {row['name_en']} ({row['card_type']})")
        except (KeyError, IndexError):
            pass

    # 統計各類型
    result = d1("""SELECT card_type, COUNT(*) as cnt
                   FROM cards WHERE set_code='SV-P'
                   GROUP BY card_type""")
    if result.get("success"):
        try:
            rows = result["result"][0]["results"]
            print("  各類型:")
            for row in rows:
                print(f"    {row['card_type']}: {row['cnt']}")
        except (KeyError, IndexError):
            pass


# ── Main ─────────────────────────────────────
def main():
    print("=" * 50)
    print("CARDSTAR v0.4 — SV-P Card Import")
    print("來源: Bulbapedia (日版)")
    print("=" * 50)

    migrate()
    cards = fetch_bulbapedia()

    if not cards:
        print("\nERROR: 沒抓到任何卡片!")
        print("可能原因: Bulbapedia 頁面結構變了")
        print("請截圖 log 給 Claude")
        return

    write_to_d1(cards)
    verify()

    print("\n" + "=" * 50)
    print("完成!")


if __name__ == "__main__":
    main()
