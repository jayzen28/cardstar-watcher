name: CARDSTAR Watcher v0.3

on:
  schedule:
    # 每 6 小時跑一次 (UTC)
    # 對應台灣時間: 02:00 / 08:00 / 14:00 / 20:00
    - cron: '0 */6 * * *'
  workflow_dispatch:  # 允許手動觸發

jobs:
  watch:
    runs-on: ubuntu-latest
    timeout-minutes: 10

    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: pip install -r requirements.txt

      - name: Run watcher
        env:
          TELEGRAM_BOT_TOKEN: ${{ secrets.TELEGRAM_BOT_TOKEN }}
          TELEGRAM_CHAT_ID: ${{ secrets.TELEGRAM_CHAT_ID }}
          CF_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
          CF_D1_DATABASE_ID: ${{ secrets.CF_D1_DATABASE_ID }}
          CF_D1_TOKEN: ${{ secrets.CF_D1_TOKEN }}
        run: python watcher.py
if __name__ == "__main__":
    main()
