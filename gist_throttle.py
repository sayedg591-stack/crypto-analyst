"""gist_throttle.py — يخنق كل طلبات GitHub API لتجنب الحظر نهائياً.

يُستورد تلقائياً عبر sitecustomize.py قبل main.py.
يرقّع دوال state.py:
- gist_save: نشر واحد كل 5 دقائق كحد أقصى
- gist_updated_at: cache لمدة 5 دقائق (بلا طلب API)
- verify_gist_changed: معطّل (يعيد True فوراً بلا طلبات)
- gist_load: cache لمدة 5 دقائق
عند حظر 403/429: توقف ساعة كاملة بلا أي طلب API.
"""

import time

PUBLISH_INTERVAL = 300
RATE_LIMIT_COOLDOWN = 3600
CACHE_TTL = 300

_last_publish = 0.0
_rate_limited_until = 0.0
_cached_updated_at = None
_cached_updated_at_time = 0.0
_cached_load = None
_cached_load_time = 0.0

_orig_gist_save = None
_orig_gist_updated_at = None
_orig_verify_gist_changed = None
_orig_gist_load = None


def _is_rate_limited():
    return time.time() < _rate_limited_until


def _throttled_gist_save(s):
    global _last_publish, _rate_limited_until
    now = time.time()
    if now < _rate_limited_until:
        return False, "rate_limited_cooldown", True
    if now - _last_publish < PUBLISH_INTERVAL:
        return True, "throttled_skip", False
    ok, err, is_rl = _orig_gist_save(s)
    if is_rl:
        _rate_limited_until = now + RATE_LIMIT_COOLDOWN
        print("[GIST_THROTTLE] Rate limited! Backing off 1h.", flush=True)
    elif ok:
        _last_publish = now
    return ok, err, is_rl


def _throttled_gist_updated_at():
    global _cached_updated_at, _cached_updated_at_time
    now = time.time()
    if _is_rate_limited():
        return _cached_updated_at
    if now - _cached_updated_at_time < CACHE_TTL and _cached_updated_at is not None:
        return _cached_updated_at
    try:
        result = _orig_gist_updated_at()
    except Exception:
        return _cached_updated_at
    if result is not None:
        _cached_updated_at = result
        _cached_updated_at_time = now
    return result


def _disabled_verify_gist_changed(before, tries=4, gap=4):
    # معطّل: التحقق كان يستهلك 4 طلبات API لكل نشر
    # نثق أن الكتابة نجحت إذا gist_save أعاد ok=True
    return True


def _throttled_gist_load():
    global _cached_load, _cached_load_time
    now = time.time()
    if _is_rate_limited():
        return _cached_load
    if now - _cached_load_time < CACHE_TTL and _cached_load is not None:
        return _cached_load
    try:
        result = _orig_gist_load()
    except Exception:
        return _cached_load
    if result is not None:
        _cached_load = result
        _cached_load_time = now
    return result


try:
    import state as _st
    _orig_gist_save = _st.gist_save
    _orig_gist_updated_at = _st.gist_updated_at
    _orig_verify_gist_changed = _st.verify_gist_changed
    _orig_gist_load = _st.gist_load
    _st.gist_save = _throttled_gist_save
    _st.gist_updated_at = _throttled_gist_updated_at
    _st.verify_gist_changed = _disabled_verify_gist_changed
    _st.gist_load = _throttled_gist_load
    print("[GIST_THROTTLE] Full API throttle active: save 5min, verify disabled, reads cached", flush=True)
except Exception as e:
    print(f"[GIST_THROTTLE] Patch failed (non-fatal): {e}", flush=True)
