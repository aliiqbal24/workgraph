"""A real, offline web project for exploring versions. Edits are disclosed examples."""
from pathlib import Path
import json
import subprocess

from .engine import Engine, WorkgraphError
from .studio import Studio

INDEX='''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Luma — objects for a slower life</title><link rel="stylesheet" href="style.css"><script src="components/navigation.js" defer></script><script src="components/hero.js" defer></script><script src="components/footer.js" defer></script></head><body><header id="navigation"></header><main id="hero"></main><footer id="footer"></footer></body></html>'''
STYLE='''*{box-sizing:border-box}body{margin:0;color:#302b25;background:#f3efe6;font:14px/1.5 Arial,sans-serif}a{color:inherit;text-decoration:none}button{font:inherit;cursor:pointer}header{padding:25px 6%;display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid #38302720}.logo{font:600 30px Georgia,serif;letter-spacing:-1px}nav{display:flex;gap:27px;align-items:center;font-size:11px}.nav-pill{border:1px solid #38302750;border-radius:30px;padding:9px 16px}.hero{padding:62px 7% 48px;display:grid;grid-template-columns:1.1fr 1fr;gap:30px;align-items:center;min-height:430px}.kicker{font:10px/1.5 monospace;letter-spacing:2px;text-transform:uppercase}.hero h1{font:normal clamp(40px,5vw,76px)/1.02 Georgia,serif;letter-spacing:-3px;margin:23px 0}.hero h1 em{font-weight:normal;color:#9b5940}.hero p{font-size:12px;max-width:290px;color:#777066;line-height:1.9}.cta{display:inline-block;background:#38352a;color:#fffaf0;padding:14px 20px;border-radius:3px;font-size:11px;margin-top:20px}.object{position:relative;height:330px;display:grid;place-items:center;background:#e5d9c5;border-radius:48% 48% 4px 4px;overflow:hidden}.object:before{content:'';position:absolute;width:80%;height:50%;background:#b6977040;filter:blur(20px);bottom:-14%;border-radius:50%}.lamp{position:relative;width:180px;height:220px;filter:drop-shadow(16px 22px 14px #765b3820)}.shade{position:absolute;top:0;left:0;width:180px;height:90px;background:linear-gradient(100deg,#d79c59,#efcb8c 45%,#b97d3b);border-radius:100px 100px 6px 6px;border-bottom:7px solid #9d6b3c}.stem{position:absolute;top:80px;left:84px;width:12px;height:130px;background:linear-gradient(90deg,#b07a44,#e7b777,#ad7340)}.base{position:absolute;bottom:0;left:25px;width:130px;height:17px;background:#bd8d52;border-radius:50%;box-shadow:0 5px #926537}.object-note{position:absolute;bottom:18px;left:22px;font:9px monospace;letter-spacing:1px}.collection{padding:15px 7% 26px;display:flex;align-items:center;justify-content:space-between;border-top:1px solid #38302720;font:10px monospace;letter-spacing:1px}footer{padding:16px 7%;font-size:9px;color:#8c8579;border-top:1px solid #38302720}.editorial{background:#eee8df;color:#482522}.editorial .hero{grid-template-columns:1fr 1.1fr;padding-top:42px}.editorial .hero h1{font-size:clamp(44px,6vw,86px)}.editorial .hero h1 em{color:#884732}.editorial .object{background:#c7b2a0;border-radius:2px;transform:rotate(-2deg)}.editorial .cta{background:#6c3c2f}.playful{background:#ece7fa;color:#3e2965}.playful .hero h1{font-family:Arial,sans-serif;font-weight:700;letter-spacing:-3px}.playful .hero h1 em{color:#7853ba;font-style:normal}.playful .object{background:#d5c6ef;border-radius:90px 8px 90px 8px}.playful .lamp{transform:rotate(12deg)}.playful .cta{background:#67479b;border-radius:30px}.playful nav .nav-pill{background:#7154a0;color:white;border:0}.busy{background:#17213b;color:#f1efc7}.busy .hero h1{font-family:Arial,sans-serif;font-weight:800;font-size:58px}.busy .hero h1 em{color:#d5f268}.busy .object{background:#7875b0;border-radius:10px}.busy .cta{background:#d5f268;color:#1c2434}.promo{padding:10px 7%;background:#d5f268;color:#26304a;font:10px monospace;letter-spacing:2px}.extras{display:flex;gap:6px;flex-wrap:wrap;margin-top:18px}.extras span{font-size:9px;border:1px solid #fff5;padding:9px;border-radius:5px}.menu-note{display:none}@media(max-width:600px){header{padding:20px 6%}nav{gap:14px;font-size:10px}.nav-secondary{display:none}.hero,.editorial .hero{grid-template-columns:1fr;padding-top:30px;gap:25px}.hero h1,.editorial .hero h1{font-size:49px}.hero p{max-width:100%}.object{height:265px}.hero{min-height:0}.collection{font-size:8px}.logo{font-size:26px}.busy .hero h1{font-size:43px}}'''
NAV='''document.querySelector('#navigation').innerHTML = `<a href="#" class="logo">luma.</a><nav><a href="#collection">Collection</a><a class="nav-secondary" href="#story">Our story</a><a href="#collection" class="nav-pill">Explore objects ↗</a></nav>`;'''
NAV_PLAY='''document.querySelector('#navigation').innerHTML = `<a href="#" class="logo">luma. ✳</a><nav><a href="#collection">Good things</a><a class="nav-secondary" href="#story">Made slowly</a><a href="#collection" class="nav-pill">Find your favorite ↗</a></nav>`;'''
OBJECT='''<div class="object"><div class="lamp"><div class="shade"></div><div class="stem"></div><div class="base"></div></div><span class="object-note">THE SOL LAMP · NATURAL OAK</span></div>'''

def hero(variant="original",early=False):
    titles={"original":"A little warmth.<br><em>A lot of home.</em>","editorial":"Good design.<br><em>Quiet company.</em>","playful":"Objects with<br><em>a bright side.</em>","busy":"BIG IDEAS.<br><em>BRIGHTER LIVING.</em>"}
    title="Objects for<br><em>every day.</em>" if early else titles[variant]
    promo='<div class="promo">NEW DROP · SIGN UP · SAVE 10% · DISCOVER THE COLLECTION</div>' if variant=="busy" else ''
    extra='<div class="extras"><span>DESIGN AWARDS</span><span>NEW ARRIVALS</span><span>LIMITED EDITION</span><span>BEST SELLERS</span></div>' if variant=="busy" else ''
    return "document.body.className="+json.dumps(variant)+";document.querySelector('#hero').innerHTML="+json.dumps(promo+f'<section class="hero"><div><div class="kicker">Thoughtfully made. Happily kept.</div><h1>{title}</h1><p>Useful, beautiful objects that make the everyday feel a little more considered. Made slowly, to stay with you.</p><a class="cta" href="#collection">Discover the collection ↗</a>{extra}</div>{OBJECT}</section><div class="collection" id="collection"><span>FEWER THINGS. BETTER THINGS.</span><span>DESIGNED FOR THE EVERYDAY →</span></div>')+";"


class Playground:
    @classmethod
    def create(cls,directory):
        root=Path(directory).resolve()
        if root.exists() and any(root.iterdir()):
            raise WorkgraphError("DIRECTORY_NOT_EMPTY","Choose an empty directory for the sample project.")
        root.mkdir(parents=True,exist_ok=True)
        subprocess.run(["git","init","-q","-b","main",str(root)],check=True)
        (root/"components").mkdir()
        for path,content in {"index.html":INDEX,"style.css":STYLE,"components/navigation.js":NAV,"components/hero.js":hero(early=True),"components/footer.js":"document.querySelector('#footer').textContent = 'Luma Objects · A sample project for exploring with Workgraph.';"}.items():
            (root/path).write_text(content)
        subprocess.run(["git","-C",str(root),"add","."],check=True)
        subprocess.run(["git","-C",str(root),"-c","user.name=Workgraph Example","-c","user.email=example@localhost","commit","-qm","Initial sample website"],check=True)
        engine=Engine(root);engine.init();studio=Studio(engine)
        original=engine.begin("Explore the Luma website",session="example-original",runtime="local")
        with engine.db() as db:db.execute("INSERT INTO studio_paths VALUES (?,?)",(original["attempt"],"Original"))
        first=engine.checkpoint(original["attempt"],"First working homepage",plan=["Make the page feel warm and considered"],decisions=["Keep the project as a small, offline static website"],questions=["Does the homepage need a more expressive direction?"])["revision"]
        (Path(original["workspace"])/"components/hero.js").write_text(hero())
        warm=engine.checkpoint(original["attempt"],"The warm, simple version",plan=["Explore alternatives without losing this version"],decisions=["Use warm colors and a single product focus"])["revision"]
        studio.note(warm,starred=True)
        (Path(original["workspace"])/"components/hero.js").write_text(hero("busy"))
        busy=engine.checkpoint(original["attempt"],"Tried more promotion and content",questions=["Did we lose the calm feeling?"])["revision"]
        for name,variant,runtime in [("Editorial","editorial","local"),("Playful","playful","local")]:
            branch=studio.branch(warm,name,runtime=runtime)
            (Path(branch["workspace"])/"components/hero.js").write_text(hero(variant))
            if variant=="playful":(Path(branch["workspace"])/"components/navigation.js").write_text(NAV_PLAY)
            saved=engine.checkpoint(branch["attempt"],f"{'A quieter editorial direction' if variant=='editorial' else 'A brighter, playful direction'}",select=False,
                plan=["Compare this direction with the warm version"],decisions=[f"Explore a {variant} direction independently"])
            branch["revision"]=saved["revision"]
            if variant=="editorial":editorial=branch
            else:playful=branch
        studio.choose(warm)
        for a in (original,editorial,playful):engine.transition(a["attempt"],"paused")
        data={"first":first,"warm":warm,"busy":busy,"editorial":editorial["revision"],"playful":playful["revision"],
              "disclosure":"Sample project with scripted saved versions; all files, branches, previews and combination operations are real."}
        (engine.home/"playground.json").write_text(json.dumps(data,indent=2))
        return engine
