#!/usr/bin/env python3
"""Ingest candidate X posts into the design-reference catalog.

    python3 scripts/ingest.py data/candidates/2026-10-18.json [--min-impressions 50000]
                              [--no-shots] [--update-existing] [--dry-run]

* candidates file: a JSON list (or {"candidates": [...]}) of objects. Required: id, url,
  author_username, author_name, created_at, text, public_metrics, media, category,
  description, replies_summary, notable_replies. Optional: hashtags, derived_tags, gold_standard.
  (scripts/mcp_to_candidates.py turns raw MCP results into stubs with all X-sourced fields filled.)
* skips ids already in data/refs.json (or refreshes their metrics with --update-existing)
* drops posts with impression_count <= threshold (default 50,000)
* captures shots/<id>.png only for new entries, extracts thumbs/<id>.jpg (media frame/image)
* writes data/refs.json, data/state.json and rebuilds index.html
"""
import argparse, json, subprocess, sys, urllib.request, datetime as dt
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
REFS, STATE, THUMBS = ROOT / "data/refs.json", ROOT / "data/state.json", ROOT / "thumbs"
CATEGORIES = ["Infographic", "Animated Website", "Product Intro", "App Intro"]
MEDIA_TYPES = {"photo": "image", "animated_gif": "gif", "video": "video"}

def now():
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

def metrics(pm):
    return {"impressions": pm.get("impression_count", 0), "likes": pm.get("like_count", 0),
            "reposts": pm.get("retweet_count", pm.get("repost_count", 0)), "replies": pm.get("reply_count", 0),
            "quotes": pm.get("quote_count", 0), "bookmarks": pm.get("bookmark_count", 0)}

def normalize(c):
    cat = c.get("category")
    if cat not in CATEGORIES:
        raise ValueError(f"{c.get('id')}: category must be one of {CATEGORIES}, got {cat!r}")
    media = c.get("media") or []
    types = [MEDIA_TYPES.get(m.get("type"), m.get("type")) for m in media]
    mtype = "video" if "video" in types else "gif" if "gif" in types else "image" if "image" in types else "none"
    tags = sorted({t.lower().lstrip("#") for t in (c.get("hashtags") or c.get("tags") or [])})
    return {
        "id": str(c["id"]),
        "url": c.get("url") or f"https://x.com/{c['author_username']}/status/{c['id']}",
        "author": {"handle": c["author_username"], "name": c.get("author_name", c["author_username"])},
        "created_at": c["created_at"],
        "collected_at": c.get("collected_at") or now(),
        "category": cat,
        "tags": tags,                                    # real X hashtags (lowercased)
        "derived_tags": [] if tags else [t.lower() for t in c.get("derived_tags", [])][:3],  # ours, only when no hashtags
        "description": c["description"],
        "text": c.get("text", ""),
        "metrics": metrics(c["public_metrics"]),
        "metrics_updated_at": now(),
        "media_type": mtype,
        "media": media,
        "replies_summary": c.get("replies_summary", ""),
        "notable_replies": c.get("notable_replies", []),
        "gold_standard": bool(c.get("gold_standard", False)),
        "screenshot": None, "screenshot_method": None, "thumbnail": None,
    }

def make_thumb(e):
    THUMBS.mkdir(exist_ok=True)
    out = THUMBS / f"{e['id']}.jpg"
    for m in e["media"]:
        try:
            if m.get("mp4"):   # grab a frame ~40% into the video (first frames are often blank)
                ss = max(1.0, (m.get("duration_ms") or 10000) / 1000 * 0.4)
                subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{ss:.1f}", "-i", m["mp4"],
                                "-frames:v", "1", "-vf", "scale=960:-2", "-q:v", "4", str(out)], check=True, timeout=90)
            else:
                u = m.get("url") or m.get("preview_image_url")
                if not u: continue
                if "pbs.twimg.com/media/" in u and "?" not in u: u += "?name=medium"
                data = urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"}), timeout=30).read()
                out.write_bytes(data)
            if out.exists() and out.stat().st_size > 0:
                return f"thumbs/{out.name}"
        except Exception as ex:
            print(f"  [{e['id']}] thumb failed: {ex}")
    return None

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("candidates", nargs="+")
    ap.add_argument("--min-impressions", type=int, default=50000)
    ap.add_argument("--no-shots", action="store_true")
    ap.add_argument("--update-existing", action="store_true", help="refresh metrics of ids already in the catalog")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    refs = json.loads(REFS.read_text()) if REFS.exists() else []
    by_id = {e["id"]: e for e in refs}
    new, updated, skipped = [], 0, []
    for f in a.candidates:
        data = json.loads(Path(f).read_text())
        for c in (data["candidates"] if isinstance(data, dict) else data):
            pid = str(c["id"])
            if pid in by_id:
                if a.update_existing and c.get("public_metrics"):
                    by_id[pid]["metrics"] = metrics(c["public_metrics"]); by_id[pid]["metrics_updated_at"] = now(); updated += 1
                else:
                    skipped.append((pid, "already in catalog"))
                continue
            if any(n["id"] == pid for n in new):
                skipped.append((pid, "duplicate in candidates")); continue
            imp = c["public_metrics"].get("impression_count", 0)
            if imp <= a.min_impressions and not c.get("gold_standard"):
                skipped.append((pid, f"impressions {imp} <= {a.min_impressions}")); continue
            try:
                new.append(normalize(c))
            except (ValueError, KeyError) as ex:
                skipped.append((pid, f"invalid/uncurated candidate: {ex}"))
    for pid, why in skipped: print(f"skip {pid}: {why}")
    print(f"{len(new)} new, {updated} metric refreshes, {len(skipped)} skipped")
    if a.dry_run: return
    if new:
        for e in new: e["thumbnail"] = make_thumb(e)
        if not a.no_shots:
            import screenshot
            screenshot.capture(new)
    refs = list(by_id.values()) + new
    refs.sort(key=lambda e: (bool(e.get("gold_standard")), e["created_at"]), reverse=True)
    REFS.write_text(json.dumps(refs, indent=1, ensure_ascii=False) + "\n")
    state = json.loads(STATE.read_text()) if STATE.exists() else {"runs": []}
    state["last_run"] = now()
    state["runs"] = (state.get("runs", []) + [{"at": state["last_run"], "added": [e["id"] for e in new],
                     "skipped": len(skipped), "metric_refreshes": updated, "files": a.candidates}])[-60:]
    state["total_entries"] = len(refs)
    state["newest_post_id"] = max((e["id"] for e in refs), key=int, default=None)
    STATE.write_text(json.dumps(state, indent=1) + "\n")
    import build_index; build_index.build()
    missing = [e["id"] for e in refs if not e.get("screenshot")]
    if missing: print("entries without screenshot:", missing)

if __name__ == "__main__":
    main()
