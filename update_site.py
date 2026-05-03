"""
CARDSTAR — 自動更新腳本
1. 從 snkrdunk 抓最新價格（含自動搜尋海賊王卡）
2. 累積到 docs/price_history.json
3. 更新 docs/index.html 裡的價格數據
4. 價格變動超過 5% 推 Telegram 通知
"""
import requests
from bs4 import BeautifulSoup
import json, re, os, time
from datetime import datetime

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

# Telegram 設定
TG_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
TG_CHAT = os.environ.get("TELEGRAM_CHAT_ID", "")

# 卡片清單：key, display name, snkrdunk apparel ID
CARDS = [
    {"id": 1, "key": "svp057", "name": "台北的皮卡丘 P [SV-P 057](特典卡「台北寶可夢中心」)【中文版】", "apparel": "520383"},
    {"id": 2, "key": "svp098", "name": "名偵探皮卡丘 P [SV-P 098](特典卡「帰ってきた名探偵ピカチュウ」)", "apparel": "135232"},
    {"id": 3, "key": "svp074", "name": "皮卡丘 P [SV-P 074](「TANTO×ポケモンカードゲーム」特典)", "apparel": "132896"},
    {"id": 4, "key": "svp218", "name": "皮卡丘 P [SV-P 218](プロモカードパック「ポケカの夏がキタ!」)", "apparel": "332798"},
    {"id": 5, "key": "svp242", "name": "皮卡丘 P [SV-P 242](「イラストレーションコンテスト2024」特典)", "apparel": "518774"},
    {"id": 6, "key": "svp001", "name": "皮卡丘 P [SV-P 001](「ポケットモンスター スカーレット・バイオレット」早期購入特典)", "apparel": "104784"},
    {"id": 7, "key": "op05119", "name": "魯夫 SEC [OP05-119](ブースターパック「新時代の主役」)", "apparel": "135437"},
    {"id": 8, "key": "op01120", "name": "紅髮傑克 SEC [OP01-120](ブースターパック「ロマンスドーン」)", "apparel": "142695"},
    {"id": 9, "key": "op02013", "name": "火拳艾斯 SR パラレル [OP02-013](ブースターパック「頂上決戦」)", "apparel": "102435"},
]

APPAREL_CACHE = "docs/apparel_cache.json"

HISTORY_FILE = "docs/price_history.json"
HTML_FILE = "docs/index.html"


def send_telegram(msg):
    """推送 Telegram 訊息"""
    if not TG_TOKEN or not TG_CHAT:
        print("  TG: 未設定 token/chat，跳過")
        return
    try:
        url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
        r = requests.post(url, json={
            "chat_id": TG_CHAT,
            "text": msg,
            "parse_mode": "Markdown",
            "disable_web_page_preview": True,
        }, timeout=10)
        if r.status_code == 200:
            print(f"  TG: 已發送")
        else:
            print(f"  TG: 發送失敗 HTTP {r.status_code}")
    except Exception as e:
        print(f"  TG: 錯誤 {e}")


def search_snkrdunk_op(keyword):
    """在 snkrdunk 搜尋海賊王卡，回傳 apparel ID"""
    try:
        url = f"https://snkrdunk.com/search?keyword={requests.utils.quote(keyword)}"
        r = requests.get(url, headers={"User-Agent": UA}, timeout=30)
        if r.status_code != 200:
            return None
        for m in re.finditer(r'<a\s+[^>]*href="[^"]*?/apparels/(\d+)"[^>]*aria-label="([^"]*?)"', r.text, re.DOTALL):
            aid, label = m.group(1), m.group(2)
            if keyword.replace(" ", "").lower() in label.replace(" ", "").lower():
                return aid
        # 找不到精確match，回傳第一個結果
        m = re.search(r'/apparels/(\d+)', r.text)
        return m.group(1) if m else None
    except:
        return None


def load_apparel_cache():
    """讀取已發現的 apparel ID 快取"""
    if os.path.exists(APPAREL_CACHE):
        with open(APPAREL_CACHE, "r") as f:
            return json.load(f)
    return {}


def save_apparel_cache(cache):
    with open(APPAREL_CACHE, "w") as f:
        json.dump(cache, f, indent=2)


def discover_op_cards():
    """搜尋尚未有 apparel ID 的海賊王卡"""
    cache = load_apparel_cache()
    search_terms = {
        "op05119": "OP05-119 ルフィ SEC",
        "op01120": "OP01-120 シャンクス SEC",
        "op02013": "OP02-013 エース SR",
    }
    for card in CARDS:
        if card["apparel"]:
            continue
        key = card["key"]
        if key in cache and cache[key]:
            card["apparel"] = cache[key]
            print(f"  {key}: 從快取取得 apparel {cache[key]}")
            continue
        if key in search_terms:
            print(f"  搜尋 {key}...", end=" ")
            aid = search_snkrdunk_op(search_terms[key])
            if aid:
                card["apparel"] = aid
                cache[key] = aid
                print(f"找到 apparel {aid}")
            else:
                print("未找到")
            time.sleep(2)
    save_apparel_cache(cache)


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

    # 0. 搜尋還沒有 apparel ID 的海賊王卡
    print(f"\n[0/4] 搜尋海賊王卡 apparel ID...")
    discover_op_cards()

    # 1. Load history
    history = load_history()
    print(f"\n[1/4] 讀取歷史: {sum(len(v) for v in history.values())} 筆")

    # 2. Fetch prices
    print(f"\n[2/4] 抓取 snkrdunk 價格...")
    now = datetime.utcnow().isoformat()
    fetched = 0
    alerts = []  # 收集要推送的通知

    for card in CARDS:
        key = card["key"]
        apparel = card["apparel"]

        if key not in history:
            history[key] = []

        price = fetch_snkrdunk_price(apparel)
        if price and price["low"] > 0:
            # 比較跟前一次的價差
            prev_prices = [p["low"] for p in history[key] if p["low"] > 0]
            if prev_prices:
                prev = prev_prices[-1]
                change_pct = round((price["low"] - prev) / prev * 100, 1)
                if abs(change_pct) >= 5:
                    direction = "📈 飆漲" if change_pct > 0 else "📉 下跌"
                    alerts.append(
                        f"{direction} *{card['name']}*\n"
                        f"¥{prev:,} → ¥{price['low']:,} ({'+' if change_pct>0 else ''}{change_pct}%)"
                    )

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
    print(f"\n[3/4] 更新網站...")
    if fetched > 0:
        update_html(history)
        print("  OK")
    else:
        print("  沒有新價格，跳過更新")

    # 5. Telegram alerts
    print(f"\n[4/4] Telegram 通知...")
    if alerts:
        msg = "🃏 *CARDSTAR 價格警報*\n\n" + "\n\n".join(alerts)
        msg += f"\n\n⏰ {datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC"
        send_telegram(msg)
    else:
        print("  無重大變動，不推送")

        # 每天 00:00 UTC 發一次每日摘要
        hour = datetime.utcnow().hour
        if hour == 0 and fetched > 0:
            summary_lines = []
            for card in CARDS:
                key = card["key"]
                prices = history.get(key, [])
                if not prices:
                    continue
                latest = prices[-1]["low"]
                # 24小時前的價格
                h24_ago = [p["low"] for p in prices[:-24] if p["low"] > 0]
                if h24_ago:
                    prev24 = h24_ago[-1]
                    chg = round((latest - prev24) / prev24 * 100, 1)
                    arrow = "↗" if chg > 0 else "↘" if chg < 0 else "→"
                    summary_lines.append(f"{arrow} {card['name']}: ¥{latest:,} ({'+' if chg>0 else ''}{chg}%)")

            if summary_lines:
                msg = "📊 *CARDSTAR 每日摘要*\n\n" + "\n".join(summary_lines)
                msg += f"\n\n⏰ {datetime.utcnow().strftime('%Y-%m-%d')} UTC"
                send_telegram(msg)

    print(f"\n完成!")


if __name__ == "__main__":
    main()
