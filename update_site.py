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
            if len(data.get("cards", {})) < 500:
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

def fetch_kapaipai(card_no, game="pcg"):
    """查詢卡拍拍台灣定價"""
    if not card_no:
        return None
    game_code = "pkmtw" if game == "pcg" else ("optcg" if game == "opcg" else "yugioh")
    url = f"https://trade.kapaipai.tw/api/card/getFilteredList?game={game_code}&name={requests.utils.quote(card_no)}"
    try:
        r = requests.get(url, headers={"User-Agent": UA}, timeout=15)
        if r.status_code != 200:
            return None
        data = r.json()
        if data.get("code") != 0:
            return None
        cards_list = data.get("data", {}).get("list", [])
        if not cards_list:
            return None
        # Search through all results for matching card number
        best_match = None
        search_parts = card_no.replace("/", "-").split("-")
        for card in cards_list:
            for rare_item in card.get("rareList", []):
                pack_card_id = rare_item.get("packCardId", "")
                # Check if card number matches
                if card_no in pack_card_id or pack_card_id in card_no:
                    low = rare_item.get("lowestPrice", 0)
                    avg = rare_item.get("averagePrice", 0)
                    if low > 0:
                        if not best_match or low > best_match["low"]:
                            best_match = {
                                "low": low,
                                "avg": avg,
                                "name": card.get("nameZh", ""),
                                "rare": rare_item.get("rare", []),
                            }
                # Also try partial match
                elif any(p in pack_card_id for p in search_parts if len(p) >= 3):
                    low = rare_item.get("lowestPrice", 0)
                    avg = rare_item.get("averagePrice", 0)
                    if low > 0 and not best_match:
                        best_match = {
                            "low": low,
                            "avg": avg,
                            "name": card.get("nameZh", ""),
                            "rare": rare_item.get("rare", []),
                        }
        return best_match
    except:
        return None


def fetch_mercari_hk(card_name_ja, card_no=""):
    """搜尋 Mercari HK，回傳最低價 (HKD → JPY)"""
    if not card_name_ja:
        return None
    query = card_name_ja[:30]  # Keep short
    if card_no:
        query = card_no.replace("/", " ")
    url = f"https://hk.mercari.com/zh-hant/search?keyword={requests.utils.quote(query)}&category-ids=1152,1289,1293,1409,7233,7234,7242"
    try:
        r = requests.get(url, headers={"User-Agent": UA}, timeout=20)
        if r.status_code != 200:
            return None
        prices = []
        for m in re.finditer(r'HK\$([\d,.]+)', r.text):
            p = float(m.group(1).replace(",", ""))
            if 1 <= p <= 500000:
                prices.append(p)
        if prices:
            prices.sort()
            # HKD to JPY roughly 19.5
            jpy = int(min(prices) * 19.5)
            return {"hkd": min(prices), "jpy": jpy, "count": len(prices)}
        return None
    except:
        return None

def fetch_yuyu_tei(card_name_ja, set_code="", game="pcg"):
    """查詢遊々亭買取價（收購價）"""
    if not card_name_ja and not set_code:
        return None
    game_code = "poc" if game == "pcg" else ("opc" if game == "opcg" else "ygo")
    if set_code:
        url = f"https://yuyu-tei.jp/buy/{game_code}/s/{set_code.lower()}"
    else:
        return None  # Need set code for yuyu-tei
    try:
        r = requests.get(url, headers={"User-Agent": UA}, timeout=20)
        if r.status_code != 200 or "reCAPTCHA" in r.text:
            return None
        # Look for card name and price
        soup = BeautifulSoup(r.text, "html.parser")
        # yuyu-tei buy prices in format: ¥XXX or XXX円
        for item in soup.find_all(class_=re.compile("card-product|buy-price|price")):
            text = item.get_text()
            if card_name_ja[:6] in text:
                pm = re.search(r"([\d,]+)円", text)
                if pm:
                    return {"buy_price": int(pm.group(1).replace(",", ""))}
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
    "イラストレーションコンテスト": "插畫大賽",
    "スカーレット&バイオレット": "朱&紫",
    "フラッグシップバトル記念品": "旗艦戰紀念品",
    "ソルガレオ&ルナアーラGX": "索爾迦雷歐&露奈雅拉GX",
    "シャイニートレジャーex": "閃耀寶藏ex",
    "スペシャルデッキセット": "特別牌組套裝",
    "VMAXクライマックス": "VMAX巔峰",
    "スペシャルレッドカード": "特殊紅卡",
    "プロモーションカード": "特典卡",
    "プレミアムブースター": "精選擴充包",
    "ポケモンカード151": "寶可夢卡牌151",
    "ポケモンカードゲーム": "寶可夢卡牌",
    "テラスタルフェスex": "太晶盛宴ex",
    "VSTARユニバース": "VSTAR宇宙",
    "MEGAドリームex": "MEGA夢想ex",
    "アニバーサリーセット": "周年套組",
    "エネルギーリサイクル": "能量回收",
    "【インドネシア語版】": "【印尼版】",
    "プロモカードパック": "特典卡包",
    "GXバトルブースト": "GX對戰強化",
    "バトルパートナーズ": "對戰夥伴",
    "バトルコレクション": "對戰收藏",
    "中国語箔押しエラー": "中文版燙金錯版",
    "ツールスクラッパー": "道具回收",
    "for Japan": "",
    "ハイクラスパック": "高級擴充包",
    "ブースターパック": "擴充包",
    "スペシャルBOX": "特別禮盒",
    "スターターセット": "起始套組",
    "ナイトワンダラー": "夜遊者",
    "ニンジャスピナー": "忍者旋鏢",
    "クリムゾンヘイズ": "緋紅薄霧",
    "レイジングサーフ": "狂浪巨浪",
    "5周年記念カード": "5周年紀念卡",
    "スペシャルカード": "特殊卡",
    "アローラナッシー": "阿羅拉椰蛋樹",
    "カウンターゲイン": "反擊增益",
    "強化拡張パック": "強化擴充包",
    "スタートデッキ": "起始牌組",
    "ポケモンカード": "寶可夢卡牌",
    "楽園ドラゴーナ": "樂園龍騎士",
    "蒼空ストリーム": "蒼空烈流",
    "インフェルノX": "煉獄X",
    "超電ブレイカー": "超電突破者",
    "熱風のアリーナ": "熱風的競技場",
    "クレイバースト": "黏土爆裂",
    "ドリームリーグ": "夢想聯盟",
    "ロマンスドーン": "ROMANCE DAWN",
    "メガシビルドン": "超級電鰻",
    "メガズルズキン": "超級頭巾混混",
    "メガドラミドロ": "超級毒藻龍",
    "メガフラエッテ": "超級花葉蒂",
    "メガカエンジシ": "超級火炎獅",
    "メガエアームド": "超級盔甲鳥",
    "メガリザードン": "超級噴火龍",
    "メガゲッコウガ": "超級甲賀忍蛙",
    "メガレックウザ": "超級烈空坐",
    "メガミュウツー": "超級超夢",
    "プリズムタワー": "稜鏡塔",
    "ジャンボアイス": "巨大冰棒",
    "エネルギー回収": "能量回收",
    "ムニキスゼロ": "蒙奇斯零",
    "黒炎の支配者": "黑炎的支配者",
    "新時代の主役": "新時代的主角",
    "新たなる皇帝": "新皇帝",
    "メガゲンガー": "超級耿鬼",
    "メガルカリオ": "超級路卡利歐",
    "ブロロローム": "噗隆隆轟",
    "ブリジュラス": "鋁鋼橋龍",
    "ボルケニオン": "波爾凱尼恩",
    "カミツオロチ": "神蛇大人",
    "テツノドクガ": "鐵毒蛾",
    "テツノコウベ": "鐵頭殼",
    "テツノカシラ": "鐵頭領",
    "テツノイサハ": "鐵荊棘",
    "テツノイワオ": "鐵巨岩",
    "テツノブジン": "鐵武者",
    "トドロクツキ": "轟鳴月",
    "タケルライコ": "猛雷鼓",
    "ハバタクカミ": "振翼蝶",
    "ウガツホムラ": "破空焰",
    "ウネルミナモ": "湧泉水蛇",
    "スナノケガワ": "沙鐵皮",
    "マフィティフ": "獒教父",
    "クエスパトラ": "超能豔鴕",
    "ジュナイパー": "狙射樹梟",
    "エンニュート": "焰后蜥",
    "カプ・コケコ": "卡璞・鳴鳴",
    "せいなるはい": "神聖之灰",
    "【中国語版】": "【中文版】",
    "拡張パック": "擴充包",
    "ドラゴーナ": "龍騎士",
    "テラスタル": "太晶",
    "ロケット団": "火箭隊",
    "テラパゴス": "太樂巴戈斯",
    "サーフゴー": "賽富豪",
    "モモワロウ": "桃歹郎",
    "コオリッポ": "凍原企鵝",
    "マシマシラ": "願增猿",
    "チルタリス": "七夕青鳥",
    "フシギバナ": "妙蛙花",
    "フシギソウ": "妙蛙草",
    "リザードン": "噴火龍",
    "カメックス": "水箭龜",
    "ピカチュウ": "皮卡丘",
    "ニドキング": "尼多王",
    "フーディン": "胡地",
    "カイリキー": "怪力",
    "ゴーリキー": "豪力",
    "ウインディ": "風速狗",
    "ギャラドス": "暴鯉龍",
    "ブラッキー": "月亮伊布",
    "ニンフィア": "仙子伊布",
    "ミュウツー": "超夢",
    "ファイヤー": "火焰鳥",
    "エレキブル": "電擊魔獸",
    "アーボック": "阿柏怪",
    "オムナイト": "菊石獸",
    "バリヤード": "魔牆人偶",
    "レックウザ": "烈空坐",
    "ガブリアス": "烈咬陸鯊",
    "ゲッコウガ": "甲賀忍蛙",
    "ミミッキュ": "謎擬Ｑ",
    "ダークライ": "達克萊伊",
    "アルセウス": "阿爾宙斯",
    "ソルガレオ": "索爾迦雷歐",
    "コライドン": "故勒頓",
    "ミライドン": "密勒頓",
    "イルカマン": "海豚俠",
    "ピジョット": "大比鳥",
    "ペルシアン": "貓老大",
    "ヨノワール": "黑夜魔靈",
    "サマヨール": "彷徨夜靈",
    "キテルグマ": "穿著熊",
    "コレクレー": "索財靈",
    "ユキメノコ": "雪妖女",
    "ユキワラシ": "雪童子",
    "ゴウカザル": "烈焰猴",
    "ダイノーズ": "大朝北鼻",
    "ラブトロス": "眷戀雲",
    "ハラバリー": "電肚蛙",
    "ハガネール": "大鋼蛇",
    "パンプジン": "南瓜精",
    "コバルオン": "勾帕路翁",
    "チラチーノ": "潔美利",
    "ラティアス": "拉帝亞斯",
    "ギャロップ": "烈馬",
    "ヤンヤンマ": "蜻蜻蜓",
    "サザンドラ": "三頭龍",
    "スターミー": "寶石海星",
    "フラエッテ": "花葉蒂",
    "ドラミドロ": "毒藻龍",
    "カエンジシ": "火炎獅",
    "エアームド": "盔甲鳥",
    "レドームシ": "蓋蓋蟲",
    "バニリッチ": "雪花冰",
    "ナットレイ": "堅果啞鈴",
    "ヨーギラス": "幼基拉斯",
    "バンギラス": "班基拉斯",
    "ヨクバリス": "藏飽栗鼠",
    "デンチュラ": "電蜘蛛",
    "キチキギス": "吉蒂吉斯",
    "イワパレス": "岩殿居蟹",
    "ウミトリオ": "三海地鼠",
    "オドリドリ": "花舞鳥",
    "ヒトデマン": "海星星",
    "ネイティオ": "天然雀",
    "カジッチュ": "啃果蟲",
    "エレザード": "光電傘蜥",
    "オーロンゲ": "長毛巨魔",
    "イイネイヌ": "夠讚狗",
    "ドンファン": "頓甲",
    "ナンジャモ": "奇樹",
    "カシオペア": "仙后",
    "オルティガ": "奧爾提加",
    "カキツバタ": "杜若",
    "マチエール": "瑪奇耶",
    "シュウメイ": "秀梅",
    "サーファー": "衝浪者",
    "からておう": "空手王",
    "おねえさん": "姐姐",
    "【英語版】": "【英文版】",
    "【中国語】": "【簡中版】",
    "アリーナ": "競技場",
    "コミパラ": "漫畫平行卡",
    "シリアル": "序號",
    "頂上決戦": "頂上決戰",
    "神速の拳": "神速之拳",
    "ゲンガー": "耿鬼",
    "ラプラス": "拉普拉斯",
    "イーブイ": "伊布",
    "エーフィ": "太陽伊布",
    "カビゴン": "卡比獸",
    "カイロス": "凱羅斯",
    "ルカリオ": "路卡利歐",
    "ゼクロム": "捷克羅姆",
    "ザシアン": "蒼響",
    "ガチグマ": "月月熊",
    "コダック": "可達鴨",
    "ピジョン": "比比鳥",
    "ヘルガー": "黑魯加",
    "デルビル": "戴魯比",
    "ヨマワル": "夜巡靈",
    "コータス": "煤炭龜",
    "フィオネ": "霏歐納",
    "ブロロン": "噗隆隆",
    "スピアー": "大針蜂",
    "シェイミ": "謝米",
    "ラクライ": "落雷獸",
    "ニャース": "喵喵",
    "ハッサム": "巨鉗螳螂",
    "オノンド": "斧牙龍",
    "エイパム": "長尾怪手",
    "リーリエ": "莉莉艾",
    "アセロラ": "阿瑟蘿拉",
    "アイリス": "艾莉絲",
    "オモダカ": "來悉",
    "オーリム": "奧琳",
    "アカマツ": "赤松",
    "ブライア": "布萊雅",
    "フトゥー": "符圖",
    "カナリィ": "卡娜莉",
    "パラソル": "陽傘",
    "アローラ": "阿羅拉",
    "いしずえ": "礎石",
    "まごころ": "真心",
    "たくらみ": "詭計",
    "はげまし": "鼓勵",
    "まなざし": "凝視",
    "なみのり": "衝浪",
    "シナリオ": "劇本",
    "スニダン": "",
    "フェス": "盛宴",
    "開封済": "已開封",
    "手配書": "懸賞令",
    "ミュウ": "夢幻",
    "ポッポ": "波波",
    "ヤンマ": "蜻蜓",
    "ロトム": "洛托姆",
    "シロナ": "竹蘭",
    "マリィ": "瑪俐",
    "セレナ": "莎莉娜",
    "エリカ": "艾莉卡",
    "カスミ": "小霞",
    "サカキ": "坂木",
    "ペパー": "胡椒",
    "スグリ": "醋栗",
    "ゼイユ": "澤乳",
    "ルチア": "露琪亞",
    "マツバ": "松葉",
    "セイジ": "聖志",
    "ポピー": "波比",
    "メロコ": "美洛可",
    "ヒビキ": "響",
    "ジプソ": "吉普索",
    "ホミカ": "霍米加",
    "ミカン": "阿蜜",
    "ホップ": "赫普",
    "ユカリ": "由加利",
    "ボタン": "牡丹",
    "リップ": "莉普",
    "ネルケ": "奈爾柯",
    "アオキ": "青木",
    "ヒスイ": "洗翠",
    "かまど": "火爐",
    "みどり": "碧綠",
    "安らぎ": "安寧",
    "プロモ": "",
    "ゲーム": "",
    "フリマ": "",
    "赤髪": "紅髮",
    "仕様": "版",
    "ベル": "貝兒",
    "チリ": "智莉",
    "ビワ": "琵琶",
    "タロ": "太郎",
    "メイ": "梅",
    "ネモ": "尼莫",
    "メガ": "超級",
    "いど": "水井",
    "めん": "面具",
    "の": "的",
}

def fix_name(name):
    name = htmlmod.unescape(name)
    name = re.sub(r'の新品.*$', '', name).strip()
    name = re.sub(r'｜スニダン.*$', '', name).strip()
    for ja, zh in sorted(TRANSLATIONS.items(), key=lambda x: -len(x[0])):
        name = name.replace(ja, zh)
    return name.replace("  ", " ").strip()

def rebuild_html(cards, history):
    if not os.path.exists(HTML_FILE):
        return
    sorted_cards = sorted(cards.values(), key=lambda x: x.get("price", 0), reverse=True)
    lines = ["var CARDS = ["]
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
        cat = "寶可夢卡" if game == "pcg" else ("航海王卡" if game == "opcg" else "遊戲王卡")
        t = name_zh.replace('\\','\\\\').replace('"','\\"')
        s = short.replace('\\','\\\\').replace('"','\\"')
        j = name_ja.replace('\\','\\\\').replace('"','\\"')
        # Build markets
        mkts = f'{{n:"snkrdunk",loc:"JP",code:"JP",j:{price}}}'
        ytw = c.get("yahoo_tw_price", 0)
        if ytw and ytw > 0:
            mkts += f',{{n:"Yahoo 拍賣",loc:"TW",code:"TW",t:{ytw}}}'
        kpp = c.get("kapaipai_price", 0)
        if kpp and kpp > 0:
            mkts += f',{{n:"卡拍拍",loc:"TW",code:"TW",t:{kpp}}}'
        mhk = c.get("mercari_hk_jpy", 0)
        if mhk and mhk > 0:
            mkts += f',{{n:"Mercari HK",loc:"HK",code:"HK",j:{mhk}}}'

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
    start = html.find("var CARDS = [")
    end = html.find("];", start) + 2
    if start >= 0 and end > start:
        html = html[:start] + "\n".join(lines) + html[end:]
        with open(HTML_FILE, "w") as f:
            f.write(html)
        print(f"  HTML: {len(sorted_cards)} 張卡")

def generate_card_pages(cards):
    """為每張卡生成獨立 HTML 頁面（SEO 社群分享用）"""
    os.makedirs("docs/card", exist_ok=True)
    R = 0.22
    sorted_cards = sorted(cards.values(), key=lambda x: x.get("price", 0), reverse=True)
    for i, c in enumerate(sorted_cards):
        cid = i + 1
        name = fix_name(c.get("name_zh", c.get("name_ja", "")))
        short = re.sub(r'\([^)]+\)$', '', name).strip()
        price = c.get("price", 0)
        twd = int(price * R)
        img = c.get("image_cdn", "") or c.get("image", "")
        game = c.get("game", "pcg")
        cat = "寶可夢卡" if game == "pcg" else ("航海王卡" if game == "opcg" else "遊戲王卡")
        desc = f"{name} · {cat} · ¥{price:,} · NT$ {twd:,}"
        page = f'<!DOCTYPE html><html lang="zh-TW"><head><meta charset="UTF-8">' \
            f'<meta name="referrer" content="no-referrer">' \
            f'<title>{short} | NT$ {twd:,} | CARDSTAR 卡市達</title>' \
            f'<meta name="description" content="{desc}">' \
            f'<meta property="og:type" content="product">' \
            f'<meta property="og:site_name" content="CARDSTAR 卡市達">' \
            f'<meta property="og:title" content="{short} — NT$ {twd:,}">' \
            f'<meta property="og:description" content="{desc}">' \
            f'<meta property="og:image" content="{img}">' \
            f'<meta property="og:image:width" content="800">' \
            f'<meta property="og:image:height" content="800">' \
            f'<meta name="twitter:card" content="summary_large_image">' \
            f'<meta name="twitter:title" content="{short} — NT$ {twd:,}">' \
            f'<meta name="twitter:image" content="{img}">' \
            f'<script>window.location.replace("../#/card/{cid}");</script>' \
            f'</head><body><p><a href="../#/card/{cid}">{short}</a></p></body></html>'
        with open(f"docs/card/{cid}.html", "w") as f:
            f.write(page)
    print(f"  Card pages: {len(sorted_cards)}")


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
            # Alert: compare to 24h ago (not previous hour)
            if len(h) >= 24:
                prev_24h = h[-24]["low"]
                if prev_24h > 0:
                    chg = round((price["low"] - prev_24h) / prev_24h * 100, 1)
                    if abs(chg) >= 10:  # 10% threshold for 24h change
                        name = fix_name(card.get("name_zh", ""))[:30]
                        d = "📈" if chg > 0 else "📉"
                        alerts.append(f"{d} *{name}*\n¥{prev_24h:,} → ¥{price['low']:,} ({'+' if chg>0 else ''}{chg}% / 24h)")
            fetched += 1
            if fetched % 20 == 0:
                print(f"  ... {fetched} 張")
        # Yahoo TW price
        card_no = card.get("card_no", "")
        if card_no:  # Every card
            ytw = fetch_yahoo_tw(card_no, card.get("game", "pcg"))
            if ytw and ytw.get("low", 0) > 0:
                card["yahoo_tw_price"] = ytw["low"]
                card["yahoo_tw_count"] = ytw.get("count", 0)

        # 卡拍拍 price
        if card_no:  # Every card
            kpp = fetch_kapaipai(card_no, card.get("game", "pcg"))
            if kpp and kpp.get("low", 0) > 0:
                card["kapaipai_price"] = kpp["low"]
                card["kapaipai_avg"] = kpp.get("avg", 0)

        # Mercari HK (every 10th card to save time)
        name_ja = card.get("name_ja", "")
        if name_ja and fetched % 10 == 0:
            mrc = fetch_mercari_hk(name_ja, card_no)
            if mrc and mrc.get("jpy", 0) > 0:
                card["mercari_hk_hkd"] = mrc["hkd"]
                card["mercari_hk_jpy"] = mrc["jpy"]

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
    generate_card_pages(cards)
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
