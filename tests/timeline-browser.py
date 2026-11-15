#!/usr/bin/env python3
"""Optional Playwright check using a synthetic feed and intercepted requests; no HTTP server."""
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
SVG = '<svg xmlns="http://www.w3.org/2000/svg" width="640" height="320"><rect width="640" height="320" fill="#163b35"/><text x="40" y="140" fill="#c8e6d4" font-family="sans-serif" font-size="52">12 rows checked</text><text x="40" y="210" fill="#c8e6d4" font-family="sans-serif" font-size="28">Synthetic snapshot</text></svg>'


def main():
    with tempfile.TemporaryDirectory(prefix="timeline-browser-") as tmp:
        work = Path(tmp) / "work"
        subprocess.run([sys.executable, str(ROOT / "skills/live-timeline/scripts/init.py"), str(work),
                        "--title", "Catalogue import", "--owner", "Owner", "--tz", "UTC"],
                       check=True, capture_output=True, env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
        feed = json.loads((work / "live/events.json").read_text())
        now = datetime.now(timezone.utc)
        start = now - timedelta(hours=4)
        stamp = lambda t: t.isoformat(timespec="seconds")
        feed["run"].update(start=stamp(start), done=True)
        feed["chapters"][0].update(title="Checking the import", start=stamp(start),
                                    summary="Two passes close a small catalogue import.")
        for lane in feed["lanes"]:
            lane["status"] = "done"
        feed["events"] = [
            {"id": "e001", "time": stamp(start), "lane": "main", "kind": "start", "importance": 2,
             "chapter": "c1", "state": "done", "title": "Import starts with twelve rows",
             "summary": "The initial pass checks ids and required fields."},
            {"id": "e002", "time": stamp(now), "lane": "main", "kind": "success", "importance": 3,
             "chapter": "c1", "title": "All twelve rows pass verification", "summary": "The second pass confirms every stored row.",
             "why": "The owner can inspect the result and the evidence together.", "causedBy": ["e001"],
             "images": [{"path": "live/thumbs/check.svg", "caption": "Synthetic batch result", "full": "assets/check.svg"}]}]
        feed["headline"].update(status={"tone": "done", "text": "Import verified", "note": "Synthetic demonstration"},
                                progress={"value": 12, "of": 12, "label": "rows checked"},
                                best={"text": "12 of 12 rows match", "eventId": "e002"})
        html = (work / "live-timeline.html").read_text()
        with sync_playwright() as p:
            browser = p.chromium.launch()
            for width in (1440, 390):
                for scheme in ("light", "dark"):
                    context = browser.new_context(viewport={"width": width, "height": 1100}, color_scheme=scheme)
                    page = context.new_page()
                    errors, requests = [], []
                    page.on("pageerror", lambda e: errors.append(str(e)))
                    state = {"malformed": False}

                    def handle(route):
                        url = urlsplit(route.request.url)
                        requests.append(route.request.url)
                        assert url.hostname == "timeline.test", route.request.url
                        if url.path == "/":
                            route.fulfill(body=html, content_type="text/html")
                        elif url.path == "/live/events.json":
                            route.fulfill(body="{" if state["malformed"] else json.dumps(feed), content_type="application/json")
                        elif url.path.endswith("check.svg"):
                            route.fulfill(body=SVG, content_type="image/svg+xml")
                        else:
                            route.fulfill(status=404, body="")

                    page.route("**/*", handle)
                    page.clock.install()
                    page.goto("https://timeline.test/")
                    page.locator("#runTitle").filter(has_text="Catalogue import").wait_for()
                    page.locator(".b-imgs img").wait_for()
                    assert page.locator(".rib-gap").count() > 0
                    assert page.locator(".b-imgs img").evaluate("e => e.complete && e.naturalWidth > 0")
                    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
                    page.locator('.b-card[data-open="e002"]').click()
                    page.locator(".m-imgs img").wait_for()
                    assert page.locator(".m-imgs a").get_attribute("href") == "assets/check.svg"
                    page.keyboard.press("Escape")
                    page.locator("#updBtn").click()
                    assert "All twelve rows" in page.locator("#updText").input_value()
                    page.keyboard.press("Escape")
                    # Refresh failure must retain the last good story and identify it as stale.
                    state["malformed"] = True
                    page.clock.run_for(61000)
                    page.wait_for_function("document.querySelector('#feedText').textContent.includes('Last good copy')")
                    assert page.locator('.b-card[data-open="e002"]').count() == 1
                    assert not errors, errors
                    print(f"PASS width={width} theme={scheme}: image/card/popup, folded gap, update draft, cached-feed fallback, no overflow or JS errors")
                    context.close()
            browser.close()


if __name__ == "__main__":
    main()
