"""Publish KDRX bot state to public Gist."""
import json, os, urllib.request, urllib.error
GIST_ID = os.environ.get("KDRX_GIST_ID", "")
GITHUB_TOKEN = os.environ.get("GH_PAT", "")
def publish(state: dict) -> bool:
    if not GIST_ID or not GITHUB_TOKEN:
        print("[GIST] not configured")
        return False
    payload = json.dumps({"files": {"kdrx-state.json": {"content": json.dumps(state, indent=2, ensure_ascii=False)}}}).encode()
    req = urllib.request.Request(f"https://api.github.com/gists/{GIST_ID}", data=payload, method="PATCH")
    req.add_header("Authorization", f"token {GITHUB_TOKEN}")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status == 200
    except Exception as e:
        print(f"[GIST] {e}")
        return False
