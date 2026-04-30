"""
CARDSTAR — 補中文卡名
從繁中官網 asia.pokemon-card.com/tw 抓 SV-P 中文名，更新到 D1。
"""

import requests
from bs4 import BeautifulSoup
import re
import os
import time

CF_ACCOUNT_ID = os.environ["CF_ACCOUNT_ID"]
CF_D1_DATABASE_ID = os.environ["CF_D1_DATABASE_ID"]
CF_D1_TOKEN = os.environ["CF_D1_TOKEN"]
D1_API = f"https://api.cloudflare.com/client/v4/accounts/{CF_ACCOUNT_ID}/d1/database/{CF_D1_DATABASE_ID}/query"

HEADERS_D1 = {
    "Authorization": f"Bearer {CF_D1_TOKEN}",
    "Content-Type": "application/json",
}

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"


def d1(sql, params=None):
    body = {"sql": sql}
    if params:
        body["params"] = params
    r = requests.post(D1_API, headers=HEADERS_D1, json=body)
    data = r.json()
    if not data.get("success"):
        print(f"  D1 ERROR: {data.get('errors', data)}")
    return data


def collect_detail_ids():
    """掃描繁中官網 SV-P 列表頁，蒐集 detail IDs"""
    print("[1/3] 掃描 SV-P 列表頁...")
    base = "https://asia.pokemon-card.com/tw/card-search/list/"
    detail_ids = []
    page = 1

    while True:
        url = f"{base}?expansionCodes=SV-P&pageNo={page}"
        print(f"  頁 {page}...", end=" ")
        r = requests.get(url, headers={"User-Agent": UA}, timeout=30)
        if r.status_code != 200:
            print(f"HTTP {r.status_code}, 停止")
            break

        soup = BeautifulSoup(r.text, "html.parser")
        found = 0
        for a in soup.find_all("a", href=True):
            m = re.search(r"/tw/card-search/detail/(\d+)/?", a["href"])
            if m:
                did = int(m.group(1))
                if did not in detail_ids:
                    detail_ids.append(did)
                    found += 1

        print(f"{found} 張")
        if found == 0:
            break
        page += 1
        time.sleep(1)

    print(f"  共 {len(detail_ids)} 個 detail ID")
    return detail_ids


def fetch_zh_name(detail_id):
    """從 detail 頁抓中文卡名 + 卡號"""
    url = f"https://asia.pokemon-card.com/tw/card-search/detail/{detail_id}/"
    r = requests.get(url, headers={"User-Agent": UA}, timeout=30)
    if r.status_code != 200:
        return None

    soup = BeautifulSoup(r.text, "html.parser")
    body_text = soup.get_text(" ", strip=True)

    # 卡名
    h1 = soup.find("h1")
    if not h1:
        return None
    raw_name = h1.get_text(strip=True)

    # 去掉階段前綴
    name_zh = raw_name
    for s in ["基礎", "1階進化", "2階進化", "MEGA進化", "V-UNION", "VSTAR", "VMAX"]:
        if raw_name.startswith(s + " "):
            name_zh = raw_name[len(s):].strip()
            break
        elif raw_name.startswith(s):
            name_zh = raw_name[len(s):].strip()
            break

    # 卡號
    m = re.search(r"(\d{3})/SV-P", body_text)
    if not m:
        return None

    card_no = m.group(1)
    return {"card_no": card_no, "name_zh": name_zh, "detail_id": detail_id}


def main():
    print("=" * 50)
    print("CARDSTAR — 補中文卡名")
    print("=" * 50)

    detail_ids = collect_detail_ids()
    if not detail_ids:
        print("ERROR: 找不到 detail IDs")
        return

    print(f"\n[2/3] 抓取 {len(detail_ids)} 張卡的中文名...")
    updated = 0
    skipped = 0

    for i, did in enumerate(detail_ids):
        result = fetch_zh_name(did)
        if result:
            card_uid = f"SV-P_{result['card_no']}"
            d1_result = d1(
                "UPDATE cards SET name_zh = ?, official_id_zh = ? WHERE card_uid = ? AND (name_zh IS NULL OR name_zh = '')",
                [result["name_zh"], result["detail_id"], card_uid]
            )
            if d1_result.get("success"):
                try:
                    changes = d1_result["result"][0]["meta"]["changes"]
                    if changes > 0:
                        updated += 1
                    else:
                        skipped += 1
                except (KeyError, IndexError):
                    skipped += 1
        else:
            skipped += 1

        if (i + 1) % 20 == 0:
            print(f"  進度: {i+1}/{len(detail_ids)} (更新: {updated})")
            time.sleep(0.5)

    print(f"  更新: {updated}, 跳過: {skipped}")

    # 驗證
    print(f"\n[3/3] 驗證...")
    result = d1("SELECT COUNT(*) as cnt FROM cards WHERE name_zh IS NOT NULL AND name_zh != ''")
    if result.get("success"):
        try:
            cnt = result["result"][0]["results"][0]["cnt"]
            print(f"  有中文名的卡: {cnt}")
        except (KeyError, IndexError):
            pass

    result = d1("SELECT card_uid, name_zh, name_en FROM cards WHERE name_zh IS NOT NULL AND name_zh != '' ORDER BY card_no LIMIT 10")
    if result.get("success"):
        try:
            rows = result["result"][0]["results"]
            print("  前 10 張:")
            for row in rows:
                print(f"    {row['card_uid']}: {row['name_zh']} ({row['name_en']})")
        except (KeyError, IndexError):
            pass

    print("\n完成！")


if __name__ == "__main__":
    main()
