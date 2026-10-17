#!/usr/bin/env python3
"""Rebuild index.html from data/refs.json + scripts/template.html (data embedded -> works via file://)."""
import json
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent

def build():
    refs = json.loads((ROOT / "data/refs.json").read_text())
    state = json.loads((ROOT / "data/state.json").read_text()) if (ROOT / "data/state.json").exists() else {}
    payload = json.dumps({"refs": refs, "last_run": state.get("last_run")}, ensure_ascii=False).replace("</", "<\\/")
    html = (ROOT / "scripts/template.html").read_text().replace("/*__DATA__*/null", payload)
    (ROOT / "index.html").write_text(html)
    print(f"index.html rebuilt with {len(refs)} entries")

if __name__ == "__main__":
    build()
