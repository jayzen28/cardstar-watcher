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
SEARCHES = [
    # 寶可夢 - 地區限定皮卡丘
    "ピカチュウ プロモ SV-P",
    "ピカチュウ プロモ S-P",
    "トウホクのピカチュウ",
    "ヒロシマのピカチュウ",
    "フクオカのピカチュウ",
    # 寶可夢 - 熱門 SAR/AR
    "ポケモンカード SAR ピカチュウ",
    "ポケモンカード SAR リザードン",
    "ポケモンカード SAR ミュウ",
    "ポケモンカード SAR イーブイ",
    "ポケモンカード SAR リーリエ",
    "ポケモンカード SAR ナンジャモ",
    "ポケモンカード MA メガリザードン",
    "ポケモンカード MUR メガゲッコウガ",
    "ポケモンカード AR SV2a",
    "ポケモンカード UR 金",
    # 寶可夢 - 新彈熱門
    "ポケモンカード ニンジャスピナー SAR",
    "ポケモンカード MEGAドリーム SAR",
    "ポケモンカード バトルパートナーズ SAR",
    # 海賊王 - SEC/コミパラ
    "ワンピースカード ルフィ SEC",
    "ワンピースカード シャンクス SEC",
    "ワンピースカード エース SEC",
    "ワンピースカード ナミ SEC",
    "ワンピースカード ロー SEC",
    "ワンピースカード カイドウ SEC",
    "ワンピースカード ヤマト SEC",
    "ワンピースカード ロビン SEC",
    "ワンピースカード コミパラ",
    "ワンピースカード 新時代の主役",
    "ワンピースカード 新たなる皇帝",
    "ワンピースカード 受け継がれる意志",
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
    """搜尋 snkrdunk，回傳找到的卡片列表"""
    url = f"https://snkrdunk.com/search?keyword={requests.utils.quote(keyword)}"
    try:
        r = requests.get(url, headers={"User-Agent": UA}, timeout=30)
        if r.status_code != 200:
            return []
        results = []
        for m in re.finditer(
            r'<a\s+[^>]*href="[^"]*?/apparels/(\d+)"[^>]*aria-label="([^"]*?)"',
            r.text, re.DOTALL
        ):
            aid, label = m.group(1), m.group(2)
            # 排除非卡片商品
            if any(x in label for x in ["ボックス", "BOX", "パック", "デッキ", "スリーブ"]):
                continue
            results.append({"apparel": aid, "label": label})
        return results
    except:
        return []


def fetch_card_detail(apparel_id):
    """從 snkrdunk 商品頁抓詳細資料"""
    url = f"https://snkrdunk.com/apparels/{apparel_id}"
    try:
        r = requests.get(url, headers={"User-Agent": UA}, timeout=30)
        if r.status_code != 200:
            return None
        soup = BeautifulSoup(r.text, "html.parser")

        # JSON-LD
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
                    return {
                        "name_ja": jd.get("name", ""),
                        "image": img,
                        "low": int(of.get("lowPrice", 0) or 0),
                        "high": int(of.get("highPrice", 0) or 0),
                        "count": int(of.get("offerCount", 0) or 0),
                    }
            except:
                pass

        # Fallback
        pm = re.search(r"¥([\d,]+)", r.text)
        if pm:
            return {
                "name_ja": "",
                "image": "",
                "low": int(pm.group(1).replace(",", "")),
                "high": 0,
                "count": 0,
            }
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
    return "pcg"


def main():
    print("=" * 50)
    print("CARDSTAR — 卡片自動探勘器")
    print("=" * 50)

    os.makedirs(IMG_DIR, exist_ok=True)
    data = load_data()
    cards = data.get("cards", {})
    initial_count = len(cards)

    print(f"\n現有卡片: {initial_count}")
    print(f"搜尋關鍵字: {len(SEARCHES)} 組\n")

    # 搜尋所有關鍵字
    all_apparels = {}
    for i, kw in enumerate(SEARCHES):
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

    print(f"\n新發現: {len(all_apparels)} 張卡")

    # 限制最多抓 100 張新卡（加上已有的）
    target = 100 - len(cards)
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

                # 生成圖片檔名
                img_filename = f"card_{aid}.jpg"
                img_downloaded = False
                if detail["image"]:
                    img_downloaded = download_image(detail["image"], img_filename)

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
                    "image": f"./images/{img_filename}" if img_downloaded else "",
                    "image_src": detail["image"],
                }

                print(f"  [{i+1}] {name_zh} | ¥{detail['low']:,} | img={'✓' if img_downloaded else '✗'}")
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

            # 下載缺失的圖片
            if not card.get("image") and detail.get("image"):
                img_filename = f"card_{aid}.jpg"
                if download_image(detail["image"], img_filename):
                    cards[aid]["image"] = f"./images/{img_filename}"

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
