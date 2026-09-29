"""
Auto-imported by Python on startup (before main.py).
Starts the self-hosted state tunnel (bypasses GitHub Gist rate limits).
Fail-safe: if anything fails, the bot continues normally with Gist.
"""
try:
    import tunnel
    _url = tunnel.start_tunnel()
    if _url:
        print(f"[SITECUSTOMIZE] Tunnel active: {_url}", flush=True)
    else:
        print("[SITECUSTOMIZE] Tunnel not started, using Gist", flush=True)
except Exception as _e:
    # Non-fatal: bot continues with Gist publishing
    print(f"[SITECUSTOMIZE] Tunnel init failed (non-fatal): {_e}", flush=True)
