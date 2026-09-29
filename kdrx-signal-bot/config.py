# -*- coding: utf-8 -*-
"""إعدادات بوت إشارات Kdrx-style — كل القيم هنا قابلة للتعديل."""

import os

# ---------- Binance (بيانات عمومية مجانية — بدون مفتاح) ----------
BINANCE_API = "https://data-api.binance.vision"
KLINES_ENDPOINT = f"{BINANCE_API}/api/v3/klines"
TICKER_ENDPOINT = f"{BINANCE_API}/api/v3/ticker/24hr"

# ---------- قائمة العملات (Top 30 USDT spot) ----------
WATCHLIST = [
    "BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT",
    "DOGEUSDT", "ADAUSDT", "AVAXUSDT", "LINKUSDT", "DOTUSDT",
    "MATICUSDT", "LTCUSDT", "ATOMUSDT", "NEARUSDT", "UNIUSDT",
    "APTUSDT", "ARBUSDT", "OPUSDT", "INJUSDT", "SUIUSDT",
    "FILUSDT", "AAVEUSDT", "GRTUSDT", "SANDUSDT", "MANAUSDT",
    "AXSUSDT", "THETAUSDT", "VETUSDT", "ALGOUSDT", "FTMUSDT",
]

TIMEFRAME = "4h"
KLINE_LIMIT = 200  # عدد الشموع لكل طلب (كافٍ لحساب كل المؤشرات)

# ---------- بوابة الإشارة ----------
MIN_SCORE = 55        # الحد الأدنى لقوة الإشارة (من 100) — معاير على بيانات حية
MIN_ADX = 20          # تأكيد الترند (ADX > 20)
SIGNAL_COOLDOWN_HOURS = 12  # لا إشارة جديدة لنفس الزوج قبل 12 ساعة

# ---------- المؤشرات ----------
RSI_PERIOD = 14
MACD_FAST, MACD_SLOW, MACD_SIGNAL = 12, 26, 9
ADX_PERIOD = 14
ATR_PERIOD = 14
BB_PERIOD, BB_STD = 20, 2.0
STOCH_RSI_PERIOD = 14
VOLUME_MA_PERIOD = 20

# ---------- المستويات (ATR-based) ----------
ATR_SL_MULT = 1.5     # وقف الخسارة = 1.5 × ATR
TP_MULTIPLES = (1.5, 2.5, 4.0)  # أهداف بـ R-multiples
MIN_RR = 2.0          # أدنى مخاطرة/عائد مقبول

# ---------- المحفظة الورقية ----------
STARTING_CASH = 100.0
RISK_PER_TRADE = 0.02   # 2% مخاطرة لكل صفقة
MAX_POSITIONS = 5
# توزيع الإغلاق الجزئي
TP1_CLOSE_PCT = 0.40    # عند الهدف 1: إغلاق 40% + نقل الوقف للتعادل
TP2_CLOSE_PCT = 0.30    # عند الهدف 2: إغلاق 30%
TP3_CLOSE_PCT = 0.30    # عند الهدف 3: إغلاق 30% المتبقية

# ---------- Telegram ----------
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
TELEGRAM_API = "https://api.telegram.org"

# ---------- التشغيل ----------
SCAN_INTERVAL_MINUTES = 15
STATE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "state")
WALLET_FILE = os.path.join(STATE_DIR, "wallet.json")
SIGNALS_FILE = os.path.join(STATE_DIR, "signals.json")
LOG_FILE = os.path.join(STATE_DIR, "bot.log")
