# -*- coding: utf-8 -*-
"""إعدادات محلل عملات الميم — عدّل العتبات هنا حسب رغبتك."""

# الشبكات الممسوحة (معرّفات Dexscreener)
CHAINS = ["bsc", "solana", "base", "ethereum"]

# عدد العملات الجديدة المفحوصة في كل دورة
SCAN_LIMIT = 40   # استنزاف API: تحليل 40 مرشحاً/جولة بدل 20

# عتبات التصفية الأولية للعملات الجديدة (تنقية البيانات: حدود أعلى = ضجيج أقل)
MIN_LIQUIDITY_USD = 30_000   # رُفع +50% (كان 20K): السيولة الهشة تنزف ببطء حتى -24%
MIN_VOLUME_24H_USD = 10_000
MIN_TXNS_24H = 50        # حد أدنى لعدد صفقات آخر 24 ساعة
MAX_PAIR_AGE_DAYS = 30

# عتبات الإشارة (من 100) — شُدّدت 2026-09-25 بعد تحليل الأرشيف:
# نسبة الفوز المحققة 25% فقط مقابل ≥50% متوقعة → الفلتر متفائل، نرفع البار
SCORE_STRONG_BUY = 80
SCORE_BUY = 70
SCORE_WATCH = 40

# إدارة الصفقة — استراتيجية v2 "النجاة أولاً" (2026-09-27):
# مبنية على بحث BSC المعمّق (base rate للنجاة ~1-2%، إجماع الممارسين على
# وقف -25%/-30%، جني الأرباح على مراحل، حد أقصى 7 أيام).
# تحل محل نظام الاستثمار الأصلي (2026-09-25) بأمر صريح من أيوب:
# "ابحت لنا عن استراتيجية تراها مناسبة لنا… وطبق".
TAKE_PROFITS = [1.00, 3.00, 9.00]  # +100% (بيع 25%)، +300% (بيع 25%)،
                                   # +900% (بيع 25%) — الباقي 25% "حقيبة القمر"
                                   # يتبعها وقف متحرك بدل البيع الكامل
# بعد الهدف الأول: وقف الخسارة ينتقل للدخول ثم يتبع القمة (وقف متحرك)
STOP_LOSS = 0.30                   # وقف الخسارة: -30% (كان -60% — إجماع الممارسين
                                   # وبحث BSC: -25%/-30%؛ -60% كان يترك الصفقات
                                   # تنزف حتى الانهيار الكامل)
TRAIL_PCT = 0.30                   # الوقف المتحرك لحقيبة القمر: 30% تحت أعلى قمة
                                   # (نطاق بحث BSC: 20-30%)
POSITION_MAX_AGE_H = 24 * 7         # حد زمني: 7 أيام (كان 14 — إجماع الممارسين:
                                   # الميم التي لا تتحرك في أسبوع نادراً ما تتحرك)
MOMENTUM_CUTOFF_H = 48              # فلتر الزخم: بعد 48 ساعة بلا هدف وبلا
MOMENTUM_MIN_GAIN = 0.30            # ربح +30% → خروج (الأطروحة ميتة — لا تنتظر
                                   # 7 أيام على عملة لا تتحرك)

# عملات الميم المتابَعة على Binance (توقيت الدخول/الخروج)
WATCHLIST = [
    "DOGEUSDT", "SHIBUSDT", "PEPEUSDT", "WIFUSDT", "BONKUSDT",
    "FLOKIUSDT", "POPCATUSDT", "PNUTUSDT", "BRETTUSDT", "MOGUSDT",
]

# ساعات الملخص اليومي (بتوقيت UTC — المغرب = UTC+1)
DIGEST_HOURS_UTC = (8, 20)

# عناوين الـ APIs المجانية
DEXSCREENER_API = "https://api.dexscreener.com"
HONEYPOT_API = "https://api.honeypot.is/v2"
RUGCHECK_API = "https://api.rugcheck.xyz"
BINANCE_API = "https://data-api.binance.vision"  # بيانات عمومية بدون مفتاح
NEWS_RSS = "https://cointelegraph.com/rss"  # (قديم — يُستخدم NEWS_FEEDS الآن)

# ---------- مصادر إضافية: عملات + أخبار ----------
USE_COINGECKO = True
COINGECKO_API = "https://api.coingecko.com/api/v3"  # مجاني بدون مفتاح

USE_NEWS = True
# ---------- تنقية البيانات: مصادر موثوقة بطبقات ثقة ----------
# الطبقة 1: إعلام مالي عالمي (الأعلى ثقة) — الطبقة 2: إعلام كريبتو متخصص معروف
# الطبقة 3: إعلام كريبتو عام (يُستخدم للمزاج العام فقط، لا لإشارات العملات)
TIER_WEIGHTS = {1: 3.0, 2: 2.0, 3: 1.0}
NEWS_FEEDS = [
    # الطبقة 1: صحافة مالية عالمية موثوقة ومشهورة
    ("Bloomberg", "https://feeds.bloomberg.com/markets/news.rss", 1),
    ("CNBC", "https://www.cnbc.com/id/10000664/device/rss/rss.html", 1),
    # الطبقة 2: إعلام كريبتو متخصص ومعروف
    ("CoinDesk", "https://www.coindesk.com/arc/outboundfeeds/rss/", 2),
    ("CoinTelegraph", "https://cointelegraph.com/rss", 2),
    ("The Block", "https://www.theblock.co/rss.xml", 2),
    ("Decrypt", "https://decrypt.co/feed", 2),
    ("CryptoSlate", "https://cryptoslate.com/feed/", 2),
    ("DL News", "https://www.dlnews.com/rss", 2),
    ("The Defiant", "https://thedefiant.io/api/feed", 2),
    # الطبقة 3: مصادر كريبتو عامة
    ("Bitcoin Magazine", "https://bitcoinmagazine.com/.rss/full/", 3),
    ("CoinJournal", "https://coinjournal.net/rss/", 3),
    ("Investing.com", "https://www.investing.com/rss/news_25.rss", 3),
    ("CoinGape", "https://coingape.com/feed/", 3),
    ("NewsBTC", "https://www.newsbtc.com/feed/", 3),
    ("Bitcoinist", "https://bitcoinist.com/feed/", 3),
    ("AMBCrypto", "https://ambcrypto.com/feed/", 3),
    ("U.Today", "https://u.today/rss.php", 3),
    ("CryptoPotato", "https://cryptopotato.com/feed/", 3),
    ("BeInCrypto", "https://beincrypto.com/feed/", 3),
    ("Coinpedia", "https://coinpedia.org/feed/", 3),
    ("DailyCoin", "https://dailycoin.com/feed/", 3),
    ("ZyCrypto", "https://zycrypto.com/feed/", 3),
]
NEWS_LOOKBACK_HOURS = 12   # أخبار آخر 12 ساعة فقط
NEWS_MAX_ITEMS = 40
NEWS_MIN_TITLE_LEN = 25    # تجاهل العناوين القصيرة/الفارغة (ضجيج)
NEWS_DEDUPE_SIM = 0.85     # دمج الأخبار المتشابهة فوق هذه النسبة

# ===== مصادر اكتشاف مجانية جديدة (بلا مفاتيح ولا تسجيل) =====
GECKOTERMINAL_API = "https://api.geckoterminal.com/api/v2"
# خريطة شبكات GeckoTerminal -> chainId المستعمل في البوت
GECKO_NETWORKS = {"solana": "solana", "bsc": "bsc", "base": "base",
                  "eth": "ethereum"}
GECKO_POOL_LIMIT = 25       # أزواج لكل شبكة من كل قائمة (2.5x بيانات بنفس عدد الطلبات)
DISCOVERY_TOKEN_CAP = 300   # سقف العناوين: 300 (DexScreener يسمح 300 طلب/دقيقة)

# ===== سلاسل المصادر الاحتياطية (failover): 1→2→3→4→5 تلقائياً =====
# كل حاجة (سعر زوج، رائج، ماكرو) لها سلسلة مصادر مرتبة بالأولوية.
# المحرك يجرّب الأول، فإذا فشل/انتهى حدّه انتقل للثاني فوراً دون تدخل.
# المصدر الذي يفشل FAILS_TO_COOL مرات متتالية يدخل «تبريداً» تلقائياً
# (يُتخطى حتى انتهاء التبريد) ثم يُعاد اختباره وحده — شفاء ذاتي كامل.
SOURCE_FAILS_TO_COOL = 2    # فشلتان متتاليتان = تبريد
SOURCE_COOLDOWN_BASE = 60   # تبريد أساسي: دقيقة واحدة (يتضاعف عند التكرار) —
                             # تدوير لا نهائي سريع: المصدر المحروق يعود للخدمة بسرعة
SOURCE_COOLDOWN_MAX = 3600  # أقصى تبريد: ساعة واحدة
SECURITY_CACHE_TTL = 21600  # كاش فحوصات الأمان: 6 ساعات (عناوين جديدة فقط تستهلك الـquota)

# ضجة Reddit العضوية (JSON عام، بلا مفتاح)
REDDIT_SUBS = ["CryptoMoonShots", "memecoins"]
REDDIT_LIMIT = 40           # منشور لكل subreddit
REDDIT_MIN_MENTIONS = 3     # ≥3 ذكرات = اهتمام حقيقي
REDDIT_PROB_BOOST = 4       # بحد أقصى +4% على الاحتمال

# مشاعر Stocktwits (API عام مجاني بلا مفتاح)
STOCKTWITS_MIN_MSGS = 5     # حد أدنى للرسائل المصنّفة قبل الاعتماد
STOCKTWITS_PROB_BOOST = 3   # ±3% كحد أقصى على الاحتمال
NEWS_MIN_TIER_FOR_COIN = 2  # أخبار العملات: فقط الطبقتان 1 و2 (الأكثر ثقة)

# ---------- تنقية البيانات: مؤشر الخوف والطمع + التحقق المتبادل للأسعار ----------
USE_FNG = True
FNG_API = "https://api.alternative.me/fng/"   # مجاني بدون مفتاح
MACRO_VERIFY_MAX_DIFF = 2.5  # أقصى فرق مقبول (نقطة مئوية) بين مصدري BTC

# ---------- إشارات الخبير الجديدة (2026-09-21) ----------
# 1) لائحة الانتظار: عملات "شبه جاهزة" (40-59 نقطة) تُعاد فحصها كل جولة
WAITLIST_MAX_AGE_H = 6    # أقصى مدة للبقاء في لائحة الانتظار
WAITLIST_MAX_SIZE = 50    # أقصى عدد عملات في اللائحة
WAITLIST_ADD_PER_RUN = 8  # إضافات جديدة في كل جولة كحد أقصى

# 6) الفرص الحقيقية في الساعات الأولى — عملة أقدم من هذا لا تُرسل كتنبيه جديد
NEW_ALERT_MAX_AGE_H = 48

# 3) كشف التداول الوهمي: حجم/سيولة فوق هذا الحد = رفض فوري (حركة مصطنعة)
WASH_RATIO_LIMIT = 20
# 3ب) تركيز الحيتان: أكبر 10 محافظ فوق هذه النسبة = رفض فوري (خطر تفريغ)
HOLDER_TOP10_REJECT = 20

# 2) ضغط الشراء/البيع
BUY_PRESSURE_STRONG = 0.65  # مشترون ≥ 65% = طلب حقيقي
BUY_PRESSURE_WEAK = 0.40    # مشترون ≤ 40% = الناس تهرب

# 4) فلتر الرموز المشبوهة: حروف خفية مرفوضة + رموز العملات الكبيرة
#    أي عملة جديدة تحمل رمز عملة مشهورة = مُقلّدة وغالباً نصب
ZERO_WIDTH_CHARS = set("​‌‍⁠﻿­⁣ㅤ")
KNOWN_SYMBOLS = {
    "BTC", "ETH", "USDT", "USDC", "SOL", "BNB", "XRP", "DOGE", "ADA",
    "TRX", "LINK", "AVAX", "XLM", "SUI", "HBAR", "LTC", "DOT", "BCH",
    "SHIB", "UNI", "PEPE", "NEAR", "APT", "ARB", "OP", "INJ", "ATOM",
    "FIL", "TAO", "RENDER", "FET", "WIF", "BONK", "FLOKI", "DAI",
    "WBTC", "WETH", "STETH", "TON", "ICP", "KAS", "CRO", "POL",
    "AAVE", "MKR", "SNX", "CRV", "LDO", "GRT", "SAND", "MANA",
}

# ---------- المحفظة الافتراضية (Paper Trading) — تجربة بلا مخاطرة ----------
PAPER_ENABLED = True
PAPER_START_BALANCE = 100.0   # رصيد البداية بالدولار (وهمي 100%)
PAPER_RISK_PER_TRADE = 2.5    # مبلغ كل صفقة وهمية (خُفّض من 5$ في v2: بعد هبوط
                              # -76%، الرهان 5$ = 21% من المتبقي — انتحار؛
                              # 2.5$ يبقي ≥9 رصاصات للتعلم الأمامي)
# ملاحظة (محدّثة 2026-09-24): صار هناك سقف PAPER_MAX_OPEN للصفقات المفتوحة —
# كل تنبيه Telegram يفتح صفقة فقط إذا كان هناك مكان شاغر ورصيد كافٍ
# ---------- حزمة الحماية (2026-09-24): فرامل رأس المال ----------
# بعد هبوط -61.5%: البوت كان يشتري كل إشارة حتى نفاد الكاش بلا سقف.
PAPER_MAX_OPEN = 6            # حتى 6 استثمارات متزامنة (كان 10 — v2: رهانات أقل
                              # وأصغر؛ التركيز على النجاة لا على كثرة الرهانات)
CIRCUIT_BREAKER_SL_STREAK = 5    # v2: إيقاف الشراء 24h بعد 5 إغلاقات خاسرة
                                 # متتالية (كاشف انهيار إحصائي — كان معطلاً 999)
CIRCUIT_BREAKER_HALT_H = 24   # إيقاف 24 ساعة بعد كسر السلسلة
SL_COOLDOWN_H = 0             # معطّل: لا معنى للتهدئة في الاستثمار
# توزيع البيع عند الأهداف (v2): 25% عند +100%، 25% عند +300%، 25% عند +900%،
# والـ25% الأخيرة "حقيبة القمر" يتبعها وقف متحرك 30% (لا بيع كامل قسري)
PAPER_SELL_FRACTIONS = (0.25, 0.25, 0.25)
# بوابة الضرائب (v2 — بحث BSC/GMGN): ضريبة شراء أو بيع >10% = رفض فوري
# (0% آمن، 1-5% تحذير، >10% رفض)
MAX_BUY_TAX_PCT = 10.0
MAX_SELL_TAX_PCT = 10.0
# الانزلاق السعري الواقعي: الميم كوينز فيها انزلاق كبير، نحسبو 3% عند كل تنفيذ
# (الشراء بسعر أغلى، والبيع بسعر أرخص) باش النتائج الوهمية تكون قريبة من الواقع
PAPER_SLIPPAGE = 0.03

# ---------- إشارات موت العملة (2026-09-25) — بحث المستثمرين ----------
# المستثمر الحقيقي يقطع العملة الميتة رخيصة بدل انتظار وقف -60%:
# إشارتان مؤكدتان معاً = خروج كامل فوري (DEAD). مجاني 100% عبر DexScreener.
# (مصدر: دراسة Therani الكمية + إجماع الممارسين على "موت الحجم/السيولة")
DEATH_LIQ_USD = 1000        # سيولة < $1K = ميتة
DEATH_VOL_M5_USD = 50       # حجم 5 دقائق < $50 = ميت
DEATH_NOBUY_MIN_SELLS = 3   # صفر شراء مع ≥3 عمليات بيع في 5 دقائق = نزيف بلا مشترين
DEATH_CONFIRM_MIN = 15      # الإشارة تُؤكَّد بعد 15 دقيقة من الاستمرار (لا إيجابيات كاذبة)
DEATH_MIN_AGE_H = 1         # لا فحص قبل ساعة من الدخول (تجنّب ضجيج البداية)

# ---------- إشارات الخبير: الدفعة الثانية (2026-09-21) ----------
# 1) فحص القيمة السوقية: FDV/سيولة فوق هذا = خطر إغراق من الفريق
FDV_LIQ_RATIO_LIMIT = 50
# 2) عملة جديدة رائجة على CoinGecko = اهتمام حقيقي (+نقاط احتمال)
TRENDING_PROB_BOOST = 5
# 3) إعادة تقييم الصفقات: تحذير إذا نزلت النقاط تحت هذا بعد الدخول
POS_REEVAL_MIN_SCORE = 40
POS_REEVAL_MIN_AGE_H = 2   # لا إعادة تقييم قبل ساعتين من الدخول
# 4) كشف الضخ المفاجئ على Binance: حجم آخر ساعة × هذا مقابل المتوسط
VOL_SPIKE_MULT = 3
VOL_SPIKE_LOOKBACK = 12    # متوسط آخر 12 ساعة
VOL_SPIKE_COOLDOWN_H = 12

# ---------- الخبير: ذاكرة تتعلم من النتائج ----------
MIN_SAMPLES_FOR_LEARNING = 5  # أقل عدد نتائج سابقة ليعتمد عليها التعلم

# معرّف الشبكة لدى honeypot.is
HONEYPOT_CHAIN_IDS = {
    "ethereum": 1, "bsc": 56, "polygon": 137,
    "base": 8453, "arbitrum": 42161, "optimism": 10,
}

# GoPlus — مصدر احتياطي لفحص أمان العقود (مجاني، بلا مفتاح، EVM + Solana)
GOPLUS_API = "https://api.gopluslabs.io"
GOPLUS_CHAIN_IDS = {
    "ethereum": "1", "bsc": "56", "polygon": "137",
    "base": "8453", "arbitrum": "42161", "optimism": "10",
    "solana": "solana",
}

REQUEST_TIMEOUT = 10   # مهلة صارمة: أي API لا يرد في 10 ثوانٍ = فاشل (بلا تعليق)
USER_AGENT = "memecoin-analyst/1.0 (free-tier)"
# بصمة متصفح حقيقي: بعض الـAPIs تحظر عناوين البوتات المعروفة (429)
BROWSER_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
# إستراتيجية إعادة المحاولة عند الحظر المؤقت (429/5xx): 3 محاولات بانتظار 2ث ثم 4ث ثم 8ث
BACKOFF_TRIES = 3
BACKOFF_BASE = 2  # ثواني — يتضاعف بعد كل فشل

# ---------- المرونة ضد الأعطال (Resilience) ----------
# الافتراض الآمن: تعذّر فحص أمان العقد = العملة خطيرة ومرفوضة (Fail-Safe)
SECURITY_FAILSAFE_REJECT = True
# موثوقية Telegram: إعادة المحاولة عند الفشل (429/5xx) — 2ث ثم 4ث ثم 8ث
TG_MAX_RETRIES = 3
TG_RETRY_BASE = 2
# طابور الرسائل الفاشلة: أقصى عدد رسائل معلقة تُحفظ بين الجولات
TG_PENDING_MAX = 20

# عتبة الثقة: صفقة بنسبة نجاح تقديرية تحتها = مراقبة فقط (لا دخول ولا تنبيه)
# الفصل بين "جمع البيانات" و"القنص الانتقائي"
# رُفعت 2026-09-25 من 50% → 60%: الأرشيف أظهر 25% فوزاً فعلياً فقط،
# أي أن تقديرات البوت متفائلة بضعفين — نشدد البوابة حتى يعيد المعايرة
MIN_PROBABILITY = 60

# ---------- جسر أخبار X عبر Telegram (Telethon) ----------
USE_XBRIDGE = True       # يحتاج أسرار TG_API_ID/TG_API_HASH/TG_SESSION/XBRIDGE_CHANNELS
XBRIDGE_MAX_AGE_H = 6    # أقصى عمر لرسائل القنوات (ساعات)

# ---------- القياس البحثي (2026-09-25) ----------
# تسجيل مقاييس ATR(14)% / مضاعف الحجم / ضغط الشراء عند التقييم والدخول
# والأرشفة — قراءة فقط، لا يغيّر أي نقطة أو إشارة أو قرار تداول.
# صفر طلبات API إضافية (كلها من الشموع المحمّلة أصلاً).
# مفتاح إيقاف سريع: False يعطّل القياس دون المساس بأي سلوك.
# ---------- قناة أوامر Brother (2026-09-25) ----------
# صندوق بريد العمليات: Brother يكتب أمراً في ops/inbox.json ويدفعه
# إلى main، وأول فحص بعده ينفذه مرة واحدة ويكتب النتيجة في
# state["ops"] فتظهر في الـGist. بديل Run Command المعطّل في Oracle.
# False يعطّل القناة تماماً دون أي أثر آخر.
OPS_INBOX_ENABLED = True

INSTRUMENT_METRICS = True
