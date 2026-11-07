"""Dedicated browser worker. JSON lines in/out; never model-provided Python/JS."""

import json, sys, os, hashlib, time, uuid
from pathlib import Path
from urllib.parse import urlsplit


def main():
    from playwright.sync_api import sync_playwright, expect

    with sync_playwright() as p:
        executable = os.environ.get("WORKGRAPH_CHROMIUM") or next(
            (
                x
                for x in ("/usr/bin/chromium", "/usr/bin/google-chrome")
                if Path(x).exists()
            ),
            None,
        )
        args = ["--no-proxy-server", "--disable-dev-shm-usage"]
        if os.environ.get("WORKGRAPH_BROWSER_NO_SANDBOX") == "1":
            args.append("--no-sandbox")
        browser = p.chromium.launch(
            executable_path=executable, headless=True, args=args
        )
        for line in sys.stdin:
            try:
                command = json.loads(line)
                root = Path(command["output"])
                root.mkdir(parents=True, exist_ok=True)
                origin = urlsplit(command["url"])
                allowed = (origin.scheme, origin.netloc)
                results = []
                context = None
                video = None
                errors = []

                def context_for(width, height, record=False):
                    ctx = browser.new_context(
                        viewport={"width": width, "height": height},
                        device_scale_factor=1,
                        reduced_motion="reduce",
                        record_video_dir=str(root / "videos") if record else None,
                        record_video_size={"width": width, "height": height}
                        if record
                        else None,
                    )
                    ctx.route(
                        "**/*",
                        lambda route: (
                            route.continue_()
                            if (
                                urlsplit(route.request.url).scheme,
                                urlsplit(route.request.url).netloc,
                            )
                            == allowed
                            or route.request.url.startswith(("data:", "blob:"))
                            else route.abort()
                        ),
                    )
                    return ctx

                if command["kind"] == "gallery":
                    for index, screen in enumerate(command["screens"]):
                        width, height = (
                            screen.get("width", 1280),
                            screen.get("height", 800),
                        )
                        context = context_for(width, height)
                        page = context.new_page()
                        page.set_default_timeout(6000)
                        page.goto(
                            command["url"] + screen.get("path", "/").lstrip("/"),
                            wait_until="domcontentloaded",
                            timeout=12000,
                        )
                        if screen.get("ready"):
                            page.locator(screen["ready"]).first.wait_for()
                        else:
                            page.wait_for_timeout(350)
                        page.evaluate("document.fonts.ready")
                        page.wait_for_timeout(120)
                        path = root / f"screen-{index}.jpg"
                        page.screenshot(path=str(path), type="jpeg", quality=88)
                        from PIL import Image

                        thumb = root / f"thumb-{index}.jpg"
                        image = Image.open(path)
                        image.thumbnail((480, 320))
                        image.save(thumb, quality=82)
                        results.append(
                            {
                                "name": screen["name"],
                                "path": screen.get("path", "/"),
                                "file": str(path),
                                "thumb": str(thumb),
                                "width": width,
                                "height": height,
                            }
                        )
                        context.close()
                        context = None
                    response = {"images": results, "browser": browser.version}
                else:
                    definition = json.loads(
                        json.dumps(command["flow"]["definition"]).replace(
                            "{run}", uuid.uuid4().hex[:10]
                        )
                    )
                    viewport = definition["viewport"]
                    context = context_for(viewport["width"], viewport["height"], True)
                    page = context.new_page()
                    page.set_default_timeout(4500)
                    page.on("pageerror", lambda error: errors.append(str(error)[:500]))
                    steps = []
                    passed = True
                    message = None
                    try:
                        page.goto(
                            command["url"] + definition.get("path", "/").lstrip("/"),
                            wait_until="domcontentloaded",
                            timeout=12000,
                        )
                        page.wait_for_timeout(250)
                        for index, step in enumerate(definition["steps"]):
                            action = step["action"]
                            start = time.time()
                            if action == "goto":
                                page.goto(
                                    command["url"] + step["value"].lstrip("/"),
                                    wait_until="domcontentloaded",
                                )
                            elif action == "reload":
                                page.reload(wait_until="domcontentloaded")
                            elif action == "visual":
                                from PIL import Image, ImageChops

                                page.wait_for_timeout(250)
                                actual = root / "actual.png"
                                page.screenshot(path=str(actual))
                                baseline = Image.open(
                                    command["baselines"][step["baseline"]]
                                ).convert("RGB")
                                current = Image.open(actual).convert("RGB")
                                if baseline.size != current.size:
                                    raise AssertionError(
                                        "The preview dimensions differ from the approved baseline."
                                    )
                                crop = step.get("crop")
                                if crop:
                                    box = (
                                        int(crop["x"]),
                                        int(crop["y"]),
                                        int(crop["x"] + crop["width"]),
                                        int(crop["y"] + crop["height"]),
                                    )
                                    baseline = baseline.crop(box)
                                    current = current.crop(box)
                                diff = ImageChops.difference(baseline, current)
                                pixels = list(diff.getdata())
                                fraction = sum(
                                    max(pixel) > 22 for pixel in pixels
                                ) / max(1, len(pixels))
                                if fraction > step.get("tolerance", 0.025):
                                    raise AssertionError(
                                        f"{fraction:.1%} of the protected area changed; expected at most {step.get('tolerance', 0.025):.1%}."
                                    )
                            else:
                                selector = step["locator"]
                                kind = selector["type"]
                                value = selector["value"]
                                loc = (
                                    page.get_by_test_id(value)
                                    if kind == "testid"
                                    else page.get_by_label(value, exact=True)
                                    if kind == "label"
                                    else page.get_by_role(
                                        selector["role"], name=value, exact=True
                                    )
                                    if kind == "role"
                                    else page.locator(value)
                                )
                                if action == "click":
                                    loc.click()
                                elif action == "fill":
                                    loc.fill(step["value"])
                                elif action == "select":
                                    loc.select_option(step["value"])
                                elif action == "press":
                                    loc.press(step["value"])
                                elif action == "expect":
                                    expect(loc).to_contain_text(step["text"])
                                elif action == "expect_hidden":
                                    expect(loc).to_be_hidden()
                            steps.append(
                                {
                                    "step": index + 1,
                                    "action": action,
                                    "passed": True,
                                    "seconds": round(time.time() - start, 3),
                                }
                            )
                            page.wait_for_timeout(110)
                    except Exception as error:
                        passed = False
                        message = str(error).split("Call log:")[0].strip()[:1000]
                        steps.append(
                            {
                                "step": len(steps) + 1,
                                "action": definition["steps"][
                                    min(len(steps), len(definition["steps"]) - 1)
                                ]["action"],
                                "passed": False,
                                "error": message,
                            }
                        )
                    page.wait_for_timeout(250)
                    path = root / "result.jpg"
                    page.screenshot(path=str(path), type="jpeg", quality=88)
                    video = page.video
                    context.close()
                    context = None
                    response = {
                        "passed": passed,
                        "error": message,
                        "steps": steps,
                        "screenshot": str(path),
                        "video": str(video.path()) if video else None,
                        "browser": browser.version,
                        "page_errors": errors,
                    }
                print(json.dumps({"ok": True, **response}), flush=True)
            except Exception as error:
                if "context" in locals() and context:
                    try:
                        context.close()
                    except Exception:
                        pass
                print(
                    json.dumps(
                        {"ok": False, "error": f"{type(error).__name__}: {error}"}
                    ),
                    flush=True,
                )
        browser.close()


if __name__ == "__main__":
    main()
