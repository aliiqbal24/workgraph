"""Optional browser acceptance test. Requires Playwright and Chromium.

Runs a separate browser against a disposable repository; never controls the
user's normal browser or stores their operator token in an artifact.
"""

import json
from pathlib import Path
import tempfile
import threading
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from workgraph.example import Example
from workgraph.server import Application, make_server
from playwright.sync_api import sync_playwright


def run(output=None):
    with tempfile.TemporaryDirectory(prefix="workgraph-browser-") as directory:
        example = Example.create(Path(directory) / "repository")
        app = Application(example.engine, example)
        server = make_server(app, 0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        address = f"http://127.0.0.1:{server.server_address[1]}/engineering#token={app.token}"
        try:
            with sync_playwright() as pw:
                browser = pw.chromium.launch(executable_path="/usr/bin/chromium", headless=True, args=["--no-sandbox"])
                page = browser.new_page(viewport={"width": 1600, "height": 1000}, device_scale_factor=1)
                errors = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.goto(address)
                page.get_by_text("Connected locally", exact=True).wait_for()
                page.get_by_role("button", name="Start two pieces of work").click()
                page.get_by_text("Which clients still read the name field?", exact=True).wait_for()
                assert page.locator(".work-card").count() == 2
                if output:
                    page.screenshot(path=str(Path(output) / "01-work.png"))
                page.get_by_role("button", name="Interrupt the API session").click()
                page.get_by_text("The session stopped. The work survived.", exact=True).wait_for()
                assert page.get_by_text("Which clients still read the name field?", exact=True).is_visible()
                page.get_by_role("button", name="Hand the work to Codex").click()
                page.get_by_text("A dependency changed. Nothing is silently overwritten.", exact=True).wait_for()
                page.get_by_text("dependency changed", exact=True).wait_for()
                assert page.locator(".dependency-note").count() >= 1
                if output:
                    page.screenshot(path=str(Path(output) / "02-dependency-changed.png"))
                page.get_by_role("button", name="Reconcile and check the client").click()
                page.get_by_text("A clean merge can still be wrong.", exact=True).wait_for()
                page.get_by_text("failed", exact=True).first.wait_for()
                assert "KeyError" in page.locator(".check-output").first.inner_text()
                assert page.get_by_role("button", name="Accept checked candidate").count() == 0
                page.get_by_role("button", name="Repair and check a new candidate").click()
                page.get_by_text("An exact candidate, with current evidence.", exact=True).wait_for()
                page.get_by_role("button", name="Accept checked candidate").wait_for()
                if output:
                    page.screenshot(path=str(Path(output) / "03-checked-candidate.png"))
                page.get_by_role("button", name="Accept the checked candidate", exact=False).last.click()
                page.get_by_text("One clean Git change. The full story stays available.", exact=True).wait_for()
                page.get_by_text("accepted", exact=True).wait_for()
                assert example.engine.git("rev-list", "--count", f"{example.state()['base']}..{example.engine.TARGET}").strip() == "1"
                page.get_by_role("button", name="Work", exact=False).first.click()
                page.get_by_role("button", name="New work", exact=False).click()
                page.get_by_placeholder("Migrate the profile API").fill("A real UI-created task")
                page.get_by_role("button", name="Create isolated attempt").click()
                page.get_by_text("A real UI-created task", exact=True).first.wait_for()
                assert len(example.engine.status()["work"]) == 3
                page.set_viewport_size({"width": 390, "height": 844})
                assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
                assert not errors, errors
                browser.close()
                return {"passed": True, "flow": "interruption → takeover → outdated dependency → failed check → repair → acceptance",
                        "ui_created_work": True, "mobile_overflow": False, "browser_errors": errors}
        finally:
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    output = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    if output:
        output.mkdir(parents=True, exist_ok=True)
    print(json.dumps(run(output), indent=2))
