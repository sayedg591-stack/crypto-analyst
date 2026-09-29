"""gist_throttle.py — يخنق نشر الـGist لتجنب حظر GitHub API.
 
يُستورد تلقائياً عبر sitecustomize.py قبل main.py.
يرقّع state.gist_save بحيث:
- النشر للـGist كل 5 دقائق كحد أقصى (بدل كل دورة)
- عند حظر 403/429: توقف ساعة كاملة بلا أي طلب API
- الحفظ المحلي يبقى دائماً (لا يتأثر)
"""
 
import time
 
PUBLISH_INTERVAL = 300        # 5 دقائق بين كل نشر
RATE_LIMIT_COOLDOWN = 3600    # ساعة توقف عند الحظر
 
_last_publish = 0.0
_rate_limited_until = 0.0
_orig_gist_save = None
 
 
def _throttled_gist_save(s):
    global _last_publish, _rate_limited_until
    now = time.time()
 
    # في فترة الحظر: لا طلبات API إطلاقاً
    if now < _rate_limited_until:
        return False, "rate_limited_cooldown", True
 
    # خنق: نشر واحد كل 5 دقائق
    if now - _last_publish < PUBLISH_INTERVAL:
        return True, "throttled_skip", False
 
    ok, err, is_rl = _orig_gist_save(s)
 
    if is_rl:
        _rate_limited_until = now + RATE_LIMIT_COOLDOWN
        print("[GIST_THROTTLE] Rate limited! Backing off 1h.")
    elif ok:
        _last_publish = now
 
    return ok, err, is_rl
 
 
try:
    import state as _st
    _orig_gist_save = _st.gist_save
    _st.gist_save = _throttled_gist_save
    print("[GIST_THROTTLE] Patched: Gist max every 5min, 1h backoff on 403/429")
except Exception as e:
    print(f"[GIST_THROTTLE] Patch failed (non-fatal): {e}")
 
