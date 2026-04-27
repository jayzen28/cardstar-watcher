# CARDSTAR Price Watcher v0.1

每 6 小時自動爬 BigGo 上你關注的卡牌價格，推播到 Telegram。

---

## 🎯 它做什麼

- 每 6 小時自動執行（透過 GitHub Actions）
- 用你 `cards.json` 裡定義的關鍵字，到 **BigGo** 搜尋
- BigGo 會回傳蝦皮、露天、Ruten、PChome 各家賣場的標價
- 取每張卡**前 5 個最低標價** + 價差百分比
- 推播到你的 Telegram

---

## 📋 你需要先準備

- ✅ Telegram Bot token（你已經有了）
- ✅ Telegram chat ID（你已經有了）
- ✅ GitHub 帳號（jayzen28，你已經有了）
- 一台電腦（不一定要長期開機，部署完就交給 GitHub 跑）
- 約 30-45 分鐘設定時間

---

## 🚀 部署步驟（GitHub Actions 路線，推薦）

### Step 1：建立 GitHub Repo

1. 打開 https://github.com/new
2. **Repository name**：填 `cardstar-watcher`
3. **設定為 Private**（私人，因為裡面有你的監控設定）
4. ✅ 勾選 **Add a README file**
5. 點 **Create repository**

### Step 2：上傳檔案到 Repo

**最簡單的做法（不用 git）：**

1. 進到你剛建好的 repo 頁面
2. 點 **Add file** → **Upload files**
3. 把這個資料夾裡的**所有檔案跟資料夾**全選拖進去：
   - `watcher.py`
   - `cards.json`
   - `requirements.txt`
   - `.github/` 資料夾（**整個拖進去**）
4. 下方填 Commit message："initial commit"
5. 點 **Commit changes**

⚠️ 注意：`.github/workflows/watch.yml` 必須在正確的路徑下。如果你拖檔案上去後，`.github/workflows/` 路徑沒有保留，可以這樣補救：
- 在 GitHub repo 頁面點 **Add file → Create new file**
- 檔名輸入 `.github/workflows/watch.yml`（會自動建立資料夾）
- 把 `watch.yml` 內容貼進去儲存

### Step 3：設定 Telegram 密鑰（重要！）

**絕對不要把 token 直接寫在程式裡或上傳到 GitHub。** 用 GitHub Secrets 加密儲存：

1. 進你的 repo 頁面 → 點上方 **Settings**（不是 GitHub 自己的 settings,是 repo 的）
2. 左邊選單找 **Secrets and variables** → 點 **Actions**
3. 點綠色按鈕 **New repository secret**

**新增第一個 secret：**
- Name: `TELEGRAM_TOKEN`
- Secret: 貼上你從 BotFather 拿到的那串 token（`8123456789:AAH-xxxxxxxxxxxxxxxxxxxxxxx`）
- 點 **Add secret**

**新增第二個 secret：**
- Name: `TELEGRAM_CHAT_ID`
- Secret: 貼上你從 @userinfobot 拿到的那串數字
- 點 **Add secret**

完成後 Secrets 頁面會看到兩個項目。值不會再顯示出來（這是正常的，安全考量）。

### Step 4：手動觸發第一次執行（測試）

1. 進 repo 頁面 → 點上方 **Actions** 分頁
2. 左邊看到 **CARDSTAR Price Watcher** workflow
3. 右邊點 **Run workflow** 按鈕（藍色下拉選單）
4. 再點 **Run workflow** 確認

等 1-2 分鐘，Actions 會跑完。如果成功，你的 Telegram 應該會收到一份報告。

---

## 🔧 排程說明

設定檔在 `.github/workflows/watch.yml`，目前是 **每 6 小時跑一次**。
對應台北時間：早上 8 點、下午 2 點、晚上 8 點、凌晨 2 點。

如果你要改頻率，編輯 `cron: '0 */6 * * *'` 這行：
- `'0 */4 * * *'` = 每 4 小時
- `'0 */12 * * *'` = 每 12 小時
- `'0 9,21 * * *'` = 每天 UTC 9 點跟 21 點（台北 17 點跟早 5 點）

---

## 🃏 修改要監控的卡片

打開 `cards.json`，每張卡是一個物件：

```json
{
  "id": "your_card_id",
  "name_zh": "卡片中文名（顯示用）",
  "card_no": "057/SV-P",
  "search_keywords": ["搜尋關鍵字 1", "搜尋關鍵字 2"],
  "exclude_keywords": ["卡套", "玩偶"],
  "primary_market": "TW",
  "notes": "你自己的備註"
}
```

- `search_keywords`：用什麼字去搜（多寫幾組，BigGo 才搜得廣）
- `exclude_keywords`：標題包含這些字就排除（避免抓到周邊商品）
- `primary_market`：`TW` / `HK` / `JP`（影響推播時的旗幟圖示）

改完之後 commit 上去，下次自動執行就會用新清單。

---

## ⚠️ 已知限制（誠實標出）

### 1. 第一版只爬 BigGo
還沒接入香港 Carousell、駿河屋、雅虎拍。等你跑通這版、確認推播能收到，我們再加進去。

### 2. BigGo 的 HTML 結構可能變
BigGo 偶爾會改前端，我寫的 selector 是用多個備案組合（`.item__container` 失敗就換 `article[data-item]` 等）。如果他們大改版，可能會抓不到資料。**第一次跑如果發現空白，把 GitHub Actions 的 log 截給我看，我修。**

### 3. 反爬風險
GitHub Actions 用的 IP 是 Microsoft Azure，不是台灣家用 IP，可能會被 BigGo 認定為爬蟲擋掉。如果發生，解法有：
- 加入 cookies 模擬登入狀態
- 用付費代理服務
- 改用無頭瀏覽器（playwright）

這些都是有解，但不是第一版的事。

### 4. 沒有歷史價格儲存
v0.1 每次跑都是當下快照，沒存歷史。**v0.2 我會加上 SQLite 儲存歷史價，這樣才能算「均價」、「最低 30 天紀錄」這種智能推播。**

---

## 🧪 在自己電腦上測試（可選）

如果你想先在自己電腦跑一次看看效果，**不一定要先部署到 GitHub**：

### macOS / Linux：

```bash
# 1. 進到資料夾
cd cardstar-watcher

# 2. 安裝套件
pip3 install -r requirements.txt

# 3. 設定環境變數（替換成你的）
export TELEGRAM_TOKEN="你的 token"
export TELEGRAM_CHAT_ID="你的 chat id"

# 4. 跑
python3 watcher.py
```

### Windows（PowerShell）：

```powershell
cd cardstar-watcher
pip install -r requirements.txt
$env:TELEGRAM_TOKEN="你的 token"
$env:TELEGRAM_CHAT_ID="你的 chat id"
python watcher.py
```

跑完應該會：
1. 終端機印出進度
2. 你的 Telegram 收到報告

如果沒設環境變數，程式會把報告印到終端機而不推播（用來測試爬蟲本身）。

---

## 📞 出錯怎麼辦

第一次部署 80% 機率不會一次成功。常見問題：

| 問題 | 解法 |
|---|---|
| Actions 跑出來但 Telegram 沒收到 | 檢查 Secrets 名字是否完全正確（大小寫敏感） |
| 抓到 0 筆資料 | BigGo 改版或被擋，截 log 給我 |
| Actions 不會自動跑 | GitHub 對 60 天沒活動的 repo 會暫停 schedule，每 60 天 push 一次或手動觸發一次 |
| 收到的訊息亂碼 | Telegram bot 沒設定好 HTML parse mode（程式裡已經設了） |

把錯誤訊息或 Actions log 直接貼給我，我幫你 debug。

---

## 🔮 接下來的版本路線圖

- **v0.1（這個版本）**：BigGo + Telegram，跑通就贏
- **v0.2**：加 SQLite 歷史價格儲存 + 「低於均價 X% 才推播」邏輯
- **v0.3**：加香港 Carousell + 駿河屋
- **v0.4**：接入 CARDSTAR 後端 API（同步成交價到你的 app）
- **v0.5**：FB 社團（如果決定付 Apify 服務費）

---

**現在你的步驟：**
1. 把這個資料夾裡的檔案下載到電腦
2. 照 Step 1-4 部署到 GitHub
3. 第一次跑完之後告訴我結果，我們 iterate
