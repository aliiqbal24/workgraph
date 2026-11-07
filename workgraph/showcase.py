"""A real full-stack project with branching directions and frozen behavior checks.

Initial example edits are scripted and disclosed. All database snapshots,
runtime launches, browser captures, and check results are real.
"""

from pathlib import Path
from contextlib import closing
import importlib.util
import json
import shutil
import sqlite3
import subprocess

from .engine import Engine
from .studio import Studio
from .product_state import ProductState
from .behaviors import Behaviors
from .errors import WorkgraphError

BOARD = """function renderBoard(list){
 return `<div class="board" data-testid="board">${Object.entries(labels).map(([status,name])=>`<section class="column"><div class="column-heading"><span class="status-dot ${status}"></span>${name}<small>${list.filter(i=>i.status===status).length}</small></div>${list.filter(i=>i.status===status).map(issue=>`<a class="board-card" href="#issue/${issue.id}" data-testid="open-issue-${issue.id}"><span class="issue-id">FW-${String(issue.id).padStart(3,'0')}</span><div class="issue-title">${esc(issue.title)}</div><div class="card-bottom"><span class="priority ${issue.priority}">${issue.priority==='high'?'▰':'▥'} ${esc(issue.priority)}</span>${avatar(issue.assignee)}</div></a>`).join('')}</section>`).join('')}</div>`;
}
"""

COMMENT_FLOW = {
    "path": "/",
    "viewport": {"width": 1280, "height": 800},
    "steps": [
        {"action": "click", "locator": {"type": "testid", "value": "open-issue-1"}},
        {
            "action": "fill",
            "locator": {"type": "label", "value": "Add a comment"},
            "value": "A thought worth keeping.",
        },
        {
            "action": "click",
            "locator": {"type": "role", "role": "button", "value": "Post comment"},
        },
        {"action": "reload"},
        {
            "action": "expect",
            "locator": {"type": "testid", "value": "comment-list"},
            "text": "A thought worth keeping.",
        },
    ],
}
CREATE_FLOW = {
    "path": "/",
    "viewport": {"width": 1280, "height": 800},
    "steps": [
        {
            "action": "click",
            "locator": {"type": "role", "role": "button", "value": "＋ New issue"},
        },
        {
            "action": "fill",
            "locator": {"type": "label", "value": "Issue title"},
            "value": "An idea that survives a refresh",
        },
        {
            "action": "click",
            "locator": {"type": "role", "role": "button", "value": "Create issue"},
        },
        {"action": "reload"},
        {
            "action": "expect",
            "locator": {"type": "css", "value": "#workspace"},
            "text": "An idea that survives a refresh",
        },
    ],
}
FILTER_FLOW = {
    "path": "/",
    "viewport": {"width": 1280, "height": 800},
    "steps": [
        {
            "action": "click",
            "locator": {"type": "role", "role": "button", "value": "High priority"},
        },
        {
            "action": "expect",
            "locator": {"type": "testid", "value": "issue-1"},
            "text": "Design the new onboarding",
        },
        {"action": "expect_hidden", "locator": {"type": "testid", "value": "issue-2"}},
    ],
}


class Showcase:
    @classmethod
    def create(cls, directory):
        root = Path(directory).resolve()
        if root.exists() and any(root.iterdir()):
            raise WorkgraphError(
                "DIRECTORY_NOT_EMPTY",
                "Choose an empty directory for the sample product.",
            )
        root.mkdir(parents=True, exist_ok=True)
        template = Path(__file__).parent / "templates/fieldwork"
        shutil.copytree(
            template,
            root,
            dirs_exist_ok=True,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )
        (root / ".gitignore").write_text(".workgraph-data/\n__pycache__/\n")
        subprocess.run(["git", "init", "-q", "-b", "main", str(root)], check=True)
        subprocess.run(["git", "-C", str(root), "add", "."], check=True)
        subprocess.run(
            [
                "git",
                "-C",
                str(root),
                "-c",
                "user.name=Workgraph Example",
                "-c",
                "user.email=example@localhost",
                "commit",
                "-qm",
                "Initial issue tracker",
            ],
            check=True,
        )
        spec = importlib.util.spec_from_file_location(
            "workgraph_sample_app", root / "app.py"
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        module.initialize(root / ".workgraph-data/app.db")
        engine = Engine(root)
        engine.init()
        studio = Studio(engine)
        states = ProductState(engine)
        behaviors = Behaviors(studio)
        states.configure(
            {
                "name": "Fieldwork",
                "command": [
                    "{python}",
                    "app.py",
                    "--port",
                    "{port}",
                    "--database",
                    ".workgraph-data/app.db",
                ],
                "health": "/health",
                "data_files": [".workgraph-data/app.db"],
                "screens": [
                    {
                        "name": "Workspace",
                        "path": "/",
                        "width": 1280,
                        "height": 800,
                        "ready": "h1",
                    },
                    {
                        "name": "A conversation",
                        "path": "/#issue/1",
                        "width": 1280,
                        "height": 800,
                        "ready": ".detail-panel h2",
                    },
                    {
                        "name": "On your phone",
                        "path": "/",
                        "width": 390,
                        "height": 844,
                        "ready": "h1",
                    },
                ],
            }
        )
        original = studio.start("The working product")
        base = original["revision"]
        behaviors.create(base, "Comments stay saved after refresh", COMMENT_FLOW)
        behaviors.create(base, "New issues survive a refresh", CREATE_FLOW)
        studio.note(base, starred=True)
        paths = [original]

        def save(branch, title, **notes):
            return engine.checkpoint(branch["attempt"], title, select=False, **notes)[
                "revision"
            ]

        def config(branch, **values):
            path = Path(branch["workspace"]) / "view.json"
            value = json.loads(path.read_text())
            value.update(values)
            path.write_text(json.dumps(value, indent=2))

        soft = studio.branch(base, "A calmer direction")
        paths.append(soft)
        config(
            soft,
            title="A little room to focus",
            subtitle="Good work feels better with a little breathing room.",
        )
        with (Path(soft["workspace"]) / "client/style.css").open("a") as file:
            file.write(
                "\nbody{background:#faf7f0}aside#sidebar{background:#f0ece1}.issue-row{min-height:80px}.primary{background:#e5d9ba;border-color:#d6c49b;color:#786543}.page-heading h1{font-family:Georgia,serif;font-size:38px;font-weight:normal}.issue-table{border-radius:14px}\n"
            )
        warm = save(
            soft,
            "A warmer, quieter workspace",
            decisions=[
                "Give each task a little more room without changing its behavior."
            ],
        )
        config(soft, title="Less noise. More good work.")
        quiet = save(
            soft,
            "More room for the work",
            plan=["Compare the visual direction with the original working app."],
        )
        board = studio.branch(base, "Board exploration")
        paths.append(board)
        js = Path(board["workspace"]) / "client/app.js"
        text = js.read_text()
        text = BOARD + text.replace("${renderRows(list)}", "${renderBoard(list)}")
        js.write_text(text)
        config(
            board,
            title="A little momentum",
            subtitle="See what’s taking shape, one small step at a time.",
            layout="board",
        )
        board_root = Path(board["workspace"])
        backend = board_root / "app.py"
        backend.write_text(
            backend.read_text().replace("SAVE_COMMENTS=True", "SAVE_COMMENTS=False")
        )
        board_version = save(
            board,
            "A board, with a behavior to repair",
            questions=[
                "Comments claim to save but do not survive a refresh. Keep that protection when borrowing this board."
            ],
        )
        focused = studio.branch(base, "A focused workspace")
        paths.append(focused)
        target = Path(focused["workspace"]) / "client/app.js"
        text = target.read_text().replace(
            "const list=issues;",
            "const list=filter==='high'?issues.filter(i=>i.priority==='high'):issues;",
        )
        text = text.replace(
            '<button data-filter="filter">⌕ Filter</button>',
            "<button data-filter=\"high\" class=\"${filter==='high'?'active':''}\">High priority</button>",
        )
        text = text.replace(
            "$('#add-issue').onclick=",
            "document.querySelectorAll('[data-filter]').forEach(button=>button.onclick=()=>{filter=button.dataset.filter;render();});\n $('#add-issue').onclick=",
        )
        target.write_text(text)
        config(
            focused,
            title="The things that matter",
            subtitle="Your work, with a little more intention.",
        )
        filtered = save(
            focused,
            "A focused list, with priority filters",
            decisions=[
                "Keep priority filtering and reliable comment storage when exploring another layout."
            ],
        )
        behaviors.create(
            filtered, "Priority filters keep the right issues", FILTER_FLOW
        )
        with closing(
            sqlite3.connect(Path(focused["workspace"]) / ".workgraph-data/app.db")
        ) as db:
            db.execute(
                "INSERT INTO issues(title,description,status,priority,assignee) VALUES ('Plan our next good idea','A new task saved only on this direction.','todo','high','NP')"
            )
            db.commit()
        current = save(
            focused,
            "Our next idea, saved with the product",
            plan=[
                "Explore the board while preserving filters, comments, and this saved issue."
            ],
        )
        studio.note(current, starred=True)
        studio.choose(current)
        mobile = studio.branch(warm, "A mobile direction")
        paths.append(mobile)
        with (Path(mobile["workspace"]) / "client/style.css").open("a") as file:
            file.write(
                "\n@media(max-width:550px){.issue-row{border:1px solid #e4dfd0;margin:0 0 10px;border-radius:10px;background:#fffdf7}.table-heading{display:none}.issue-table{border:0;background:none}.page-heading h1{font-size:33px}.page{background:#f8f2e7}.primary{border-radius:20px}}\n"
            )
        mobile_version = save(mobile, "A softer pocket-sized workspace")
        for path in paths:
            engine.transition(path["attempt"], "paused")
        data = {
            "base": base,
            "warm": warm,
            "quiet": quiet,
            "board": board_version,
            "filtered": filtered,
            "current": current,
            "mobile": mobile_version,
            "kind": "fieldwork",
            "disclosure": "Initial example directions and the board regression are scripted. All source versions, SQLite snapshots, app previews, screenshots, recordings and checks are real.",
        }
        (engine.home / "playground.json").write_text(json.dumps(data, indent=2))
        return engine
