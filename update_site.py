"""
CARDSTAR — 自動更新腳本
1. 從 snkrdunk 抓最新價格
2. 累積到 docs/price_history.json
3. 更新 docs/index.html 裡的價格數據
"""
import requests
from bs4 import BeautifulSoup
import json, re, os, time
from datetime import datetime

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

# snkrdunk apparel IDs for each card
CARDS = [
    {"id": 1, "key": "svp057", "apparel": "520383"},
    {"id": 2, "key": "svp098", "apparel": "135232"},
    {"id": 3, "key": "svp074", "apparel": "132896"},
    {"id": 4, "key": "svp218", "apparel": "332798"},
    {"id": 5, "key": "svp242", "apparel": "518774"},
    {"id": 6, "key": "svp001", "apparel": "104784"},
    {"id": 7, "key": "op05119", "apparel": None},  # 需要找到 apparel ID
    {"id": 8, "key": "op01120", "apparel": None},
    {"id": 9, "key": "op02013", "apparel": None},
]

HISTORY_FILE = "docs/price_history.json"
HTML_FILE = "docs/index.html"


def fetch_snkrdunk_price(apparel_id):
    """從 snkrdunk 抓即時價格"""
    if not apparel_id:
        return None
    url = f"https://snkrdunk.com/apparels/{apparel_id}"
    try:
        r = requests.get(url, headers={"User-Agent": UA}, timeout=30)
        if r.status_code != 200:
            return None
        soup = BeautifulSoup(r.text, "html.parser")
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                jd = json.loads(script.string)
                if isinstance(jd, list):
                    jd = next((x for x in jd if x.get("@type") == "Product"), None)
                if jd and jd.get("@type") == "Product":
                    of = jd.get("offers", {})
                    return {
                        "low": int(of.get("lowPrice", 0) or 0),
                        "high": int(of.get("highPrice", 0) or 0),
                        "count": int(of.get("offerCount", 0) or 0),
                        "name": jd.get("name", ""),
                    }
            except:
                pass
        # Fallback: HTML price
        pm = re.search(r"¥([\d,]+)", r.text)
        if pm:
            p = int(pm.group(1).replace(",", ""))
            return {"low": p, "high": p, "count": 0, "name": ""}
    except:
        pass
    return None


def load_history():
    """讀取價格歷史"""
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "r") as f:
            return json.load(f)
    return {}


def save_history(history):
    """儲存價格歷史"""
    with open(HISTORY_FILE, "w") as f:
        json.dump(history, f, indent=2)


def update_html(history):
    """更新 HTML 裡的價格數據"""
    if not os.path.exists(HTML_FILE):
        print("  ERROR: docs/index.html not found")
        return False

    with open(HTML_FILE, "r") as f:
        html = f.read()

    now = datetime.utcnow()
    date_str = now.strftime("%m/%d")

    for card in CARDS:
        key = card["key"]
        if key not in history or not history[key]:
            continue

        prices = history[key]
        latest = prices[-1]["low"] if prices else 0
        if latest <= 0:
            continue

        card_id = card["id"]

        # Calculate 7-day average
        recent = [p["low"] for p in prices[-168:] if p["low"] > 0]  # 168 = 7 days * 24 hours
        avg = int(sum(recent) / len(recent)) if recent else latest

        # Calculate change %
        old_prices = [p["low"] for p in prices[:-24] if p["low"] > 0]
        if old_prices:
            old_avg = sum(old_prices[-168:]) / len(old_prices[-168:]) if len(old_prices) > 0 else latest
            chg = round((avg - old_avg) / old_avg * 100, 1) if old_avg > 0 else 0
        else:
            chg = 0
        direction = "up" if chg >= 0 else "dn"

        # Build chart data (last N data points)
        all_lows = [p["low"] for p in prices if p["low"] > 0]
        h24 = all_lows[-12:] if len(all_lows) >= 12 else all_lows  # 24h = 12 data points (every 2h)
        w1 = all_lows[-84::12] if len(all_lows) >= 84 else all_lows[-7:]  # weekly
        m1 = all_lows[-720::60] if len(all_lows) >= 720 else all_lows[-12:]  # monthly
        q3 = all_lows[-2160::180] if len(all_lows) >= 2160 else all_lows[-12:]  # 3 months

        # Ensure minimum data points
        while len(h24) < 6:
            h24 = [h24[0]] + h24 if h24 else [latest]
        while len(w1) < 4:
            w1 = [w1[0]] + w1 if w1 else [latest]
        while len(m1) < 4:
            m1 = [m1[0]] + m1 if m1 else [latest]
        while len(q3) < 4:
            q3 = [q3[0]] + q3 if q3 else [latest]

        # Offers count
        offers = prices[-1].get("count", 0)

        # Update avg
        html = re.sub(
            rf'(id:{card_id},.*?)avg:\d+',
            rf'\g<1>avg:{avg}',
            html
        )
        # Update chg
        html = re.sub(
            rf'(id:{card_id},.*?)chg:[+-]?[\d.]+',
            rf'\g<1>chg:{chg}',
            html
        )
        # Update dir
        html = re.sub(
            rf'(id:{card_id},.*?)dir:"(?:up|dn)"',
            rf'\g<1>dir:"{direction}"',
            html
        )
        # Update offers
        html = re.sub(
            rf'(id:{card_id},.*?)offers:\d+',
            rf'\g<1>offers:{offers}',
            html
        )
        # Update chart data
        html = re.sub(
            rf'(id:{card_id},.*?)h:\[[^\]]+\]',
            rf'\g<1>h:{json.dumps(h24)}',
            html
        )
        html = re.sub(
            rf'(id:{card_id},.*?)w:\[[^\]]+\]',
            rf'\g<1>w:{json.dumps(w1)}',
            html
        )
        html = re.sub(
            rf'(id:{card_id},.*?)m:\[[^\]]+\]',
            rf'\g<1>m:{json.dumps(m1)}',
            html
        )
        html = re.sub(
            rf'(id:{card_id},.*?)q:\[[^\]]+\]',
            rf'\g<1>q:{json.dumps(q3)}',
            html
        )

        # Update market price (snkrdunk)
        html = re.sub(
            rf'(id:{card_id},.*?n:"snkrdunk".*?)j:\d+',
            rf'\g<1>j:{latest}',
            html
        )

        # Add latest transaction
        new_tx = f'{{d:"{date_str}",s:"snkrdunk · JP",p:{latest}}}'
        html = re.sub(
            rf'(id:{card_id},.*?txs:\[)',
            rf'\g<1>{new_tx},',
            html
        )

        print(f"  Card {card_id} ({key}): avg=¥{avg:,} chg={chg}% offers={offers}")

    with open(HTML_FILE, "w") as f:
        f.write(html)

    return True


def main():
    print("=" * 50)
    print(f"CARDSTAR 自動更新 — {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")
    print("=" * 50)

    # 1. Load history
    history = load_history()
    print(f"\n[1/3] 讀取歷史: {sum(len(v) for v in history.values())} 筆")

    # 2. Fetch prices
    print(f"\n[2/3] 抓取 snkrdunk 價格...")
    now = datetime.utcnow().isoformat()
    fetched = 0

    for card in CARDS:
        key = card["key"]
        apparel = card["apparel"]

        if key not in history:
            history[key] = []

        price = fetch_snkrdunk_price(apparel)
        if price and price["low"] > 0:
            history[key].append({
                "time": now,
                "low": price["low"],
                "high": price["high"],
                "count": price["count"],
            })
            fetched += 1
            print(f"  {key}: ¥{price['low']:,} ~ ¥{price['high']:,} ({price['count']} offers)")
        elif apparel:
            print(f"  {key}: 無法取得")
        else:
            print(f"  {key}: 尚無 apparel ID，跳過")

        if apparel:
            time.sleep(2)

    print(f"  取得: {fetched} 張")

    # 3. Save history
    save_history(history)
    total = sum(len(v) for v in history.values())
    print(f"\n  歷史累積: {total} 筆")

    # 4. Update HTML
    print(f"\n[3/3] 更新網站...")
    if fetched > 0:
        update_html(history)
        print("  OK")
    else:
        print("  沒有新價格，跳過更新")

    print(f"\n完成!")


if __name__ == "__main__":
    main()
