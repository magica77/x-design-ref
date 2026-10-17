#!/usr/bin/env python3
"""Render index.html in headless Chromium -> preview.png (grid) and preview-detail.png (detail modal)."""
from pathlib import Path
from playwright.sync_api import sync_playwright
ROOT = Path(__file__).resolve().parent.parent
with sync_playwright() as p:
    b = p.chromium.launch(args=["--no-sandbox"])
    for scheme, suffix in (("light", ""), ("dark", "-dark")):
        pg = b.new_page(viewport={"width": 1440, "height": 1500}, device_scale_factor=1, color_scheme=scheme)
        pg.goto((ROOT / "index.html").as_uri()); pg.wait_for_timeout(2500)
        pg.screenshot(path=str(ROOT / f"preview{suffix}.png"))
        if not suffix:
            pg.click(".card.gold"); pg.wait_for_timeout(1200)
            pg.screenshot(path=str(ROOT / "preview-detail.png"))
        pg.close()
    b.close()
print("wrote preview.png, preview-dark.png, preview-detail.png")
