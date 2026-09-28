# -*- coding: utf-8 -*-
"""اختبارات طبقة جمع بيانات البحث (research.py) — بلا شبكة."""
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import research
from research import ResearchStore


def _make_res(signal="AVOID", score=42, price=0.001):
    pair = {
        "chainId": "solana",
        "pairAddress": "PAIRADDR123",
        "baseToken": {"symbol": "TEST", "address": "MINTADDR123"},
        "priceUsd": str(price),
        "liquidity": {"usd": 75000},
        "volume": {"m5": 1200, "h1": 8000, "h6": 30000, "h24": 150000},
        "txns": {"h24": {"buys": 400, "sells": 350}},
        "priceChange": {"m5": 2.0, "h1": 12.0, "h6": 25.0, "h24": 60.0},
        "marketCap": 500000,
        "fdv": 900000,
        "url": "https://dexscreener.com/solana/PAIRADDR123",
    }
    sec = {"is_honeypot": False, "buy_tax": 0, "sell_tax": 0,
           "risk_level": 2, "lp_locked": 95}
    return {
        "score": score, "signal": signal,
        "reasons": [], "warnings": ["⛔ سيولة مركزة"],
        "display": "TEST/SOL", "chain": "solana", "pair": "PAIRADDR123",
        "mint": "MINTADDR123",
        "metrics": {"price": price, "liq": 75000, "vol24": 150000,
                    "fdv": 900000, "pc1h": 12.0, "pc24h": 60.0,
                    "buys": 400, "sells": 350, "age_h": 5.0,
                    "holders_top10": 12.5},
        "_pair": pair, "_sec": sec,
        "_verdict_prob": 64 if signal in ("BUY", "STRONG_BUY") else None,
    }


def _store():
    fd, path = tempfile.mkstemp(suffix=".duckdb")
    os.close(fd)
    os.unlink(path)
    return ResearchStore(path=path), path


def test_schema_and_record():
    rs, path = _store()
    oid = rs.record_opportunity(_make_res())
    assert oid == "solana:pairaddr123", oid
    c = rs.counts()
    assert c["opportunities"] == 1, c
    assert c["observations"] == 1, c  # الملاحظة الصفرية
    assert c["outcomes"] == 1, c
    rs.close()


def test_dedup_keeps_first_seen():
    rs, path = _store()
    r1 = _make_res(price=0.001)
    oid1 = rs.record_opportunity(r1)
    ts1 = rs._connect().execute(
        "SELECT first_seen_ts FROM scan_opportunities WHERE opportunity_id=?",
        [oid1]).fetchone()[0]
    time.sleep(0.05)
    r2 = _make_res(price=0.002, score=50)  # نفس العملة بسعر جديد
    oid2 = rs.record_opportunity(r2)
    assert oid1 == oid2
    row = rs._connect().execute(
        "SELECT first_seen_ts, n_seen, price FROM scan_opportunities "
        "WHERE opportunity_id=?", [oid1]).fetchone()
    assert row[0] == ts1, "first_seen_ts يجب ألا يتغير"
    assert row[1] == 2, "n_seen يجب أن يزيد"
    assert abs(row[2] - 0.002) < 1e-9, "السعر اللحظي يتحدث"
    assert rs.counts()["opportunities"] == 1
    rs.close()


def test_outcome_math():
    # مسار سعري اصطناعي: 1.0 → 1.5 (د5) → 0.7 (د15) → 2.5 (د60) → 1.1 (د24س)
    ref = 1.0
    now = time.time()
    t0 = now - 86400
    obs = [
        {"ts": t0, "elapsed_s": 0, "price": 1.0},
        {"ts": t0 + 300, "elapsed_s": 300, "price": 1.5},
        {"ts": t0 + 900, "elapsed_s": 900, "price": 0.7},
        {"ts": t0 + 3600, "elapsed_s": 3600, "price": 2.5},
        {"ts": now, "elapsed_s": 86400, "price": 1.1},
    ]
    out = ResearchStore.compute_outcome(ref, obs)
    assert out["price_5m"] == 1.5, out
    assert out["price_15m"] == 0.7, out
    assert out["price_1h"] == 2.5, out
    assert out["price_24h"] == 1.1, out
    assert out["mfe_pct"] == 150.0, out  # (2.5/1-1)*100
    assert out["mae_pct"] == -30.0, out  # (0.7/1-1)*100
    assert out["time_to_peak_s"] == 3600, out
    assert out["time_to_drawdown_s"] == 900, out
    assert out["hit_100"] == 1, out  # وصل 2.5x
    assert out["hit_300"] == 0, out
    assert out["hit_900"] == 0, out
    assert out["ret_24h_pct"] == 10.0, out
    assert out["status"] == "tracking", out  # 86400s = 24h < 25h


def test_horizon_tolerance():
    # |200-300| = 100 <= 150 (تسامح 50%) → تُقبل
    ref = 1.0
    obs = [{"ts": 0, "elapsed_s": 0, "price": 1.0},
           {"ts": 200, "elapsed_s": 200, "price": 9.9}]
    out = ResearchStore.compute_outcome(ref, obs)
    assert out["price_5m"] == 9.9, out
    # |1000-300| = 700 > 150 → تُرفض
    obs2 = [{"ts": 0, "elapsed_s": 0, "price": 1.0},
            {"ts": 1000, "elapsed_s": 1000, "price": 9.9}]
    out2 = ResearchStore.compute_outcome(ref, obs2)
    assert out2["price_5m"] is None, out2


def test_run_collection_with_fake_fetcher():
    rs, path = _store()
    research._store = rs  # حقن المخزن المؤقت
    try:
        res = _make_res(signal="BUY", score=75)
        calls = {"n": 0}

        def fake_fetch(o):
            calls["n"] += 1
            return {"priceUsd": "0.0011",
                    "liquidity": {"usd": 76000},
                    "volume": {"m5": 1300}}

        research.run_collection([res], price_fetcher=fake_fetch)
        c = rs.counts()
        assert c["opportunities"] == 1, c
        assert c["observations"] >= 2, c  # صفرية + تتبع
        assert calls["n"] == 1
        # تحقق من حقول القرار
        row = rs._connect().execute(
            "SELECT decision, score, probability, avoid_reason "
            "FROM scan_opportunities").fetchone()
        assert row[0] == "BUY", row
        assert row[1] == 75, row
        assert row[2] == 64, row
    finally:
        research._store = None
        rs.close()


def test_fail_safe_on_garbage():
    rs, path = _store()
    assert rs.record_opportunity({}) is None
    assert rs.record_opportunity(None) is None
    assert rs.record_opportunity({"chain": "solana"}) is None  # بلا pair
    assert rs.record_observation("x", time.time(), 0, -5) is False
    assert rs.record_observation("x", time.time(), 0, None) is False
    out = ResearchStore.compute_outcome(0, [])
    assert out["status"] == "tracking"
    out2 = ResearchStore.compute_outcome(1.0, [])
    assert out2["n_obs"] == 0
    rs.close()


def test_avoid_reason_extraction():
    rs, path = _store()
    r = _make_res(signal="AVOID")
    r["warnings"] = ["تحذير عادي", "⛔ نصب مؤكد", "⛔ ضريبة فخ"]
    oid = rs.record_opportunity(r)
    reason = rs._connect().execute(
        "SELECT avoid_reason FROM scan_opportunities "
        "WHERE opportunity_id=?", [oid]).fetchone()[0]
    assert "نصب مؤكد" in reason and "تحذير عادي" not in reason, reason
    rs.close()


if __name__ == "__main__":
    test_schema_and_record()
    test_dedup_keeps_first_seen()
    test_outcome_math()
    test_horizon_tolerance()
    test_run_collection_with_fake_fetcher()
    test_fail_safe_on_garbage()
    test_avoid_reason_extraction()
    print("كل اختبارات research نجحت ✓")
