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
STORE = "live-timeline:/:"
stamp = lambda t: t.isoformat(timespec="seconds")
SMALL = """() => [...document.querySelectorAll('button, a[href], input, select, textarea, [tabindex="0"]')].filter(el => {
  const r = el.getBoundingClientRect(); return r.width && r.height && !el.closest('[hidden]') && (r.width < 40 || r.height < 40); }).map(el => el.outerHTML.slice(0, 80))"""
ROWS = """() => { const l = document.querySelector('.m-live .list'), L = l.getBoundingClientRect(), b = Math.min(L.bottom, innerHeight);
  return [...l.querySelectorAll('.row')].filter(r => { const x = r.getBoundingClientRect(); return x.top >= L.top - .5 && x.bottom <= b + .5; }).length; }"""


def serve(page, html, feed, state=None):
    def handle(route):
        url = urlsplit(route.request.url)
        assert url.hostname == "timeline.test", route.request.url
        if url.path == "/":
            route.fulfill(body=html, content_type="text/html")
        elif url.path == "/live/events.json":
            route.fulfill(body="{" if state and state.get("malformed") else json.dumps(feed), content_type="application/json")
        elif url.path.endswith(".svg"):
            route.fulfill(body=SVG, content_type="image/svg+xml")
        else:
            route.fulfill(status=404, body="")
    page.route("**/*", handle)


def open_page(browser, html, feed, width=1280, height=900, scheme="dark", mode=None, init="", clock=False, state=None, hash=""):
    context = browser.new_context(viewport={"width": width, "height": height}, color_scheme=scheme)
    page = context.new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    if mode:
        init += f"localStorage.setItem('{STORE}mode', '{mode}');"
    if init:
        page.add_init_script(init)
    serve(page, html, feed, state)
    if clock:
        page.clock.install()
    page.goto("https://timeline.test/" + hash)
    page.locator("#runTitle").filter(has_text=feed["run"]["title"]).wait_for(state="attached")
    page.wait_for_function("document.querySelector('.app .body')?.children.length > 0")
    return context, page, errors


def switch(page, mode):
    page.locator(f'[data-mv="{mode}"]').filter(visible=True).first.click()
    page.locator(f".app.m-{mode}").wait_for()


def no_overflow(page, what):
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), f"sideways scroll: {what}"


def main():
    with tempfile.TemporaryDirectory(prefix="timeline-browser-") as tmp:
        work = Path(tmp) / "work"
        subprocess.run([sys.executable, str(ROOT / "skills/live-timeline/scripts/init.py"), str(work),
                        "--title", "Catalogue import", "--owner", "Owner", "--tz", "UTC"],
                       check=True, capture_output=True, env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
        base = lambda: json.loads((work / "live/events.json").read_text())
        html = (work / "live-timeline.html").read_text()
        with sync_playwright() as p:
            browser = p.chromium.launch()
            finished_import(browser, html, base())
            busy_feed(browser, html, base())
            story_and_lanes(browser, html, base())
            finished_with_open_start(browser, html, base())
            live_controls(browser, html, base())
            phones(browser, html, base())
            browser.close()


def finished_import(browser, html, feed):
    """A finished two-beat run with a snapshot: opens in Story, images and their full links, update text, cached-feed fallback."""
    now = datetime.now(timezone.utc)
    start = now - timedelta(hours=4)
    feed["run"].update(start=stamp(start), done=True)
    feed["chapters"][0].update(title="Checking the import", start=stamp(start), summary="Two passes close a small catalogue import.")
    for lane in feed["lanes"]:
        lane["status"] = "done"
    feed["events"] = [
        {"id": "e001", "time": stamp(start), "lane": "main", "kind": "start", "importance": 2, "chapter": "c1", "state": "done",
         "title": "Import starts with twelve rows", "summary": "The initial pass checks ids and required fields."},
        {"id": "e002", "time": stamp(now), "lane": "main", "kind": "success", "importance": 3, "chapter": "c1",
         "title": "All twelve rows pass verification", "summary": "The second pass confirms every stored row.",
         "why": "The owner can inspect the result and the evidence together.", "causedBy": ["e001"],
         "images": [{"path": "live/thumbs/check.svg", "caption": "Synthetic batch result", "full": "assets/check.svg"}]}]
    feed["headline"].update(status={"tone": "done", "text": "Import verified", "note": "Synthetic demonstration"},
                            progress={"value": 12, "of": 12, "label": "rows checked"}, best={"text": "12 of 12 rows match", "eventId": "e002"})
    for width in (1440, 390):
        for scheme in ("light", "dark"):
            state = {"malformed": False}
            context, page, errors = open_page(browser, html, feed, width, 1100, scheme, clock=True, state=state)
            assert page.locator('.app.m-story [data-mv="story"][aria-pressed="true"]').count() >= 1, "a finished run opens in Story"
            page.locator(".film-s img").wait_for()
            assert page.locator(".film-s img").evaluate("e => e.complete && e.naturalWidth > 0")
            assert page.locator("#feed").is_visible() and "Finished" in page.locator("#feedText").inner_text()
            assert "12 of 12 rows match" in page.locator(".hcells").inner_text()
            no_overflow(page, f"story {width}")
            page.locator(".film-s button").first.click()
            page.locator('[data-beat="e002"] .ed-imgs img').wait_for()
            assert page.locator('[data-beat="e002"] .ed-imgs a').get_attribute("href") == "assets/check.svg"
            page.locator("#updBtn").click()
            assert "All twelve rows" in page.locator("#updText").input_value()
            page.keyboard.press("Escape")
            switch(page, "live")
            assert page.locator(".m-live .brk").count() > 0, "the run map folds the four quiet hours"
            page.locator('.list .row[data-ev="e002"] .ri img').wait_for()
            no_overflow(page, f"live {width}")
            state["malformed"] = True
            page.clock.run_for(61000)
            page.wait_for_function("document.querySelector('#feedText').textContent.includes('Last good copy')")
            assert page.locator('.list .row[data-ev="e002"]').count() == 1, "the last good story stays on screen"
            assert not errors, errors
            print(f"PASS width={width} theme={scheme}: opens in Story, image and full link, folded gap, update draft, cached-feed fallback, no overflow or JS errors")
            context.close()


def finished_with_open_start(browser, html, feed):
    """A finished run whose log never closed a start: nothing reads as running and busy time stops at the run's end."""
    start = datetime.now(timezone.utc) - timedelta(hours=30)
    feed["run"].update(start=stamp(start), done=True)
    feed["lanes"] = [{"id": "build", "name": "Build", "short": "Build", "status": "done", "model": "opus"}]
    feed["chapters"][0].update(start=stamp(start))
    feed["events"] = [
        {"id": "e1", "time": stamp(start), "lane": "build", "kind": "start", "importance": 2, "chapter": "c1", "state": "running",
         "title": "Build starts", "summary": "Never closed."},
        {"id": "e2", "time": stamp(start + timedelta(hours=2)), "lane": "build", "kind": "success", "importance": 2, "chapter": "c1",
         "title": "Build ships", "summary": "Last beat."}]
    feed["metrics"] = []
    context, page, errors = open_page(browser, html, feed, hash="#e2")
    assert page.locator('[data-beat="e2"].open').count() == 1, "a #id link opens that beat"
    page.locator("#themeBtn").click()
    assert page.evaluate("document.documentElement.dataset.theme") == "light" and page.evaluate(f"localStorage.getItem('{STORE}theme')") == "light"
    page.locator('.tabs [data-id="lanes"]').click()
    row = page.locator(".lrow").first.inner_text()
    assert "running" not in row and "2 h" in row, row
    page.locator('[data-act="group"][data-v="models"]').click()
    assert page.locator(".ltab .dot").count() == 0, "a finished run has no live model"
    switch(page, "live")
    assert page.locator(".row .rn").count() == 0 and page.locator(".m-live .bar.run").count() == 0
    assert "2 h of work" in page.locator(".lanes").inner_text()
    assert not errors, errors
    print("PASS finished run with an unclosed start: not running, busy time capped at the last beat, #id link, theme toggle")
    context.close()


def busy_feed(browser, html, feed):
    """A three-day, 300-event run with many quiet gaps: the phone map keeps time order, folds the gaps, and idle lanes don't count."""
    start = datetime.now(timezone.utc) - timedelta(hours=80)
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
    context, page, errors = open_page(browser, html, feed, 390, 900)
    assert page.locator(".app.m-live").count() == 1, "a running run opens in Live"
    page.locator('[data-act="zoom"][data-z="3"]').click()
    xs = page.evaluate("[...document.querySelectorAll('.rib-s .dot')].map(d => [d.dataset.id, +d.dataset.x])")
    assert len(xs) > 200, len(xs)
    order = [x for _, x in sorted(xs, key=lambda p: times[p[0]])]
    assert all(b >= a - 0.01 for a, b in zip(order, order[1:])), "map x must follow time"
    assert page.locator(".m-live .brk").count() >= 20, "quiet gaps are folded"
    page.locator('[data-act="tab"][data-tab="now"]').click()
    assert page.locator(".nact").inner_text() == "0", "lanes marked running with nothing open and no recent beat are not active"
    no_overflow(page, "busy feed at 390")
    assert not errors, errors
    print(f"PASS busy feed at 390: {len(xs)} map dots in time order, quiet gaps folded, idle lanes not counted")
    context.close()


def story_feed(feed):
    start = datetime.now(timezone.utc) - timedelta(hours=10)
    feed["run"].update(start=stamp(start), done=False, t3={"env": "env-1", "thread": "lead-thread"}, digest=["Three chapters: build, test, ship."])
    feed["lanes"] = [feed["lanes"][0]] + [{"id": i, "name": i.title(), "short": i.title(), "status": "running"} for i in ("build", "test")]
    feed["chapters"] = [{"id": f"c{k + 1}", "title": f"Part {k + 1}", "start": stamp(start + timedelta(hours=3 * k)), "summary": f"Part {k + 1} summary."} for k in range(3)]
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
    feed["updated"] = stamp(datetime.now(timezone.utc))
    return feed


def story_and_lanes(browser, html, feed):
    """A running run: Story's key beats and digests, lanes and models, owner choices, T3 links, withheld links and every mode."""
    feed = story_feed(feed)
    for width in (390, 1280):
        context, page, errors = open_page(browser, html, feed, width)
        assert page.locator(".app.m-live").count() == 1, "a running run opens in Live"
        assert page.locator("#t3Btn").get_attribute("href") == "t3code://threads/env-1/lead-thread"
        ask = page.locator(".askbar .ask")
        assert ask.locator(".t3").get_attribute("href") == "t3code://threads/env-1/lead-thread"
        assert [ask.locator(".opt").nth(i).inner_text() for i in range(3)] == ["Neon", "Paper", "Pixel"]
        assert page.locator(".m-live .bar:not(.run)").count() > 0, "closed starts draw as bars"
        if width < 700:
            page.locator('[data-act="tab"][data-tab="now"]').click()
        lanes = page.locator(".lanes").inner_text()
        assert "Build" in lanes and "Opus" in lanes, lanes
        switch(page, "story")
        assert "Three chapters" in page.locator(".digest").inner_text()
        assert page.locator(".chap").count() == 3
        page.locator('.chap[data-ch="c1"] .chh').click()
        keys = page.locator('.chap[data-ch="c1"] .keys [data-beat]')
        assert sorted(keys.nth(i).get_attribute("data-beat") for i in range(keys.count())) == ["e003", "e010"], "keyBeats override the ranking"
        assert page.locator('.chap[data-ch="c1"] .dg').inner_text() == "Opus builds the loop."
        assert "A playable loop." in page.locator('.chap[data-ch="c1"] .co').inner_text()
        page.locator('.chap[data-ch="c2"] .chh').click()
        assert page.locator('.chap[data-ch="c2"] .keys [data-beat]').count() <= 4
        assert "Key update" in page.locator('.chap[data-ch="c2"] .keys').inner_text(), "[key] beats outrank ordinary results"
        page.locator('.chap[data-ch="c2"] [data-act="allbeats"]').click()
        assert page.locator('.chap[data-ch="c2"] .keys [data-beat]').count() > 4
        page.locator('.tabs [data-id="lanes"]').click()
        assert page.locator(".lrow").count() == 2 and "running" in page.locator(".ltab").inner_text()
        page.locator('[data-act="group"][data-v="models"]').click()
        names = page.locator(".lrow .ln b").all_inner_texts()
        assert len(names) == 2 and any("Haiku" in n for n in names), "a lane's default model counts its unlabelled starts"
        no_overflow(page, f"story {width}")
        switch(page, "detail")
        page.locator('[data-act="view"][data-id="all"]').filter(visible=True).first.click() if width >= 1040 else (
            page.locator('.qbar [data-act="drawer"]').click(), page.locator('[data-act="view"][data-id="all"]').click())
        assert page.locator(".rows .row").count() == 140, "Detail's Everything view lists every beat"
        page.locator('.rows .row[data-ev="e003"]').click()
        page.locator(".rbody .ed").wait_for()
        hrefs = page.evaluate("[...document.querySelectorAll('.rbody .ed-links a')].map(a => a.getAttribute('href'))")
        assert hrefs == ["reports/ok.md", "https://example.com/x"], hrefs
        assert page.locator(".rbody .ed-links code", has_text="withheld").count() == 3
        no_overflow(page, f"detail {width}")
        switch(page, "live")
        assert page.evaluate(f"localStorage.getItem('{STORE}mode')") == "live", "the chosen mode is remembered"
        assert not errors, errors
        print(f"PASS story and lanes at {width}: opens in Live, key beats, digest override, expand, lanes+models, choices, T3 links, withheld links, every mode")
        context.close()


def live_controls(browser, html, feed):
    """Order, collapse, new since last looked, the stale pill and an ask choice with an image."""
    feed = story_feed(feed)
    feed["events"][-1]["choices"] = [{"label": "Neon", "image": "live/thumbs/neon.svg"}, "Paper"]
    seen = json.dumps([e["id"] for e in feed["events"][:130]])
    looked = f"localStorage.setItem('{STORE}seenIds', JSON.stringify({seen})); localStorage.setItem('{STORE}lookedAt', '{int(datetime.now().timestamp() * 1000) - 3600000}');"
    context, page, errors = open_page(browser, html, feed, init=looked, clock=True)
    page.locator(".askbar .opt.img img").wait_for()
    assert page.locator(".askbar .opt.img img").evaluate("e => e.complete && e.naturalWidth > 0 && e.getAttribute('src') === 'live/thumbs/neon.svg'")
    first = page.locator(".list .row").first.get_attribute("data-ev")
    page.locator('[data-act="order"][data-o="old"]').click()
    assert page.locator(".list .row").first.get_attribute("data-ev") != first, "the order toggle changes the first row"
    assert page.evaluate(f"localStorage.getItem('{STORE}order')") == "old"
    page.locator('[data-act="order"][data-o="new"]').click()
    assert page.locator('[data-act="lens"][data-id="new"] .n').inner_text() == "10"
    assert page.locator(".list .row.new").count() == 10 and "10 new since" in page.locator(".list .seen").inner_text()
    page.locator('.list .seen [data-act="seen"]').click()
    assert page.locator(".list .row.new").count() == 0 and page.locator(".list .seen").count() == 0
    assert len(json.loads(page.evaluate(f"localStorage.getItem('{STORE}seenIds')"))) == 140
    wide = page.locator(".rib-s").evaluate("e => e.clientWidth")
    page.locator(".collb").click()
    assert not page.locator(".m-live .stream").is_visible() and page.locator(".edge").is_visible()
    assert page.locator(".rib-s").evaluate("e => e.clientWidth") > wide, "the map takes the stream's width"
    strip = page.locator(".strip").bounding_box()
    page.mouse.click(strip["x"] + strip["width"] * (0.5 / 3), strip["y"] + strip["height"] / 2)
    page.locator(".edge").click()
    assert page.locator(".m-live .stream").is_visible() and page.evaluate(f"localStorage.getItem('{STORE}collapsed')") == "0"
    top = page.evaluate("""() => { const l = document.querySelector('.list'), r = l.getBoundingClientRect();
      const row = [...l.querySelectorAll('.row')].find(x => x.getBoundingClientRect().top >= r.top + 30); return row && row.dataset.ev; }""")
    assert top and int(top[1:]) <= 46, f"a chapter picked while the stream was collapsed is where it reopens, got {top}"
    assert "Live" in page.locator("#feedText").inner_text()
    page.clock.fast_forward("31:00")
    page.wait_for_function("document.querySelector('#feedText').textContent.includes('No update for')")
    assert not errors, errors
    print("PASS live controls: order toggle, new since last looked and Mark all seen, collapse and expand, strip jump while collapsed, stale pill, choice image")
    context.close()


def phones(browser, html, feed):
    """No sideways scroll at 390, 382 and 867; no phone control under 40 px; Live keeps two stream rows on screen."""
    feed = story_feed(feed)
    for width, height in ((390, 844), (382, 678), (867, 669)):
        for mode in ("live", "detail", "story"):
            context, page, errors = open_page(browser, html, feed, width, height, mode=mode)
            no_overflow(page, f"{mode} {width}")
            if width < 700:
                small = page.evaluate(SMALL)
                assert not small, f"{mode} {width}: {small[:3]}"
            if mode == "live" and width < 700:
                rows = page.evaluate(ROWS)
                assert rows >= 2, f"Live at {width}x{height} shows {rows} whole stream rows"
            assert not errors, errors
            context.close()
    print("PASS phones: no sideways scroll at 390, 382 and 867, no control under 40 px, two stream rows in Live")


if __name__ == "__main__":
    main()
