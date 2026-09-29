# -*- coding: utf-8 -*-
"""المنسق الرئيسي: فحص كل 15 دقيقة → إشارات → تنفيذ → نشر."""

import json
import logging
import os
import sys
import time
from datetime import datetime, timezone

import config
from scanner import scan_all, fetch_market_pulse
from wallet import PaperWallet
from executor import Executor
import publisher
import gist_pub
import sysstats
import sources

# ---------- السجلات ----------
os.makedirs(config.STATE_DIR, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(config.LOG_FILE),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("kdrx")


def load_signals_state():
    if os.path.exists(config.SIGNALS_FILE):
        try:
            with open(config.SIGNALS_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return {"seen": {}, "last_summary": ""}


def save_signals_state(state):
    tmp = config.SIGNALS_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(state, f)
    os.replace(tmp, config.SIGNALS_FILE)


def is_cooldown_ok(state, symbol):
    """تحقق من cooldown الـ 12 ساعة لنفس الزوج."""
    last = state["seen"].get(symbol, 0)
    return (time.time() - last) > config.SIGNAL_COOLDOWN_HOURS * 3600


def run_cycle():
    """دورة واحدة: فحص → تنفيذ → مراقبة → نشر."""
    log.info("=== Cycle start ===")
    wallet = PaperWallet()
    ex = Executor(wallet)
    state = load_signals_state()

    # 1. فحص الإشارات
    try:
        signals = scan_all()
        sources.report("binance", True)
    except Exception as e:
        log.warning(f"Scanner failed: {e}")
        sources.report("binance", False)
        signals = []
    log.info(f"Scanner found {len(signals)} raw signals")

    # 2. فلترة الـ cooldown
    fresh = [s for s in signals if is_cooldown_ok(state, s["symbol"])]
    log.info(f"{len(fresh)} signals pass cooldown filter")

    # 3. فتح المراكز + نشر الإشارات
    for sig in fresh:
        pos_id, result = wallet.open_position(sig)
        if pos_id:
            state["seen"][sig["symbol"]] = int(time.time())
            publisher.publish_signal(sig, result)
            log.info(f"Published signal {sig['symbol']} {sig['direction']}")
        else:
            log.info(f"Skipped {sig['symbol']}: {result}")

    # 4. مراقبة المراكز المفتوحة
    events = ex.check_positions()
    for ev in events:
        publisher.publish_event(ev)
        log.info(f"Published event {ev['reason']} {ev['symbol']} pnl={ev['pnl']}")

    save_signals_state(state)

    # 5. الملخص اليومي (مرة واحدة يومياً)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if state.get("last_summary") != today:
        hour = datetime.now(timezone.utc).hour
        if hour >= 8:  # بعد 08:00 UTC
            stats = wallet.stats()
            publisher.publish_summary(stats)
            state["last_summary"] = today
            save_signals_state(state)
            log.info("Published daily summary")

    # 5b. نبض السوق (كل 6 ساعات)
    last_pulse = state.get("last_pulse", 0)
    if time.time() - last_pulse > 6 * 3600:
        try:
            pulse = fetch_market_pulse()
            if pulse:
                publisher.publish_market_pulse(pulse)
                state["last_pulse"] = int(time.time())
                save_signals_state(state)
                log.info("Published market pulse")
        except Exception as e:
            log.warning(f"Market pulse failed: {e}")

    log.info(f"=== Cycle end: equity=${wallet.equity():.2f} ===")
    
    # 6. نشر الحالة إلى Gist للـ dashboard
    try:
        gist_state = {
            "wallet": wallet.to_dict(),
            "system": sysstats.get_stats(),
            "sources": sources.get_status(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        gist_pub.publish(gist_state)
    except Exception as e:
        log.warning(f"Gist publish failed: {e}")
    
    return {"signals": len(fresh), "events": len(events), "equity": wallet.equity()}


def main():
    log.info("KDRX signal bot starting (paper trading $100)")
    publisher.publish_startup()
    while True:
        try:
            run_cycle()
        except Exception as e:
            log.exception(f"Cycle failed: {e}")
        log.info(f"Sleeping {config.SCAN_INTERVAL_MINUTES} min...")
        time.sleep(config.SCAN_INTERVAL_MINUTES * 60)


def run_once():
    """تشغيل دورة واحدة (للـ cron)."""
    return run_cycle()


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--once":
        run_once()
    else:
        main()
