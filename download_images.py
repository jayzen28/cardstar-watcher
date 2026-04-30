"""
CARDSTAR — 卡圖下載器 v2
模擬瀏覽器下載，加完整 headers。
"""
import requests
import os
import time

IMAGES = {
    "svp-057.png": {
        "url": "https://asia.pokemon-card.com/tw/card-img/tw00009219.png",
        "referer": "https://asia.pokemon-card.com/tw/card-search/"
    },
    "svp-098.jpg": {
        "url": "https://www.pokemon-card.com/assets/images/card_images/large/SV-P/044245_P_MEITANTEIPIKACHIXYUU.jpg",
        "referer": "https://www.pokemon-card.com/card-search/"
    },
    "svp-074.jpg": {
        "url": "https://www.pokemon-card.com/assets/images/card_images/large/SV-P/044212_P_PIKACHIXYUU.jpg",
        "referer": "https://www.pokemon-card.com/card-search/"
    },
    "svp-218.jpg": {
        "url": "https://www.pokemon-card.com/assets/images/card_images/large/SV-P/046150_P_PIKACHIXYUU.jpg",
        "referer": "https://www.pokemon-card.com/card-search/"
    },
    "svp-242.jpg": {
        "url": "https://www.pokemon-card.com/assets/images/card_images/large/SV-P/047363_P_PIKACHIXYUU.jpg",
        "referer": "https://www.pokemon-card.com/card-search/"
    },
    "svp-001.jpg": {
        "url": "https://www.pokemon-card.com/assets/images/card_images/large/SV-P/042261_P_PIKACHIXYUU.jpg",
        "referer": "https://www.pokemon-card.com/card-search/"
    },
    "op05-119.png": {
        "url": "https://www.onepiece-cardgame.com/images/cardlist/card/OP05-119.png",
        "referer": "https://www.onepiece-cardgame.com/cardlist/"
    },
    "op01-120.png": {
        "url": "https://www.onepiece-cardgame.com/images/cardlist/card/OP01-120.png",
        "referer": "https://www.onepiece-cardgame.com/cardlist/"
    },
    "op02-013.png": {
        "url": "https://www.onepiece-cardgame.com/images/cardlist/card/OP02-013.png",
        "referer": "https://www.onepiece-cardgame.com/cardlist/"
    },
}

def download(url, referer, path):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
        "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
        "Referer": referer,
        "Sec-Ch-Ua": '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
        "Sec-Ch-Ua-Mobile": "?0",
        "Sec-Ch-Ua-Platform": '"Windows"',
        "Sec-Fetch-Dest": "image",
        "Sec-Fetch-Mode": "no-cors",
        "Sec-Fetch-Site": "same-origin",
    }
    r = requests.get(url, headers=headers, timeout=30)
    if r.status_code == 200 and len(r.content) > 1000:
        with open(path, "wb") as f:
            f.write(r.content)
        return True, len(r.content)
    return False, r.status_code

def main():
    print("CARDSTAR — 下載卡圖 v2")
    print("=" * 40)
    os.makedirs("docs/images", exist_ok=True)

    ok = 0
    fail = 0
    for filename, info in IMAGES.items():
        path = f"docs/images/{filename}"
        if os.path.exists(path) and os.path.getsize(path) > 1000:
            print(f"  ✓ {filename} (已存在, {os.path.getsize(path):,} bytes)")
            ok += 1
            continue

        print(f"  下載 {filename}...", end=" ")
        success, detail = download(info["url"], info["referer"], path)
        if success:
            print(f"OK ({detail:,} bytes)")
            ok += 1
        else:
            print(f"FAIL (status {detail})")
            fail += 1
        time.sleep(1)

    print(f"\n結果: {ok} 成功, {fail} 失敗")

    # 列出 docs/images 內容
    imgs = os.listdir("docs/images") if os.path.exists("docs/images") else []
    print(f"docs/images/ 共 {len(imgs)} 個檔案:")
    for f in sorted(imgs):
        size = os.path.getsize(f"docs/images/{f}")
        print(f"  {f}: {size:,} bytes")

if __name__ == "__main__":
    main()
