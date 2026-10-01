# -*- coding: utf-8 -*-
"""
Independent audit of the KDRX public sealed record + paper-trading replay.
Source: https://kdrx.online/record.json
Method (matches their published method):
 - spot only, longs only (LONG/BUY_NOW/WAIT_DIP), crypto only; AVOID and forex excluded
 - position = 5% of wallet (within their stated 3.09%-7.79% range), no leverage
 - TP1 -> sell 50% + move stop to entry (breakeven); TP2 -> sell 30%; TP3 -> sell 20%
 - the record only gives the highest target reached, so blended outcome:
     SL  -> full risk lost
     TP1 -> 50% at TP1 + 50% at entry  = 0.5 * TP1%
     TP2 -> 50% at TP1 + 30% at TP2 + 20% at entry
     TP3 -> 50% at TP1 + 30% at TP2 + 20% at TP3
 - 0.2% cost per trade (spot round-trip fees)
Assumptions are listed explicitly in the output.
"""
import json
import os
import urllib.request

RECORD_URL = "https://kdrx.online/record.json"
STATE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "state")
OUT_FILE = os.path.join(STATE_DIR, "kdrx_real.json")

POSITION_PCT = 0.05
FEE_PCT = 0.002


def fetch_record():
    req = urllib.request.Request(RECORD_URL, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def parse_line(line):
    p = line.split("|")
    if len(p) < 13:
        return None
    try:
        return {
            "symbol": p[3], "market": p[4], "tf": p[5], "direction": p[6],
            "entry": float(p[7]), "sl": float(p[8]),
            "tp1": float(p[9]), "tp2": float(p[10]), "tp3": float(p[11]),
        }
    except (ValueError, IndexError):
        return None


def blended_pct(sig, result):
    e = sig["entry"]
    tp1 = (sig["tp1"] - e) / e * 100
    tp2 = (sig["tp2"] - e) / e * 100
    tp3 = (sig["tp3"] - e) / e * 100
    if result == "TP3":
        return 0.5 * tp1 + 0.3 * tp2 + 0.2 * tp3
    if result == "TP2":
        return 0.5 * tp1 + 0.3 * tp2
    if result == "TP1":
        return 0.5 * tp1
    return None


def main():
    data = fetch_record()
    items = data.get("items", [])
    trades = []
    for it in items:
        if len(it) < 14:
            continue
        result = it[8]
        if result not in ("SL", "TP1", "TP2", "TP3"):
            continue
        line = it[13] or ""
        if not line or "•" in line:
            continue
        sig = parse_line(line)
        if not sig:
            continue
        if sig["market"] != "crypto":
            continue
        if sig["direction"] not in ("LONG", "BUY_NOW", "WAIT_DIP"):
            continue
        if sig["entry"] <= 0 or sig["sl"] <= 0 or sig["sl"] >= sig["entry"]:
            continue
        if result == "SL":
            bp = -round((sig["entry"] - sig["sl"]) / sig["entry"] * 100, 4)
        else:
            bp = blended_pct(sig, result)
        if bp is None:
            continue
        trades.append({
            "symbol": sig["symbol"],
            "issued": it[2],
            "closed": it[10],
            "result": result,
            "entry": sig["entry"],
            "sl": sig["sl"],
            "blended_pct": round(bp, 4),
            "sl_dist_pct": round((sig["entry"] - sig["sl"]) / sig["entry"] * 100, 4),
        })
    trades.sort(key=lambda t: (t["closed"] or t["issued"]))

    equity = 100.0
    curve = [{"t": trades[0]["closed"] if trades else None, "equity": 100.0}] if trades else []
    wins = losses = 0
    gross_win = gross_loss = 0.0
    peak = 100.0
    max_dd = 0.0
    for t in trades:
        notional = equity * POSITION_PCT
        if t["result"] == "SL":
            pnl = -notional * (t["sl_dist_pct"] / 100)
            losses += 1
            gross_loss += -pnl
        else:
            pnl = notional * (t["blended_pct"] / 100)
            wins += 1
            gross_win += pnl
        pnl -= notional * FEE_PCT
        equity += pnl
        t["pnl"] = round(pnl, 4)
        t["equity_after"] = round(equity, 2)
        peak = max(peak, equity)
        max_dd = max(max_dd, (peak - equity) / peak * 100)
        curve.append({"t": t["closed"], "equity": round(equity, 2)})

    n = len(trades)
    stats = {
        "n_trades": n,
        "wins": wins,
        "losses": losses,
        "win_rate": round(100 * wins / n, 1) if n else 0,
        "start_equity": 100.0,
        "end_equity": round(equity, 2),
        "total_return_pct": round((equity - 100) / 100 * 100, 2),
        "max_drawdown_pct": round(max_dd, 2),
        "profit_factor": round(gross_win / gross_loss, 2) if gross_loss > 0 else None,
        "period_from": trades[0]["issued"][:10] if trades else None,
        "period_to": trades[-1]["closed"][:10] if trades and trades[-1]["closed"] else None,
        "record_generated_at": data.get("generatedAt"),
        "assumptions": [
            "Literal copy of KDRX signals from their public sealed record (kdrx.online/record.json)",
            "crypto spot longs only - AVOID and forex excluded",
            "position 5% of wallet (within their stated 3.09%-7.79%), no leverage",
            "their method: sell 50% at TP1 + stop to entry, 30% at TP2, 20% at TP3",
            "record gives highest target reached only - blended outcome computed on that basis",
            "0.2% fees per trade, sequential chronological replay",
        ],
    }
    out = {"stats": stats, "equity_curve": curve, "trades": trades[-200:]}
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(OUT_FILE, "w") as f:
        json.dump(out, f)
    s = stats
    print("trades=%d win_rate=%.1f%% equity=%.2f return=%+.2f%% maxDD=%.2f%% PF=%s" % (
        s["n_trades"], s["win_rate"], s["end_equity"], s["total_return_pct"],
        s["max_drawdown_pct"], s["profit_factor"]))
    print("period:", s["period_from"], "->", s["period_to"])


if __name__ == "__main__":
    main()
