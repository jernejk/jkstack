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
                    assert page.locator("#feed").is_visible(), "the finished/stale banner must stay visible"
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
            busy_feed(browser, html, json.loads((work / "live/events.json").read_text()))
            story_and_lanes(browser, html, json.loads((work / "live/events.json").read_text()))
            finished_with_open_start(browser, html, json.loads((work / "live/events.json").read_text()))
            browser.close()


def finished_with_open_start(browser, html, feed):
    """A finished run whose log never closed a start: nothing reads as running and busy time stops at the run's end."""
    start = datetime.now(timezone.utc) - timedelta(hours=30)
    stamp = lambda t: t.isoformat(timespec="seconds")
    feed["run"].update(start=stamp(start), done=True)
    feed["lanes"] = [{"id": "build", "name": "Build", "short": "Build", "status": "done", "model": "opus"}]
    feed["chapters"][0].update(start=stamp(start))
    feed["events"] = [
        {"id": "e1", "time": stamp(start), "lane": "build", "kind": "start", "importance": 2, "chapter": "c1", "state": "running",
         "title": "Build starts", "summary": "Never closed."},
        {"id": "e2", "time": stamp(start + timedelta(hours=2)), "lane": "build", "kind": "success", "importance": 2, "chapter": "c1",
         "title": "Build ships", "summary": "Last beat."}]
    feed["metrics"] = []
    context = browser.new_context(viewport={"width": 1280, "height": 900})
    page = context.new_page()
    page.add_init_script("localStorage.setItem('live-timeline:/:view', 'full')")
    page.route("**/*", lambda route: route.fulfill(body=html, content_type="text/html") if urlsplit(route.request.url).path == "/"
               else route.fulfill(body=json.dumps(feed), content_type="application/json"))
    page.goto("https://timeline.test/")
    page.locator(".l-row").first.wait_for()
    row = page.locator(".l-row").first.inner_text()
    assert "running" not in row and "2 h" in row, row
    assert page.locator(".mo .dot.on").count() == 0, "a finished run has no live model"
    assert page.locator(".pill.run").count() == 0 and page.locator(".rib-run").count() == 0
    print("PASS finished run with an unclosed start: not running, busy time capped at the last beat")
    context.close()


def busy_feed(browser, html, feed):
    """A two-day, 300-event run with many quiet gaps: the phone ribbon must keep time order and readable gap labels."""
    start = datetime.now(timezone.utc) - timedelta(hours=80)
    stamp = lambda t: t.isoformat(timespec="seconds")
    feed["run"].update(start=stamp(start), done=False)
    feed["lanes"] = [{"id": f"l{i}", "name": f"Lane {i}", "short": f"L{i}", "status": "running"} for i in range(6)]
    feed["chapters"][0].update(start=stamp(start))
    t, events = start, []
    for i in range(300):
        t += timedelta(minutes=95 if i % 8 == 7 else 3)
        events.append({"id": f"e{i + 1:03d}", "time": stamp(t), "lane": f"l{i % 6}", "kind": "update",
                       "importance": 2, "chapter": "c1", "title": f"Beat {i + 1}", "summary": "Synthetic beat."})
    feed["events"], feed["metrics"] = events, []
    times = {e["id"]: e["time"] for e in events}
    context = browser.new_context(viewport={"width": 390, "height": 900})
    page = context.new_page()
    page.add_init_script("localStorage.setItem('live-timeline:/:view', 'full')")
    page.route("**/*", lambda route: route.fulfill(body=html, content_type="text/html") if urlsplit(route.request.url).path == "/"
               else route.fulfill(body=json.dumps(feed), content_type="application/json"))
    page.goto("https://timeline.test/")
    page.locator(".rib-gap").first.wait_for()
    xs = page.evaluate("[...document.querySelectorAll('#ribbon .mk')].map(g => [g.dataset.id, +g.querySelector('.hit').getAttribute('cx')])")
    order = [x for _, x in sorted(xs, key=lambda p: times[p[0]])]
    assert all(b >= a - 0.01 for a, b in zip(order, order[1:])), "ribbon x must follow time"
    labels = sorted(page.evaluate("[...document.querySelectorAll('#ribbon .rib-gap text')].map(t => +t.getAttribute('x'))"))
    assert all(b - a >= 24 for a, b in zip(labels, labels[1:])), labels
    assert page.locator(".c-lanes .big").inner_text().startswith("0 "), "lanes marked running with nothing open and no recent beat are not active"
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    print(f"PASS busy feed at 390: {len(xs)} markers in time order, {len(labels)} gap labels apart, idle lanes not counted")
    context.close()


def story_and_lanes(browser, html, feed):
    """A busy run opens in Story view: key beats per chapter, digests, models per lane, owner choices and T3 links."""
    start = datetime.now(timezone.utc) - timedelta(hours=10)
    stamp = lambda t: t.isoformat(timespec="seconds")
    feed["run"].update(start=stamp(start), done=False, t3={"env": "env-1", "thread": "lead-thread"},
                       digest=["Three chapters: build, test, ship."])
    feed["lanes"] = [feed["lanes"][0]] + [{"id": i, "name": i.title(), "short": i.title(), "status": "running"} for i in ("build", "test")]
    feed["chapters"] = [{"id": f"c{k + 1}", "title": f"Part {k + 1}", "start": stamp(start + timedelta(hours=3 * k)),
                         "summary": f"Part {k + 1} summary."} for k in range(3)]
    feed["chapters"][0].update(digest="Opus builds the loop.", outcome="A playable loop.", keyBeats=["e003", "e010"])
    kinds = ["update", "success", "start", "review", "fail", "update", "nudge", "update"]
    events = []
    for i in range(140):
        t = start + timedelta(minutes=4 * i + 1)
        lane = "build" if (i // 8) % 2 else "test"
        e = {"id": f"e{i + 1:03d}", "time": stamp(t), "lane": lane, "kind": kinds[i % 8], "importance": 1 if kinds[i % 8] == "update" else 2,
             "title": f"Beat {i + 1}", "summary": "Synthetic beat."}
        if e["kind"] == "nudge":
            e["lane"] = feed["lanes"][0]["id"]
        if e["kind"] == "start":
            e.update(model="opus" if lane == "build" else "luna", state="done", end=stamp(t + timedelta(minutes=30)), thread=f"{lane}-thread")
        events.append(e)
    events[-1].update(kind="blocked", importance=3, ask="Pick the art style.", choices=["Neon", "Paper", "Pixel"])
    events[60].update(kind="update", importance=3, title="Key update")
    events[2]["links"] = [{"label": "ok", "path": "reports/ok.md"}, {"label": "space", "path": " demo:example"},
                          {"label": "plus", "path": "demo+foo:example"}, {"label": "dots", "path": "%2e%2e/up.md"},
                          {"label": "web", "path": "https://example.com/x"}]
    feed["lanes"][2]["model"] = "haiku"
    for e in events:
        if e["lane"] == "test" and e["kind"] == "start":
            e.pop("model", None)
    events[-2].update(kind="start", state="running", model="opus", thread="build-thread")
    feed["events"], feed["metrics"] = events, []
    for width in (390, 1280):
        context = browser.new_context(viewport={"width": width, "height": 900})
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.route("**/*", lambda route: route.fulfill(body=html, content_type="text/html") if urlsplit(route.request.url).path == "/"
                   else route.fulfill(body=json.dumps(feed), content_type="application/json"))
        page.goto("https://timeline.test/")
        page.locator(".ch-story .keys").first.wait_for()
        assert page.locator('#viewSeg [aria-pressed="true"]').inner_text() == "Story"
        assert page.locator(".beat").count() == 0 and page.locator(".chapter").count() == 3
        first = page.locator('.chapter[data-ch="c1"] .keys button')
        assert [first.nth(i).get_attribute("data-open") for i in range(first.count())] == ["e003", "e010"], "keyBeats override the ranking"
        assert page.locator('.chapter[data-ch="c1"] .ch-digest').inner_text() == "Opus builds the loop."
        assert all(page.locator(f'.chapter[data-ch="c{k}"] .keys li').count() <= 4 for k in (2, 3))
        assert "Three chapters" in page.locator(".run-digest").inner_text()
        page.locator('.chapter[data-ch="c2"] .ch-more').click()
        assert page.locator('.chapter[data-ch="c2"] .beat').count() > 4
        assert page.locator("#t3Btn").get_attribute("href") == "t3code://threads/env-1/lead-thread"
        block = page.locator(".cellwrap .t3link")
        assert block.get_attribute("href") == "t3code://threads/env-1/lead-thread" and "Neon · Paper · Pixel" in page.locator(".c-block").inner_text()
        assert "Build · Opus" in page.locator(".c-lanes").inner_text()
        assert page.locator(".l-row").count() == 2 and page.locator(".mo").count() == 2
        assert "running" in page.locator(".l-row").first.inner_text() or "running" in page.locator(".l-row").nth(1).inner_text()
        assert page.locator(".rib-span").count() > 0, "closed starts draw as bars"
        assert "Key update" in page.locator('.chapter[data-ch="c2"] .keys').inner_text(), "[key] beats outrank ordinary results"
        assert page.locator(".mo-n span", has_text="Haiku").count() == 1, "a lane's default model counts its unlabelled starts"
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        page.locator('.chapter[data-ch="c1"] .keys button').first.click()
        page.locator("#mTitle").wait_for()
        hrefs = page.evaluate("[...document.querySelectorAll('#sheet .links a')].map(a => a.getAttribute('href'))")
        assert hrefs == ["reports/ok.md", "https://example.com/x"], hrefs
        page.keyboard.press("Escape")
        page.locator('[data-view="highlights"]').click()
        assert 3 <= page.locator(".beat").count() <= 12
        page.locator('[data-view="full"]').click()
        assert page.locator(".beat").count() > 80
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        assert not errors, errors
        print(f"PASS story view at {width}: key beats, digest override, expand, highlights/full, lanes+models, choices, T3 links")
        context.close()


if __name__ == "__main__":
    main()
