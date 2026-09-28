# -*- coding: utf-8 -*-
"""اختبارات طبقة جمع بيانات البحث (research.py) — v2 corrective."""
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import research
from research import ResearchStore, REJECT_REASONS

def _tmp_store(tmp_path):
    return ResearchStore(path=str(tmp_path / "t.duckdb"))

def _pair(symbol="TST", price=0.001, liq=5000.0, vol24=20000.0,
          created_h_ago=2.0):
    now_ms = time.time() * 1000
    return {
        "chainId": "solana",
        "pairAddress": f"pair_{symbol}_{int(now_ms)}",
        "baseToken": {"symbol": symbol, "address": f"mint_{symbol}"},
        "priceUsd": str(price),
        "liquidity": {"usd": liq},
        "volume": {"m5": 100.0, "h1": 500.0, "h6": 2000.0, "h24": vol24},
        "txns": {"h24": {"buys": 50, "sells": 30}},
        "priceChange": {"m5": 1.0, "h1": 5.0, "h6": 10.0, "h24": 25.0},
        "pairCreatedAt": now_ms - created_h_ago * 3600000,
        "marketCap": 100000.0,
        "fdv": 1000000.0,
    }

def _res(symbol="TST", signal="BUY", score=75, price=0.001):
    p = _pair(symbol, price)
    return {
        "signal": signal, "score": score, "chain": "solana",
        "pair": p["pairAddress"], "mint": p["baseToken"]["address"],
        "display": f"{symbol}/SOL", "boosted": False,
        "_verdict_prob": 64, "_momentum": 1.5, "_verdict_sent": 0.2,
        "_flow_cvd": None, "_flow_obi": None, "_flow_z": None,
        "_pair": p, "_sec": {}, "metrics": {}, "warnings": [],
    }

def test_record_opportunity_basic(tmp_path):
    rs = _tmp_store(tmp_path)
    oid = rs.record_opportunity(_res("AAA"))
    assert oid and oid.startswith("solana:pair_aaa")
    c = rs.counts()
    assert c["opportunities"] == 1
    assert c["observations"] == 1  # الملاحظة الصفرية
    assert c["outcomes"] == 1
    rs.close()

def test_record_opportunity_dedup(tmp_path):
    rs = _tmp_store(tmp_path)
    r = _res("BBB")
    rs.record_opportunity(r)
    rs.record_opportunity(r)
    rs.record_opportunity(r)
    c = rs.counts()
    assert c["opportunities"] == 1
    row = rs._connect().execute(
        "SELECT n_seen, first_seen_ts, last_seen_ts FROM scan_opportunities"
    ).fetchone()
    assert row[0] == 3
    rs.close()

def test_prefilter_reject_recorded(tmp_path):
    rs = _tmp_store(tmp_path)
    for reason in REJECT_REASONS:
        p = _pair(f"R{abs(hash(reason)) % 9999}", price=0.01)
        oid = rs.record_prefilter_reject(p, reason)
        assert oid, reason
    rows = rs._connect().execute(
        "SELECT decision, signal FROM scan_opportunities").fetchall()
    assert len(rows) == len(REJECT_REASONS)
    decisions = {r[0] for r in rows}
    assert decisions == set(REJECT_REASONS)
    assert {r[1] for r in rows} == {"PREFILTER"}
    # صدق الـNULL: بلا score/probability
    nulls = rs._connect().execute(
        "SELECT COUNT(*) FROM scan_opportunities "
        "WHERE score IS NULL AND probability IS NULL").fetchone()[0]
    assert nulls == len(REJECT_REASONS)
    rs.close()

def test_prefilter_reject_dedup(tmp_path):
    rs = _tmp_store(tmp_path)
    p = _pair("DUP", price=0.02)
    rs.record_prefilter_reject(p, "REJECTED_LIQUIDITY")
    rs.record_prefilter_reject(p, "REJECTED_LIQUIDITY")
    n = rs._connect().execute(
        "SELECT n_seen FROM scan_opportunities").fetchone()[0]
    assert n == 2
    assert rs.counts()["opportunities"] == 1
    rs.close()

def test_evaluated_decision_protected_from_reject(tmp_path):
    """رفض مبكر لاحق لا يمحو قرار تقييم سابق."""
    rs = _tmp_store(tmp_path)
    r = _res("PROT", signal="BUY", score=80)
    rs.record_opportunity(r)
    # نفس الزوج يُرفض لاحقاً في الـprefilter
    rs.record_prefilter_reject(r["_pair"], "REJECTED_LIQUIDITY")
    row = rs._connect().execute(
        "SELECT decision, signal, score FROM scan_opportunities").fetchone()
    assert row[0] == "BUY" and row[1] == "BUY" and row[2] == 80
    n = rs._connect().execute(
        "SELECT n_seen FROM scan_opportunities").fetchone()[0]
    assert n == 2
    rs.close()

def test_scan_events_immutable(tmp_path):
    rs = _tmp_store(tmp_path)
    r = _res("EVT", signal="WATCH", score=55)
    rs.record_opportunity(r)
    assert rs.record_scan_event(r, time.time())
    r2 = dict(r)
    r2["score"] = 90
    r2["signal"] = "STRONG_BUY"
    assert rs.record_scan_event(r2, time.time() + 60)
    rows = rs._connect().execute(
        "SELECT score, signal FROM scan_events ORDER BY scan_ts").fetchall()
    assert rows == [(55, "WATCH"), (90, "STRONG_BUY")]
    assert rs.counts()["scan_events"] == 2
    rs.close()

def test_record_observation_and_outcome(tmp_path):
    rs = _tmp_store(tmp_path)
    r = _res("OBS", price=1.0)
    oid = rs.record_opportunity(r)
    now = time.time()
    # ملاحظات متدرجة: صعود ثم هبوط
    rs.record_observation(oid, now + 60, 60, 1.5)     # +50%
    rs.record_observation(oid, now + 3600, 3600, 3.0)  # +200% → hit_100
    rs.record_observation(oid, now + 7200, 7200, 0.5)  # -50%
    rs.refresh_outcome(oid)
    out = rs._connect().execute(
        "SELECT mfe_pct, mae_pct, hit_100, hit_300, hit_900, n_obs,"
        " max_price_24h, min_price_24h FROM opportunity_outcomes"
    ).fetchone()
    assert out[0] == 200.0   # MFE من القمة الحقيقية
    assert out[1] == -50.0   # MAE من القاع الحقيقي
    assert out[2] == 1 and out[3] == 0 and out[4] == 0
    assert out[5] == 4  # 3 + الملاحظة الصفرية
    assert out[6] == 3.0 and out[7] == 0.5
    rs.close()

def test_horizon_capture(tmp_path):
    rs = _tmp_store(tmp_path)
    r = _res("HOR", price=1.0)
    oid = rs.record_opportunity(r)
    now = time.time()
    rs.record_observation(oid, now + 58, 58, 1.1)
    rs.record_observation(oid, now + 310, 310, 1.2)
    rs.record_observation(oid, now + 3590, 3590, 2.0)
    rs.refresh_outcome(oid)
    out = rs._connect().execute(
        "SELECT price_1m, price_5m, price_1h, price_24h,"
        " ret_24h_pct FROM opportunity_outcomes").fetchone()
    assert out[0] == 1.1 and out[1] == 1.2 and out[2] == 2.0
    assert out[3] is None  # بلا ملاحظة قرب 24h → NULL صادق
    assert out[4] is None
    rs.close()

def test_finalize_due_closes_old(tmp_path):
    rs = _tmp_store(tmp_path)
    r = _res("OLD", price=1.0)
    oid = rs.record_opportunity(r)
    now = time.time()
    rs.record_observation(oid, now + 60, 60, 2.0)
    # نقدّم first_seen_ts إلى ما قبل 26 ساعة
    rs._connect().execute(
        "UPDATE scan_opportunities SET first_seen_ts = ? "
        "WHERE opportunity_id = ?", [now - 26 * 3600, oid])
    n = rs.finalize_due()
    assert n == 1
    st = rs._connect().execute(
        "SELECT status FROM opportunity_outcomes").fetchone()[0]
    assert st in ("complete", "stale")
    # لم تعد ضمن المفتوحة
    assert rs.open_opportunities() == []
    rs.close()

def test_open_opportunities_fair_order(tmp_path):
    rs = _tmp_store(tmp_path)
    now = time.time()
    # ثلاث فرص: الأقدم بلا ملاحظة يجب أن تأتي أولاً
    for sym, age_s in (("N1", 300), ("N2", 200), ("N3", 100)):
        r = _res(sym, price=1.0)
        oid = rs.record_opportunity(r)
        rs._connect().execute(
            "UPDATE scan_opportunities SET first_seen_ts = ? "
            "WHERE opportunity_id = ?", [now - age_s, oid])
    # ملاحظة حديثة لـN1 فقط (قبل 10 ثوانٍ — داخل فاصل الـ90s)
    oid1 = rs._connect().execute(
        "SELECT opportunity_id FROM scan_opportunities "
        "WHERE symbol='N1'").fetchone()[0]
    rs.record_observation(oid1, now - 10, 290, 1.0)
    opps = rs.open_opportunities(limit=10)
    syms = [rs._connect().execute(
        "SELECT symbol FROM scan_opportunities WHERE opportunity_id=?",
        [o["opportunity_id"]]).fetchone()[0] for o in opps]
    # N1 مستبعدة (ملاحظة حديثة داخل الـstagger) — N2,N3 بلا ملاحظات
    assert "N1" not in syms
    assert set(syms) == {"N2", "N3"}
    rs.close()

def test_prefilter_excluded_from_tracking(tmp_path):
    rs = _tmp_store(tmp_path)
    rs.record_prefilter_reject(_pair("PX", price=0.5), "REJECTED_VOLUME")
    rs.record_opportunity(_res("PY", price=1.0))
    opps = rs.open_opportunities(limit=10)
    assert len(opps) == 1
    rs.close()

def test_fail_safe_no_db(tmp_path):
    rs = ResearchStore(path="/nonexistent_dir_xyz/t.duckdb")
    assert rs.record_opportunity(_res("ZZ")) is None
    assert rs.record_prefilter_reject(_pair("ZZ"), "REJECTED_LIQUIDITY") is None
    assert rs.record_scan_event(_res("ZZ"), time.time()) is False
    assert rs.open_opportunities() == []
    assert rs.finalize_due() == 0
    assert rs.counts() == {}
    rs.close()

def test_note_prefilter_reject_buffer():
    research._prefilter_buffer.clear()
    p = _pair("BUF", price=0.1)
    research.note_prefilter_reject(p, "REJECTED_AGE")
    research.note_prefilter_reject(None, "REJECTED_AGE")  # لا يرفع
    assert len(research._prefilter_buffer) == 2
    research._prefilter_buffer.clear()

def test_run_collection_drains_buffer(tmp_path):
    import tempfile
    research._prefilter_buffer.clear()
    with tempfile.TemporaryDirectory() as d:
        rs = ResearchStore(path=os.path.join(d, "c.duckdb"))
        research._store = rs
        try:
            p = _pair("DRN", price=0.3)
            research.note_prefilter_reject(p, "REJECTED_TXNS")
            research.run_collection([], price_fetcher=lambda o: None)
            assert research._prefilter_buffer == []
            n = rs._connect().execute(
                "SELECT COUNT(*) FROM scan_opportunities").fetchone()[0]
            assert n == 1
        finally:
            research._store = None
            rs.close()

def test_run_collection_records_events(tmp_path):
    import tempfile
    research._prefilter_buffer.clear()
    with tempfile.TemporaryDirectory() as d:
        rs = ResearchStore(path=os.path.join(d, "e.duckdb"))
        research._store = rs
        try:
            r = _res("EV2", signal="AVOID", score=20)
            research.run_collection([r], price_fetcher=lambda o: None)
            c = rs.counts()
            assert c["opportunities"] == 1
            assert c["scan_events"] == 1
            dec = rs._connect().execute(
                "SELECT decision FROM scan_opportunities").fetchone()[0]
            assert dec == "AVOID"
        finally:
            research._store = None
            rs.close()

def test_note_reevaluation_updates(tmp_path):
    import tempfile
    research._prefilter_buffer.clear()
    with tempfile.TemporaryDirectory() as d:
        rs = ResearchStore(path=os.path.join(d, "r.duckdb"))
        research._store = rs
        try:
            r = _res("RE", signal="WATCH", score=50)
            research.run_collection([r], price_fetcher=lambda o: None)
            r2 = dict(r)
            r2["score"] = 72
            r2["signal"] = "BUY"
            research.note_reevaluation(r2)
            row = rs._connect().execute(
                "SELECT n_seen, score, signal FROM scan_opportunities"
            ).fetchone()
            assert row[0] == 2 and row[1] == 72 and row[2] == "BUY"
            assert rs.counts()["scan_events"] == 2
        finally:
            research._store = None
            rs.close()
