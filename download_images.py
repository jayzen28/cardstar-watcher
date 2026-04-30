"""
CARDSTAR 卡市達 — 圖片下載器
下載所有卡圖到 docs/images/，解決防盜連問題。
GitHub Actions 跑這支，圖片永久存在 repo 裡。
"""

import requests
import os
import time

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

# 所有需要下載的卡圖
IMAGES = {
    # 寶可夢（日本官網）
    "svp-057.png": "https://asia.pokemon-card.com/tw/card-img/tw00009219.png",
    "svp-098.jpg": "https://www.pokemon-card.com/assets/images/card_images/large/SV-P/044245_P_MEITANTEIPIKACHIXYUU.jpg",
    "svp-074.jpg": "https://www.pokemon-card.com/assets/images/card_images/large/SV-P/044212_P_PIKACHIXYUU.jpg",
    "svp-218.jpg": "https://www.pokemon-card.com/assets/images/card_images/large/SV-P/046150_P_PIKACHIXYUU.jpg",
    "svp-242.jpg": "https://www.pokemon-card.com/assets/images/card_images/large/SV-P/047363_P_PIKACHIXYUU.jpg",
    "svp-001.jpg": "https://www.pokemon-card.com/assets/images/card_images/large/SV-P/042261_P_PIKACHIXYUU.jpg",
    # 海賊王（日本官網）
    "op05-119.png": "https://www.onepiece-cardgame.com/images/cardlist/card/OP05-119.png",
    "op01-120.png": "https://www.onepiece-cardgame.com/images/cardlist/card/OP01-120.png",
    "op02-013.png": "https://www.onepiece-cardgame.com/images/cardlist/card/OP02-013.png",
}


def main():
    print("CARDSTAR — 下載卡圖")
    print("=" * 40)

    os.makedirs("docs/images", exist_ok=True)

    ok = 0
    fail = 0

    for filename, url in IMAGES.items():
        path = f"docs/images/{filename}"

        # 已存在就跳過
        if os.path.exists(path) and os.path.getsize(path) > 1000:
            print(f"  ✓ {filename} (已存在)")
            ok += 1
            continue

        print(f"  下載 {filename}...", end=" ")
        try:
            r = requests.get(url, headers={"User-Agent": UA}, timeout=30)
            if r.status_code == 200 and len(r.content) > 1000:
                with open(path, "wb") as f:
                    f.write(r.content)
                print(f"OK ({len(r.content):,} bytes)")
                ok += 1
            else:
                print(f"FAIL (HTTP {r.status_code}, {len(r.content)} bytes)")
                fail += 1
        except Exception as e:
            print(f"ERROR: {e}")
            fail += 1

        time.sleep(1)

    print(f"\n完成: {ok} 成功, {fail} 失敗")
    print(f"圖片存放: docs/images/")


if __name__ == "__main__":
    main()
