# -*- coding: utf-8 -*-
"""تتبع حالة مصادر البيانات مع التبديل التلقائي."""
import time
import json
import os

STATE_FILE = os.path.join(os.path.dirname(__file__), "state", "sources.json")

SOURCES = ["binance", "dexscreener", "coingecko"]


def _load():
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except Exception:
        return {}


def _save(data):
    try:
        os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
        with open(STATE_FILE, "w") as f:
            json.dump(data, f)
    except Exception:
        pass


def report(source, ok):
    """تسجيل نجاح/فشل مصدر."""
    data = _load()
    s = data.get(source, {"ok_count": 0, "fail_count": 0, "last_ok": 0, "last_fail": 0, "status": "unknown"})
    now = int(time.time())
    if ok:
        s["ok_count"] += 1
        s["last_ok"] = now
        s["status"] = "up"
        s["fail_count"] = 0  # reset on success
    else:
        s["fail_count"] += 1
        s["last_fail"] = now
        if s["fail_count"] >= 3:
            s["status"] = "down"
        else:
            s["status"] = "degraded"
    data[source] = s
    _save(data)


def get_status():
    """إرجاع حالة كل المصادر."""
    data = _load()
    result = {}
    for src in SOURCES:
        s = data.get(src, {})
        result[src] = {
            "status": s.get("status", "unknown"),
            "last_ok": s.get("last_ok", 0),
            "fail_count": s.get("fail_count", 0),
        }
    return result
