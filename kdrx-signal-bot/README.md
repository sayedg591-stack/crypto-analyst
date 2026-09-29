# KDRX Signal Bot
Kdrx-style crypto signal bot with $100 paper wallet.
- 4h timeframe, 30 USDT pairs
- 8 technical indicators, scored 0-100
- Auto paper trading, 2% risk/trade
- Telegram alerts in Arabic

## Run
```
cd kdrx-signal-bot
pip3 install pandas numpy requests
TELEGRAM_BOT_TOKEN=xxx TELEGRAM_CHAT_ID=yyy python3 main.py --once
```

## Files
- scanner.py: signal engine
- wallet.py: $100 paper wallet
- executor.py: auto-trade + TP/SL management
- publisher.py: Telegram (Arabic, Kdrx format)
- main.py: orchestrator (every 15 min)
- backtest.py: historical test
- config.py: settings
