# -*- coding: utf-8 -*-
"""إعدادات بوت إشارات Kdrx-style — كل القيم هنا قابلة للتعديل."""

import os


def _load_dotenv(path="/home/ubuntu/bot/.env"):
    """تحميل متغيرات البيئة من ملف .env — لأن cron لا يملكها في بيئته."""
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k, v = k.strip(), v.strip().strip('"').strip("'")
                if k and k not in os.environ:
                    os.environ[k] = v
    except FileNotFoundError:
        pass


_load_dotenv()

# أسماء بديلة للتوافق: GIST_ID/GH_PAT في .env ←→ KDRX_GIST_ID/GITHUB_TOKEN في الكود
if not os.environ.get("KDRX_GIST_ID") and os.environ.get("GIST_ID"):
    os.environ["KDRX_GIST_ID"] = os.environ["GIST_ID"]
if not os.environ.get("GITHUB_TOKEN") and os.environ.get("GH_PAT"):
    os.environ["GITHUB_TOKEN"] = os.environ["GH_PAT"]

# ---------- Binance (بيانات عمومية مجانية — بدون مفتاح) ----------
BINANCE_API = "https://data-api.binance.vision"
KLINES_ENDPOINT = f"{BINANCE_API}/api/v3/klines"
TICKER_ENDPOINT = f"{BINANCE_API}/api/v3/ticker/24hr"

# ---------- قائمة العملات (Top 50 USDT spot — سيولة عالية) ----------
WATCHLIST = [
    "BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT",
    "DOGEUSDT", "ADAUSDT", "AVAXUSDT", "LINKUSDT", "DOTUSDT",
    "MATICUSDT", "LTCUSDT", "ATOMUSDT", "NEARUSDT", "UNIUSDT",
    "APTUSDT", "ARBUSDT", "OPUSDT", "INJUSDT", "SUIUSDT",
    "FILUSDT", "AAVEUSDT", "GRTUSDT", "SANDUSDT", "MANAUSDT",
    "AXSUSDT", "THETAUSDT", "VETUSDT", "ALGOUSDT", "FTMUSDT",
    "TRXUSDT", "ETCUSDT", "XLMUSDT", "HBARUSDT", "BONKUSDT",
    "SHIBUSDT", "PEPEUSDT", "WLDUSDT", "SEIUSDT", "TIAUSDT",
    "JUPUSDT", "ONDOUSDT", "FETUSDT", "RENDERUSDT", "ARUSDT",
    "DASHUSDT", "ZECUSDT", "EGLDUSDT", "TONUSDT", "NEIROUSDT",
]

TIMEFRAME = "4h"
KLINE_LIMIT = 200

# ---------- السرعة ----------
SCAN_WORKERS = 8
SCAN_INTERVAL_MINUTES = 5
MONITOR_INTERVAL_MINUTES = 2

# ---------- بوابة الإشارة ----------
MIN_SCORE = 55
MIN_ADX = 20
SIGNAL_COOLDOWN_HOURS = 12

# ---------- المؤشرات ----------
RSI_PERIOD = 14
MACD_FAST, MACD_SLOW, MACD_SIGNAL = 12, 26, 9
ADX_PERIOD = 14
ATR_PERIOD = 14
BB_PERIOD, BB_STD = 20, 2.0
STOCH_RSI_PERIOD = 14
VOLUME_MA_PERIOD = 20

# ---------- المستويات (ATR-based) — طريقة Kdrx ----------
ATR_SL_MULT = 1.5
TP_MULTIPLES = (2.0, 3.0, 5.0)
MIN_RR = 2.0

# ---------- المحفظة الورقية ----------
STARTING_CASH = 100.0
RISK_PER_TRADE = 0.03
MAX_POSITIONS = 5
TP1_CLOSE_PCT = 0.50
TP2_CLOSE_PCT = 0.30
TP3_CLOSE_PCT = 0.20

# ---------- فلاتر Kdrx ----------
SUPPORT_LOOKBACK = 50
SUPPORT_PROXIMITY_PCT = 0.03

# ---------- نسخة Kdrx الكاملة (من البحث المباشر في قناته الرسمية) ----------
LONG_ONLY = True
ENTRY_ZONE_PCT = 0.015
RISK_MIN = 0.0309
RISK_MAX = 0.0667
MIN_BUYER_DOMINANCE = 0.484
DOMINANCE_LOOKBACK = 20

# ---------- Telegram ----------
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
TELEGRAM_API = "https://api.telegram.org"

# ---------- التشغيل ----------
STATE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "state")
WALLET_FILE = os.path.join(STATE_DIR, "wallet.json")
SIGNALS_FILE = os.path.join(STATE_DIR, "signals.json")
LOG_FILE = os.path.join(STATE_DIR, "bot.log")

# ---------- نسخ KDRX الحي (إشارات مُحوّلة من أيوب) ----------
KDRX_LIVE_WALLET_FILE = os.path.join(STATE_DIR, "kdrx_live.json")
KDRX_LIVE_RISK = 0.05          # مخاطرة افتراضية 5% إذا لم تُذكر في الإشارة
KDRX_LIVE_MAX_POSITIONS = 5
