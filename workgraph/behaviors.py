"""Operator-approved behavior and visual expectations, inherited along ancestry."""

import json
import time
import uuid

from .errors import WorkgraphError
from .product_state import ProductState, fingerprint


class Behaviors:
    ACTIONS = {
        "click",
        "fill",
        "select",
        "press",
        "expect",
        "expect_hidden",
        "reload",
        "goto",
        "visual",
    }

    def __init__(self, studio):
        self.studio = studio
        self.engine = studio.engine

    def list(self, revision):
        self.studio.revision(revision)
        ancestors = []
        seen = set()
        key = revision
        with self.engine.db() as db:
            while key and key not in seen:
                seen.add(key)
                ancestors.append(key)
                row = db.execute(
                    "SELECT parent FROM revisions WHERE id=?", (key,)
                ).fetchone()
                key = row[0] if row else None
            rows = []
            for key in reversed(ancestors):
                rows.extend(
                    dict(row)
                    for row in db.execute(
                        "SELECT f.* FROM product_flows f JOIN product_flow_bindings b ON f.id=b.flow_id WHERE b.revision_id=? ORDER BY f.created",
                        (key,),
                    )
                )
        return [
            {**row, "definition": json.loads(row["definition"])}
            for row in {r["id"]: r for r in rows}.values()
        ]

    def create(self, revision, name, definition, request_id=None):
        self.studio.revision(revision)
        name = self.studio.name(name)
        if not isinstance(definition, dict) or set(definition) - {
            "steps",
            "path",
            "viewport",
            "visual",
        }:
            raise WorkgraphError(
                "INVALID_FLOW", "Provide a recorded flow and its expected result."
            )
        path = definition.get("path", "/")
        if (
            not isinstance(path, str)
            or not path.startswith("/")
            or path.startswith("//")
            or len(path) > 500
        ):
            raise WorkgraphError("INVALID_FLOW", "A flow starts at a local app route.")
        viewport = definition.get("viewport", {"width": 1280, "height": 800})
        if (
            not isinstance(viewport, dict)
            or set(viewport) != {"width", "height"}
            or any(
                type(viewport[x]) is not int or not 320 <= viewport[x] <= 2000
                for x in viewport
            )
        ):
            raise WorkgraphError(
                "INVALID_FLOW", "Choose a viewport between 320 and 2000 pixels."
            )
        steps = definition.get("steps")
        if not isinstance(steps, list) or not 1 <= len(steps) <= 30:
            raise WorkgraphError("INVALID_FLOW", "Record between one and thirty steps.")
        has_expectation = False
        for step in steps:
            if not isinstance(step, dict) or set(step) - {
                "action",
                "locator",
                "value",
                "text",
                "baseline",
                "crop",
                "tolerance",
            }:
                raise WorkgraphError(
                    "INVALID_FLOW", "This recorded step contains an unsupported field."
                )
            action = step.get("action")
            if action not in self.ACTIONS:
                raise WorkgraphError(
                    "INVALID_FLOW", "This recorded action is not supported."
                )
            if action not in ("reload", "goto", "visual"):
                locator = step.get("locator")
                if (
                    not isinstance(locator, dict)
                    or set(locator) - {"type", "value", "role"}
                    or locator.get("type") not in ("css", "testid", "label", "role")
                    or not isinstance(locator.get("value"), str)
                    or not 0 < len(locator["value"]) <= 500
                ):
                    raise WorkgraphError(
                        "INVALID_FLOW",
                        "Use a visible control, label, test ID, or CSS selector.",
                    )
                if locator["type"] == "role" and locator.get("role") not in (
                    "button",
                    "link",
                    "heading",
                    "textbox",
                    "checkbox",
                    "combobox",
                    "tab",
                ):
                    raise WorkgraphError(
                        "INVALID_FLOW", "Choose a supported accessible control."
                    )
            for field in ("value", "text"):
                if field in step and (
                    not isinstance(step[field], str) or len(step[field]) > 3000
                ):
                    raise WorkgraphError(
                        "INVALID_FLOW",
                        "Recorded values must be short text or test fixtures.",
                    )
            if action == "goto" and (
                not step.get("value", "").startswith("/")
                or step["value"].startswith("//")
            ):
                raise WorkgraphError(
                    "INVALID_FLOW", "Flows can only navigate inside their app."
                )
            if action == "press" and step.get("value") not in (
                "Enter",
                "Tab",
                "Escape",
                "Control+Enter",
                "Meta+Enter",
            ):
                raise WorkgraphError(
                    "INVALID_FLOW", "This recorded key is not supported."
                )
            if action == "expect" and not step.get("text"):
                raise WorkgraphError(
                    "INVALID_FLOW", "Choose the text that should remain visible."
                )
            if action == "visual":
                baseline = step.get("baseline", "")
                with self.engine.db() as db:
                    record = db.execute(
                        "SELECT manifest FROM product_artifacts WHERE revision_id=? AND state='ready'",
                        (revision,),
                    ).fetchone()
                images = json.loads(record[0]).get("images", []) if record else []
                if baseline not in [image["file"] for image in images]:
                    raise WorkgraphError(
                        "INVALID_BASELINE",
                        "Choose an actual saved screenshot of this exact version.",
                    )
                crop = step.get("crop")
                if crop is not None and (
                    not isinstance(crop, dict)
                    or set(crop) != {"x", "y", "width", "height"}
                    or any(type(v) not in (int, float) or v < 0 for v in crop.values())
                    or crop["width"] < 10
                    or crop["height"] < 10
                ):
                    raise WorkgraphError(
                        "INVALID_FLOW", "Choose a visible rectangle to protect."
                    )
                if (
                    type(step.get("tolerance", 0.025)) not in (int, float)
                    or not 0 <= step.get("tolerance", 0.025) <= 0.2
                ):
                    raise WorkgraphError(
                        "INVALID_FLOW",
                        "Choose a visual difference tolerance from 0 to 20%.",
                    )
            has_expectation = has_expectation or action in (
                "expect",
                "expect_hidden",
                "visual",
            )
        if not has_expectation:
            raise WorkgraphError(
                "EXPECTATION_REQUIRED",
                "Add a visible-text or visual expectation so this flow can detect a regression.",
            )
        value = {"steps": steps, "path": path, "viewport": viewport}

        def action(key):
            fid = "flow_" + uuid.uuid4().hex[:16]
            now = time.time()
            sha = fingerprint(value)
            with self.engine.db() as db:
                db.execute(
                    "INSERT INTO product_flows VALUES (?,?,?,?,?,?)",
                    (fid, revision, name, json.dumps(value), sha, now),
                )
                db.execute(
                    "INSERT INTO product_flow_bindings VALUES (?,?)", (revision, fid)
                )
                return self.engine._finish(
                    db,
                    key,
                    {
                        "id": fid,
                        "baseline": revision,
                        "name": name,
                        "definition": value,
                        "fingerprint": sha,
                    },
                    "behavior.protected",
                    revision,
                )

        return self.engine._request(
            "behavior.protect",
            {"revision": revision, "name": name, "definition": value},
            action,
            request_id,
        )

    def basis(self, revision):
        state = ProductState(self.engine).get(revision)
        source = self.studio.revision(revision)
        flows = self.list(revision)
        return fingerprint(
            {
                "revision": revision,
                "tree": source["tree_oid"],
                "state": state["fingerprint"] if state else None,
                "flows": [[f["id"], f["fingerprint"]] for f in flows],
            }
        )

    def latest(self, revision):
        basis = self.basis(revision)
        with self.engine.db() as db:
            row = db.execute(
                "SELECT * FROM product_flow_runs WHERE revision_id=? AND fingerprint=? ORDER BY created DESC LIMIT 1",
                (revision, basis),
            ).fetchone()
        if not row:
            return {
                "state": "unverified",
                "results": [],
                "total": len(self.list(revision)),
                "passed": 0,
            }
        value = dict(row)
        value["results"] = json.loads(value["results"])
        value["total"] = len(self.list(revision))
        value["passed"] = sum(r.get("passed") is True for r in value["results"])
        return value
