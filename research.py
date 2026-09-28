# -*- coding: utf-8 -*-
"""طبقة جمع بيانات البحث — Full Opportunity Dataset (Phase 1).

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
- scan_opportunities: كل فرصة + features وقت أول مشاهدة.
- price_observations: سلسلة سعرية لكل فرصة (كل ~دقيقتين عبر الـscan).
- opportunity_outcomes: ملخص محسوب (MFE/MAE، الأسعار عند الآفاق،
  hit_100/300/900) — يُعاد حسابه مع كل دفعة ملاحظات.

ملاحظة صدق: CVD/OBI/volatility_z من محرك flow.py تغطي رموز Binance
فقط، بينما الـscanner يقيّم أزواج DEX — لذلك ستكون هذه الأعمدة NULL
في الغالب. الأعمدة موجودة للتوافق المستقبلي، وعدم الاستعلام عنها
في مسار الفحص قرار متعمد (تجنب إبطاء الـscan).
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
            decision = ("BUY" if sig in ("BUY", "STRONG_BUY")
                        else "AVOID" if sig == "AVOID" else "WATCH")
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
        """الفرص المفتوحة للتتبع: عمرها < 25h وحالتها tracking."""
        try:
            con = self._connect()
            if con is None:
                return []
            cutoff = time.time() - TRACK_TTL_S
            rows = con.execute(
                """SELECT o.opportunity_id, o.chain, o.pair_address,
                          o.first_seen_ts
                   FROM scan_opportunities o
                   LEFT JOIN opportunity_outcomes oc
                     ON o.opportunity_id = oc.opportunity_id
                   WHERE o.first_seen_ts >= ?
                     AND (oc.status IS NULL OR oc.status = 'tracking')
                   ORDER BY o.first_seen_ts DESC
                   LIMIT ?""",
                [cutoff, int(limit)]).fetchall()
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
    def compute_outcome(ref_price, obs):
        """يحسب ملخص الفرصة من الملاحظات. خالص وقابل للاختبار."""
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
            return out
        pts = [(o["elapsed_s"], o["price"]) for o in obs
               if o.get("price") and o["price"] > 0]
        if not pts:
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
        return out

    def _upsert_outcome(self, opportunity_id, ref_price=None):
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
            out = self.compute_outcome(ref_price, obs)
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

    # ---------- إحصاءات ----------
    def counts(self):
        try:
            con = self._connect()
            if con is None:
                return {}
            n_opp = con.execute(
                "SELECT COUNT(*) FROM scan_opportunities").fetchone()[0]
            n_obs = con.execute(
                "SELECT COUNT(*) FROM price_observations").fetchone()[0]
            n_out = con.execute(
                "SELECT COUNT(*) FROM opportunity_outcomes").fetchone()[0]
            return {"opportunities": n_opp, "observations": n_obs,
                    "outcomes": n_out}
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


def run_collection(results, price_fetcher=None):
    """تسجيل الفرص + تتبع الأسعار. تُستدعى من _scan بعد scan_new_coins.
    price_fetcher: دالة (chain, pair) → dict بيانات الزوج (للحقن في
    الاختبارات). لا ترفع أبداً."""
    try:
        rs = _get_store()
        n_new = 0
        for res in (results or []):
            try:
                if rs.record_opportunity(res):
                    n_new += 1
            except Exception:
                continue
        n_obs = _track_open(rs, price_fetcher)
        if n_new or n_obs:
            print(f"  -> بحث: {n_new} فرصة مسجلة، {n_obs} ملاحظة سعرية")
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
