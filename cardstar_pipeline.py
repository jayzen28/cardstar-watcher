"""
CARDSTAR 卡市達 — 完整資料管線 v1.0
一鍵完成：建表 → 匯入卡片 → 補中文名 → 抓價格 → 產生網站

用法：python cardstar_pipeline.py [動作]
  full          全部重來（DROP 表 + 匯入 + 中文 + 價格 + 網站）
  import        只匯入卡片（從 Bulbapedia）
  zh            只補中文名（從繁中官網）
  prices        只抓價格（從 snkrdunk）
  site          只產生網站
"""

import requests
from bs4 import BeautifulSoup
import json
import re
import os
import sys
import time

# ── 設定 ─────────────────────────────────────
CF_ACCOUNT_ID = os.environ["CF_ACCOUNT_ID"]
CF_D1_DATABASE_ID = os.environ["CF_D1_DATABASE_ID"]
CF_D1_TOKEN = os.environ["CF_D1_TOKEN"]
D1_API = f"https://api.cloudflare.com/client/v4/accounts/{CF_ACCOUNT_ID}/d1/database/{CF_D1_DATABASE_ID}/query"
HEADERS_D1 = {"Authorization": f"Bearer {CF_D1_TOKEN}", "Content-Type": "application/json"}
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

TYPE_MAP = {
    "Grass": "草", "Fire": "火", "Water": "水", "Lightning": "雷",
    "Psychic": "超", "Fighting": "鬥", "Darkness": "惡", "Metal": "鋼",
    "Dragon": "龍", "Colorless": "無", "Fairy": "妖",
}

KNOWN_SNKRDUNK = {
    "SV-P_001": "104784", "SV-P_074": "132896", "SV-P_098": "135232",
    "SV-P_120": "134393", "SV-P_197": "475194", "SV-P_218": "332798",
    "SV-P_242": "518774", "SV-P_057": "520383", "SV-P_062": "126655",
}


def d1(sql, params=None):
    body = {"sql": sql}
    if params:
        body["params"] = params
    try:
        r = requests.post(D1_API, headers=HEADERS_D1, json=body, timeout=30)
        data = r.json()
        if not data.get("success"):
            print(f"  D1 ERR: {data.get('errors', ['unknown'])}")
        return data
    except Exception as e:
        print(f"  D1 EXCEPTION: {e}")
        return {"success": False}


def d1_rows(sql):
    data = d1(sql)
    try:
        return data["result"][0]["results"]
    except (KeyError, IndexError, TypeError):
        return []


def d1_changes(data):
    try:
        return data["result"][0]["meta"]["changes"]
    except (KeyError, IndexError, TypeError):
        return 0


# ═══════════════════════════════════════════════
# STEP 1: 建表
# ═══════════════════════════════════════════════
def create_tables(drop=False):
    print("\n[STEP 1] 建表...")
    if drop:
        print("  DROP 所有舊表...")
        for t in ["prices", "source_mappings", "cards", "sets"]:
            d1(f"DROP TABLE IF EXISTS {t}")

    d1("""CREATE TABLE IF NOT EXISTS sets (
        set_code TEXT PRIMARY KEY, name_ja TEXT, name_zh TEXT, name_en TEXT,
        era TEXT NOT NULL, set_type TEXT NOT NULL, release_date TEXT,
        total_cards INTEGER, status TEXT DEFAULT 'active'
    )""")

    d1("""CREATE TABLE IF NOT EXISTS cards (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        card_uid TEXT UNIQUE NOT NULL, set_code TEXT NOT NULL,
        card_no TEXT NOT NULL, card_no_display TEXT NOT NULL,
        name_ja TEXT, name_zh TEXT, name_en TEXT,
        rarity TEXT, card_type TEXT, energy_type TEXT,
        mark TEXT, promotion TEXT, image_url TEXT,
        track_price INTEGER DEFAULT 0, status TEXT DEFAULT 'active',
        created_at INTEGER DEFAULT (strftime('%s','now')),
        updated_at INTEGER DEFAULT (strftime('%s','now')),
        FOREIGN KEY (set_code) REFERENCES sets(set_code)
    )""")

    d1("""CREATE TABLE IF NOT EXISTS source_mappings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        card_uid TEXT NOT NULL, source TEXT NOT NULL,
        source_id TEXT NOT NULL, source_name TEXT, source_url TEXT,
        created_at INTEGER DEFAULT (strftime('%s','now')),
        UNIQUE(card_uid, source, source_id)
    )""")

    d1("""CREATE TABLE IF NOT EXISTS prices (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        card_uid TEXT NOT NULL, source TEXT NOT NULL,
        price INTEGER, currency TEXT DEFAULT 'JPY',
        price_type TEXT DEFAULT 'low', offer_count INTEGER,
        scraped_at INTEGER DEFAULT (strftime('%s','now'))
    )""")

    d1("CREATE UNIQUE INDEX IF NOT EXISTS idx_card_uid ON cards(card_uid)")
    d1("CREATE INDEX IF NOT EXISTS idx_cards_set ON cards(set_code)")
    d1("CREATE INDEX IF NOT EXISTS idx_cards_track ON cards(track_price)")
    d1("CREATE INDEX IF NOT EXISTS idx_sm_card ON source_mappings(card_uid)")
    d1("CREATE INDEX IF NOT EXISTS idx_prices_card ON prices(card_uid, scraped_at)")

    d1("""INSERT OR IGNORE INTO sets (set_code, name_ja, name_zh, name_en, era, set_type, release_date)
          VALUES ('SV-P', 'プロモーションカード スカーレット&バイオレット',
                  '特典卡 朱&紫', 'SV-P Promotional cards', 'SV', 'promo', '2022-11-18')""")
    print("  OK")


# ═══════════════════════════════════════════════
# STEP 2: 從 Bulbapedia 匯入卡片（英文名）
# ═══════════════════════════════════════════════
def import_cards():
    print("\n[STEP 2] 從 Bulbapedia 匯入 SV-P 卡片...")
    url = "https://bulbapedia.bulbagarden.net/wiki/SV-P_Promotional_cards_(TCG)"
    r = requests.get(url, headers={"User-Agent": UA}, timeout=60)
    r.raise_for_status()
    print(f"  HTTP {r.status_code}, {len(r.text):,} bytes")

    soup = BeautifulSoup(r.text, "html.parser")
    cards = []

    for tr in soup.find_all("tr"):
        cell0 = tr.find("td")
        if not cell0 or not re.search(r"\d{3}/SV-P", cell0.get_text()):
            continue
        cells = tr.find_all("td")
        if len(cells) < 5:
            continue

        no_m = re.match(r"(\d{3})/SV-P", cells[0].get_text(strip=True))
        if not no_m:
            continue
        card_no = no_m.group(1)

        mark = cells[1].get_text(strip=True)
        if mark in ("—", ""):
            mark = None

        links = cells[2].find_all("a")
        if not links:
            continue
        name_en = links[0].get_text(strip=True)
        if len(links) > 1:
            suf = links[1].get_text(strip=True)
            if suf == "ex" and " ex" not in name_en:
                name_en += " ex"
        bold = cells[2].find("b")
        if bold:
            name_en += f" {bold.get_text(strip=True)}"

        typ = cells[3].get_text(strip=True)
        if typ in ("I", "PT", "Su", "St"):
            card_type, energy = "Trainer", None
        elif typ.endswith("E"):
            card_type = "Energy"
            energy = TYPE_MAP.get(typ.replace("E", "").strip())
        elif typ in TYPE_MAP:
            card_type, energy = "Pokemon", TYPE_MAP.get(typ)
        else:
            card_type, energy = "Pokemon", None
            la = cells[3].find("a")
            if la:
                for eng, zh in TYPE_MAP.items():
                    if eng.lower() in la.get("href", "").lower():
                        energy = zh
                        break

        rarity = cells[4].get_text(strip=True)
        if rarity == "—":
            rarity = None

        promotion = cells[5].get_text(strip=True) if len(cells) > 5 else None
        if promotion and len(promotion) > 200:
            promotion = promotion[:200]

        cards.append((card_no, name_en, card_type, energy, mark, rarity, promotion))

    print(f"  解析: {len(cards)} 張")
    new = 0
    for i, (no, name, ct, en, mk, ra, pr) in enumerate(cards):
        uid = f"SV-P_{no}"
        res = d1("INSERT OR IGNORE INTO cards (card_uid,set_code,card_no,card_no_display,name_en,card_type,energy_type,mark,rarity,promotion) VALUES (?,?,?,?,?,?,?,?,?,?)",
                 [uid, "SV-P", no, f"{no}/SV-P", name, ct, en, mk, ra, pr])
        if d1_changes(res) > 0:
            new += 1
        if (i+1) % 50 == 0:
            print(f"  {i+1}/{len(cards)}")
            time.sleep(0.5)

    print(f"  新增: {new}, 總共: {len(cards)}")
    return len(cards)


# ═══════════════════════════════════════════════
# STEP 3: 從繁中官網補中文名
# ═══════════════════════════════════════════════
def update_zh_names():
    print("\n[STEP 3] 從繁中官網補中文卡名...")
    base = "https://asia.pokemon-card.com/tw/card-search/list/"
    detail_ids = []
    page = 1

    while True:
        url = f"{base}?expansionCodes=SV-P&pageNo={page}"
        try:
            r = requests.get(url, headers={"User-Agent": UA}, timeout=30)
        except Exception as e:
            print(f"  頁 {page} 失敗: {e}")
            break
        if r.status_code != 200:
            break
        found = 0
        soup = BeautifulSoup(r.text, "html.parser")
        for a in soup.find_all("a", href=True):
            m = re.search(r"/tw/card-search/detail/(\d+)/?", a["href"])
            if m:
                did = int(m.group(1))
                if did not in detail_ids:
                    detail_ids.append(did)
                    found += 1
        print(f"  頁 {page}: {found} 張")
        if found == 0:
            break
        page += 1
        time.sleep(1)

    print(f"  共 {len(detail_ids)} 個 detail ID")
    updated = 0

    for i, did in enumerate(detail_ids):
        try:
            r = requests.get(f"https://asia.pokemon-card.com/tw/card-search/detail/{did}/",
                             headers={"User-Agent": UA}, timeout=30)
            if r.status_code != 200:
                continue
        except:
            continue

        soup = BeautifulSoup(r.text, "html.parser")
        h1 = soup.find("h1")
        if not h1:
            continue
        raw = h1.get_text(strip=True)
        name_zh = raw
        for s in ["基礎 ", "1階進化 ", "2階進化 ", "MEGA進化 "]:
            if raw.startswith(s):
                name_zh = raw[len(s):]
                break

        body = soup.get_text(" ", strip=True)
        m = re.search(r"(\d{3})/SV-P", body)
        if not m:
            continue
        card_no = m.group(1)
        card_uid = f"SV-P_{card_no}"

        res = d1("UPDATE cards SET name_zh = ? WHERE card_uid = ? AND (name_zh IS NULL OR name_zh = '')",
                 [name_zh, card_uid])
        if d1_changes(res) > 0:
            updated += 1

        if (i+1) % 30 == 0:
            print(f"  {i+1}/{len(detail_ids)} (更新: {updated})")
            time.sleep(0.5)

    print(f"  中文名更新: {updated}")
    return updated


# ═══════════════════════════════════════════════
# STEP 4: 從 snkrdunk 抓價格
# ═══════════════════════════════════════════════
def scrape_prices():
    print("\n[STEP 4] 從 snkrdunk 抓價格...")

    # 先搜尋發現更多 mapping
    mappings = {}
    for kw in ["SV-P プロモ", "SV-P ピカチュウ", "SV-P ポケモン"]:
        url = f"https://snkrdunk.com/search?keyword={requests.utils.quote(kw)}"
        try:
            r = requests.get(url, headers={"User-Agent": UA}, timeout=30)
            if r.status_code != 200:
                continue
            for m in re.finditer(r'<a\s+[^>]*href="[^"]*?/apparels/(\d+)"[^>]*aria-label="([^"]*?)"', r.text, re.DOTALL):
                aid, label = m.group(1), m.group(2)
                svp = re.search(r'\[(?:SV-P\s*)?(\d{3})(?:/SV-P)?\]', label)
                if svp:
                    uid = f"SV-P_{svp.group(1)}"
                    if uid not in mappings:
                        mappings[uid] = aid
        except:
            pass
        time.sleep(2)

    print(f"  搜尋找到: {len(mappings)} 張")

    # 加上已知 mapping
    for uid, aid in KNOWN_SNKRDUNK.items():
        if uid not in mappings:
            mappings[uid] = aid
    print(f"  加上已知後: {len(mappings)} 張")

    # 儲存 mapping + 抓價格
    price_count = 0
    for i, (uid, aid) in enumerate(mappings.items()):
        # Save mapping
        d1("INSERT OR IGNORE INTO source_mappings (card_uid,source,source_id,source_url) VALUES (?,'snkrdunk',?,?)",
           [uid, aid, f"https://snkrdunk.com/apparels/{aid}"])

        # Fetch price
        try:
            r = requests.get(f"https://snkrdunk.com/apparels/{aid}", headers={"User-Agent": UA}, timeout=30)
            if r.status_code != 200:
                continue

            # Try JSON-LD
            soup = BeautifulSoup(r.text, "html.parser")
            low, high, count, name_ja = 0, 0, 0, ""

            for script in soup.find_all("script", type="application/ld+json"):
                try:
                    jd = json.loads(script.string)
                    if isinstance(jd, list):
                        jd = next((x for x in jd if x.get("@type") == "Product"), None)
                    if jd and jd.get("@type") == "Product":
                        of = jd.get("offers", {})
                        if isinstance(of, dict):
                            low = int(of.get("lowPrice", 0) or 0)
                            high = int(of.get("highPrice", 0) or 0)
                            count = int(of.get("offerCount", 0) or 0)
                        name_ja = jd.get("name", "")
                        break
                except:
                    pass

            # Fallback: HTML price
            if low == 0:
                pm = re.search(r'¥([\d,]+)', r.text)
                if pm:
                    low = int(pm.group(1).replace(',', ''))
                    high = low

            if low > 0:
                d1("INSERT INTO prices (card_uid,source,price,currency,price_type,offer_count) VALUES (?,'snkrdunk',?,'JPY','low',?)",
                   [uid, low, count])
                if high > 0 and high != low:
                    d1("INSERT INTO prices (card_uid,source,price,currency,price_type,offer_count) VALUES (?,'snkrdunk',?,'JPY','high',?)",
                       [uid, high, count])
                price_count += 1
                print(f"  {uid}: ¥{low:,} ~ ¥{high:,}")

            if name_ja:
                d1("UPDATE cards SET name_ja = ? WHERE card_uid = ? AND (name_ja IS NULL OR name_ja = '')",
                   [name_ja, uid])

        except Exception as e:
            print(f"  {uid}: 錯誤 {e}")

        if (i+1) % 5 == 0:
            time.sleep(2)
        else:
            time.sleep(1)

    print(f"  有價格: {price_count} 張")
    return price_count


# ═══════════════════════════════════════════════
# STEP 5: 產生網站
# ═══════════════════════════════════════════════
def generate_site():
    print("\n[STEP 5] 產生網站...")
    cards = d1_rows("""
        SELECT c.card_uid, c.name_en, c.name_ja, c.name_zh,
               c.set_code, c.card_no, c.card_no_display,
               c.card_type, c.energy_type, sm.source_url,
               MIN(CASE WHEN p.price_type='low' THEN p.price END) as low_price,
               MAX(CASE WHEN p.price_type='high' THEN p.price END) as high_price,
               MAX(p.offer_count) as offer_count
        FROM cards c
        LEFT JOIN source_mappings sm ON c.card_uid = sm.card_uid
        LEFT JOIN prices p ON c.card_uid = p.card_uid
        GROUP BY c.card_uid
        ORDER BY CASE WHEN p.price IS NOT NULL THEN 0 ELSE 1 END, MAX(p.price) DESC, c.card_no ASC
    """)

    total = len(cards)
    with_price = sum(1 for c in cards if c.get("low_price"))
    has_zh = sum(1 for c in cards if c.get("name_zh"))
    cj = json.dumps(cards, ensure_ascii=False)
    print(f"  卡片: {total}, 有價格: {with_price}, 有中文名: {has_zh}")

    html = """<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>CARDSTAR 卡市達</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Bebas+Neue&family=Noto+Sans+TC:wght@400;500;700;900&family=DM+Mono:wght@400;500;700&display=swap" rel="stylesheet">
<style>
:root{--bg:#13120e;--s1:#1a1912;--s2:#201f17;--s3:#28271d;--b1:#2e2d22;--b2:#3a3928;--gold:#f5c518;--gold2:#e6b800;--up:#00d084;--dn:#ff3b5c;--text:#f0eed8;--dim:#6b6a52;--dim2:#9b9a78}
[data-theme="light"]{--bg:#f5f3ed;--s1:#fff;--s2:#f0ede5;--s3:#e8e5db;--b1:#d8d4c8;--b2:#c8c4b8;--text:#1a1912;--dim:#9b9a78;--dim2:#6b6a52}
*{margin:0;padding:0;box-sizing:border-box}
body{background:var(--bg);color:var(--text);font-family:'Noto Sans TC',sans-serif;min-height:100vh;transition:background .3s,color .3s}
nav{display:flex;align-items:center;gap:8px;padding:0 20px;height:54px;background:var(--s1);border-bottom:1px solid var(--b1);position:sticky;top:0;z-index:100;transition:background .3s}
.logo{font-family:'Bebas Neue',sans-serif;font-size:20px;letter-spacing:3px;color:var(--gold)}
.logo-zh{font-size:13px;font-weight:900;color:var(--text);letter-spacing:1px;margin-left:2px}
.nav-right{margin-left:auto;display:flex;align-items:center;gap:8px}
.theme-btn{width:34px;height:34px;border-radius:6px;border:1px solid var(--b2);background:var(--s2);color:var(--dim2);font-size:16px;cursor:pointer;display:flex;align-items:center;justify-content:center;transition:all .2s}
.theme-btn:hover{border-color:var(--gold);color:var(--gold)}
.stats-row{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;padding:14px 20px;max-width:800px;margin:0 auto}
.stat-box{background:var(--s1);border:1px solid var(--b1);border-radius:6px;padding:12px;transition:background .3s}
.stat-label{font-size:10px;color:var(--dim2);font-family:'DM Mono',monospace;letter-spacing:1px;text-transform:uppercase;margin-bottom:4px}
.stat-val{font-family:'Bebas Neue',sans-serif;font-size:28px;letter-spacing:1px;line-height:1}
.stat-val.gold{color:var(--gold)}
.search-wrap{max-width:800px;margin:0 auto;padding:0 20px 10px}
.search-input{width:100%;padding:11px 14px;border-radius:6px;border:1px solid var(--b1);background:var(--s2);color:var(--text);font-size:14px;font-family:'Noto Sans TC',sans-serif;outline:none;transition:border-color .2s,background .3s}
.search-input:focus{border-color:var(--gold)}
.search-input::placeholder{color:var(--dim)}
.filter-row{max-width:800px;margin:0 auto;padding:0 20px 10px;display:flex;gap:6px;flex-wrap:wrap}
.fpill{font-size:11px;font-weight:700;padding:6px 14px;border-radius:4px;cursor:pointer;letter-spacing:1px;transition:all .15s;border:1px solid var(--b2);color:var(--dim2);background:transparent;font-family:'DM Mono',monospace}
.fpill.active{background:var(--gold);color:#111;border-color:var(--gold)}
.fpill:hover:not(.active){color:var(--text);border-color:var(--dim2)}
.card-count{max-width:800px;margin:0 auto;padding:0 20px 6px;font-size:11px;color:var(--dim);font-family:'DM Mono',monospace;letter-spacing:1px}
.card-list{max-width:800px;margin:0 auto;padding:0 20px 40px}
.ccard{background:var(--s1);border:1px solid var(--b1);border-radius:8px;padding:14px 16px;margin-bottom:8px;cursor:pointer;transition:transform .15s,border-color .15s,background .3s}
.ccard:hover{transform:translateY(-1px);border-color:var(--gold)}
.ccard.has-price{border-left:3px solid var(--gold)}
.ccard-top{display:flex;justify-content:space-between;align-items:flex-start;gap:10px}
.ccard-name{font-size:14px;font-weight:900;line-height:1.3;flex:1}
.ccard-sub{font-size:11px;color:var(--dim2);margin-top:2px;font-family:'DM Mono',monospace}
.ccard-price{text-align:right;flex-shrink:0}
.price-main{font-family:'Bebas Neue',sans-serif;font-size:22px;color:var(--gold);letter-spacing:1px}
.price-high{font-family:'DM Mono',monospace;font-size:11px;color:var(--dim2);margin-top:1px}
.no-price{font-size:12px;color:var(--dim);font-family:'DM Mono',monospace}
.ccard-meta{display:flex;gap:6px;margin-top:8px;flex-wrap:wrap}
.tag{font-size:10px;padding:2px 7px;border-radius:3px;background:var(--s2);color:var(--dim2);font-family:'DM Mono',monospace;letter-spacing:.5px;transition:background .3s}
.ccard-link{display:inline-block;margin-top:6px;font-size:11px;color:var(--gold);text-decoration:none;font-family:'DM Mono',monospace;opacity:.8}
.ccard-link:hover{opacity:1}
.empty{text-align:center;padding:60px 20px;color:var(--dim)}
.footer{text-align:center;padding:20px;color:var(--dim);font-size:11px;font-family:'DM Mono',monospace;letter-spacing:1px;max-width:800px;margin:0 auto}
@media(max-width:500px){.stats-row{gap:6px;padding:10px 16px}.stat-val{font-size:22px}.card-list,.search-wrap,.filter-row,.card-count{padding-left:16px;padding-right:16px}nav{padding:0 16px}}
</style>
</head>
<body>
<nav><span class="logo">CARDSTAR</span><span class="logo-zh">卡市達</span><div class="nav-right"><button class="theme-btn" onclick="toggleTheme()" id="themeBtn" title="切換主題">🌙</button></div></nav>
<div class="stats-row"><div class="stat-box"><div class="stat-label">TOTAL CARDS</div><div class="stat-val gold">""" + str(total) + """</div></div><div class="stat-box"><div class="stat-label">WITH PRICE</div><div class="stat-val gold">""" + str(with_price) + """</div></div><div class="stat-box"><div class="stat-label">SOURCE</div><div class="stat-val" style="font-size:18px;color:var(--text)">SNKRDUNK</div></div></div>
<div class="search-wrap"><input class="search-input" type="text" id="search" placeholder="搜尋卡片名稱、編號..." oninput="render()"></div>
<div class="filter-row"><button class="fpill active" onclick="setFilter(this,'all')">全部</button><button class="fpill" onclick="setFilter(this,'priced')">有價格</button><button class="fpill" onclick="setFilter(this,'Pokemon')">寶可夢</button><button class="fpill" onclick="setFilter(this,'Trainer')">訓練家</button><button class="fpill" onclick="setFilter(this,'Energy')">能量</button></div>
<div class="card-count" id="cc"></div><div class="card-list" id="cl"></div>
<div class="footer">CARDSTAR v0.4 · DATA FROM SNKRDUNK · PRICES ARE REFERENCE ONLY</div>
<script>
const C=""" + cj + """;let fi='all';
function fmt(p){return p?'¥'+Number(p).toLocaleString():''}
function render(){const q=document.getElementById('search').value.toLowerCase();const l=document.getElementById('cl');const cc=document.getElementById('cc');
let f=C.filter(c=>{const s=[c.name_zh,c.name_en,c.name_ja,c.card_uid,c.card_no_display].filter(Boolean).join(' ').toLowerCase();if(q&&!s.includes(q))return false;if(fi==='priced')return c.low_price>0;if(fi!=='all')return c.card_type===fi;return true});
cc.textContent=f.length+' / '+C.length+' CARDS';const sh=f.slice(0,80);
l.innerHTML=sh.map(c=>{const nm=c.name_zh||c.name_ja||c.name_en||c.card_uid;const sub=c.card_no_display+(c.name_en&&c.name_zh?' · '+c.name_en:'');const hp=c.low_price>0;const u=c.source_url||'';
const ph=hp?'<div class="ccard-price"><div class="price-main">'+fmt(c.low_price)+'</div>'+(c.high_price&&c.high_price!==c.low_price?'<div class="price-high">~ '+fmt(c.high_price)+'</div>':'')+'</div>':'<div class="no-price">—</div>';
const lk=u?'<a class="ccard-link" href="'+u+'" target="_blank" rel="noopener">SNKRDUNK →</a>':'';
return'<div class="ccard '+(hp?'has-price':'')+'"'+(u?' onclick="window.open(\''+u+'\',\'_blank\')"':'')+'><div class="ccard-top"><div><div class="ccard-name">'+nm+'</div><div class="ccard-sub">'+sub+'</div></div>'+ph+'</div><div class="ccard-meta"><span class="tag">'+c.set_code+'</span>'+(c.energy_type?'<span class="tag">'+c.energy_type+'</span>':'')+(c.offer_count?'<span class="tag">'+c.offer_count+' LISTED</span>':'')+'</div>'+lk+'</div>'}).join('');
if(f.length>80)l.innerHTML+='<div class="empty">還有 '+(f.length-80)+' 張，請用搜尋縮小範圍</div>';if(f.length===0)l.innerHTML='<div class="empty">找不到符合的卡片</div>'}
function setFilter(b,f){fi=f;document.querySelectorAll('.fpill').forEach(x=>x.classList.remove('active'));b.classList.add('active');render()}
function toggleTheme(){const h=document.documentElement;const b=document.getElementById('themeBtn');if(h.getAttribute('data-theme')==='light'){h.removeAttribute('data-theme');b.textContent='🌙';localStorage.setItem('theme','dark')}else{h.setAttribute('data-theme','light');b.textContent='☀️';localStorage.setItem('theme','light')}}
if(localStorage.getItem('theme')==='light'){document.documentElement.setAttribute('data-theme','light');document.getElementById('themeBtn').textContent='☀️'}
render();
</script></body></html>"""

    os.makedirs("site", exist_ok=True)
    with open("site/index.html", "w", encoding="utf-8") as f:
        f.write(html)
    print(f"  site/index.html ({len(html):,} bytes)")


# ═══════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════
def main():
    action = sys.argv[1] if len(sys.argv) > 1 else "full"
    print("=" * 50)
    print(f"CARDSTAR 卡市達 Pipeline — [{action}]")
    print("=" * 50)

    if action == "full":
        create_tables(drop=True)
        import_cards()
        update_zh_names()
        scrape_prices()
        generate_site()
    elif action == "import":
        create_tables(drop=True)
        import_cards()
    elif action == "zh":
        create_tables()
        update_zh_names()
    elif action == "prices":
        create_tables()
        scrape_prices()
    elif action == "site":
        create_tables()
        generate_site()
    else:
        print(f"未知動作: {action}")
        print("可用: full / import / zh / prices / site")
        return

    # 最終統計
    print("\n" + "=" * 50)
    print("最終統計:")
    for label, sql in [
        ("卡片總數", "SELECT COUNT(*) as n FROM cards"),
        ("有中文名", "SELECT COUNT(*) as n FROM cards WHERE name_zh IS NOT NULL AND name_zh != ''"),
        ("有價格", "SELECT COUNT(*) as n FROM prices"),
        ("有 mapping", "SELECT COUNT(*) as n FROM source_mappings"),
    ]:
        rows = d1_rows(sql)
        print(f"  {label}: {rows[0]['n'] if rows else '?'}")

    print("\n完成!")


if __name__ == "__main__":
    main()
