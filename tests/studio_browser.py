"""Real browser acceptance of the five exploration stories. No model calls."""
import json
from pathlib import Path
import tempfile
import threading
import sys
import subprocess
import zipfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from workgraph.playground import Playground
from workgraph.engine import Engine
from workgraph.server import Application,make_server
from playwright.sync_api import sync_playwright


def run(output):
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="workgraph-browser-stories-") as directory:
        engine=Playground.create(Path(directory)/"Luma")
        refs=json.loads((engine.home/"playground.json").read_text())
        app=Application(engine);server=make_server(app,0)
        threading.Thread(target=server.serve_forever,daemon=True).start()
        address=f"http://127.0.0.1:{server.server_address[1]}/#token={app.token}"
        errors=[];console=[]
        try:
            with sync_playwright() as p:
                browser=p.chromium.launch(executable_path="/usr/bin/chromium",headless=True,args=["--no-sandbox"])
                page=browser.new_page(viewport={"width":1600,"height":1350})
                page.on("pageerror",lambda e:errors.append(str(e)))
                page.on("console",lambda m:console.append(m.text) if m.type=="error" else None)
                page.goto(address);page.get_by_text("Connected locally",exact=True).wait_for()
                page.frame_locator("iframe").first.get_by_role("heading",name="A little warmth. A lot of home.").wait_for()
                page.get_by_role("button",name="Find a version",exact=False).click()
                page.get_by_label("Find a saved version",exact=True).fill("busier")
                # Search matches saved decisions/notes as well as the visible title.
                page.get_by_label("Find a saved version",exact=True).fill("promotion")
                page.locator(".version-result").first.click()
                page.frame_locator("iframe").first.get_by_role("heading",name="BIG IDEAS. BRIGHTER LIVING.").wait_for()
                page.get_by_role("button",name="Open The warm, simple version",exact=True).click()
                page.screenshot(path=str(output/"01-explore.png"))
                page.get_by_role("button",name="Open Tried more promotion and content",exact=True).click()
                page.frame_locator("iframe").first.get_by_role("heading",name="BIG IDEAS. BRIGHTER LIVING.").wait_for()
                assert app.studio.history()["current"]==refs["warm"]
                page.get_by_role("button",name="Open First working homepage",exact=True).click()
                page.get_by_role("button",name="Make current",exact=False).click()
                page.get_by_text("CURRENT DIRECTION",exact=True).wait_for()
                assert app.studio.history()["current"]==refs["first"]
                page.reload();page.get_by_text("CURRENT DIRECTION",exact=True).wait_for()
                assert engine.git("rev-list","--count",engine.TARGET).strip()=="1"
                page.get_by_role("button",name="Open The warm, simple version",exact=True).click()
                page.get_by_role("button",name="Try another direction",exact=True).click()
                page.get_by_label("Name this direction").fill("A new idea from the warm page")
                page.get_by_label("What would you like to try?").fill("Keep the calm feeling; explore another layout.")
                page.get_by_role("button",name="Create direction",exact=False).click()
                page.get_by_role("button",name="Open Start A new idea from the warm page",exact=True).wait_for()
                created=next(p for p in app.studio.history()["paths"] if p["name"]=="A new idea from the warm page")
                assert created["origin"]==refs["warm"]
                assert app.studio.history()["current"]==refs["first"]
                page.get_by_role("button",name="Compare versions",exact=False).click()
                page.get_by_label("Starting version",exact=True).select_option(refs["warm"])
                page.get_by_label("Source version",exact=True).select_option(refs["playful"])
                page.get_by_text("Keep the parts you like.",exact=True).wait_for()
                page.frame_locator("iframe").nth(0).get_by_role("heading",name="A little warmth. A lot of home.").wait_for()
                page.frame_locator("iframe").nth(1).get_by_role("heading",name="Objects with a bright side.").wait_for()
                assert page.frames[1].evaluate("innerWidth")==1100
                assert page.frames[2].evaluate("innerWidth")==1100
                page.screenshot(path=str(output/"02-compare.png"))
                page.locator('input[data-file="components/navigation.js"]').check()
                page.get_by_role("button",name="Bring 1 part into a new path",exact=False).click()
                page.get_by_label("Name this direction").fill("Warm layout, playful navigation")
                page.get_by_role("button",name="Create combined version",exact=False).click()
                page.get_by_role("button",name="Open Warm layout, playful navigation",exact=True).wait_for()
                frame=page.frame_locator("iframe").first
                frame.get_by_role("heading",name="A little warmth. A lot of home.").wait_for()
                frame.get_by_role("link",name="Find your favorite",exact=False).wait_for()
                page.screenshot(path=str(output/"03-combination.png"))
                combined=next(v for v in app.studio.history()["versions"] if v["title"]=="Warm layout, playful navigation")
                assert app.studio.read(combined["id"],"components/hero.js")==app.studio.read(refs["warm"],"components/hero.js")
                assert app.studio.read(combined["id"],"components/navigation.js")==app.studio.read(refs["playful"],"components/navigation.js")
                assert app.studio.history()["current"]==refs["first"]
                page.get_by_role("button",name="Make current",exact=False).click()
                with page.expect_download() as exported:
                    page.get_by_role("button",name="Download this version",exact=False).click()
                downloaded=output/"chosen-version.zip";exported.value.save_as(downloaded)
                with zipfile.ZipFile(downloaded) as z:
                    assert z.read("components/navigation.js")==app.studio.read(refs["playful"],"components/navigation.js")
                    assert z.read("components/hero.js")==app.studio.read(refs["warm"],"components/hero.js")
                page.get_by_role("button",name="Continue with an agent",exact=False).click()
                assert "Warm layout, playful navigation" in page.locator("dialog").inner_text()
                assert page.get_by_label("Continue with",exact=True).input_value()=="hermes"
                page.locator("#reuse-path").uncheck()
                page.get_by_label("Name this direction").fill("A second opinion")
                page.get_by_label("What would you like to try?").fill("Check the navigation and keep this warm layout.")
                page.screenshot(path=str(output/"04-agent-start.png"))
                page.get_by_role("button",name="Close",exact=True).click()
                # Saved preview origin cannot read the operator app or its storage.
                sandbox=page.locator("iframe").get_attribute("sandbox")
                assert sandbox=="allow-scripts"
                frame_object=page.frames[1]
                assert frame_object.evaluate("(()=>{try{return parent.document.body.innerText}catch(e){return 'blocked'}})()")=='blocked'
                assert frame_object.evaluate("(()=>{try{return localStorage.length}catch(e){return 'blocked'}})()")=='blocked'
                page.get_by_role("button",name="Expand preview",exact=True).click()
                page.locator("dialog iframe").wait_for();page.get_by_role("button",name="Close",exact=True).click()
                page.set_viewport_size({"width":390,"height":844});page.wait_for_timeout(250)
                assert page.evaluate("document.documentElement.scrollWidth<=innerWidth")
                page.screenshot(path=str(output/"05-phone.png"))
                assert not errors,errors
                assert not console,console
                # Start from a person's own dirty checkout, rather than a sample.
                own=Path(directory)/"own-project";own.mkdir()
                subprocess.run(["git","init","-q","-b","main",str(own)],check=True)
                (own/"index.html").write_text("<h1>Original page</h1>")
                (own/".gitignore").write_text("ignored.local\n")
                subprocess.run(["git","-C",str(own),"add","."],check=True)
                subprocess.run(["git","-C",str(own),"-c","user.name=Test","-c","user.email=test@localhost","commit","-qm","Initial"],check=True)
                (own/"index.html").write_text("<h1>My unsaved page</h1>")
                (own/"notes.txt").write_text("An untracked project file")
                (own/"ignored.local").write_text("Not part of this saved source")
                own_engine=Engine(own);own_engine.init();index=own_engine.git("write-tree")
                own_app=Application(own_engine);own_server=make_server(own_app,0)
                threading.Thread(target=own_server.serve_forever,daemon=True).start()
                try:
                    own_page=browser.new_page(viewport={"width":1440,"height":1000},accept_downloads=True)
                    own_page.on("pageerror",lambda e:errors.append(str(e)))
                    own_page.goto(f"http://127.0.0.1:{own_server.server_address[1]}/#token={own_app.token}")
                    own_page.get_by_role("button",name="Save a starting point",exact=True).click()
                    own_page.get_by_label("Name this starting point").fill("My real starting point")
                    own_page.get_by_role("button",name="Save starting point",exact=True).click()
                    own_page.frame_locator("iframe").first.get_by_role("heading",name="My unsaved page").wait_for()
                    with own_page.expect_download() as exported:
                        own_page.get_by_role("button",name="Download this version",exact=False).click()
                    own_download=output/"own-project.zip";exported.value.save_as(own_download)
                    with zipfile.ZipFile(own_download) as z:
                        assert z.read("index.html")==b"<h1>My unsaved page</h1>"
                        assert z.read("notes.txt")==b"An untracked project file"
                        assert "ignored.local" not in z.namelist()
                    assert own_engine.git("write-tree")==index
                    assert (own/"index.html").read_text()=="<h1>My unsaved page</h1>"
                    starting=own_app.studio.history()["current"]
                    built=own_app.studio.branch(starting,"Built static app");built_root=Path(built["workspace"])
                    (built_root/"index.html").write_text('<script type="module" src="/src/main.tsx"></script>');(built_root/"dist/assets").mkdir(parents=True)
                    (built_root/"dist/index.html").write_text('<html><head><link rel="stylesheet" href="/assets/theme.css"><script type="module" src="/assets/main.js"></script></head><body></body></html>')
                    (built_root/"dist/assets/theme.css").write_text('h1{color:rgb(32, 64, 96)}')
                    (built_root/"dist/assets/main.js").write_text('import {label} from "/assets/module.js";document.body.innerHTML="<h1>"+label+"</h1>"')
                    (built_root/"dist/assets/module.js").write_text('export const label="Built static preview"')
                    built_revision=own_engine.checkpoint(built["attempt"],"Built static preview",select=False)["revision"]
                    own_page.reload();own_page.get_by_role("button",name="Open Built static preview",exact=True).click()
                    own_page.frame_locator("iframe").first.get_by_role("heading",name="Built static preview",exact=True).wait_for()
                    assert own_page.frames[1].evaluate('getComputedStyle(document.querySelector("h1")).color')=="rgb(32, 64, 96)"
                    own_page.close()
                finally:own_server.shutdown();own_server.server_close()
                assert not errors,errors
                browser.close()
                result={"passed":True,"stories":["recover an earlier version","branch from an exact saved point","compare runnable pages","bring selected changes","prepare cross-runtime continuation"],"own_project_start_and_download":True,"built_static_css_and_modules":True,"combination_download_byte_match":True,"combination_preserves_originals":True,"saved_preview_isolation":True,"mobile_overflow":False,"browser_errors":errors,"console_errors":console,"model_calls":0}
                (output/"result.json").write_text(json.dumps(result,indent=2));return result
        finally:server.shutdown();server.server_close()


if __name__=="__main__":print(json.dumps(run(sys.argv[1] if len(sys.argv)>1 else "/tmp/workgraph-studio-qa"),indent=2))
