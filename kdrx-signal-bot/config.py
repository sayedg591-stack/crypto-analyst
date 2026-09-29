# -*- coding: utf-8 -*-
"""إعدادات بوت إشارات Kdrx-style — كل القيم هنا قابلة للتعديل."""

import os

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
KLINE_LIMIT = 200  # عدد الشموع لكل طلب (كافٍ لحساب كل المؤشرات)

# ---------- السرعة (استغلال كامل للـVM — مجاني 100%) ----------
SCAN_WORKERS = 8          # عدد الخيوط المتوازية للفحص
SCAN_INTERVAL_MINUTES = 5  # فحص الإشارات كل 5 دقائق
MONITOR_INTERVAL_MINUTES = 2  # مراقبة المراكز (TP/SL) كل دقيقتين

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

# ---------- المستويات (ATR-based) — طريقة Kdrx ----------
ATR_SL_MULT = 1.5     # وقف الخسارة = 1.5 × ATR
TP_MULTIPLES = (2.0, 3.0, 5.0)  # أهداف بـ R-multiples — الهدف 1 = 2R (مخاطرة/عائد 2:1 مثل Kdrx)
MIN_RR = 2.0          # أدنى مخاطرة/عائد مقبول

# ---------- المحفظة الورقية ----------
STARTING_CASH = 100.0
RISK_PER_TRADE = 0.03   # 3% مخاطرة لكل صفقة (مثل Kdrx: 3.09%)
MAX_POSITIONS = 5
# توزيع الإغلاق الجزئي (طريقة Kdrx: بيع 50% عند الهدف الأول + نقل الوقف للدخول)
TP1_CLOSE_PCT = 0.50    # عند الهدف 1: إغلاق 50% + نقل الوقف للدخول (صفقة بلا مخاطرة)
TP2_CLOSE_PCT = 0.30    # عند الهدف 2: إغلاق 30%
TP3_CLOSE_PCT = 0.20    # عند الهدف 3: إغلاق 20% المتبقية

# ---------- فلاتر Kdrx ----------
SUPPORT_LOOKBACK = 50       # عدد الشموع للبحث عن الدعم/المقاومة
SUPPORT_PROXIMITY_PCT = 0.03  # السعر قريب من الدعم: ضمن 3%

# ---------- Telegram ----------
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
TELEGRAM_API = "https://api.telegram.org"

# ---------- التشغيل ----------
STATE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "state")
WALLET_FILE = os.path.join(STATE_DIR, "wallet.json")
SIGNALS_FILE = os.path.join(STATE_DIR, "signals.json")
LOG_FILE = os.path.join(STATE_DIR, "bot.log")
