"""
Auto-imported by Python on startup (before main.py).
- Loads gist_throttle: limits Gist publishing to avoid GitHub rate limits.
- Starts the self-hosted state tunnel (best effort).
Fail-safe: if anything fails, the bot continues normally.
"""

# Gist throttle first (most important fix)
try:
    import gist_throttle
    print("[SITECUSTOMIZE] gist_throttle loaded", flush=True)
except Exception as _e:
    print(f"[SITECUSTOMIZE] gist_throttle failed (non-fatal): {_e}", flush=True)

# Tunnel (best effort)
try:
    import tunnel
    _url = tunnel.start_tunnel()
    if _url:
        print(f"[SITECUSTOMIZE] Tunnel active: {_url}", flush=True)
    else:
        print("[SITECUSTOMIZE] Tunnel not started, using Gist", flush=True)
except Exception as _e:
    print(f"[SITECUSTOMIZE] Tunnel init failed (non-fatal): {_e}", flush=True)
