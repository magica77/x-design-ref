#!/usr/bin/env python3
"""Convert raw X MCP results (search_posts_all / get_posts_by_ids JSON, as saved by
CallDynamicTool write_to_file) into candidate stubs for ingest.py.

    python3 scripts/mcp_to_candidates.py raw1.txt raw2.txt ... -o data/candidates/2026-10-18.json

Keeps originals only (no replies/retweets), impression_count > --min-impressions (default 50,000),
drops ids already in data/refs.json, de-dupes, sorts by impressions. Fills every X-sourced field;
leaves category/description/replies_summary/notable_replies as "TODO" for the curator (agent) to fill
after reading the post and its top replies.
"""
import argparse, json
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent

def load(path):
    t = Path(path).read_text(); s = t.find('{"data"')
    return json.JSONDecoder().raw_decode(t[s:])[0] if s >= 0 else {}

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("raw", nargs="+"); ap.add_argument("-o", "--out", required=True)
    ap.add_argument("--min-impressions", type=int, default=50000); a = ap.parse_args()
    have = {e["id"] for e in json.loads((ROOT / "data/refs.json").read_text())} if (ROOT / "data/refs.json").exists() else set()
    out = {}
    for f in a.raw:
        o = load(f); data = o.get("data") or []
        data = data if isinstance(data, list) else [data]
        inc = o.get("includes", {})
        users = {u["id"]: u for u in inc.get("users", [])}; media = {m["media_key"]: m for m in inc.get("media", [])}
        for d in data:
            if d["id"] in have or d["id"] in out: continue
            if any(r.get("type") in ("retweeted", "replied_to") for r in d.get("referenced_tweets", [])) or d["text"].startswith("RT @"): continue
            if d.get("public_metrics", {}).get("impression_count", 0) <= a.min_impressions: continue
            u = users.get(d.get("author_id"), {})
            ms = []
            for k in d.get("attachments", {}).get("media_keys", []):
                m = media.get(k)
                if not m: continue
                mp4s = sorted([v for v in m.get("variants", []) if v.get("content_type") == "video/mp4"], key=lambda v: v.get("bit_rate", 0))
                ms.append({"type": m.get("type"), "url": m.get("url"), "preview_image_url": m.get("preview_image_url"),
                           "duration_ms": m.get("duration_ms"), "mp4": (mp4s[min(1, len(mp4s) - 1)]["url"] if mp4s else None)})
            note = d.get("note_tweet") or {}
            ents = note.get("entities") or d.get("entities") or {}
            out[d["id"]] = {"id": d["id"], "url": d.get("url") or f"https://x.com/{u.get('username')}/status/{d['id']}",
                "author_username": u.get("username"), "author_name": u.get("name"), "created_at": d.get("created_at"),
                "text": note.get("text") or d["text"], "public_metrics": d["public_metrics"],
                "hashtags": [h["tag"].lower() for h in ents.get("hashtags", [])], "media": ms,
                "category": "TODO", "description": "TODO", "derived_tags": [], "replies_summary": "TODO", "notable_replies": []}
    c = sorted(out.values(), key=lambda x: -x["public_metrics"]["impression_count"])
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(c, indent=1, ensure_ascii=False))
    for x in c: print(f"{x['public_metrics']['impression_count']:>9} {x['id']} @{x['author_username']}: {x['text'][:90]!r}")
    print(f"{len(c)} candidate stubs -> {a.out}")

if __name__ == "__main__":
    main()
