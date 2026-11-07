"""Explicit live runtime acceptance. Uses existing agent logins; consumes model usage.

Not included in unit discovery. Run deliberately when live integration is needed.
"""
import json
from pathlib import Path
import sys,threading,time,uuid
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from workgraph.playground import Playground
from workgraph.server import Application,make_server
from playwright.sync_api import sync_playwright


def run(directory):
    out=Path(directory);out.mkdir(parents=True,exist_ok=True)
    engine=Playground.create(out/('project-'+uuid.uuid4().hex[:8]))
    app=Application(engine);server=make_server(app,0)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    record={"repository":str(engine.repo),"runtimes":[],"original_current":app.studio.history()["current"]}
    def save(): (out/'result.json').write_text(json.dumps(record,indent=2))
    def wait_job(runtime):
        deadline=time.monotonic()+260
        while time.monotonic()<deadline:
            jobs=app.studio.history()['jobs']
            job=next((j for j in jobs if j['runtime']==runtime),None)
            if job and job['state'] not in ('queued','running'):
                print(runtime,job['state'],job.get('error'),flush=True)
                if job['state']!='completed':
                    print(job['output'][-6000:],flush=True)
                    record['error']={"runtime":runtime,"state":job['state'],"message":job.get('error')};save()
                    raise AssertionError(runtime+' did not complete')
                return job
            time.sleep(.5)
        raise AssertionError('Runtime timed out')
    try:
        with sync_playwright() as pw:
            browser=pw.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox'])
            page=browser.new_page(viewport={'width':1600,'height':1350})
            page.goto(f'http://127.0.0.1:{server.server_address[1]}/classic#token={app.token}')
            page.get_by_text('Connected locally',exact=True).wait_for()
            page.get_by_role('button',name='Continue with an agent',exact=False).click()
            page.get_by_label('Name this direction').fill('A direction that outlives its worker')
            page.get_by_label('What would you like to try?').fill('Resume the attached Workgraph attempt; do not create or fork another attempt. First use the workgraph history action to inspect saved versions. Change only components/hero.js: replace the headline A little warmth.<br><em>A lot of home.</em> with Small objects.<br><em>Brighter days.</em>. Keep the existing layout and colors and every other file unchanged. Use the workgraph checkpoint action with summary A brighter headline and a decision to preserve the warm layout. Stop after saving.')
            page.get_by_label('Continue with',exact=True).select_option('hermes')
            page.get_by_role('button',name='Start exploring',exact=False).click()
            first=wait_job('hermes');state=app.studio.history();path=next(p for p in state['paths'] if p['id']==first['path'])
            original=record['original_current'];head=path['head']
            assert b'Small objects.' in app.studio.read(head,'components/hero.js')
            for f in app.studio.files(original):
                if f!='components/hero.js':assert app.studio.read(head,f)==app.studio.read(original,f),f
            record['runtimes'].append({'runtime':'hermes','job':first['id'],'path':path['id'],'revision':head,'state':'completed','only_requested_file_changed':True})
            save();print('Hermes produced a real saved version through the UI.',flush=True)
            page.reload();page.get_by_text('Connected locally',exact=True).wait_for()
            page.locator(f'button.path-button[data-view="{head}"]').click()
            page.frame_locator('iframe').first.get_by_role('heading',name='Small objects. Brighter days.').wait_for()
            page.screenshot(path=str(out/'hermes-result.png'))
            count=len(state['paths']);hero=app.studio.read(head,'components/hero.js')
            page.get_by_role('button',name='Continue with an agent',exact=False).click()
            assert page.locator('#reuse-path').is_checked()
            page.get_by_label('Continue with',exact=True).select_option('codex')
            page.get_by_label('What would you like to try?').fill('Resume the attached Workgraph attempt; do not create or fork another attempt. Inspect the saved context with the read-only workgraph_read tool. Another worker already changed the hero to Small objects / Brighter days; preserve that file byte for byte. Change only components/navigation.js: replace Explore objects with Find your glow. Keep everything else unchanged. If the normal workgraph checkpoint tool needs approval, do not call or bypass it. The launcher will automatically save the source on exit. Report your completed result and stop.')
            page.get_by_role('button',name='Start exploring',exact=False).click()
            second=wait_job('codex');state=app.studio.history();continued=next(p for p in state['paths'] if p['id']==path['id'])
            assert len(state['paths'])==count
            assert second['path']==first['path']
            assert app.studio.read(continued['head'],'components/hero.js')==hero
            assert b'Find your glow' in app.studio.read(continued['head'],'components/navigation.js')
            assert engine.resume(first['attempt_id'])['state']=='superseded'
            assert state['current']==original
            record['runtimes'].append({'runtime':'codex','job':second['id'],'path':continued['id'],'revision':continued['head'],'state':'completed','same_named_path':True,'previous_hero_preserved':True})
            page.reload();page.get_by_text('Connected locally',exact=True).wait_for()
            page.locator(f'button.path-button[data-view="{continued["head"]}"]').click()
            page.frame_locator('iframe').first.get_by_role('link',name='Find your glow',exact=False).wait_for()
            page.screenshot(path=str(out/'cross-runtime-result.png'))
            browser.close()
            record.update(passed=True,current_direction_unchanged=True,path_count=count)
            save();return record
    finally:server.shutdown();server.server_close()


if __name__=='__main__':
    print(json.dumps(run(sys.argv[1] if len(sys.argv)>1 else '/home/ali/.cache/workgraph/live-exploration'),indent=2))
