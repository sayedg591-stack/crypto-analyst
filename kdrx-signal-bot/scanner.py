# -*- coding: utf-8 -*-
"""محرك الإشارات: جلب بيانات 4h من Binance → مؤشرات → نقاط 0-100 → إشارات."""

import time
import requests
import pandas as pd
import numpy as np

import config


# ================= جلب البيانات =================

def fetch_klines(symbol, interval=None, limit=None):
    """جلب شموع OHLCV من Binance (عمومي، بدون مفتاح)."""
    interval = interval or config.TIMEFRAME
    limit = limit or config.KLINE_LIMIT
    try:
        r = requests.get(
            config.KLINES_ENDPOINT,
            params={"symbol": symbol, "interval": interval, "limit": limit},
            timeout=15,
        )
        r.raise_for_status()
        data = r.json()
        df = pd.DataFrame(data, columns=[
            "open_time", "open", "high", "low", "close", "volume",
            "close_time", "qav", "trades", "taker_base", "taker_quote", "ignore",
        ])
        for c in ["open", "high", "low", "close", "volume"]:
            df[c] = df[c].astype(float)
        return df
    except Exception as e:
        print(f"[SCANNER] fetch failed {symbol}: {e}", flush=True)
        return None


def fetch_price(symbol):
    """السعر الحالي (آخر إغلاق)."""
    df = fetch_klines(symbol, limit=2)
    if df is None or len(df) == 0:
        return None
    return float(df["close"].iloc[-1])


def fetch_market_pulse():
    """جلب أسعار العملات الرئيسية مع تغير 24 ساعة (نبض السوق)."""
    symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"]
    result = {}
    try:
        r = requests.get(
            config.TICKER_ENDPOINT,
            params={"symbols": str(symbols).replace("'", '"')},
            timeout=15,
        )
        # Binance API يقبل symbols كمصفوفة JSON
        if r.status_code == 400:
            # fallback: طلب واحد واحد
            for sym in symbols:
                try:
                    rr = requests.get(config.TICKER_ENDPOINT, params={"symbol": sym}, timeout=10)
                    if rr.status_code == 200:
                        d = rr.json()
                        result[sym] = {
                            "price": float(d.get("lastPrice", 0)),
                            "change_pct": float(d.get("priceChangePercent", 0)),
                        }
                    time.sleep(0.2)
                except Exception:
                    pass
            return result
        r.raise_for_status()
        for d in r.json():
            sym = d.get("symbol")
            if sym in symbols:
                result[sym] = {
                    "price": float(d.get("lastPrice", 0)),
                    "change_pct": float(d.get("priceChangePercent", 0)),
                }
    except Exception as e:
        print(f"[SCANNER] market pulse failed: {e}", flush=True)
    return result


# ================= المؤشرات (تطبيق يدوي — بدون مكتبات خارجية) =================

def rsi(series, period=None):
    period = period or config.RSI_PERIOD
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def macd(series, fast=None, slow=None, signal=None):
    fast = fast or config.MACD_FAST
    slow = slow or config.MACD_SLOW
    signal = signal or config.MACD_SIGNAL
    ema_fast = series.ewm(span=fast, min_periods=slow).mean()
    ema_slow = series.ewm(span=slow, min_periods=slow).mean()
    line = ema_fast - ema_slow
    sig = line.ewm(span=signal, min_periods=signal).mean()
    hist = line - sig
    return line, sig, hist


def adx(high, low, close, period=None):
    period = period or config.ADX_PERIOD
    up = high.diff()
    dn = -low.diff()
    plus_dm = np.where((up > dn) & (up > 0), up, 0.0)
    minus_dm = np.where((dn > up) & (dn > 0), dn, 0.0)
    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low - close.shift()).abs(),
    ], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1 / period, min_periods=period).mean()
    plus_di = 100 * pd.Series(plus_dm, index=high.index).ewm(alpha=1 / period, min_periods=period).mean() / atr
    minus_di = 100 * pd.Series(minus_dm, index=high.index).ewm(alpha=1 / period, min_periods=period).mean() / atr
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    return dx.ewm(alpha=1 / period, min_periods=period).mean(), plus_di, minus_di


def atr(high, low, close, period=None):
    period = period or config.ATR_PERIOD
    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low - close.shift()).abs(),
    ], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / period, min_periods=period).mean()


def bollinger(series, period=None, std=None):
    period = period or config.BB_PERIOD
    std = std or config.BB_STD
    ma = series.rolling(period).mean()
    sd = series.rolling(period).std()
    return ma + std * sd, ma, ma - std * sd


def stoch_rsi(series, period=None):
    period = period or config.STOCH_RSI_PERIOD
    r = rsi(series, period)
    min_r = r.rolling(period).min()
    max_r = r.rolling(period).max()
    return (r - min_r) / (max_r - min_r).replace(0, np.nan) * 100


def compute_indicators(df):
    """حساب كل المؤشرات وإضافتها للـ DataFrame."""
    c, h, l, v = df["close"], df["high"], df["low"], df["volume"]
    df["rsi"] = rsi(c)
    m_line, m_sig, m_hist = macd(c)
    df["macd_line"], df["macd_sig"], df["macd_hist"] = m_line, m_sig, m_hist
    df["adx"], df["plus_di"], df["minus_di"] = adx(h, l, c)
    df["atr"] = atr(h, l, c)
    df["ema9"] = c.ewm(span=9, min_periods=9).mean()
    df["ema21"] = c.ewm(span=21, min_periods=21).mean()
    df["ema50"] = c.ewm(span=50, min_periods=50).mean()
    bb_u, bb_m, bb_l = bollinger(c)
    df["bb_u"], df["bb_m"], df["bb_l"] = bb_u, bb_m, bb_l
    df["bb_pct"] = (c - bb_l) / (bb_u - bb_l).replace(0, np.nan)
    df["stoch_rsi"] = stoch_rsi(c)
    df["vol_ratio"] = v / v.rolling(config.VOLUME_MA_PERIOD).mean()
    return df


# ================= الدعم والمقاومة (طريقة Kdrx: الدخول قرب الدعم) =================

def find_support_resistance(df, lookback=None):
    """إيجاد أقرب دعم ومقاومة من القيعان/القمم المحلية."""
    lookback = lookback or config.SUPPORT_LOOKBACK
    recent = df.tail(lookback)
    price = float(df["close"].iloc[-2])  # آخر سعر مغلق

    # القيعان المحلية (دعم): low أقل من الجيران
    lows = recent["low"]
    supports = []
    for i in range(2, len(lows) - 2):
        if lows.iloc[i] < lows.iloc[i-1] and lows.iloc[i] < lows.iloc[i+1] \
           and lows.iloc[i] < lows.iloc[i-2] and lows.iloc[i] < lows.iloc[i+2]:
            supports.append(float(lows.iloc[i]))

    # القمم المحلية (مقاومة)
    highs = recent["high"]
    resistances = []
    for i in range(2, len(highs) - 2):
        if highs.iloc[i] > highs.iloc[i-1] and highs.iloc[i] > highs.iloc[i+1] \
           and highs.iloc[i] > highs.iloc[i-2] and highs.iloc[i] > highs.iloc[i+2]:
            resistances.append(float(highs.iloc[i]))

    # أقرب دعم تحت السعر، أقرب مقاومة فوق السعر
    support = max([s for s in supports if s < price], default=None)
    resistance = min([r for r in resistances if r > price], default=None)
    return support, resistance


def is_near_support(price, support):
    """هل السعر قريب من الدعم (ضمن النسبة المحددة)؟"""
    if support is None or support <= 0:
        return False
    return abs(price - support) / support <= config.SUPPORT_PROXIMITY_PCT


def is_near_resistance(price, resistance):
    """هل السعر قريب من المقاومة؟"""
    if resistance is None or resistance <= 0:
        return False
    return abs(price - resistance) / resistance <= config.SUPPORT_PROXIMITY_PCT


def risk_level(strength):
    """مستوى المخاطرة مثل Kdrx: قوة عالية = مخاطرة منخفضة."""
    if strength >= 80:
        return "منخفضة", "🟢"
    elif strength >= 65:
        return "متوسطة", "🟡"
    else:
        return "مرتفعة", "🔴"


def build_analysis_text(direction, rsi_val, support, resistance, vol_ratio, entry):
    """نص التحليل مثل Kdrx: الاتجاه + مؤشر القوة + الدعم + الحجم."""
    trend = "صاعد" if direction == "long" else "هابط"
    parts = [f"الاتجاه {trend} ومؤشر القوة {rsi_val:.0f}"]
    if direction == "long" and support:
        parts.append(f"والسعر قريب من دعم عند {_fmt(support)}")
    elif direction == "short" and resistance:
        parts.append(f"والسعر قريب من مقاومة عند {_fmt(resistance)}")
    parts.append(f"حجم التداول ×{vol_ratio:.2f} المعدل.")
    return "📌 " + "، ".join(parts)


def _fmt(x):
    if x >= 1000:
        return f"{x:,.2f}"
    if x >= 1:
        return f"{x:.4f}"
    return f"{x:.6f}"


# ================= التقييم (0-100) =================

def score_row(row, prev):
    """تقييم شمعة واحدة → (نقاط الشراء 0-100، نقاط البيع 0-100، التفاصيل)."""
    long_pts, short_pts, details = 0.0, 0.0, {}

    # RSI (وزن 15)
    r = row["rsi"]
    if pd.notna(r):
        if r < 30:
            long_pts += 15; details["rsi"] = "oversold→long"
        elif r < 45:
            long_pts += 7; details["rsi"] = "weak→long"
        elif r > 70:
            short_pts += 15; details["rsi"] = "overbought→short"
        elif r > 55:
            short_pts += 7; details["rsi"] = "strong→short"

    # MACD histogram (وزن 15)
    mh, mh_prev = row["macd_hist"], prev["macd_hist"]
    if pd.notna(mh) and pd.notna(mh_prev):
        if mh > 0 and mh_prev <= 0:
            long_pts += 15; details["macd"] = "bullish cross"
        elif mh > 0:
            long_pts += 7; details["macd"] = "bullish"
        elif mh < 0 and mh_prev >= 0:
            short_pts += 15; details["macd"] = "bearish cross"
        elif mh < 0:
            short_pts += 7; details["macd"] = "bearish"

    # EMA alignment (وزن 15)
    e9, e21, e50 = row["ema9"], row["ema21"], row["ema50"]
    if pd.notna(e9) and pd.notna(e21) and pd.notna(e50):
        if e9 > e21 > e50:
            long_pts += 15; details["ema"] = "bull aligned"
        elif e9 > e21:
            long_pts += 7; details["ema"] = "bull partial"
        elif e9 < e21 < e50:
            short_pts += 15; details["ema"] = "bear aligned"
        elif e9 < e21:
            short_pts += 7; details["ema"] = "bear partial"

    # Bollinger %B (وزن 10)
    bbp = row["bb_pct"]
    if pd.notna(bbp):
        if bbp < 0.1:
            long_pts += 10; details["bb"] = "lower band→long"
        elif bbp < 0.3:
            long_pts += 5
        elif bbp > 0.9:
            short_pts += 10; details["bb"] = "upper band→short"
        elif bbp > 0.7:
            short_pts += 5

    # Stochastic RSI (وزن 10)
    sr = row["stoch_rsi"]
    if pd.notna(sr):
        if sr < 20:
            long_pts += 10; details["stoch"] = "oversold→long"
        elif sr > 80:
            short_pts += 10; details["stoch"] = "overbought→short"

    # ADX trend strength (وزن 15 — مكافأة للاتجاه القوي)
    a = row["adx"]
    pdi, mdi = row["plus_di"], row["minus_di"]
    if pd.notna(a) and pd.notna(pdi) and pd.notna(mdi):
        if a > 25:
            if pdi > mdi:
                long_pts += 15; details["adx"] = f"strong uptrend ({a:.0f})"
            else:
                short_pts += 15; details["adx"] = f"strong downtrend ({a:.0f})"
        elif a > 20:
            if pdi > mdi:
                long_pts += 8; details["adx"] = f"trend up ({a:.0f})"
            else:
                short_pts += 8; details["adx"] = f"trend down ({a:.0f})"

    # Volume confirmation (وزن 10)
    vr = row["vol_ratio"]
    if pd.notna(vr) and vr > 1.5:
        if long_pts > short_pts:
            long_pts += 10; details["vol"] = f"high vol ({vr:.1f}x)"
        elif short_pts > long_pts:
            short_pts += 10; details["vol"] = f"high vol ({vr:.1f}x)"

    total = long_pts + short_pts
    if total == 0:
        return 50, 50, details, "neutral"

    long_score = round(long_pts)  # من 100 (مجموع الأوزان = 100)
    short_score = round(short_pts)
    direction = "long" if long_score > short_score else "short" if short_score > long_score else "neutral"
    strength = max(long_score, short_score)
    return strength, direction, details, direction


# ================= بناء الإشارة =================

def build_signal(symbol, df):
    """بناء إشارة كاملة من آخر شمعة مغلقة (نستبعد الشمعة الجارية)."""
    if df is None or len(df) < 60:
        return None
    df = compute_indicators(df.copy())
    # آخر شمعة مغلقة = قبل الأخيرة (الأخيرة قد تكون جارية)
    row = df.iloc[-2]
    prev = df.iloc[-3]

    # تحقق من صحة المؤشرات الأساسية
    if pd.isna(row["adx"]) or pd.isna(row["atr"]) or pd.isna(row["rsi"]):
        return None

    strength, direction, details, _ = score_row(row, prev)

    # البوابة: نقاط ≥ 55 و ADX > 20
    if direction == "neutral" or strength < config.MIN_SCORE:
        return None
    if row["adx"] < config.MIN_ADX:
        return None

    entry = float(row["close"])

    # فلتر Kdrx: الدخول قرب الدعم (شراء) أو قرب المقاومة (بيع)
    support, resistance = find_support_resistance(df)
    if direction == "long" and not is_near_support(entry, support):
        return None  # السعر بعيد عن الدعم — ليست صفقة Kdrx
    if direction == "short" and not is_near_resistance(entry, resistance):
        return None

    atr_val = float(row["atr"])
    sl_dist = atr_val * config.ATR_SL_MULT

    if direction == "long":
        sl = entry - sl_dist
        tp1 = entry + sl_dist * config.TP_MULTIPLES[0]
        tp2 = entry + sl_dist * config.TP_MULTIPLES[1]
        tp3 = entry + sl_dist * config.TP_MULTIPLES[2]
    else:
        sl = entry + sl_dist
        tp1 = entry - sl_dist * config.TP_MULTIPLES[0]
        tp2 = entry - sl_dist * config.TP_MULTIPLES[1]
        tp3 = entry - sl_dist * config.TP_MULTIPLES[2]

    rr = round(sl_dist * config.TP_MULTIPLES[0] / sl_dist, 2)  # = 2.0 (مثل Kdrx)
    risk_pct = round(sl_dist / entry * 100, 2)

    # حقول Kdrx الإضافية
    risk_lbl, risk_emoji = risk_level(strength)
    rsi_val = float(row["rsi"]) if pd.notna(row["rsi"]) else 50
    vol_r = float(row["vol_ratio"]) if pd.notna(row["vol_ratio"]) else 1.0
    analysis = build_analysis_text(direction, rsi_val, support, resistance, vol_r, entry)

    return {
        "symbol": symbol,
        "direction": direction,  # long = شراء, short = بيع
        "timeframe": config.TIMEFRAME,
        "type": "spot",
        "strength": strength,
        "entry": round(entry, 6),
        "sl": round(sl, 6),
        "tp1": round(tp1, 6),
        "tp2": round(tp2, 6),
        "tp3": round(tp3, 6),
        "rr": f"{rr:.0f} : 1",
        "risk_pct": risk_pct,
        "adx": round(float(row["adx"]), 1),
        "atr": round(atr_val, 6),
        "details": details,
        "candle_time": int(df["open_time"].iloc[-2]),
        "created_at": int(time.time()),
        # حقول Kdrx
        "risk_level": risk_lbl,
        "risk_emoji": risk_emoji,
        "rsi_value": round(rsi_val, 0),
        "support": round(support, 6) if support else None,
        "resistance": round(resistance, 6) if resistance else None,
        "vol_ratio": round(vol_r, 2),
        "analysis": analysis,
    }


def scan_all():
    """فحص كل العملات بشكل متوازي (سريع) → قائمة الإشارات."""
    from concurrent.futures import ThreadPoolExecutor, as_completed
    signals = []

    def scan_one(symbol):
        try:
            df = fetch_klines(symbol)
            if df is None:
                return None
            sig = build_signal(symbol, df)
            if sig:
                print(f"[SCANNER] SIGNAL {symbol} {sig['direction']} strength={sig['strength']}", flush=True)
            return sig
        except Exception as e:
            print(f"[SCANNER] error {symbol}: {e}", flush=True)
            return None

    t0 = time.time()
    with ThreadPoolExecutor(max_workers=config.SCAN_WORKERS) as ex:
        futures = {ex.submit(scan_one, s): s for s in config.WATCHLIST}
        for f in as_completed(futures):
            sig = f.result()
            if sig:
                signals.append(sig)
    dt = time.time() - t0
    print(f"[SCANNER] Scanned {len(config.WATCHLIST)} pairs in {dt:.1f}s → {len(signals)} signals", flush=True)
    return signals


def scan_all_sequential():
    """فحص تسلسلي (احتياطي)."""
    signals = []
    for symbol in config.WATCHLIST:
        df = fetch_klines(symbol)
        if df is None:
            continue
        sig = build_signal(symbol, df)
        if sig:
            signals.append(sig)
            print(f"[SCANNER] SIGNAL {symbol} {sig['direction']} strength={sig['strength']}", flush=True)
        time.sleep(0.2)
    return signals


if __name__ == "__main__":
    print(f"[SCANNER] Scanning {len(config.WATCHLIST)} pairs on {config.TIMEFRAME}...", flush=True)
    sigs = scan_all()
    print(f"[SCANNER] Done. {len(sigs)} signals found.", flush=True)
    for s in sigs:
        print(f"  {s['symbol']} {s['direction']} score={s['strength']} entry={s['entry']} sl={s['sl']}", flush=True)
