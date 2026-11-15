#!/usr/bin/env python3
"""Screenshot a page, or a before/after pair, into live/full and live/thumbs, and print the `images` JSON for a patch.

  python3 live/snap.py --name 0105-cart --after http://127.0.0.1:8000/cart
  python3 live/snap.py --name 0105-cart --before http://127.0.0.1:8001/cart --after http://127.0.0.1:8000/cart \
      [--size 1280x720] [--wait 1500] [--click "#menu"]

It checks every shot itself, so a keeper never needs to open the images: an error response, a blank page or a page
showing a denied term (keeper/config.json) fails with nothing kept, and an identical before/after pair is flagged.
Needs Python Playwright (`pip install playwright && playwright install chromium`).
"""
import argparse
import hashlib
import json
import re
import sys
from pathlib import Path


LIVE = Path(__file__).resolve().parent
sys.dont_write_bytecode = True
sys.path.insert(0, str(LIVE))
import validate  # noqa: E402

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    raise SystemExit(f"FAIL: Python Playwright isn't installed for {sys.executable}; write the event without images")

SEEN = "() => [document.body ? document.body.innerText.trim().length : 0, document.querySelectorAll('img,svg,canvas,video').length]"


def shoot(browser, url, name, w, h, wait, click, written):
    shots = {}
    for kind, scale in (("full", 1), ("thumbs", 640 / w)):
        page = browser.new_page(viewport={"width": w, "height": h}, device_scale_factor=scale)
        response = page.goto(url)
        if response and response.status >= 400:
            raise SystemExit(f"FAIL {url}: HTTP {response.status}; nothing kept")
        page.wait_for_timeout(wait)
        if click:
            page.click(click)
            page.wait_for_timeout(400)
        if kind == "full":
            chars, media = page.evaluate(SEEN)
            if not chars and not media:
                raise SystemExit(f"FAIL {url}: the page is blank; nothing kept")
            text = page.evaluate("() => document.body.innerText").lower()
            words, phrases = validate.deny_terms(validate.config())
            if any(re.search(rf"\b{re.escape(t)}\b", text) for t in words) or any(t in text for t in phrases):
                raise SystemExit(f"FAIL {url}: the page shows a denied term; nothing kept")
        out = LIVE / kind / f"{name}.jpg"
        out.parent.mkdir(exist_ok=True)
        page.screenshot(path=str(out), type="jpeg", quality=82)
        written.append(out)
        page.close()
        shots[kind] = f"live/{kind}/{name}.jpg"
    return shots


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", required=True, help="file stem, e.g. 0105-cart")
    ap.add_argument("--after", required=True)
    ap.add_argument("--before")
    ap.add_argument("--size", default="1280x720")
    ap.add_argument("--wait", type=int, default=1500)
    ap.add_argument("--click")
    a = ap.parse_args()
    w, h = (int(v) for v in a.size.split("x"))
    pairs = ([("before", a.before, "Before")] if a.before else []) + [("after", a.after, "After" if a.before else "")]
    images, written = [], []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            for side, url, caption in pairs:
                stem = f"{a.name}-{side}" if a.before else a.name
                shot = shoot(browser, url, stem, w, h, a.wait, a.click, written)
                images.append({"path": shot["thumbs"], **({"caption": caption} if caption else {}), "full": shot["full"]})
            browser.close()
    except SystemExit:
        for f in written:
            f.unlink(missing_ok=True)
        raise
    checked = f"{len(images)} shot(s) checked: loaded, not blank, no denied terms"
    if a.before:
        same = len({hashlib.sha1((LIVE.parent / i["full"]).read_bytes()).hexdigest() for i in images}) == 1
        checked += "; warn: before and after look identical" if same else "; before and after differ"
    print(json.dumps({"images": images, "checked": checked + ". No need to open them."}))


if __name__ == "__main__":
    main()
