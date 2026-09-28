# -*- coding: utf-8 -*-
"""طبقة جمع بيانات البحث — Full Opportunity Dataset (Phase 1 + تصحيحات).

الهدف: تسجيل كل عملة يراها الـscanner (وليس فقط التي اجتازت الفلاتر)
مع كل الـfeatures وقت التقييم، ثم تتبع سعرها لاحقاً حتى للعملات
المرفوضة (AVOID) — لاكتشاف الـRejected Winners وقياس الـExpectancy
الحقيقي قبل لمس أي قاعدة في Strategy v2.

التصميم:
- طبقة مستقلة تماماً: قراءة فقط، لا تغيّر أي قرار ولا أي عتبة.
- كل الدوال العامة fail-safe: أي استثناء يُسجَّل ويُتجاهَل —
  مستحيل أن تُسقط الفحص الرئيسي.
- قاعدة منفصلة ~/bot/research.duckdb (ليست market.duckdb) لتفادي
  أي تعارض كتابة مع مخزن السوق.
- إزالة التكرار: صف واحد لكل (chain, pair_address) — الظهور المتكرر
  يحدّث n_seen و last_seen_ts فقط.

الجداول:
- scan_opportunities: كل فرصة + features وقت أول مشاهدة —
  تشمل رفضات الـprefilter (signal='PREFILTER', decision='REJECTED_*').
- scan_events: لقطة ثابتة لكل فحص لكل فرصة مقيَّمة (immutable —
  وقود الـreplay في Phase 2). رفضات الـprefilter لا تُسجَّل هنا:
  featuresها ثابتة وقرارها حتمي من العتبات، وصف الفرصة
  (n_seen/last_seen) يكفي لتتبع ظهورها.
- price_observations: سلسلة سعرية للفرص المقيَّمة (كل ~دقيقتين).
- opportunity_outcomes: ملخص محسوب (MFE/MAE، الأسعار عند الآفاق،
  hit_100/300/900) — يُعاد حسابه مع كل دفعة ملاحظات، ويُغلق قسراً
  عند انتهاء نافذة 25h عبر finalize_due.

التتبع العادل: أولوية لمن طال انتظار ملاحظته (بلا تجويع للقديمة)،
مع فاصل 90s بين ملاحظتين لنفس الفرصة لتوزيع حمل الـAPI.

ملاحظة صدق: CVD/OBI/volatility_z من محرك flow.py تغطي رموز Binance
فقط، بينما الـscanner يقيّم أزواج DEX — لذلك ستكون هذه الأعمدة NULL
في الغالب. الأعمدة موجودة للتوافق المستقبلي، وعدم الاستعلام عنها
في مسار الفحص قرار متعمد (تجنب إبطاء الـscan). وبالمثل: رفضات
الـprefilter تُسجَّل بلا score/probability (NULL صادق — لم تُقيَّم).
تتبع أسعار رفضات الـprefilter مؤجَّل لـPhase 1 (ميزانية API).
"""
import os
import time

# الآفاق الزمنية المطلوبة (ثواني) → أسماء الأعمدة
HORIZONS = [
    (60, "price_1m"),
    (300, "price_5m"),
    (900, "price_15m"),
    (1800, "price_30m"),
    (3600, "price_1h"),
    (14400, "price_4h"),
    (86400, "price_24h"),
]
TRACK_TTL_S = 25 * 3600      # نافذة التتبع: 25 ساعة ثم تُغلق الفرصة
TRACK_CAP = 150              # أقصى فرص مفتوحة تُتبع في كل جولة
STALE_AFTER_S = 2 * 3600     # بلا ملاحظات لأكثر من ساعتين = stale
TRACK_STAGGER_S = 90         # أقل فاصل بين ملاحظتين لنفس الفرصة

# أسباب الرفض المبكر (قبل التحليل) — تُسجَّل كلها، بلا استثناء
REJECT_REASONS = (
    "REJECTED_LIQUIDITY",
    "REJECTED_VOLUME",
    "REJECTED_TXNS",
    "REJECTED_AGE",
    "REJECTED_SYMBOL",
    "REJECTED_NO_PRICE",
    "REJECTED_BLACKLIST",
    "REJECTED_ERROR",
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS scan_opportunities (
    opportunity_id TEXT PRIMARY KEY,
    first_seen_ts DOUBLE,
    last_seen_ts DOUBLE,
    n_seen INTEGER,
    chain TEXT,
    token_address TEXT,
    pair_address TEXT,
    symbol TEXT,
    price DOUBLE,
    liquidity DOUBLE,
    volume_m5 DOUBLE,
    volume_h1 DOUBLE,
    volume_h6 DOUBLE,
    volume_h24 DOUBLE,
    market_cap DOUBLE,
    fdv DOUBLE,
    txns_buys_h24 INTEGER,
    txns_sells_h24 INTEGER,
    pc_m5 DOUBLE,
    pc_h1 DOUBLE,
    pc_h6 DOUBLE,
    pc_h24 DOUBLE,
    age_h DOUBLE,
    boosted INTEGER,
    honeypot INTEGER,
    buy_tax DOUBLE,
    sell_tax DOUBLE,
    sec_risk_level INTEGER,
    top10_holder_pct DOUBLE,
    lp_locked_pct DOUBLE,
    score INTEGER,
    signal TEXT,
    probability INTEGER,
    momentum DOUBLE,
    sentiment DOUBLE,
    cvd DOUBLE,
    obi DOUBLE,
    volatility_z DOUBLE,
    decision TEXT,
    avoid_reason TEXT
);
CREATE TABLE IF NOT EXISTS scan_events (
    scan_ts DOUBLE,
    opportunity_id TEXT,
    decision TEXT,
    signal TEXT,
    score INTEGER,
    probability INTEGER,
    price DOUBLE,
    liquidity DOUBLE,
    volume_h24 DOUBLE,
    pc_h1 DOUBLE,
    pc_h24 DOUBLE,
    age_h DOUBLE,
    n_seen INTEGER
);
CREATE INDEX IF NOT EXISTS idx_events_opp_ts
    ON scan_events (opportunity_id, scan_ts);
CREATE TABLE IF NOT EXISTS price_observations (
    opportunity_id TEXT,
    ts DOUBLE,
    elapsed_s DOUBLE,
    price_usd DOUBLE,
    liq_usd DOUBLE,
    vol_m5_usd DOUBLE,
    source TEXT
);
CREATE INDEX IF NOT EXISTS idx_obs_opp_ts
    ON price_observations (opportunity_id, ts);
CREATE TABLE IF NOT EXISTS opportunity_outcomes (
    opportunity_id TEXT PRIMARY KEY,
    ref_price DOUBLE,
    n_obs INTEGER,
    price_1m DOUBLE,
    price_5m DOUBLE,
    price_15m DOUBLE,
    price_30m DOUBLE,
    price_1h DOUBLE,
    price_4h DOUBLE,
    price_24h DOUBLE,
    max_price_24h DOUBLE,
    min_price_24h DOUBLE,
    mfe_pct DOUBLE,
    mae_pct DOUBLE,
    time_to_peak_s DOUBLE,
    time_to_drawdown_s DOUBLE,
    ret_24h_pct DOUBLE,
    hit_100 INTEGER,
    hit_300 INTEGER,
    hit_900 INTEGER,
    status TEXT,
    updated_ts DOUBLE
);
"""


def default_db_path():
    env = os.environ.get("RESEARCH_DB_PATH")
    if env:
        return env
    home = os.environ.get("HOME") or os.path.expanduser("~")
    return os.path.join(home, "bot", "research.duckdb")


def _f(v, default=None):
    try:
        return float(v) if v is not None else default
    except (TypeError, ValueError):
        return default


def _i(v, default=None):
    try:
        return int(v) if v is not None else default
    except (TypeError, ValueError):
        return default


def _opp_id(chain, pair_address):
    return f"{(chain or '?').lower()}:{(pair_address or '').lower()}"


def _decision_of(res):
    sig = res.get("signal") or "UNKNOWN"
    return ("BUY" if sig in ("BUY", "STRONG_BUY")
            else "AVOID" if sig == "AVOID" else "WATCH")


def _avoid_reason(res):
    """سبب الرفض: أول تحذيرين من فئة ⛔، وإلا كل التحذيرات مختصرة."""
    try:
        warns = res.get("warnings") or []
        hard = [w for w in warns if "⛔" in str(w)]
        pick = (hard or warns)[:2]
        txt = " | ".join(str(w) for w in pick)
        return txt[:300] if txt else None
    except Exception:
        return None


class ResearchStore:
    """واجهة fail-safe فوق DuckDB لبيانات البحث."""

    def __init__(self, path=None):
        self.path = path or default_db_path()
        self._con = None
        self._ok = None

    def _connect(self):
        if self._ok is not None:
            return self._con
        try:
            import duckdb
            d = os.path.dirname(self.path)
            if d:
                os.makedirs(d, exist_ok=True)
            self._con = duckdb.connect(self.path)
            for stmt in _SCHEMA.split(";"):
                stmt = stmt.strip()
                if stmt:
                    self._con.execute(stmt)
            self._ok = True
        except Exception as e:
            print(f"[research] تعطّل المخزن (سيُتخطى بصمت): {e}")
            self._con = None
            self._ok = False
        return self._con

    # ---------- تسجيل الفرص ----------
    def record_opportunity(self, res):
        """يسجل فرصة من نتيجة analyzer.annalyze_pair + البيانات الخام.
        يعيد opportunity_id أو None. لا يرفع أبداً."""
        try:
            con = self._connect()
            if con is None:
                return None
            chain = res.get("chain")
            pair_addr = res.get("pair")
            oid = _opp_id(chain, pair_addr)
            if not pair_addr:
                return None
            now = time.time()
            p = res.get("_pair") or {}
            sec = res.get("_sec") or {}
            m = res.get("metrics") or {}
            liq = (p.get("liquidity") or {}).get("usd")
            vol = p.get("volume") or {}
            tx = (p.get("txns") or {}).get("h24") or {}
            pc = p.get("priceChange") or {}
            base = (p.get("baseToken") or {})
            price = _f(p.get("priceUsd")) or _f(m.get("price"))
            if not (price and price > 0):
                return None
            sig = res.get("signal") or "UNKNOWN"
            decision = _decision_of(res)
            row = {
                "opportunity_id": oid,
                "first_seen_ts": now,
                "last_seen_ts": now,
                "n_seen": 1,
                "chain": chain,
                "token_address": res.get("mint") or base.get("address"),
                "pair_address": pair_addr,
                "symbol": base.get("symbol") or res.get("display"),
                "price": price,
                "liquidity": _f(liq),
                "volume_m5": _f(vol.get("m5")),
                "volume_h1": _f(vol.get("h1")),
                "volume_h6": _f(vol.get("h6")),
                "volume_h24": _f(vol.get("h24")) or _f(m.get("vol24")),
                "market_cap": _f(p.get("marketCap")),
                "fdv": _f(p.get("fdv")) or _f(m.get("fdv")),
                "txns_buys_h24": _i(tx.get("buys")),
                "txns_sells_h24": _i(tx.get("sells")),
                "pc_m5": _f(pc.get("m5")),
                "pc_h1": _f(pc.get("h1")) or _f(m.get("pc1h")),
                "pc_h6": _f(pc.get("h6")),
                "pc_h24": _f(pc.get("h24")) or _f(m.get("pc24h")),
                "age_h": _f(m.get("age_h")),
                "boosted": 1 if res.get("boosted") else 0,
                "honeypot": 1 if sec.get("is_honeypot") else 0,
                "buy_tax": _f(sec.get("buy_tax")),
                "sell_tax": _f(sec.get("sell_tax")),
                "sec_risk_level": _i(sec.get("risk_level")),
                "top10_holder_pct": _f(m.get("holders_top10")),
                "lp_locked_pct": _f(sec.get("lp_locked")),
                "score": _i(res.get("score")),
                "signal": sig,
                "probability": _i(res.get("_verdict_prob")),
                "momentum": _f(res.get("_momentum")),
                "sentiment": _f(res.get("_verdict_sent")),
                "cvd": _f(res.get("_flow_cvd")),
                "obi": _f(res.get("_flow_obi")),
                "volatility_z": _f(res.get("_flow_z")),
                "decision": decision,
                "avoid_reason": _avoid_reason(res),
            }
            exists = con.execute(
                "SELECT first_seen_ts, n_seen FROM scan_opportunities "
                "WHERE opportunity_id = ?", [oid]).fetchone()
            if exists:
                # ظهور متكرر: نحدّث آخر مشاهدة والعداد والقيم اللحظية فقط —
                # first_seen_ts والسعر المرجعي لا يتغيران أبداً.
                con.execute(
                    """UPDATE scan_opportunities SET last_seen_ts = ?,
                       n_seen = n_seen + 1, price = ?, liquidity = ?,
                       volume_m5 = ?, volume_h1 = ?, volume_h24 = ?,
                       score = ?, signal = ?, decision = ?,
                       avoid_reason = ?
                       WHERE opportunity_id = ?""",
                    [now, row["price"], row["liquidity"], row["volume_m5"],
                     row["volume_h1"], row["volume_h24"], row["score"],
                     row["signal"], row["decision"], row["avoid_reason"],
                     oid])
            else:
                cols = ", ".join(row.keys())
                ph = ", ".join(["?"] * len(row))
                con.execute(
                    f"INSERT INTO scan_opportunities ({cols}) VALUES ({ph})",
                    list(row.values()))
                # الملاحظة الصفرية: السعر المرجعي من بيانات الفحص نفسها —
                # بلا أي طلب API إضافي.
                self.record_observation(oid, now, 0.0, price,
                                        row["liquidity"], row["volume_m5"],
                                        source="scan")
                self._upsert_outcome(oid, price)
            return oid
        except Exception as e:
            print(f"[research] record_opportunity skipped: {e}")
            return None

    def record_prefilter_reject(self, p, reason):
        """يسجل عملة رُفضت قبل التحليل (عتبات مبكرة/رمز/قائمة سوداء...).
        صف واحد لكل زوج: التكرار يحدّث n_seen/last_seen فقط.
        لا يمس قرار فرصة مقيَّمة سابقاً (التقييم أبقى من الرفض).
        لا تُفتح لها ملاحظات سعرية ولا نتيجة — تسجيل فقط (قرار Phase 1:
        ميزانية الـAPI للمقيَّمة). لا يرفع أبداً."""
        try:
            con = self._connect()
            if con is None or not isinstance(p, dict):
                return None
            if reason not in REJECT_REASONS:
                reason = "REJECTED_ERROR"
            chain = p.get("chainId")
            pair_addr = p.get("pairAddress")
            if not pair_addr:
                return None
            oid = _opp_id(chain, pair_addr)
            now = time.time()
            base = p.get("baseToken") or {}
            price = _f(p.get("priceUsd"))  # قد يكون NULL — صدق البيانات
            liq = _f((p.get("liquidity") or {}).get("usd"))
            vol24 = _f((p.get("volume") or {}).get("h24"))
            age_h = None
            try:
                created = p.get("pairCreatedAt") or 0
                if created:
                    age_h = round((now * 1000 - created) / 3600000, 2)
            except Exception:
                pass
            exists = con.execute(
                "SELECT n_seen, signal FROM scan_opportunities "
                "WHERE opportunity_id = ?", [oid]).fetchone()
            if exists:
                _n_seen, sig = exists
                if sig == "PREFILTER":
                    con.execute(
                        """UPDATE scan_opportunities SET last_seen_ts = ?,
                           n_seen = n_seen + 1, price = ?, liquidity = ?,
                           volume_h24 = ?, age_h = ?, decision = ?,
                           avoid_reason = ?
                           WHERE opportunity_id = ?""",
                        [now, price, liq, vol24, age_h, reason, reason, oid])
                else:
                    # مقيَّمة سابقاً: نحدّث المشاهدة فقط — القرار يبقى.
                    con.execute(
                        """UPDATE scan_opportunities SET last_seen_ts = ?,
                           n_seen = n_seen + 1
                           WHERE opportunity_id = ?""",
                        [now, oid])
            else:
                con.execute(
                    """INSERT INTO scan_opportunities
                       (opportunity_id, first_seen_ts, last_seen_ts, n_seen,
                        chain, token_address, pair_address, symbol, price,
                        liquidity, volume_h24, age_h, signal, decision,
                        avoid_reason)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    [oid, now, now, 1, chain, base.get("address"), pair_addr,
                     base.get("symbol"), price, liq, vol24, age_h,
                     "PREFILTER", reason, reason])
            return oid
        except Exception as e:
            print(f"[research] record_prefilter_reject skipped: {e}")
            return None

    def record_scan_event(self, res, scan_ts):
        """لقطة ثابتة لفرصة مقيَّمة في فحص واحد — تُدرَج ولا تُحدَّث أبداً.
        وقود الـreplay في Phase 2. لا يرفع أبداً."""
        try:
            con = self._connect()
            if con is None:
                return False
            chain = res.get("chain")
            pair_addr = res.get("pair")
            oid = _opp_id(chain, pair_addr)
            if not pair_addr:
                return False
            p = res.get("_pair") or {}
            m = res.get("metrics") or {}
            pc = p.get("priceChange") or {}
            n_seen = con.execute(
                "SELECT n_seen FROM scan_opportunities "
                "WHERE opportunity_id = ?", [oid]).fetchone()
            con.execute(
                "INSERT INTO scan_events VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                [float(scan_ts), oid, _decision_of(res),
                 res.get("signal"), _i(res.get("score")),
                 _i(res.get("_verdict_prob")),
                 _f(p.get("priceUsd")) or _f(m.get("price")),
                 _f((p.get("liquidity") or {}).get("usd")),
                 _f((p.get("volume") or {}).get("h24")) or _f(m.get("vol24")),
                 _f(pc.get("h1")) or _f(m.get("pc1h")),
                 _f(pc.get("h24")) or _f(m.get("pc24h")),
                 _f(m.get("age_h")),
                 n_seen[0] if n_seen else 1])
            return True
        except Exception as e:
            print(f"[research] record_scan_event skipped: {e}")
            return False

    # ---------- الملاحظات السعرية ----------
    def record_observation(self, opportunity_id, ts, elapsed_s, price_usd,
                           liq_usd=None, vol_m5_usd=None, source="track"):
        try:
            con = self._connect()
            if con is None or not price_usd or price_usd <= 0:
                return False
            con.execute(
                "INSERT INTO price_observations VALUES (?,?,?,?,?,?,?)",
                [opportunity_id, ts, elapsed_s, float(price_usd),
                 _f(liq_usd), _f(vol_m5_usd), source])
            return True
        except Exception as e:
            print(f"[research] record_observation skipped: {e}")
            return False

    def open_opportunities(self, limit=TRACK_CAP):
        """الفرص المفتوحة للتتبع — جدولة عادلة: الأقدم بلا ملاحظة أولاً
        (لا تجويع للقديمة عند تجاوز السقف)، مع فاصل TRACK_STAGGER_S بين
        الملاحظات لتوزيع حمل الـAPI. تُستبعد رفضات الـprefilter."""
        try:
            con = self._connect()
            if con is None:
                return []
            now = time.time()
            cutoff = now - TRACK_TTL_S
            due = now - TRACK_STAGGER_S
            rows = con.execute(
                """SELECT o.opportunity_id, o.chain, o.pair_address,
                          o.first_seen_ts, MAX(po.ts) AS last_obs
                   FROM scan_opportunities o
                   LEFT JOIN opportunity_outcomes oc
                     ON o.opportunity_id = oc.opportunity_id
                   LEFT JOIN price_observations po
                     ON o.opportunity_id = po.opportunity_id
                   WHERE o.first_seen_ts >= ?
                     AND o.signal != 'PREFILTER'
                     AND (oc.status IS NULL OR oc.status = 'tracking')
                   GROUP BY o.opportunity_id, o.chain, o.pair_address,
                            o.first_seen_ts
                   HAVING MAX(po.ts) IS NULL OR MAX(po.ts) < ?
                   ORDER BY last_obs ASC NULLS FIRST
                   LIMIT ?""",
                [cutoff, due, int(limit)]).fetchall()
            return [{"opportunity_id": r[0], "chain": r[1],
                     "pair": r[2], "first_seen_ts": r[3]} for r in rows]
        except Exception as e:
            print(f"[research] open_opportunities skipped: {e}")
            return []

    def observations(self, opportunity_id):
        try:
            con = self._connect()
            if con is None:
                return []
            rows = con.execute(
                "SELECT ts, elapsed_s, price_usd FROM price_observations "
                "WHERE opportunity_id = ? ORDER BY ts ASC",
                [opportunity_id]).fetchall()
            return [{"ts": r[0], "elapsed_s": r[1], "price": r[2]}
                    for r in rows]
        except Exception:
            return []

    # ---------- حساب النتائج ----------
    @staticmethod
    def compute_outcome(ref_price, obs, force_close=False):
        """يحسب ملخص الفرصة من الملاحظات. خالص وقابل للاختبار.
        force_close: إغلاق قسري عند انتهاء نافذة 25h — ما لدينا هو
        كل ما سنحصل عليه."""
        out = {"ref_price": ref_price, "n_obs": len(obs),
               "status": "tracking"}
        for _, col in HORIZONS:
            out[col] = None
        out.update({"max_price_24h": None, "min_price_24h": None,
                    "mfe_pct": None, "mae_pct": None,
                    "time_to_peak_s": None, "time_to_drawdown_s": None,
                    "ret_24h_pct": None,
                    "hit_100": 0, "hit_300": 0, "hit_900": 0})
        if not ref_price or ref_price <= 0 or not obs:
            if force_close:
                out["status"] = "stale"
            return out
        pts = [(o["elapsed_s"], o["price"]) for o in obs
               if o.get("price") and o["price"] > 0]
        if not pts:
            if force_close:
                out["status"] = "stale"
            return out
        pts.sort()
        # أقرب ملاحظة لكل أفق (بتسامح ±50% من الأفق)
        for h_s, col in HORIZONS:
            best = min(pts, key=lambda t: abs(t[0] - h_s))
            if abs(best[0] - h_s) <= h_s * 0.5:
                out[col] = best[1]
        # القمم والقيعان الحقيقية من كل الملاحظات (MFE/MAE حقيقيان —
        # يلتقطان ما حدث بين نقاط القياس لا عندها فقط)
        peak = max(pts, key=lambda t: t[1])
        trough = min(pts, key=lambda t: t[1])
        out["max_price_24h"] = peak[1]
        out["min_price_24h"] = trough[1]
        out["mfe_pct"] = round((peak[1] / ref_price - 1) * 100, 2)
        out["mae_pct"] = round((trough[1] / ref_price - 1) * 100, 2)
        out["time_to_peak_s"] = peak[0]
        out["time_to_drawdown_s"] = trough[0]
        if out["price_24h"]:
            out["ret_24h_pct"] = round(
                (out["price_24h"] / ref_price - 1) * 100, 2)
        out["hit_100"] = 1 if peak[1] >= ref_price * 2 else 0
        out["hit_300"] = 1 if peak[1] >= ref_price * 4 else 0
        out["hit_900"] = 1 if peak[1] >= ref_price * 10 else 0
        max_elapsed = pts[-1][0]
        if max_elapsed >= TRACK_TTL_S:
            out["status"] = "complete"
        elif max_elapsed >= STALE_AFTER_S and \
                (time.time() - obs[-1]["ts"]) >= STALE_AFTER_S:
            out["status"] = "stale"
        if force_close and out["status"] == "tracking":
            out["status"] = "complete" if out["n_obs"] > 1 else "stale"
        return out

    def _upsert_outcome(self, opportunity_id, ref_price=None,
                        force_close=False):
        try:
            con = self._connect()
            if con is None:
                return
            if ref_price is None:
                r = con.execute(
                    "SELECT price FROM scan_opportunities "
                    "WHERE opportunity_id = ?", [opportunity_id]).fetchone()
                ref_price = r[0] if r else None
            obs = self.observations(opportunity_id)
            out = self.compute_outcome(ref_price, obs,
                                       force_close=force_close)
            out["opportunity_id"] = opportunity_id
            out["updated_ts"] = time.time()
            cols = ["opportunity_id", "ref_price", "n_obs"] + \
                   [c for _, c in HORIZONS] + \
                   ["max_price_24h", "min_price_24h", "mfe_pct", "mae_pct",
                    "time_to_peak_s", "time_to_drawdown_s", "ret_24h_pct",
                    "hit_100", "hit_300", "hit_900", "status", "updated_ts"]
            ph = ", ".join(["?"] * len(cols))
            # DuckDB يدعم ON CONFLICT
            con.execute(
                f"INSERT INTO opportunity_outcomes ({', '.join(cols)}) "
                f"VALUES ({ph}) ON CONFLICT (opportunity_id) DO UPDATE SET "
                + ", ".join(f"{c} = excluded.{c}" for c in cols
                            if c != "opportunity_id"),
                [out.get(c) for c in cols])
        except Exception as e:
            print(f"[research] _upsert_outcome skipped: {e}")

    def refresh_outcome(self, opportunity_id):
        """يعيد حساب ملخص فرصة بعد دفعة ملاحظات جديدة."""
        try:
            self._upsert_outcome(opportunity_id)
        except Exception as e:
            print(f"[research] refresh_outcome skipped: {e}")

    def finalize_due(self):
        """إغلاق الفرص التي تجاوزت نافذة 25h — حساب نهائي من الملاحظات
        الموجودة حتى لو لم تصل ملاحظة عند 24h بالضبط. لا يرفع أبداً."""
        try:
            con = self._connect()
            if con is None:
                return 0
            cutoff = time.time() - TRACK_TTL_S
            rows = con.execute(
                """SELECT o.opportunity_id FROM scan_opportunities o
                   LEFT JOIN opportunity_outcomes oc
                     ON o.opportunity_id = oc.opportunity_id
                   WHERE o.first_seen_ts < ?
                     AND o.signal != 'PREFILTER'
                     AND (oc.status IS NULL OR oc.status = 'tracking')""",
                [cutoff]).fetchall()
            n = 0
            for (oid,) in rows:
                try:
                    self._upsert_outcome(oid, force_close=True)
                    n += 1
                except Exception:
                    continue
            return n
        except Exception as e:
            print(f"[research] finalize_due skipped: {e}")
            return 0

    # ---------- إحصاءات ----------
    def counts(self):
        try:
            con = self._connect()
            if con is None:
                return {}
            n_opp = con.execute(
                "SELECT COUNT(*) FROM scan_opportunities").fetchone()[0]
            n_ev = con.execute(
                "SELECT COUNT(*) FROM scan_events").fetchone()[0]
            n_obs = con.execute(
                "SELECT COUNT(*) FROM price_observations").fetchone()[0]
            n_out = con.execute(
                "SELECT COUNT(*) FROM opportunity_outcomes").fetchone()[0]
            return {"opportunities": n_opp, "scan_events": n_ev,
                    "observations": n_obs, "outcomes": n_out}
        except Exception:
            return {}

    def close(self):
        try:
            if self._con is not None:
                self._con.close()
        except Exception:
            pass
        self._con = None
        self._ok = None


# ---------- نقطة الدخول من الـscanner ----------
_store = None


def _get_store():
    global _store
    if _store is None:
        _store = ResearchStore()
    return _store


# مخزن مؤقت لرفضات الـprefilter — تُصرَّف دفعة واحدة في run_collection
# (حلقة التصفية حرجة زمنياً: لا I/O فيها إطلاقاً).
_prefilter_buffer = []
_PREFILTER_BUF_CAP = 5000


def note_prefilter_reject(p, reason):
    """تخزين مؤقت لرفض مبكر — يُصرَّف في run_collection. fail-safe."""
    try:
        if len(_prefilter_buffer) >= _PREFILTER_BUF_CAP:
            del _prefilter_buffer[:1000]
        _prefilter_buffer.append((p, reason))
    except Exception:
        pass


def _drain_prefilter_rejects(rs):
    items = _prefilter_buffer[:]
    del _prefilter_buffer[:]
    n = 0
    for p, reason in items:
        try:
            if rs.record_prefilter_reject(p, reason):
                n += 1
        except Exception:
            continue
    return n


def note_reevaluation(res):
    """إعادة تقييم من لائحة الانتظار — تحديث مباشر fail-safe
    (n_seen + لقطة فحص)، تُستدعى من check_waitlist بعد run_collection."""
    try:
        rs = _get_store()
        if rs.record_opportunity(res):
            rs.record_scan_event(res, time.time())
    except Exception as e:
        print("research.note_reevaluation skipped:", e)


def run_collection(results, price_fetcher=None):
    """تسجيل الفرص + لقطات الفحص + تتبع الأسعار + إغلاق المنتهية.
    تُستدعى من _scan بعد scan_new_coins.
    price_fetcher: دالة (chain, pair) → dict بيانات الزوج (للحقن في
    الاختبارات). لا ترفع أبداً."""
    try:
        rs = _get_store()
        scan_ts = time.time()
        n_rej = _drain_prefilter_rejects(rs)
        n_new = 0
        n_ev = 0
        for res in (results or []):
            try:
                if rs.record_opportunity(res):
                    n_new += 1
                    if rs.record_scan_event(res, scan_ts):
                        n_ev += 1
            except Exception:
                continue
        n_obs = _track_open(rs, price_fetcher)
        n_fin = rs.finalize_due()
        if n_new or n_obs or n_rej or n_fin:
            print(f"  -> بحث: {n_new} فرصة، {n_rej} رفض مبكر، "
                  f"{n_ev} لقطة فحص، {n_obs} ملاحظة سعرية، "
                  f"{n_fin} إغلاق نهائي")
    except Exception as e:
        print("research.run_collection skipped:", e)


def _track_open(rs, price_fetcher=None):
    """يجلب أسعار الفرص المفتوحة ويسجل ملاحظات. لا يرفع أبداً."""
    try:
        opps = rs.open_opportunities()
        if not opps:
            return 0
        if price_fetcher is None:
            import clients
            pmap = clients.pmap
            fetcher = lambda o: clients.get_pair(o["chain"], o["pair"])
        else:
            pmap = lambda fn, items, max_workers=8: [fn(x) for x in items]
            fetcher = price_fetcher

        def _one(o):
            try:
                d = fetcher(o)
                price = _f((d or {}).get("priceUsd"))
                if not (price and price > 0):
                    return None
                liq = _f(((d or {}).get("liquidity") or {}).get("usd"))
                vol_m5 = _f(((d or {}).get("volume") or {}).get("m5"))
                return (o, price, liq, vol_m5)
            except Exception:
                return None

        fetched = pmap(_one, opps, max_workers=8)
        now = time.time()
        n = 0
        for item in fetched:
            if not item:
                continue
            o, price, liq, vol_m5 = item
            elapsed = now - (o.get("first_seen_ts") or now)
            if rs.record_observation(o["opportunity_id"], now, elapsed,
                                     price, liq, vol_m5, source="track"):
                n += 1
            rs.refresh_outcome(o["opportunity_id"])
        return n
    except Exception as e:
        print("research._track_open skipped:", e)
        return 0
