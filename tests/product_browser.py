"""Actual browser → operator API → SQLite snapshot → replay → reopening story.
Run with a Python containing Playwright and Pillow. No model calls.
"""

import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import threading
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from workgraph.showcase import Showcase
from workgraph.server import Application, make_server
from workgraph.product_state import ProductState
from playwright.sync_api import sync_playwright


def run(output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    errors = []
    with tempfile.TemporaryDirectory(prefix="workgraph-product-qa-") as directory:
        engine = Showcase.create(Path(directory) / "fieldwork")
        app = Application(engine, autocapture=False)
        server = make_server(app, 0)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{server.server_address[1]}"
        initial = app.studio.history()
        original = initial["current"]
        app.artifacts.request(original)
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(
                    executable_path="/usr/bin/chromium",
                    headless=True,
                    args=["--no-proxy-server"],
                )
                context = browser.new_context(viewport={"width": 1600, "height": 1000})
                page = context.new_page()
                page.on("pageerror", lambda e: errors.append(str(e)))
                page.goto(base + "/#token=" + app.token)
                page.locator(".node").first.wait_for()
                page.get_by_role(
                    "button", name="Our next idea, saved with the product.", exact=False
                ).click()
                assert "#token" not in page.url
                page.locator("#open-app").click()
                page.locator(".live-main iframe").wait_for(timeout=30000)
                frame = page.frame_locator(".live-main iframe")
                frame.locator("h1").wait_for()
                page.locator("#record-flow").click()
                frame.get_by_test_id("open-issue-1").click()
                frame.get_by_label("Add a comment").fill(
                    "Keep this little conversation."
                )
                frame.get_by_role("button", name="Post comment").click()
                frame.get_by_test_id("comment-list").get_by_text(
                    "Keep this little conversation."
                ).wait_for()
                page.locator("#live-reload").click()
                frame.get_by_test_id("comment-list").get_by_text(
                    "Keep this little conversation."
                ).wait_for()
                page.locator("#expect-flow").click()
                frame.get_by_test_id("comment-list").get_by_text(
                    "Keep this little conversation."
                ).click()
                page.locator("#save-flow").wait_for()
                page.screenshot(path=str(output / "01-record-behavior.png"))
                page.locator("#save-flow").click()
                page.locator("#flow-form input[name=name]").fill(
                    "A conversation survives refresh"
                )
                page.locator("#flow-form button").click()
                page.locator("#dialog").wait_for(state="hidden")
                assert len(app.behaviors.list(original)) == 4
                page.locator("#open-app").click()
                page.locator(".live-main iframe").wait_for()
                frame = page.frame_locator(".live-main iframe")
                frame.get_by_test_id("open-issue-1").click()
                frame.get_by_test_id("comment-list").get_by_text(
                    "Keep this little conversation."
                ).wait_for()
                before = ProductState(engine).get(original)["fingerprint"]
                page.locator("#save-data").click()
                page.locator("#dialog").wait_for(state="hidden")
                page.get_by_role(
                    "heading", name="An interactive exploration", exact=True
                ).wait_for()
                history = app.studio.history()
                new = history["versions"][-1]["id"]
                assert new != original
                assert ProductState(engine).get(original)["fingerprint"] == before
                assert ProductState(engine).get(new)["fingerprint"] != before
                assert (
                    app.studio.revision(new)["tree_oid"]
                    == app.studio.revision(original)["tree_oid"]
                )
                assert history["current"] == original
                # Reopening a tab restores browse selection, camera, and controls.
                camera = page.locator("#world").get_attribute("style")
                page.reload()
                page.get_by_role(
                    "heading", name="An interactive exploration", exact=True
                ).wait_for()
                assert page.locator("#world").get_attribute("style") == camera
                assert app.studio.history()["current"] == original
                deadline = time.monotonic() + 75
                while time.monotonic() < deadline:
                    proof = app.behaviors.latest(new)
                    if proof["state"] not in ("queued", "running", "unverified"):
                        break
                    time.sleep(0.2)
                assert proof["state"] == "passed", proof
                custom = app.behaviors.list(new)[-1]
                assert any(
                    "{run}" in str(step) for step in custom["definition"]["steps"]
                ), custom
                broken = app.studio.branch(
                    new, "A broken save with old example text still present"
                )
                backend = Path(broken["workspace"]) / "app.py"
                backend.write_text(
                    backend.read_text().replace(
                        "SAVE_COMMENTS=True", "SAVE_COMMENTS=False"
                    )
                )
                bad = engine.checkpoint(
                    broken["attempt"], "A broken comment save", select=False
                )["revision"]
                app.artifacts.request(bad)
                deadline = time.monotonic() + 75
                while time.monotonic() < deadline:
                    bad_proof = app.behaviors.latest(bad)
                    if bad_proof["state"] not in ("queued", "running", "unverified"):
                        break
                    time.sleep(0.2)
                assert (
                    next(r for r in bad_proof["results"] if r["id"] == custom["id"])[
                        "passed"
                    ]
                    is False
                ), bad_proof
                page.reload()
                page.get_by_role(
                    "heading", name="An interactive exploration", exact=True
                ).wait_for()
                page.screenshot(path=str(output / "02-saved-state.png"))
                page.get_by_role(
                    "button", name="A conversation survives refresh", exact=False
                ).click()
                video = page.locator("video")
                video.wait_for()
                assert video.get_attribute("src").endswith(".webm")
                page.locator("#close-dialog").click()
                # Browsing does not alter files and viewing links cannot edit.
                viewer = browser.new_context(viewport={"width": 390, "height": 844})
                view = viewer.new_page()
                view.goto(base + "/#view=" + app.viewer)
                view.locator(".node").first.wait_for()
                assert view.locator("#new-direction").is_disabled()
                assert view.evaluate("document.documentElement.scrollWidth") <= 390
                response = view.request.post(
                    base + "/api/action",
                    headers={"Authorization": "Bearer " + app.viewer},
                    data={"action": "studio.choose", "revision": new},
                )
                assert response.status == 403
                view.screenshot(path=str(output / "03-phone.png"))
                viewer.close()
                context.close()
                browser.close()
            assert not errors, errors
            report = {
                "story": "record → protect → replay → save interactions → restore code/data → reopen → view-only link",
                "checks": "passed",
                "protected_flows": proof["total"],
                "page_errors": errors,
                "original_state_preserved": True,
                "source_unchanged_on_data_save": True,
                "chosen_direction_unchanged": True,
                "old_fixture_cannot_mask_broken_save": True,
            }
            (output / "report.json").write_text(json.dumps(report, indent=2))
            print(json.dumps(report, indent=2))
        finally:
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    run(sys.argv[1] if len(sys.argv) > 1 else "/tmp/workgraph-product-browser")
