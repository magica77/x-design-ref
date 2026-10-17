#!/usr/bin/env python3
"""Capture PNG screenshots of X posts without logging in.

Method order (first that works wins):
  1. "embed"   – local HTML page with the official <blockquote class="twitter-tweet"> + widgets.js,
                 wait for the rendered iframe, screenshot the element.
  2. "iframe"  – load https://platform.twitter.com/embed/Tweet.html?id=ID directly.
  3. "media"   – download the post's media preview image (preview_image_url / url) from refs.json.
Usage: python3 scripts/screenshot.py ID [ID ...]   (or imported by ingest.py)
"""
import sys, os, json, urllib.request, tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
SHOTS = ROOT / "shots"

EMBED_HTML = """<!doctype html><html><head><meta charset="utf-8">
<style>body{margin:0;padding:24px;background:#fff;font-family:sans-serif}#wrap{width:550px}</style></head>
<body><div id="wrap"><blockquote class="twitter-tweet" data-dnt="true" data-theme="light" data-conversation="none">
<a href="https://twitter.com/x/status/%s"></a></blockquote></div>
<script async src="https://platform.twitter.com/widgets.js" charset="utf-8"></script></body></html>"""

def _browser(p):
    return p.chromium.launch(args=["--no-sandbox"])

def _settle(page):
    """Wait until every <img>/<video poster> inside the embed iframe has actually loaded."""
    page.wait_for_timeout(1500)
    for f in page.frames:
        if "platform.twitter.com" not in f.url:
            continue
        try:
            f.evaluate("() => document.querySelectorAll('img').forEach(i => { i.loading='eager'; })")
            f.wait_for_function("""() => { const im=[...document.querySelectorAll('img')];
                const vids=[...document.querySelectorAll('video')];
                const ok = im.every(i => i.complete && i.naturalWidth > 0);
                const posters = vids.every(v => !v.poster || v.readyState>=0);
                return ok && posters && (im.length > 1 || vids.length > 0); }""", timeout=15000)
        except Exception as ex:
            print("   settle:", str(ex).splitlines()[0][:80])
    page.wait_for_timeout(2500)

def shot_embed(page, pid, out):
    tmp = Path(tempfile.gettempdir()) / f"embed_{pid}.html"
    tmp.write_text(EMBED_HTML % pid)
    page.goto(tmp.as_uri())
    page.wait_for_selector("iframe[id^='twitter-widget']", timeout=25000)
    fr = page.frame_locator("iframe[id^='twitter-widget']")
    fr.locator("article").first.wait_for(timeout=25000)
    page.wait_for_function("""() => { const f=document.querySelector("iframe[id^='twitter-widget']"); return f && f.getBoundingClientRect().height > 150 }""", timeout=20000)
    # let images/video posters settle
    _settle(page)
    page.locator("iframe[id^='twitter-widget']").screenshot(path=str(out))

def shot_iframe(page, pid, out):
    page.goto(f"https://platform.twitter.com/embed/Tweet.html?id={pid}&dnt=true&theme=light", wait_until="networkidle", timeout=30000)
    page.locator("article").first.wait_for(timeout=20000)
    page.wait_for_timeout(5000)
    page.locator("article").first.screenshot(path=str(out))

def shot_media(entry, out):
    for m in entry.get("media", []):
        u = m.get("preview_image_url") or m.get("url")
        if u:
            req = urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"})
            data = urllib.request.urlopen(req, timeout=30).read()
            # convert jpg -> png via Pillow if available, else save raw bytes
            try:
                from PIL import Image; import io
                Image.open(io.BytesIO(data)).save(out, "PNG")
            except Exception:
                out.write_bytes(data)
            return
    raise RuntimeError("no media url")

def capture(entries, force=False):
    """entries: list of catalog dicts. Sets entry['screenshot'] and entry['screenshot_method']."""
    from playwright.sync_api import sync_playwright
    SHOTS.mkdir(exist_ok=True)
    with sync_playwright() as p:
        b = _browser(p)
        ctx = b.new_context(viewport={"width": 640, "height": 1400}, device_scale_factor=2, locale="en-US")
        for e in entries:
            pid = e["id"]; out = SHOTS / f"{pid}.png"
            if out.exists() and not force and e.get("screenshot"):
                continue
            ok = None
            for name, fn in (("embed", lambda pg: shot_embed(pg, pid, out)), ("iframe", lambda pg: shot_iframe(pg, pid, out))):
                page = ctx.new_page()
                try:
                    fn(page); ok = name; break
                except Exception as ex:
                    print(f"  [{pid}] {name} failed: {str(ex).splitlines()[0][:120]}")
                finally:
                    page.close()
            if not ok:
                try:
                    shot_media(e, out); ok = "media"
                except Exception as ex:
                    print(f"  [{pid}] media failed: {ex}")
            e["screenshot"] = f"shots/{pid}.png" if ok else None
            e["screenshot_method"] = ok
            print(f"  [{pid}] screenshot -> {ok}")
        b.close()
    return entries

if __name__ == "__main__":
    refs = json.loads((ROOT / "data/refs.json").read_text()) if (ROOT / "data/refs.json").exists() else []
    by = {e["id"]: e for e in refs}
    ids = sys.argv[1:]
    capture([by.get(i, {"id": i, "media": []}) for i in ids], force=True)
