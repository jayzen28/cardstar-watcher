"""
CARDSTAR — 自動更新腳本 v3
1. 自動探勘新卡（不足 100 張時觸發）
2. 從 cards_data.json 讀取所有卡片
3. 抓 snkrdunk 最新價格（全部卡片）
4. 累積價格歷史 + 計算走勢
5. 重建網站 HTML
6. Telegram 推播
"""
import requests
from bs4 import BeautifulSoup
import json, re, os, sys, time, subprocess
import html as htmlmod
from datetime import datetime

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
TG_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
TG_CHAT = os.environ.get("TELEGRAM_CHAT_ID", "")
DATA_FILE = "docs/cards_data.json"
HISTORY_FILE = "docs/price_history.json"
HTML_FILE = "docs/index.html"

def auto_discover():
    need = False
    if not os.path.exists(DATA_FILE):
        need = True
    else:
        try:
            with open(DATA_FILE) as f:
                data = json.load(f)
            if len(data.get("cards", {})) < 100:
                need = True
        except:
            need = True
    if need and os.path.exists("discover_cards.py"):
        print("[AUTO] 卡片不足 100 張，啟動自動探勘...")
        subprocess.run([sys.executable, "discover_cards.py"], check=False)
        print("[AUTO] 探勘完成\n")

def fetch_price(apparel_id):
    if not apparel_id:
        return None
    url = f"https://snkrdunk.com/apparels/{apparel_id}"
    try:
        r = requests.get(url, headers={"User-Agent": UA}, timeout=30)
        if r.status_code != 200:
            return None
        soup = BeautifulSoup(r.text, "html.parser")
        result = {}
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                jd = json.loads(script.string)
                if isinstance(jd, list):
                    jd = next((x for x in jd if x.get("@type") == "Product"), None)
                if jd and jd.get("@type") == "Product":
                    of = jd.get("offers", {})
                    result = {
                        "low": int(of.get("lowPrice", 0) or 0),
                        "high": int(of.get("highPrice", 0) or 0),
                        "count": int(of.get("offerCount", 0) or 0),
                    }
                    break
            except:
                pass
        if not result:
            pm = re.search(r"¥([\d,]+)", r.text)
            if pm:
                result = {"low": int(pm.group(1).replace(",", "")), "high": 0, "count": 0}
        # Also grab og:image if available
        og = soup.find("meta", property="og:image")
        if og and og.get("content") and "cdn.snkrdunk.com" in og["content"]:
            result["image_cdn"] = og["content"]
        return result if result.get("low", 0) > 0 else None
    except:
        return None

YAHOO_EXCLUDES = ["玩具","公仔","玩偶","絨毛","figure","悠遊卡","鑰匙圈","貼紙",
    "磁鐵","徽章","文件夾","筆記本","T恤","衣服","帽子","襪子","外套",
    "兒童餐","機台","gaole","Gaole","Tretta","代購","預購","仿品",
    "盒玩","扭蛋","吊飾","手機殼","收納","杯","碗","筷","餐具","毛巾"]

def fetch_yahoo_tw(card_no, game="pcg"):
    """搜尋 Yahoo 拍賣台灣，回傳最低價 (TWD)"""
    if not card_no:
        return None
    prefix = "PTCG" if game == "pcg" else "航海王卡"
    clean_no = card_no.replace("/", " ")
    query = f"{prefix} {clean_no}"
    url = f"https://tw.bid.yahoo.com/search/auction/product?ht={requests.utils.quote(query)}"
    try:
        r = requests.get(url, headers={"User-Agent": UA}, timeout=30)
        if r.status_code != 200:
            return None
        prices = []
        for m in re.finditer(r'\$\s*([\d,]+)', r.text):
            p = int(m.group(1).replace(",", ""))
            if 50 <= p <= 5000000:
                prices.append(p)
        if prices:
            prices.sort()
            return {"low": min(prices), "count": len(prices)}
        return None
    except:
        return None

def send_telegram(msg):
    if not TG_TOKEN or not TG_CHAT:
        return
    try:
        requests.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
            json={"chat_id": TG_CHAT, "text": msg, "parse_mode": "Markdown", "disable_web_page_preview": True}, timeout=10)
        print("  TG: 已發送")
    except Exception as e:
        print(f"  TG: 錯誤 {e}")

TRANSLATIONS = {
    "ハイクラスパック": "高級擴充包", "拡張パック": "擴充包", "強化拡張パック": "強化擴充包",
    "プロモーションカード": "特典卡", "プロモカードパック": "特典卡包", "スタートデッキ": "起始牌組",
    "ブースターパック": "擴充包", "スペシャルBOX": "特別禮盒", "スターターセット": "起始套組",
    "スカーレット&バイオレット": "朱&紫", "ポケモンカード151": "寶可夢卡牌151",
    "ポケモンカードゲーム": "寶可夢卡牌", "ポケモンカード": "寶可夢卡牌",
    "メガエボリューション": "超級進化", "ウルトラプレミアムコレクション": "極致典藏組",
    "テラスタルフェスex": "太晶盛宴ex", "メガブレイブ": "MEGA勇者",
    "ドリームリーグ": "夢想聯盟", "クレイバースト": "黏土爆裂",
    "クリムゾンヘイズ": "緋紅薄霧", "レイジングサーフ": "狂浪巨浪",
    "VMAXクライマックス": "VMAX巔峰", "蒼空ストリーム": "蒼空烈流",
    "GXバトルブースト": "GX對戰強化", "シャイニートレジャーex": "閃耀寶藏ex",
    "MEGAドリームex": "MEGA夢想ex", "インフェルノX": "煉獄X",
    "超電ブレイカー": "超電突破者", "黒炎の支配者": "黑炎的支配者",
    "ニンジャスピナー": "忍者旋鏢", "バトルパートナーズ": "對戰夥伴",
    "バトルコレクション": "對戰收藏", "スペシャルデッキセット": "特別牌組套裝",
    "プレミアムブースター": "精選擴充包", "コレクション ムーン": "收藏 月亮",
    "熱風のアリーナ": "熱風的競技場", "アリーナ": "競技場",
    "メガ噴火龍Xex": "超級噴火龍Xex", "メガ路卡利歐ex": "超級路卡利歐ex",
    "メガ甲賀忍蛙ex": "超級甲賀忍蛙ex", "メガ耿鬼ex": "超級耿鬼ex",
    "ロケット団の超夢": "火箭隊的超夢", "ロケット団の栄光": "火箭隊的榮光",
    "奇樹のハラバリーex": "奇樹的電肚蛙ex",
    "莉莉艾のピッピex": "莉莉艾的皮皮ex", "リーリエのピッピex": "莉莉艾的皮皮ex",
    "名探偵皮卡丘": "名偵探皮卡丘", "オドリドリ": "花舞鳥",
    "ヒトデマン": "海星星", "ネイティオ": "天然雀", "ファイヤー": "火焰鳥",
    "ソルガレオ&ルナアーラGX": "索爾迦雷歐&露奈雅拉GX",
    "トウホクの皮卡丘": "東北的皮卡丘", "ヒロシマの皮卡丘": "廣島的皮卡丘",
    "フクオカの皮卡丘": "福岡的皮卡丘",
    "ポケモンセンタートウホク": "寶可夢中心東北", "ポケモンセンターヒロシマ": "寶可夢中心廣島",
    "ポケモンセンターフクオカ": "寶可夢中心福岡", "台北オープン記念": "台北開幕紀念",
    "中国語箔押しエラー": "中文版燙金錯版", "仕様": "版",
    "コミパラ": "漫畫平行卡", "シリアル": "序號", "赤髪": "紅髮", "開封済": "已開封",
    "新時代の主役": "新時代的主角", "ロマンスドーン": "ROMANCE DAWN",
    "頂上決戦": "頂上決戰", "新たなる皇帝": "新皇帝", "神速の拳": "神速之拳",
    "フラッグシップバトル記念品": "旗艦戰紀念品", "イラストレーションコンテスト": "插畫大賽",
    "5周年記念カード": "5周年紀念卡", "ポケカの夏がキタ!": "寶可夢卡之夏來了！",
    "プロモ": "", "の": "的", "ゲーム": "", "タント": "TANTO", "for Japan": "",
    "【中国語版】": "【中文版】", "【インドネシア語版】": "【印尼版】",
    "【英語版】": "【英文版】", "【中国語】": "【簡中版】",
}

def fix_name(name):
    name = htmlmod.unescape(name)
    name = re.sub(r'の新品.*$', '', name).strip()
    name = re.sub(r'｜スニダン.*$', '', name).strip()
    for ja, zh in TRANSLATIONS.items():
        name = name.replace(ja, zh)
    return name.replace("  ", " ").strip()

def rebuild_html(cards, history):
    if not os.path.exists(HTML_FILE):
        return
    sorted_cards = sorted(cards.values(), key=lambda x: x.get("price", 0), reverse=True)
    lines = ["const CARDS = ["]
    for i, c in enumerate(sorted_cards):
        aid = c.get("apparel", "")
        name_zh = fix_name(c.get("name_zh", c.get("name_ja", "")))
        name_ja = htmlmod.unescape(c.get("name_ja", ""))
        price = c.get("price", 0)
        game = c.get("game", "pcg")
        img = c.get("image_cdn", "") or c.get("image", "")
        card_no = c.get("card_no", "")
        offers = c.get("offers", 0)
        chg = 0.0
        direction = "up"
        lows = [p["low"] for p in history.get(aid, []) if p.get("low", 0) > 0]
        if len(lows) >= 2:
            old = lows[-24] if len(lows) >= 24 else lows[0]
            if old > 0:
                chg = round((price - old) / old * 100, 1)
                direction = "up" if chg >= 0 else "dn"
        h24 = lows[-12:] or [price]
        w1 = (lows[-84::12] if len(lows) >= 84 else lows[-7:]) or [price]
        m1 = (lows[-720::60] if len(lows) >= 720 else lows[-12:]) or [price]
        q3 = (lows[-2160::180] if len(lows) >= 2160 else lows[-12:]) or [price]
        for arr in [h24, w1, m1, q3]:
            while len(arr) < 4:
                arr.insert(0, arr[0])
        short = re.sub(r'\([^)]+\)$', '', name_zh).strip()
        cat = "寶可夢卡" if game == "pcg" else "航海王卡"
        t = name_zh.replace('\\','\\\\').replace('"','\\"')
        s = short.replace('\\','\\\\').replace('"','\\"')
        j = name_ja.replace('\\','\\\\').replace('"','\\"')
        # Build markets
        mkts = f'{{n:"snkrdunk",loc:"JP",code:"JP",j:{price}}}'
        ytw = c.get("yahoo_tw_price", 0)
        if ytw and ytw > 0:
            mkts += f',{{n:"Yahoo 拍賣",loc:"TW",code:"TW",t:{ytw}}}'

        line = (
            f'  {{id:{i+1},title:"{t}",sub:"{cat}",name:"{s}",ja:"{j}",'
            f'img:"{img}",avg:{price},chg:{chg},dir:"{direction}",'
            f'tracked:{max(100,5000-i*50)},offers:{offers},desc:"",apparel:"{aid}",'
            f'mkts:[{mkts}],'
            f'txs:[],ch:{{h:{json.dumps(h24)},w:{json.dumps(w1)},m:{json.dumps(m1)},q:{json.dumps(q3)}}},'
            f'info:{{分類:"{cat}",編號:"{card_no}"}}}},'
        )
        lines.append(line)
    lines.append("];")
    with open(HTML_FILE, "r") as f:
        html = f.read()
    start = html.find("const CARDS = [")
    end = html.find("];", start) + 2
    if start >= 0 and end > start:
        html = html[:start] + "\n".join(lines) + html[end:]
        with open(HTML_FILE, "w") as f:
            f.write(html)
        print(f"  HTML: {len(sorted_cards)} 張卡")

def main():
    print("=" * 50)
    print(f"CARDSTAR v3 — {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")
    print("=" * 50)
    auto_discover()
    if not os.path.exists(DATA_FILE):
        print("ERROR: cards_data.json not found")
        return
    with open(DATA_FILE) as f:
        data = json.load(f)
    cards = data.get("cards", {})
    print(f"\n[1/4] 卡片: {len(cards)} 張")
    history = {}
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE) as f:
            history = json.load(f)
    print(f"[2/4] 歷史: {sum(len(v) for v in history.values())} 筆")
    print(f"\n[3/4] 抓取價格（全 {len(cards)} 張）...")
    now = datetime.utcnow().isoformat()
    fetched = 0
    alerts = []
    for aid, card in cards.items():
        apparel = card.get("apparel", aid)
        if not apparel:
            continue
        price = fetch_price(apparel)
        if price and price.get("low", 0) > 0:
            card["price"] = price["low"]
            card["high"] = price.get("high", 0)
            card["offers"] = price.get("count", 0)
            if not card.get("image_cdn") and price.get("image_cdn"):
                card["image_cdn"] = price["image_cdn"]
            if apparel not in history:
                history[apparel] = []
            history[apparel].append({"time": now, "low": price["low"], "high": price.get("high", 0), "count": price.get("count", 0)})
            h = history[apparel]
            if len(h) >= 48 and len(h) >= 2:
                prev = h[-2]["low"]
                if prev > 0:
                    chg = round((price["low"] - prev) / prev * 100, 1)
                    if abs(chg) >= 5:
                        name = fix_name(card.get("name_zh", ""))[:30]
                        d = "📈" if chg > 0 else "📉"
                        alerts.append(f"{d} *{name}*\n¥{prev:,} → ¥{price['low']:,} ({'+' if chg>0 else ''}{chg}%)")
            fetched += 1
            if fetched % 20 == 0:
                print(f"  ... {fetched} 張")
        # Yahoo TW price
        card_no = card.get("card_no", "")
        if card_no and fetched % 3 == 0:  # Every 3rd card to save time
            ytw = fetch_yahoo_tw(card_no, card.get("game", "pcg"))
            if ytw and ytw.get("low", 0) > 0:
                card["yahoo_tw_price"] = ytw["low"]
                card["yahoo_tw_count"] = ytw.get("count", 0)

        time.sleep(1.5)
    print(f"  完成: {fetched}/{len(cards)}")
    data["cards"] = cards
    data["updated"] = now
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    with open(HISTORY_FILE, "w") as f:
        json.dump(history, f)
    print(f"  歷史: {sum(len(v) for v in history.values())} 筆")
    print(f"\n[4/4] 重建網站...")
    rebuild_html(cards, history)
    if alerts:
        msg = "🃏 *CARDSTAR 價格警報*\n\n" + "\n\n".join(alerts[:10])
        msg += f"\n\n⏰ {datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC"
        send_telegram(msg)
    elif datetime.utcnow().hour == 0 and fetched > 0:
        tops = sorted(cards.values(), key=lambda x: x.get("price", 0), reverse=True)[:10]
        summary = "\n".join(f"{'💰' if i<3 else '·'} {fix_name(c.get('name_zh',''))[:20]}: ¥{c.get('price',0):,}" for i, c in enumerate(tops))
        send_telegram(f"📊 *CARDSTAR 每日摘要*\n\n{summary}\n\n⏰ {datetime.utcnow().strftime('%Y-%m-%d')} UTC")
    print(f"\n完成!")

if __name__ == "__main__":
    main()
