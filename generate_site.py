"""
CARDSTAR 卡市達 — 靜態網站產生器 v2
設計語言：金色交易所風格（參考 Jay 的 v3 demo）
"""

import requests
import json
import os

CF_ACCOUNT_ID = os.environ["CF_ACCOUNT_ID"]
CF_D1_DATABASE_ID = os.environ["CF_D1_DATABASE_ID"]
CF_D1_TOKEN = os.environ["CF_D1_TOKEN"]
D1_API = f"https://api.cloudflare.com/client/v4/accounts/{CF_ACCOUNT_ID}/d1/database/{CF_D1_DATABASE_ID}/query"

HEADERS_D1 = {
    "Authorization": f"Bearer {CF_D1_TOKEN}",
    "Content-Type": "application/json",
}


def d1(sql):
    r = requests.post(D1_API, headers=HEADERS_D1, json={"sql": sql})
    data = r.json()
    if not data.get("success"):
        return []
    try:
        return data["result"][0]["results"]
    except (KeyError, IndexError):
        return []


def main():
    print("CARDSTAR 卡市達 — 網站產生中...")

    cards = d1("""
        SELECT c.card_uid, c.name_en, c.name_ja, c.name_zh,
               c.set_code, c.card_no, c.card_no_display,
               c.card_type, c.energy_type,
               sm.source_url,
               MIN(CASE WHEN p.price_type='low' THEN p.price END) as low_price,
               MAX(CASE WHEN p.price_type='high' THEN p.price END) as high_price,
               MAX(p.offer_count) as offer_count
        FROM cards c
        LEFT JOIN source_mappings sm ON c.card_uid = sm.card_uid
        LEFT JOIN prices p ON c.card_uid = p.card_uid
        GROUP BY c.card_uid
        ORDER BY
            CASE WHEN p.price IS NOT NULL THEN 0 ELSE 1 END,
            MAX(p.price) DESC, c.card_no ASC
    """)

    with_price = sum(1 for c in cards if c.get("low_price"))
    total = len(cards)
    cards_json = json.dumps(cards, ensure_ascii=False)

    print(f"  卡片: {total}, 有價格: {with_price}")

    html = """<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>CARDSTAR 卡市達</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Bebas+Neue&family=Noto+Sans+TC:wght@400;500;700;900&family=DM+Mono:wght@400;500;700&display=swap" rel="stylesheet">
<style>
:root {
  --bg:#13120e; --s1:#1a1912; --s2:#201f17; --s3:#28271d;
  --b1:#2e2d22; --b2:#3a3928;
  --gold:#f5c518; --gold2:#e6b800;
  --up:#00d084; --dn:#ff3b5c;
  --text:#f0eed8; --dim:#6b6a52; --dim2:#9b9a78;
}
[data-theme="light"] {
  --bg:#f5f3ed; --s1:#ffffff; --s2:#f0ede5; --s3:#e8e5db;
  --b1:#d8d4c8; --b2:#c8c4b8;
  --text:#1a1912; --dim:#9b9a78; --dim2:#6b6a52;
}

*{margin:0;padding:0;box-sizing:border-box;}
body{background:var(--bg);color:var(--text);font-family:'Noto Sans TC',sans-serif;min-height:100vh;transition:background .3s,color .3s;}

/* ── NAV ── */
nav{display:flex;align-items:center;gap:8px;padding:0 20px;height:54px;background:var(--s1);border-bottom:1px solid var(--b1);position:sticky;top:0;z-index:100;transition:background .3s;}
.logo{font-family:'Bebas Neue',sans-serif;font-size:20px;letter-spacing:3px;color:var(--gold);}
.logo-zh{font-size:13px;font-weight:900;color:var(--text);letter-spacing:1px;margin-left:2px;}
.nav-right{margin-left:auto;display:flex;align-items:center;gap:8px;}
.theme-btn{width:34px;height:34px;border-radius:6px;border:1px solid var(--b2);background:var(--s2);color:var(--dim2);font-size:16px;cursor:pointer;display:flex;align-items:center;justify-content:center;transition:all .2s;}
.theme-btn:hover{border-color:var(--gold);color:var(--gold);}

/* ── STATS ── */
.stats-row{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;padding:14px 20px;max-width:800px;margin:0 auto;}
.stat-box{background:var(--s1);border:1px solid var(--b1);border-radius:6px;padding:12px;transition:background .3s;}
.stat-label{font-size:10px;color:var(--dim2);font-family:'DM Mono',monospace;letter-spacing:1px;text-transform:uppercase;margin-bottom:4px;}
.stat-val{font-family:'Bebas Neue',sans-serif;font-size:28px;letter-spacing:1px;line-height:1;}
.stat-val.gold{color:var(--gold);}

/* ── SEARCH ── */
.search-wrap{max-width:800px;margin:0 auto;padding:0 20px 10px;}
.search-input{width:100%;padding:11px 14px;border-radius:6px;border:1px solid var(--b1);background:var(--s2);color:var(--text);font-size:14px;font-family:'Noto Sans TC',sans-serif;outline:none;transition:border-color .2s,background .3s;}
.search-input:focus{border-color:var(--gold);}
.search-input::placeholder{color:var(--dim);}

/* ── FILTERS ── */
.filter-row{max-width:800px;margin:0 auto;padding:0 20px 10px;display:flex;gap:6px;flex-wrap:wrap;}
.fpill{font-size:11px;font-weight:700;padding:6px 14px;border-radius:4px;cursor:pointer;letter-spacing:1px;transition:all .15s;border:1px solid var(--b2);color:var(--dim2);background:transparent;font-family:'DM Mono',monospace;}
.fpill.active{background:var(--gold);color:#111;border-color:var(--gold);}
.fpill:hover:not(.active){color:var(--text);border-color:var(--dim2);}

.card-count{max-width:800px;margin:0 auto;padding:0 20px 6px;font-size:11px;color:var(--dim);font-family:'DM Mono',monospace;letter-spacing:1px;}

/* ── CARD LIST ── */
.card-list{max-width:800px;margin:0 auto;padding:0 20px 40px;}

.ccard{background:var(--s1);border:1px solid var(--b1);border-radius:8px;padding:14px 16px;margin-bottom:8px;cursor:pointer;transition:transform .15s,border-color .15s,background .3s;}
.ccard:hover{transform:translateY(-1px);border-color:var(--gold);}
.ccard.has-price{border-left:3px solid var(--gold);}

.ccard-top{display:flex;justify-content:space-between;align-items:flex-start;gap:10px;}
.ccard-name{font-size:14px;font-weight:900;line-height:1.3;flex:1;}
.ccard-sub{font-size:11px;color:var(--dim2);margin-top:2px;font-family:'DM Mono',monospace;}

.ccard-price{text-align:right;flex-shrink:0;}
.price-main{font-family:'Bebas Neue',sans-serif;font-size:22px;color:var(--gold);letter-spacing:1px;}
.price-high{font-family:'DM Mono',monospace;font-size:11px;color:var(--dim2);margin-top:1px;}
.no-price{font-size:12px;color:var(--dim);font-family:'DM Mono',monospace;}

.ccard-meta{display:flex;gap:6px;margin-top:8px;flex-wrap:wrap;}
.tag{font-size:10px;padding:2px 7px;border-radius:3px;background:var(--s2);color:var(--dim2);font-family:'DM Mono',monospace;letter-spacing:0.5px;transition:background .3s;}

.ccard-link{display:inline-block;margin-top:6px;font-size:11px;color:var(--gold);text-decoration:none;font-family:'DM Mono',monospace;letter-spacing:0.5px;opacity:0.8;}
.ccard-link:hover{opacity:1;}

.empty{text-align:center;padding:60px 20px;color:var(--dim);}

/* ── FOOTER ── */
.footer{text-align:center;padding:20px;color:var(--dim);font-size:11px;font-family:'DM Mono',monospace;letter-spacing:1px;max-width:800px;margin:0 auto;}

@media(max-width:500px){
  .stats-row{grid-template-columns:repeat(3,1fr);gap:6px;padding:10px 16px;}
  .stat-val{font-size:22px;}
  .card-list,.search-wrap,.filter-row,.card-count{padding-left:16px;padding-right:16px;}
  nav{padding:0 16px;}
}
</style>
</head>
<body>

<nav>
  <span class="logo">CARDSTAR</span>
  <span class="logo-zh">卡市達</span>
  <div class="nav-right">
    <button class="theme-btn" onclick="toggleTheme()" id="themeBtn" title="切換主題">🌙</button>
  </div>
</nav>

<div class="stats-row">
  <div class="stat-box">
    <div class="stat-label">TOTAL CARDS</div>
    <div class="stat-val gold">""" + str(total) + """</div>
  </div>
  <div class="stat-box">
    <div class="stat-label">WITH PRICE</div>
    <div class="stat-val gold">""" + str(with_price) + """</div>
  </div>
  <div class="stat-box">
    <div class="stat-label">SOURCE</div>
    <div class="stat-val" style="font-size:18px;color:var(--text)">SNKRDUNK</div>
  </div>
</div>

<div class="search-wrap">
  <input class="search-input" type="text" id="search" placeholder="搜尋卡片 / Search cards..." oninput="render()">
</div>

<div class="filter-row">
  <button class="fpill active" onclick="setFilter(this,'all')">ALL</button>
  <button class="fpill" onclick="setFilter(this,'priced')">有價格</button>
  <button class="fpill" onclick="setFilter(this,'Pokemon')">POKEMON</button>
  <button class="fpill" onclick="setFilter(this,'Trainer')">TRAINER</button>
  <button class="fpill" onclick="setFilter(this,'Energy')">ENERGY</button>
</div>

<div class="card-count" id="cardCount"></div>
<div class="card-list" id="cardList"></div>

<div class="footer">
  CARDSTAR v0.4 &middot; DATA FROM SNKRDUNK<br>
  PRICES ARE REFERENCE ONLY
</div>

<script>
const CARDS = """ + cards_json + """;
let filter = 'all';

function fmt(p) {
  if (!p) return '';
  return '¥' + Number(p).toLocaleString();
}

function render() {
  const q = document.getElementById('search').value.toLowerCase();
  const list = document.getElementById('cardList');
  const countEl = document.getElementById('cardCount');

  let f = CARDS.filter(c => {
    const s = [c.name_en, c.name_ja, c.name_zh, c.card_uid, c.card_no_display]
      .filter(Boolean).join(' ').toLowerCase();
    if (q && !s.includes(q)) return false;
    if (filter === 'priced') return c.low_price > 0;
    if (filter !== 'all') return c.card_type === filter;
    return true;
  });

  countEl.textContent = f.length + ' / ' + CARDS.length + ' CARDS';

  const show = f.slice(0, 80);
  list.innerHTML = show.map(c => {
    const name = c.name_ja || c.name_en || c.card_uid;
    const sub = c.card_no_display || '';
    const hp = c.low_price > 0;
    const url = c.source_url || '';

    const priceHtml = hp
      ? '<div class="ccard-price"><div class="price-main">' + fmt(c.low_price) + '</div>'
        + (c.high_price && c.high_price !== c.low_price
          ? '<div class="price-high">~ ' + fmt(c.high_price) + '</div>' : '')
        + '</div>'
      : '<div class="no-price">—</div>';

    const link = url
      ? '<a class="ccard-link" href="' + url + '" target="_blank" rel="noopener">SNKRDUNK →</a>'
      : '';

    return '<div class="ccard ' + (hp ? 'has-price' : '') + '"'
      + (url ? ' onclick="window.open(\\''+url+'\\',\\'_blank\\')"' : '')
      + '>'
      + '<div class="ccard-top"><div>'
      + '<div class="ccard-name">' + name + '</div>'
      + '<div class="ccard-sub">' + sub + '</div>'
      + '</div>' + priceHtml + '</div>'
      + '<div class="ccard-meta">'
      + '<span class="tag">' + c.set_code + '</span>'
      + (c.energy_type ? '<span class="tag">' + c.energy_type + '</span>' : '')
      + (c.offer_count ? '<span class="tag">' + c.offer_count + ' LISTED</span>' : '')
      + '</div>'
      + link + '</div>';
  }).join('');

  if (f.length > 80) {
    list.innerHTML += '<div class="empty">還有 ' + (f.length - 80) + ' 張，請用搜尋縮小範圍</div>';
  }
  if (f.length === 0) {
    list.innerHTML = '<div class="empty">找不到符合的卡片</div>';
  }
}

function setFilter(btn, f) {
  filter = f;
  document.querySelectorAll('.fpill').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  render();
}

function toggleTheme() {
  const body = document.documentElement;
  const btn = document.getElementById('themeBtn');
  if (body.getAttribute('data-theme') === 'light') {
    body.removeAttribute('data-theme');
    btn.textContent = '🌙';
    localStorage.setItem('theme', 'dark');
  } else {
    body.setAttribute('data-theme', 'light');
    btn.textContent = '☀️';
    localStorage.setItem('theme', 'light');
  }
}

// Restore theme
if (localStorage.getItem('theme') === 'light') {
  document.documentElement.setAttribute('data-theme', 'light');
  document.getElementById('themeBtn').textContent = '☀️';
}

render();
</script>
</body>
</html>"""

    os.makedirs("site", exist_ok=True)
    with open("site/index.html", "w", encoding="utf-8") as f:
        f.write(html)

    print(f"  完成: site/index.html ({len(html):,} bytes)")


if __name__ == "__main__":
    main()
