"""
CARDSTAR — 卡片自動探勘器
搜尋 snkrdunk 熱門卡 → 抓名稱/價格/圖片 → 存到 cards_data.json
在 GitHub Actions 上跑，自動擴充卡片庫。
"""
import requests
from bs4 import BeautifulSoup
import json, re, os, time

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
DATA_FILE = "docs/cards_data.json"
IMG_DIR = "docs/images"

# 搜尋關鍵字：覆蓋寶可夢 + 海賊王的熱門卡

# 已知的海賊王卡 apparel IDs（手動搜集，確保一定能找到）
KNOWN_OP_CARDS = {
    # OP05-119 魯夫 Gear 5
    "135437": "魯夫 SEC [OP05-119](擴充包「新時代的主角」)",
    "135438": "魯夫 SEC-P [OP05-119](擴充包「新時代的主角」)",
    "135439": "魯夫 SEC-SP 漫畫平行卡 [OP05-119](擴充包「新時代的主角」)",
    # OP01-120 紅髮傑克
    "142695": "紅髮傑克 SEC [OP01-120](擴充包「ROMANCE DAWN」)",
    "93512": "紅髮傑克 SEC-P [OP01-120](擴充包「ROMANCE DAWN」)",
    "93520": "紅髮傑克 SEC-SP 漫畫平行卡 [OP01-120](擴充包「ROMANCE DAWN」)",
    "117170": "紅髮傑克 SEC-P 序號卡 [OP01-120](旗艦戰紀念品)",
    # OP01-121 大和
    "93511": "大和 SEC-P [OP01-121](擴充包「ROMANCE DAWN」)",
    "328423": "大和 SEC [OP01-121](精選包「ONE PIECE CARD THE BEST」)",
    # OP02-013 火拳艾斯
    "102435": "火拳艾斯 SR 平行卡 [OP02-013](擴充包「頂上決戰」)",
    # OP01-016 娜美
    "310224": "娜美 R-SP 漫畫平行卡 [OP01-016](精選包「ONE PIECE CARD THE BEST」)",
    "254304": "娜美 R [OP01-016]【中文版】(1周年紀念套組)",
    # OP05-119 特殊版本
    "349476": "魯夫 SEC-SPC 手配書 [OP05-119](擴充包「新皇帝」)",
    "515454": "魯夫 SEC-SPC 3周年(銀) [OP05-119](擴充包「神速之拳」)",
    "515455": "魯夫 SEC-SPC 3周年(金) [OP05-119](擴充包「神速之拳」)",
    # OP01-120 THE BEST 版
    "328421": "紅髮傑克 SEC [OP01-120](精選包「ONE PIECE CARD THE BEST」)",

    # ── OP06 双璧の覇者 ──
    "349476": "魯夫 SEC-SPC 懸賞令 [OP05-119](擴充包「新皇帝」)",
    # ── OP09 新たなる皇帝 ──
    "349475": "魯夫 SEC-SP (漫畫平行卡) [OP09-119](擴充包「新皇帝」)",
    # ── OP07 500年後の未来 ──
    "277330": "女帝漢考克 SR-SP [OP07-051](擴充包「500年後的未來」)",
    "277329": "女帝漢考克 L-P [OP07-038](擴充包「500年後的未來」)",
    # ── OP06 双璧の覇者 ──  
    "252825": "索隆 SEC-SP (漫畫平行卡) [OP06-118](擴充包「雙璧的霸者」)",
    "252826": "香吉士 SEC [OP06-119](擴充包「雙璧的霸者」)",
    # ── OP03 強大な敵 ──
    "113997": "狙擊王 SEC-SP (漫畫平行卡) [OP03-122](擴充包「強大的敵人」)",
    "113996": "鬼之御田 SEC [OP03-121](擴充包「強大的敵人」)",
    # ── OP04 謀略の王国 ──
    "120655": "大和 SEC-SP (漫畫平行卡) [OP04-120](擴充包「謀略的王國」)",
    "120654": "多佛朗明哥 SEC [OP04-119](擴充包「謀略的王國」)",
    # ── OP08 二つの伝説 ──
    "329800": "雷利 SEC-SP (漫畫平行卡) [OP08-118](擴充包「兩個傳說」)",
    "329801": "雷利 SEC [OP08-118](擴充包「兩個傳說」)",
    # ── OP09 新たなる皇帝 ──
    "349474": "魯夫 SEC [OP09-119](擴充包「新皇帝」)",
    "349477": "黑鬍子 SR-SP [OP09-093](擴充包「新皇帝」)",
    "349478": "巴乘 SEC-SP [OP09-051](擴充包「新皇帝」)",
    "349479": "紅髮傑克 SEC-SP (漫畫平行卡) [OP09-004](擴充包「新皇帝」)",
    # ── OP10 王族の血統 ──
    "412001": "羅 SEC-SP (漫畫平行卡) [OP10-119](擴充包「王族的血統」)",
    # ── OP05 新時代の主役 ── (補充)
    "135440": "羅 SR-SP (漫畫平行卡) [OP05-069](擴充包「新時代的主角」)",
    "135441": "乘奇 SEC-SP (漫畫平行卡) [OP05-074](擴充包「新時代的主角」)",
    "135438": "魯夫 SEC-P [OP05-119](擴充包「新時代的主角」)",
    # ── EB01 メモリアルコレクション ──
    "163860": "喬巴 SEC-SP (漫畫平行卡) [EB01-006](紀念收藏包)",
    # ── Promo / Event ──
    "209833": "魯夫 P [P-041](BANDAI CARD GAMES Fest)",
    "131255": "魯夫 P [P-043](週刊少年Jump附錄)",
    "102449": "烏塔 SEC-SP (漫畫平行卡) [OP02-120](擴充包「頂上決戰」)",
    "252827": "科比 R [OP02-098](旗艦戰紀念品)",
    # ── OP11 神速の拳 ──
    "515456": "魯夫 SEC-SP (超級平行卡) [OP11-118](擴充包「神速之拳」)",
    # ── OP13 ──
    "752858": "魯夫 SEC-SP (漫畫平行卡) [OP13-118](擴充包)",
    "752860": "艾斯 SEC-SP (漫畫平行卡) [OP13-119](擴充包)",
    "752861": "薩乘 SEC-SP (漫畫平行卡) [OP13-120](擴充包)",
    # ── OP14 ──
    "793189": "鷹眼 SEC-SP (漫畫平行卡) [OP14-119](擴充包)",
}

SEARCHES = [
    # ── 寶可夢 SAR（各系列）──
    "SAR SV2a", "SAR SV3", "SAR SV4a", "SAR SV4K", "SAR SV4M",
    "SAR SV5a", "SAR SV5K", "SAR SV5M", "SAR SV6", "SAR SV6a",
    "SAR SV7", "SAR SV8", "SAR SV8a", "SAR SV9", "SAR SV9a",
    "SAR M2a", "SAR M3", "SAR M4",
    # ── 寶可夢 SR ──
    "SR SV2a", "SR SV3", "SR SV5K", "SR SV5M", "SR SV6",
    "SR SV7", "SR SV8", "SR SV9", "SR M2a", "SR M3", "SR M4",
    # ── 寶可夢 AR ──
    "AR SV2a", "AR SV3", "AR SV4a", "AR SV5a", "AR SV6a",
    "AR SV8a", "AR SV9a", "AR M2a", "AR M3", "AR M4",
    # ── 寶可夢 UR ──
    "UR SV2a", "UR SV3", "UR SV6", "UR SV7", "UR M2a", "UR M3",
    # ── 寶可夢 MA ──
    "MA M2a", "MA M3", "MA M4",
    # ── 寶可夢 角色（高價） ──
    "ピカチュウ SAR", "ピカチュウ SR", "ピカチュウ AR",
    "リザードン SAR", "リザードン SR", "リザードンex SAR",
    "ミュウツー SAR", "ミュウツー SR",
    "ミュウ SAR", "ミュウ SR", "ミュウ AR",
    "イーブイ SAR", "イーブイ SR",
    "ブラッキー SAR", "ブラッキー SR", "ブラッキー VMAX",
    "リーリエ SAR", "リーリエ SR",
    "ナンジャモ SAR", "ナンジャモ SR",
    "レックウザ SAR", "レックウザ VMAX", "レックウザ V",
    "ゲッコウガ SAR", "ゲッコウガex SAR",
    "ゲンガー SAR", "ゲンガー VMAX",
    "ルカリオ SAR", "ルカリオ SR",
    "ガブリアス SAR",
    "シロナ SAR", "シロナ SR",
    "アセロラ SAR", "アセロラ SR",
    "カイ SAR", "カイ SR",
    "セレナ SAR", "セレナ SR",
    "マリィ SAR", "マリィ SR",
    "メロン SR", "ボスの指令 SAR",
    # ── 寶可夢 MEGA 系列 ──
    "メガリザードンXex", "メガリザードンYex",
    "メガゲッコウガex", "メガゲンガーex",
    "メガルカリオex", "メガレックウザex",
    "メガミュウツーXex", "メガミュウツーYex",
    # ── 寶可夢 Promo ──
    "ピカチュウ SV-P", "ピカチュウ S-P",
    "リザードン SV-P", "イーブイ SV-P",
    # ── 寶可夢 舊系列高價 ──
    "HR SA s7R", "HR SA s8b", "CSR s12a",
    "CHR s8b", "VMAX RRR s12a",
    # ── 海賊王 SEC（各彈） ──
    "OP01-120", "OP01-121",
    "OP02-120", "OP02-121",
    "OP03-120", "OP03-121", "OP03-122",
    "OP04-119", "OP04-120",
    "OP05-119", "OP05-120",
    "OP06-118", "OP06-119", "OP06-120",
    "OP07-118", "OP07-119",
    "OP08-118", "OP08-119",
    "OP09-118", "OP09-119",
    "OP10-118", "OP10-119",
    # ── 海賊王 SR Parallel ──
    "OP01-016 パラレル", "OP02-013 パラレル",
    "OP03-112 パラレル", "OP04-112 パラレル",
    "OP05-114 パラレル", "OP06-101 パラレル",
    # ── 海賊王 角色 ──
    "ルフィ SEC ワンピース", "シャンクス SEC ワンピース",
    "エース ワンピースカード SEC", "ナミ SEC ワンピース",
    "ヤマト SEC ワンピース", "ロー SEC ワンピース",
    "ロビン ワンピースカード", "ハンコック ワンピースカード",
    "カイドウ SEC ワンピース", "サボ SEC ワンピース",
    "ゾロ SEC ワンピース", "ロジャー SEC ワンピース",
    # ── 海賊王 コミパラ / SPC ──
    "ワンピースカード コミパラ", "ワンピースカード SPC",
    "ワンピースカード スーパーパラレル",
    # ── 遊戲王（第三類） ──
    "遊戯王 20thシークレット", "遊戯王 プリズマティック",
    "遊戯王 ホログラフィック", "遊戯王 アルティメット",
    "遊戯王 スターライト",
    "青眼の白龍 シークレット", "ブラック・マジシャン シークレット",
    "灰流うらら シークレット", "増殖するG シークレット",
]

# 中文翻譯對照表
NAME_ZH = {
    "ピカチュウ": "皮卡丘", "リザードン": "噴火龍", "ミュウツー": "超夢",
    "ミュウ": "夢幻", "イーブイ": "伊布", "ブラッキー": "月亮伊布",
    "リーリエ": "莉莉艾", "ナンジャモ": "奇樹", "シロナ": "竹蘭",
    "レックウザ": "烈空坐", "ゲッコウガ": "甲賀忍蛙", "ゲンガー": "耿鬼",
    "ガブリアス": "烈咬陸鯊", "ルカリオ": "路卡利歐",
    "メガリザードン": "超級噴火龍", "メガゲッコウガ": "超級甲賀忍蛙",
    "メガゲンガー": "超級耿鬼",
    "モンキー・D・ルフィ": "魯夫", "シャンクス": "紅髮傑克",
    "ポートガス・D・エース": "火拳艾斯", "トラファルガー・ロー": "特拉法爾加·羅",
    "ナミ": "娜美", "ロロノア・ゾロ": "索隆", "ニコ・ロビン": "妮可·羅賓",
    "カイドウ": "乘頓", "ヤマト": "大和", "ボア・ハンコック": "女帝漢乔克",
    "サボ": "薩乘", "ロジャー": "羅傑", "ゴール・D・ロジャー": "哥爾·D·羅傑",
    "エネル": "乘尼路", "サンジ": "香吉士", "ドフラミンゴ": "乘佛朗明哥",
}

# 系列中文翻譯
SET_ZH = {
    "新時代の主役": "新時代的主角", "頂上決戦": "頂上決戰",
    "ロマンスドーン": "ROMANCE DAWN", "強大な敵": "強大的敵人",
    "謀略の王国": "謀略王國", "500年後の未来": "500年後的未來",
    "双璧の覇者": "雙壁霸者", "二つの伝説": "兩個傳說",
    "新たなる皇帝": "新皇帝", "受け継がれる意志": "繼承的意志",
    "メモリアルコレクション": "紀念收藏",
    "ブースターパック": "擴充包", "プロモーションカード": "特典卡",
    "スタートデッキ": "起始牌組",
}


def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE) as f:
            return json.load(f)
    return {"cards": {}, "updated": ""}


def save_data(data):
    from datetime import datetime
    data["updated"] = datetime.utcnow().isoformat()
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def translate_name(ja_name):
    """把日文名翻成中文"""
    zh = ja_name
    for ja, cn in NAME_ZH.items():
        zh = zh.replace(ja, cn)
    return zh


def translate_set(ja_set):
    """把日文系列名翻成中文"""
    zh = ja_set
    for ja, cn in SET_ZH.items():
        zh = zh.replace(ja, cn)
    return zh


def search_snkrdunk(keyword):
    """搜尋 snkrdunk（限定卡牌分類 categoryId=6），回傳找到的卡片列表"""
    url = f"https://snkrdunk.com/search?keywords={requests.utils.quote(keyword)}&searchCategoryIds=6"
    try:
        r = requests.get(url, headers={"User-Agent": UA}, timeout=30)
        if r.status_code != 200:
            return []
        results = []

        # Pattern 1: aria-label links
        for m in re.finditer(
            r'<a\s+[^>]*href="[^"]*?/apparels/(\d+)"[^>]*aria-label="([^"]*?)"',
            r.text, re.DOTALL
        ):
            aid, label = m.group(1), m.group(2)
            if aid not in [r2["apparel"] for r2 in results]:
                results.append({"apparel": aid, "label": label})

        # Pattern 2: fallback - any /apparels/ link
        if not results:
            for m in re.finditer(r'/apparels/(\d+)', r.text):
                aid = m.group(1)
                if aid not in [r2["apparel"] for r2 in results]:
                    results.append({"apparel": aid, "label": keyword})

        return results
    except:
        return []


def fetch_card_detail(card_id):
    """從 snkrdunk 商品頁抓詳細資料"""
    url = f"https://snkrdunk.com/apparels/{card_id}"
    try:
        r = requests.get(url, headers={"User-Agent": UA}, timeout=30)
        if r.status_code != 200:
            return None

        soup = BeautifulSoup(r.text, "html.parser")
        result = {"name_ja": "", "image": "", "low": 0, "high": 0, "count": 0}

        # 1. Try JSON-LD
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                jd = json.loads(script.string)
                if isinstance(jd, list):
                    jd = next((x for x in jd if x.get("@type") == "Product"), None)
                if jd and jd.get("@type") == "Product":
                    of = jd.get("offers", {})
                    img = jd.get("image", "")
                    if isinstance(img, list):
                        img = img[0] if img else ""
                    result = {
                        "name_ja": jd.get("name", ""),
                        "image": img,
                        "low": int(of.get("lowPrice", 0) or 0),
                        "high": int(of.get("highPrice", 0) or 0),
                        "count": int(of.get("offerCount", 0) or 0),
                    }
                    break
            except:
                pass

        # 2. If no image from JSON-LD, try og:image
        if not result["image"]:
            og = soup.find("meta", property="og:image")
            if og and og.get("content"):
                result["image"] = og["content"]

        # 3. If still no image, try first img with cdn.snkrdunk.com
        if not result["image"]:
            for img_tag in soup.find_all("img", src=True):
                src = img_tag["src"]
                if "cdn.snkrdunk.com" in src and "upload" in src:
                    result["image"] = src
                    break

        # 4. If no name from JSON-LD, try og:title
        if not result["name_ja"]:
            og_title = soup.find("meta", property="og:title")
            if og_title and og_title.get("content"):
                result["name_ja"] = og_title["content"]

        # 5. Fallback price from HTML
        if result["low"] == 0:
            pm = re.search(r"¥([\d,]+)", r.text)
            if pm:
                result["low"] = int(pm.group(1).replace(",", ""))
                result["high"] = result["low"]

        return result if result["low"] > 0 or result["name_ja"] else None
    except:
        pass
    return None


def download_image(url, filename):
    """下載圖片"""
    path = f"{IMG_DIR}/{filename}"
    if os.path.exists(path) and os.path.getsize(path) > 1000:
        return True
    try:
        r = requests.get(url, headers={
            "User-Agent": UA,
            "Referer": "https://snkrdunk.com/",
        }, timeout=30)
        if r.status_code == 200 and len(r.content) > 1000:
            with open(path, "wb") as f:
                f.write(r.content)
            return True
    except:
        pass
    return False


def determine_game(name):
    """判斷是寶可夢還是海賊王"""
    op_keywords = ["ルフィ", "シャンクス", "エース", "ナミ", "ゾロ", "ロビン",
                   "カイドウ", "ヤマト", "ハンコック", "サボ", "ロジャー",
                   "ロー", "サンジ", "ドフラミンゴ", "エネル", "コビー",
                   "OP01", "OP02", "OP03", "OP04", "OP05", "OP06", "OP07",
                   "OP08", "OP09", "OP10", "OP11", "OP12", "OP13", "OP14",
                   "ST01", "ST10", "EB01"]
    for kw in op_keywords:
        if kw in name:
            return "opcg"
    # Yu-Gi-Oh keywords
    ygo_keywords = ["遊戯王", "遊戲王", "青眼", "ブラック・マジシャン", "デュエル",
                    "シークレット", "20th", "プリズマティック", "スターライト",
                    "灰流うらら", "増殖するG"]
    for kw in ygo_keywords:
        if kw in name:
            return "ygo"
    return "pcg"


def main():
    print("=" * 50)
    print("CARDSTAR — 卡片自動探勘器")
    print("=" * 50)

    os.makedirs(IMG_DIR, exist_ok=True)
    data = load_data()
    cards = data.get("cards", {})
    initial_count = len(cards)

    # 先加入已知的 OP 卡
    for aid, label in KNOWN_OP_CARDS.items():
        if aid not in cards:
            all_apparels_known = all_apparels_known if 'all_apparels_known' in dir() else {}
            all_apparels_known[aid] = label
    
    print(f"\n現有卡片: {initial_count}")
    print(f"搜尋關鍵字: {len(SEARCHES)} 組\n")

    # 搜尋所有關鍵字
    all_apparels = {}
    # 加入已知 OP 卡
    for aid, label in KNOWN_OP_CARDS.items():
        if aid not in cards:
            all_apparels[aid] = label
    if all_apparels:
        print(f"  已知 OP 卡待新增: {len(all_apparels)} 張")
    for i, kw in enumerate(SEARCHES):
        print(f"[{i+1}/{len(SEARCHES)}] 搜尋: {kw}...", end=" ")
        results = search_snkrdunk(kw)

        # Debug: dump first search HTML
        if i == 0:
            try:
                r = requests.get(f"https://snkrdunk.com/search?keywords={requests.utils.quote(kw)}&searchCategoryIds=6", headers={"User-Agent": UA}, timeout=30)
                # Find all href links
                links = re.findall(r'href="([^"]*?/(?:en/)?(?:apparels|trading-cards)/\d+[^"]*)"', r.text)
                print(f"\n  DEBUG: Found {len(links)} card links in HTML")
                for link in links[:5]:
                    print(f"    {link}")
                # Also check for other patterns
                all_links = re.findall(r'href="(/[^"]+)"', r.text)
                card_related = [l for l in all_links if any(x in l for x in ['/trading', '/apparel', '/card'])]
                print(f"  DEBUG: {len(card_related)} card-related links total")
                for link in card_related[:10]:
                    print(f"    {link}")
            except:
                pass
        print(f"[{i+1}/{len(SEARCHES)}] 搜尋: {kw}...", end=" ")
        results = search_snkrdunk(kw)
        new = 0
        for r in results:
            aid = r["apparel"]
            if aid not in all_apparels and aid not in cards:
                all_apparels[aid] = r["label"]
                new += 1
        print(f"{len(results)} 結果, {new} 新卡")
        time.sleep(2)

    print(f"\n新發現（主搜尋）: {len(all_apparels)} 張卡")

    # OP 專用搜尋（不加 category filter，因為 OP 可能分類不同）
    op_kws = [
        "OP05-119 ルフィ", "OP01-120 シャンクス", "OP02-013 エース",
        "OP03-121 ルフィ", "OP04-120 ヤマト", "OP05-120 ロー",
        "OP06-119 ルフィ", "OP07-119 ルフィ", "OP08-118 ナミ",
        "OP09-119 ルフィ", "OP02-121 シャンクス", "OP01-121 ナミ",
        "ワンピースカード SEC", "ワンピカ ルフィ", "ワンピカ シャンクス",
    ]
    print(f"\n[OP 專用搜尋] {len(op_kws)} 組...")
    for j, kw in enumerate(op_kws):
        try:
            surl = f"https://snkrdunk.com/search?keywords={requests.utils.quote(kw)}"
            sr = requests.get(surl, headers={"User-Agent": UA}, timeout=30)
            if sr.status_code == 200:
                found = 0
                for m2 in re.finditer(r'/apparels/(\d+)', sr.text):
                    aid2 = m2.group(1)
                    if aid2 not in all_apparels and aid2 not in cards:
                        all_apparels[aid2] = kw
                        found += 1
                print(f"  [{j+1}/{len(op_kws)}] {kw}: {found} 新卡")
        except:
            pass
        time.sleep(2)

    print(f"\n新發現（含 OP）: {len(all_apparels)} 張卡")

    # 限制最多抓 200 張新卡（加上已有的）
    target = 500 - len(cards)
    if target <= 0:
        print(f"已有 {len(cards)} 張，不需要更多")
        all_apparels = {}
    elif len(all_apparels) > target:
        # 只取前 target 張
        all_apparels = dict(list(all_apparels.items())[:target])

    # 抓每張卡的詳細資料
    if all_apparels:
        print(f"\n抓取 {len(all_apparels)} 張卡的詳細資料...")
        for i, (aid, label) in enumerate(all_apparels.items()):
            detail = fetch_card_detail(aid)
            if detail and detail["low"] > 0:
                name_ja = detail["name_ja"] or label.split(" - ")[0]
                name_zh = translate_name(name_ja)

                # 提取卡號
                card_no_m = re.search(r'\[([^\]]+)\]', name_ja)
                card_no = card_no_m.group(1) if card_no_m else ""

                # 提取來源
                source_m = re.search(r'\(([^\)]+)\)', name_ja)
                source_ja = source_m.group(1) if source_m else ""
                source_zh = translate_set(source_ja)

                # 判斷遊戲類型
                game = determine_game(name_ja)

                cards[aid] = {
                    "apparel": aid,
                    "name_ja": name_ja,
                    "name_zh": name_zh,
                    "card_no": card_no,
                    "source_zh": source_zh,
                    "game": game,
                    "price": detail["low"],
                    "high": detail["high"],
                    "offers": detail["count"],
                    "image_cdn": detail["image"],
                }

                print(f"  [{i+1}] {name_zh} | ¥{detail['low']:,} | img={'✓' if detail['image'] else '✗'}")
            else:
                print(f"  [{i+1}] {label[:30]}... 無法取得")

            if (i + 1) % 5 == 0:
                time.sleep(3)
            else:
                time.sleep(1)

    # 更新已有卡片的價格
    print(f"\n更新已有卡片價格...")
    updated = 0
    for aid, card in list(cards.items()):
        if not card.get("apparel"):
            continue
        detail = fetch_card_detail(aid)
        if detail and detail["low"] > 0:
            cards[aid]["price"] = detail["low"]
            cards[aid]["high"] = detail["high"]
            cards[aid]["offers"] = detail["count"]
            updated += 1

            # 儲存 CDN 圖片 URL（不下載，直接用 CDN）
            if detail.get("image"):
                cards[aid]["image_cdn"] = detail["image"]

        if updated % 5 == 0:
            time.sleep(3)
        else:
            time.sleep(1)

    print(f"  更新: {updated} 張")

    # 儲存
    data["cards"] = cards
    save_data(data)

    print(f"\n" + "=" * 50)
    print(f"完成！")
    print(f"  總卡片數: {len(cards)}")
    print(f"  新增: {len(cards) - initial_count}")
    print(f"  寶可夢: {sum(1 for c in cards.values() if c.get('game') == 'pcg')}")
    print(f"  海賊王: {sum(1 for c in cards.values() if c.get('game') == 'opcg')}")
    print(f"  有圖片: {sum(1 for c in cards.values() if c.get('image'))}")


if __name__ == "__main__":
    main()
