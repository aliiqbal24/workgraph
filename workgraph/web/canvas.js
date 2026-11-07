"use strict";
const $ = (s) => document.querySelector(s),
  $$ = (s) => [...document.querySelectorAll(s)],
  esc = (v) =>
    String(v ?? "").replace(
      /[&<>"']/g,
      (c) =>
        ({
          "&": "&amp;",
          "<": "&lt;",
          ">": "&gt;",
          '"': "&quot;",
          "'": "&#39;",
        })[c],
    );
const hash = new URLSearchParams(location.hash.slice(1));
let bearer =
  hash.get("token") ||
  hash.get("view") ||
  localStorage.getItem("workgraph-access") ||
  "";
if (hash.has("token") || hash.has("view")) {
  localStorage.setItem("workgraph-access", bearer);
  history.replaceState(null, "", location.pathname);
}
let data = null,
  selected = null,
  filter = "all",
  camera = { x: 50, y: 50, z: 1 },
  positions = new Map(),
  visible = [],
  colors = new Map(),
  nodeEls = new Map(),
  first = true,
  detailImage = 0,
  inspecting = false,
  toastTimer,
  focusTimer,
  dialogCleanup = null,
  live = null,
  polling = false,
  workspaceStopped = false,
  signature = "",
  jobsSignature = "";
const palette = [
  "#95ac80",
  "#ba9bd9",
  "#d9ad68",
  "#80ab9a",
  "#83b6c4",
  "#b9a4bd",
  "#b6bc73",
  "#cc9a8a",
];
const api = async (path, body) => {
  const response = await fetch(path, {
    method: body ? "POST" : "GET",
    headers: {
      Authorization: "Bearer " + bearer,
      ...(body ? { "Content-Type": "application/json" } : {}),
    },
    body: body ? JSON.stringify(body) : undefined,
  });
  let value;
  try {
    value = await response.json();
  } catch {
    throw Error(
      "The project workspace did not respond. Reopen Workgraph to reconnect.",
    );
  }
  if (!response.ok)
    throw Error(
      value.message || value.error || "The request could not finish.",
    );
  return value;
};
const action = async (name, values = {}) =>
  api("/api/action", {
    action: name,
    request_id: crypto.randomUUID(),
    ...values,
  });
function toast(message, error = false) {
  clearTimeout(toastTimer);
  $("#toast").textContent = message;
  $("#toast").className = error ? "error" : "";
  $("#toast").hidden = false;
  toastTimer = setTimeout(
    () => ($("#toast").hidden = true),
    error ? 7000 : 4200,
  );
}
function safely(fn) {
  return async (...args) => {
    try {
      return await fn(...args);
    } catch (e) {
      toast(e.message, true);
    }
  };
}
function version(id) {
  return data?.versions.find((v) => v.id === id);
}
function pathFor(v) {
  return data?.paths.find((p) => p.id === v?.path);
}
function media(file) {
  return file ? data.media_base + file : "";
}
function images(v) {
  return data?.artifacts[v?.id]?.manifest?.images || [];
}
function when(t) {
  return new Date(t * 1000).toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}
function proof(v) {
  const p = v.protection;
  if (!p?.total) return { label: "No protected flows yet", cls: "" };
  if (p.state === "passed")
    return {
      label: p.passed + " / " + p.total + " behaviors kept",
      cls: "pass",
    };
  if (p.state === "failed")
    return {
      label:
        p.total -
        p.passed +
        " behavior" +
        (p.total - p.passed === 1 ? "" : "s") +
        " to repair",
      cls: "fail",
    };
  if (["queued", "running"].includes(p.state))
    return { label: "Checking " + p.total + " behaviors…", cls: "" };
  if (["error", "interrupted"].includes(p.state))
    return { label: "Checks need another run", cls: "fail" };
  return { label: p.total + " behaviors · not checked", cls: "" };
}
function localKey() {
  return "workgraph-canvas:" + data.repository;
}
function remember() {
  if (!data || !selected) return;
  const value = { revision: selected, camera, inspecting };
  localStorage.setItem(localKey(), JSON.stringify(value));
  clearTimeout(focusTimer);
  if (data.operator)
    focusTimer = setTimeout(
      () =>
        action("studio.focus", { revision: selected, camera }).catch(() => {}),
      550,
    );
}
function transform() {
  $("#world").style.transform =
    `translate(${camera.x}px,${camera.y}px) scale(${camera.z})`;
  $("#zoom-value").textContent = Math.round(camera.z * 100) + "%";
  drawMini();
}
function zoom(factor, x, y) {
  const rect = $("#canvas").getBoundingClientRect();
  x = x ?? rect.width / 2;
  y = y ?? rect.height / 2;
  const z = Math.max(0.12, Math.min(2, camera.z * factor)),
    ratio = z / camera.z;
  camera = { x: x - (x - camera.x) * ratio, y: y - (y - camera.y) * ratio, z };
  transform();
  remember();
}
function bounds() {
  if (!visible.length) return { x: 0, y: 0, w: 800, h: 500 };
  const ps = visible.map((v) => positions.get(v.id));
  const x = Math.min(...ps.map((p) => p.x)) - 35,
    y = Math.min(...ps.map((p) => p.y)) - 155;
  return {
    x,
    y,
    w: Math.max(...ps.map((p) => p.x)) + 285 - x,
    h: Math.max(...ps.map((p) => p.y)) + 155 - y,
  };
}
function fit() {
  if (!visible.length) return;
  const b = bounds(),
    rect = $("#canvas").getBoundingClientRect();
  camera.z = Math.max(
    0.12,
    Math.min(1, (rect.width - 100) / b.w, (rect.height - 125) / b.h),
  );
  camera.x = (rect.width - b.w * camera.z) / 2 - b.x * camera.z;
  camera.y = (rect.height - b.h * camera.z) / 2 - b.y * camera.z - 6;
  transform();
  remember();
}
function drawMini() {
  const svg = $("#minimap");
  if (!visible.length) {
    svg.innerHTML = "";
    return;
  }
  const b = bounds(),
    s = Math.min(110 / b.w, 65 / b.h),
    ox = 8 - b.x * s,
    oy = 7 - b.y * s;
  svg.setAttribute("viewBox", "0 0 126 80");
  svg.innerHTML = visible
    .map((v) => {
      const p = positions.get(v.id),
        parent = positions.get(p.parent);
      return (
        (parent
          ? `<path d="M${ox + (parent.x + 248) * s} ${oy + parent.y * s} C${ox + (parent.x + 280) * s} ${oy + parent.y * s},${ox + (p.x - 50) * s} ${oy + p.y * s},${ox + p.x * s} ${oy + p.y * s}" fill="none" stroke="${colors.get(v.path)}" stroke-width="1"/>`
          : "") +
        `<rect x="${ox + p.x * s}" y="${oy + (p.y - 100) * s}" width="${248 * s}" height="${210 * s}" rx="1" fill="${v.id === selected ? "#7e9c6c" : "#cedbc2"}"/>`
      );
    })
    .join("");
  const rect = $("#canvas").getBoundingClientRect();
  svg.innerHTML += `<rect x="${ox - (camera.x / camera.z) * s}" y="${oy - (camera.y / camera.z) * s}" width="${(rect.width / camera.z) * s}" height="${(rect.height / camera.z) * s}" rx="2" fill="none" stroke="#97aa87" stroke-width=".7"/>`;
}
function layout() {
  colors = new Map(
    data.paths.map((p, i) => [p.id, palette[i % palette.length]]),
  );
  const all = $("#all-saves").checked,
    byId = new Map(data.versions.map((v) => [v.id, v])),
    heads = new Set(data.paths.map((p) => p.head));
  visible = data.versions.filter(
    (v) =>
      all ||
      !v.title.startsWith("Start ") ||
      heads.has(v.id) ||
      v.starred ||
      v.id === selected,
  );
  const kept = new Set(visible.map((v) => v.id)),
    children = new Map();
  positions = new Map();
  for (const v of visible) {
    let parent = v.parent;
    while (parent && !kept.has(parent)) parent = byId.get(parent)?.parent;
    positions.set(v.id, { parent, x: 0, y: 0 });
    if (!children.has(parent)) children.set(parent, []);
    children.get(parent).push(v.id);
  }
  let leaf = 0;
  function visit(id, depth) {
    const p = positions.get(id),
      kids = children.get(id) || [];
    p.x = depth * 355 + 60;
    if (kids.length) {
      kids.forEach((k) => visit(k, depth + 1));
      p.y =
        (positions.get(kids[0]).y + positions.get(kids[kids.length - 1]).y) / 2;
    } else {
      p.y = 160 + leaf * 250;
      leaf++;
    }
  }
  (children.get(null) || children.get(undefined) || []).forEach((id) =>
    visit(id, 0),
  );
  for (const v of visible) if (!positions.get(v.id).y) visit(v.id, 0);
}
function matches(v) {
  return (
    filter === "all" ||
    (filter === "starred" && v.starred) ||
    (filter === "protected" && v.protection.total > 0) ||
    filter === v.path
  );
}
function renderTree() {
  layout();
  $("#version-count").textContent = data.versions.length;
  $("#path-count").textContent = data.paths.length;
  $("#canvas-summary").textContent =
    `${data.paths.length} direction${data.paths.length === 1 ? "" : "s"} · ${data.versions.length} saved moment${data.versions.length === 1 ? "" : "s"} · nothing lost`;
  const alive = new Set(visible.map((v) => v.id));
  for (const [id, el] of nodeEls)
    if (!alive.has(id)) {
      el.remove();
      nodeEls.delete(id);
    }
  const svg = $("#branches");
  let curves = "";
  for (const v of visible) {
    const p = positions.get(v.id),
      color = colors.get(v.path);
    if (p.parent) {
      const q = positions.get(p.parent),
        start = q.x + 248,
        end = p.x;
      curves += `<path d="M${start} ${q.y} C${start + 70} ${q.y},${end - 85} ${p.y},${end} ${p.y}" fill="none" stroke="${color}" opacity="${matches(v) ? ".68" : ".12"}" stroke-width="3" stroke-linecap="round"/>`;
    }
    let el = nodeEls.get(v.id);
    if (!el) {
      el = document.createElement("button");
      el.className = "node";
      el.dataset.id = v.id;
      el.onclick = () => select(v.id);
      $("#nodes").append(el);
      nodeEls.set(v.id, el);
    }
    el.classList.toggle("selected", v.id === selected);
    el.classList.toggle("dimmed", !matches(v));
    el.style.left = p.x + "px";
    el.style.top = p.y + "px";
    el.style.setProperty("--branch", color);
    el.setAttribute("aria-label", v.title + ". " + proof(v).label);
    const img = images(v)[0],
      artifact = data.artifacts[v.id],
      photo = img
        ? `<img src="${media(img.thumb)}" alt="${esc(v.title)} — actual saved product" loading="lazy" draggable="false">`
        : `<div class="pending-photo">${artifact?.state === "capturing" || artifact?.state === "queued" ? '<span class="spinner"></span>' : ""}${artifact?.state === "failed" ? "Capture needs a retry" : artifact ? "Capturing this moment…" : "Preview not captured yet"}</div>`;
    const pr = proof(v),
      html = `${v.id === data.current ? '<span class="node-chosen">Your chosen direction</span>' : ""}<span class="node-port"></span><span class="node-port out"></span><div class="node-chrome"><i></i><i></i><i></i><span>${v.product_state ? "CODE + DATA" : "SAVED SOURCE"}</span></div><div class="node-photo">${photo}</div><div class="node-label"><strong class="node-title">${esc(v.title)}</strong><div class="node-meta"><span class="proof ${pr.cls}">${esc(pr.label)}</span><span>${v.starred ? '<span class="favorite">☆</span>' : esc(v.runtime === "local" ? "you" : v.runtime)}</span></div></div>`;
    if (el.innerHTML !== html) el.innerHTML = html;
  }
  for (const link of data.lineage || []) {
    const source = positions.get(link.source_revision),
      target = positions.get(link.revision_id);
    if (source && target)
      curves += `<path d="M${source.x + 124} ${source.y + 120} Q${(source.x + target.x) / 2 + 124} ${Math.max(source.y, target.y) + 200},${target.x + 124} ${target.y + 120}" fill="none" stroke="#a6b59a" stroke-width="1.5" stroke-dasharray="5 6"/>`;
  }
  svg.innerHTML = curves;
  $("#paths").innerHTML = data.paths
    .map(
      (p) =>
        `<button class="path-button ${filter === p.id ? "selected" : ""}" data-path="${p.id}"><span class="path-dot" style="background:${colors.get(p.id)}"></span><span>${esc(p.name)}</span><small>${data.versions.filter((v) => v.path === p.id).length}</small></button>`,
    )
    .join("");
  $$("[data-path]").forEach(
    (b) =>
      (b.onclick = () => {
        filter = b.dataset.path;
        renderTree();
        const head = data.paths.find((p) => p.id === filter)?.head;
        if (head) select(head, false);
      }),
  );
  $$(".nav-item").forEach((b) =>
    b.classList.toggle("active", b.dataset.filter === filter),
  );
  $("#empty").hidden = !!visible.length;
  if (!visible.length)
    $("#empty").innerHTML =
      `<div class="empty-content"><div class="eyebrow">THIS IS WHERE POSSIBILITIES BEGIN</div><h2>Your next idea has a home.</h2><p>Save your project's starting point. Then explore a new direction with your agent, knowing you can always come back.</p><button class="button primary" id="start-project" ${data.operator ? "" : "disabled"}>Save my starting point</button><p class="muted">${data.operator ? "Your working files stay where they are." : "Run workgraph open locally to open editing controls."}</p></div>`;
  if ($("#start-project"))
    $("#start-project").onclick = safely(async () => {
      const r = await action("studio.start");
      selected = r.revision;
      await refresh();
      fit();
    });
  drawMini();
}
function select(id, open = true) {
  if (!version(id)) return;
  selected = id;
  detailImage = 0;
  if (open) {
    if (!inspecting) camera.x -= Math.min(210, $("#canvas").clientWidth * 0.15);
    inspecting = true;
    document.body.classList.add("inspecting");
    $("#inspector").hidden = false;
  }
  renderTree();
  transform();
  renderDetails();
  remember();
}
function closeInspector() {
  if (inspecting)
    camera.x += Math.min(210, ($("#canvas").clientWidth + 420) * 0.15);
  inspecting = false;
  transform();
  document.body.classList.remove("inspecting");
  $("#inspector").hidden = true;
  remember();
}
function renderDetails() {
  if (!inspecting || !version(selected)) return;
  const v = version(selected),
    path = pathFor(v),
    gallery = images(v),
    image = gallery[Math.min(detailImage, gallery.length - 1)],
    pr = proof(v),
    p = v.protection,
    can = data.operator ? "" : "disabled";
  const html = `<div class="detail-head"><div class="path-name"><span class="path-dot" style="background:${colors.get(v.path)}"></span>${esc(path?.name || "A direction")}</div><h2>${esc(v.title)}</h2><div class="when">${when(v.created)} <span>·</span> ${esc(v.runtime === "local" ? "Saved by you" : v.runtime)}</div></div><div class="gallery">${image ? `<img class="gallery-image" src="${media(image.file)}" alt="${esc(image.name)} — saved ${when(v.created)}">` : `<div class="gallery-empty">${esc(data.artifacts[v.id]?.error || "Actual screenshots appear here after capture. The saved source is already available.")}</div>`}<div class="gallery-tabs">${gallery.map((img, i) => `<button class="gallery-tab ${i === detailImage ? "active" : ""}" data-image="${i}">${esc(img.name)}</button>`).join("")}<button class="gallery-tab" id="refresh-capture" title="Capture this exact saved state again" ${can}>↻</button></div></div><div class="detail-actions"><button class="button primary wide" id="continue-here" ${can}>Continue from here <span>↗</span></button><div class="secondary-actions"><button class="button" id="open-app" ${can}>${v.product_state ? "Open working app" : v.preview_entry ? "Open saved page" : "Connect app"} ↗</button><button class="button" id="compare-here">Compare & borrow</button></div></div><div class="state-strip"><span>Source saved</span><span>${v.product_state ? v.product_state.files + " database" + (v.product_state.files === 1 ? "" : "s") + " saved" : "Code-only version"}</span><span>Context saved</span></div><div class="section"><div class="section-heading"><span>BEHAVIORS THAT SHOULD KEEP WORKING</span><span class="proof ${pr.cls}">${p.passed || 0} / ${p.total}</span></div>${
    v.flows
      .map((f) => {
        const run = p.results.find((r) => r.id === f.id),
          status = run ? (run.passed ? "✓" : "!") : "·";
        return `<button class="flow ${run && !run.passed ? "failed" : ""}" data-flow="${f.id}"><span class="status-icon">${status}</span><span>${esc(f.name)}<small>${run ? (run.passed ? "Passed on this exact saved state · watch replay" : "Needs attention · see what happened") : p.state === "running" ? "Replaying in a fresh copy…" : "Protected · awaiting a recorded check"}</small></span></button>`;
      })
      .join("") ||
    '<p class="muted">Keep a good interaction working. Record it once, then replay it on future directions.</p>'
  }<button class="text-button" id="protect-flow" ${can}>＋ Record a behavior to protect</button></div><div class="section"><div class="section-heading"><span>THOUGHTS TO CARRY FORWARD</span></div><div class="notes">${[...(v.context.decisions || []), ...(v.context.plan || []), ...(v.context.questions || [])].map((n) => `<p class="note-item">${esc(n)}</p>`).join("") || "This moment is ready for your next idea."}</div></div><div class="section"><div class="detail-links"><button id="favorite" ${can}>${v.starred ? "★ Remove favorite" : "☆ Save favorite"}</button><button id="rename" ${can}>Rename moment</button><button id="rename-path" ${can}>Rename direction</button><button id="choose" ${can}>${v.id === data.current ? "✓ Chosen direction" : "Choose this direction"}</button><button id="download">Download source</button><button id="undo" ${can}>Undo one feature</button></div></div>`;
  if ($("#details").innerHTML !== html) {
    $("#details").innerHTML = html;
    $$("[data-image]").forEach(
      (b) =>
        (b.onclick = () => {
          detailImage = Number(b.dataset.image);
          renderDetails();
        }),
    );
    if ($(".gallery-image")) $(".gallery-image").onclick = () => showGallery(v);
    $("#continue-here").onclick = () => agentForm(v);
    $("#open-app").onclick = safely(() =>
      v.product_state || v.preview_entry ? openLive(v) : connectForm(v),
    );
    $("#compare-here").onclick = () => compareForm(v.id);
    $("#refresh-capture").onclick = safely(async () => {
      await action("capture.refresh", { revision: v.id });
      toast("Capturing this saved state and replaying its behaviors.");
      await refresh();
    });
    $("#protect-flow").onclick = safely(() =>
      v.product_state ? openLive(v, true) : connectForm(v),
    );
    $("#favorite").onclick = safely(async () => {
      await action("studio.note", { revision: v.id, starred: !v.starred });
      await refresh();
    });
    $("#rename").onclick = () => renameForm(v);
    $("#rename-path").onclick = () => renamePathForm(path);
    $("#choose").onclick = safely(async () => {
      await action("studio.choose", { revision: v.id });
      toast(
        "Direction chosen. Your conversation and working files stay where they are.",
      );
      await refresh();
    });
    $("#download").onclick = safely(async () => {
      const response = await fetch("/api/export?revision=" + v.id, {
        headers: { Authorization: "Bearer " + bearer },
      });
      if (!response.ok) throw Error("The saved source could not be exported.");
      const url = URL.createObjectURL(await response.blob()),
        link = document.createElement("a");
      link.href = url;
      link.download = "workgraph-" + v.id + ".zip";
      link.click();
      setTimeout(() => URL.revokeObjectURL(url), 5000);
    });
    $("#undo").onclick = () => adaptForm(v, "undo");
    $$("[data-flow]").forEach(
      (b) => (b.onclick = () => flowDetails(v, b.dataset.flow)),
    );
  }
}
function showDialog(title, html, cls = "") {
  closeDialog();
  $("#dialog").className = cls;
  $("#dialog-title").textContent = title;
  $("#dialog-body").innerHTML = html;
  $("#dialog").showModal();
}
function closeDialog() {
  if (dialogCleanup) {
    dialogCleanup();
    dialogCleanup = null;
  }
  live = null;
  $("#dialog").close();
  $("#dialog").className = "";
}
function runtimeOptions() {
  return Object.entries(data.runtimes)
    .map(
      ([id, available]) =>
        `<option value="${id}" ${available ? "" : "disabled"} ${id === "codex" && available ? "selected" : ""}>${id === "claude" ? "Claude Code" : id === "hermes" ? "Hermes" : "Codex"}${available ? "" : " · not installed"}</option>`,
    )
    .join("");
}
function agentForm(v) {
  const head = pathFor(v)?.head === v.id;
  showDialog(
    "Continue from this moment",
    `<p class="dialog-intro">Where should this go next?</p><p class="muted">Start a focused agent task from <strong>${esc(v.title)}</strong>.</p><div class="context-card">✓ Exact saved source${v.product_state ? " + development database" : ""}<br>✓ Decisions and ${v.flows.length} protected behavior${v.flows.length === 1 ? "" : "s"} carried forward<br>✓ Result saved back to this tree</div><form id="agent-form"><label class="field">What would you like to try?<textarea name="prompt" required maxlength="12000" placeholder="Make this feel more spacious. Keep everything that already works."></textarea></label><label class="field">Agent<select name="runtime">${runtimeOptions()}</select></label><label class="field">Direction<select name="reuse"><option value="false">Explore a new branch</option>${head ? '<option value="true">Continue this direction</option>' : ""}</select></label><div class="form-bottom"><small>Your existing conversation stays open.</small><button class="button primary" type="submit" ${data.operator ? "" : "disabled"}>Start exploring ↗</button></div></form>`,
  );
  $("#agent-form").onsubmit = safely(async (e) => {
    e.preventDefault();
    const f = new FormData(e.currentTarget),
      button = e.currentTarget.querySelector("[type=submit]");
    button.disabled = true;
    try {
      const r = await action("studio.agent", {
        revision: v.id,
        name: String(f.get("prompt")).slice(0, 100),
        runtime: f.get("runtime"),
        prompt: f.get("prompt"),
        reuse_path: f.get("reuse") === "true",
      });
      closeDialog();
      await refresh();
      select(r.revision);
      toast("Your agent is working. You can close this window and come back.");
    } finally {
      button.disabled = false;
    }
  });
  $("#agent-form textarea").focus();
}
function renameForm(v) {
  showDialog(
    "Give this moment a name",
    `<form id="rename-form"><label class="field">Name<input name="name" maxlength="120" value="${esc(v.title)}" required></label><div class="form-bottom"><small>Its saved state stays the same.</small><button class="button primary">Save name</button></div></form>`,
  );
  $("#rename-form").onsubmit = safely(async (e) => {
    e.preventDefault();
    await action("studio.note", {
      revision: v.id,
      label: new FormData(e.currentTarget).get("name"),
    });
    closeDialog();
    await refresh();
  });
  $("#rename-form input").select();
}
function showGallery(v) {
  const gallery = images(v);
  showDialog(
    "Inside this saved moment",
    `<img class="gallery-image" style="height:auto;max-height:70vh" src="${media(gallery[detailImage]?.file)}" alt="${esc(gallery[detailImage]?.name)}"><p class="muted">${esc(v.title)} · actual saved code${v.product_state ? " + data" : ""} · ${when(v.created)}</p><button class="button" id="protect-look" ${data.operator ? "" : "disabled"}>Protect this view’s appearance</button>`,
    "large",
  );
  $("#protect-look").onclick = () => visualForm(v, gallery[detailImage]);
}
function visualForm(v, image) {
  showDialog(
    "Protect a visual expectation",
    `<p class="muted">Future directions will be compared against this saved screenshot at ${image.width} × ${image.height}. This protects the whole view; use behavior recording for interactive expectations.</p><form id="visual-form"><label class="field">What should keep looking right?<input name="name" value="${esc(image.name)} keeps its appearance" required maxlength="120"></label><img style="width:100%;border-radius:8px" src="${media(image.file)}" alt="Saved visual baseline"><div class="form-bottom"><small>Up to 2.5% changed pixels allowed.</small><button class="button primary">Protect this view</button></div></form>`,
  );
  $("#visual-form").onsubmit = safely(async (e) => {
    e.preventDefault();
    await action("behavior.protect", {
      revision: v.id,
      name: new FormData(e.currentTarget).get("name"),
      definition: {
        path: image.path,
        viewport: { width: image.width, height: image.height },
        steps: [{ action: "visual", baseline: image.file, tolerance: 0.025 }],
      },
    });
    closeDialog();
    await refresh();
    toast("Visual expectation protected. Future branches inherit it.");
  });
}
function compareForm(source = selected) {
  if (data.versions.length < 2)
    return toast("Save another moment to compare it with this one.");
  const from = version(source) || data.versions[0],
    target =
      version(data.current) && data.current !== from.id
        ? data.current
        : data.versions.find((v) => v.id !== from.id).id;
  showDialog(
    "Compare possibilities",
    `<div class="compare-grid"><div><label class="field">Borrow from<select id="compare-source">${versionOptions(from.id)}</select></label><div id="compare-left"></div></div><div><label class="field">Keep as the starting point<select id="compare-target">${versionOptions(target)}</select></label><div id="compare-right"></div></div></div><div class="transfer"><p class="dialog-intro">Keep the best of both.</p><p class="muted">Describe one feature to bring across. Your agent adapts it into a new branch, preserving the target’s data and protected behaviors.</p><form id="borrow-form"><label class="field">What should come across?<textarea name="prompt" placeholder="Bring the board layout across. Keep the priority filter, and make sure comments still survive a refresh." required maxlength="6000"></textarea></label><div class="form-bottom"><select name="runtime" class="button">${runtimeOptions()}</select><button class="button primary" ${data.operator ? "" : "disabled"}>Borrow into a new branch ↗</button></div></form><p id="compare-facts" class="muted"></p></div>`,
    "large",
  );
  const update = () => {
    for (const [selectId, viewId] of [
      ["#compare-source", "#compare-left"],
      ["#compare-target", "#compare-right"],
    ]) {
      const v = version($(selectId).value),
        img = images(v)[0];
      $(viewId).innerHTML =
        `${img ? `<img src="${media(img.file)}" alt="${esc(v.title)}">` : '<div class="gallery-empty">Capture pending</div>'}<h3>${esc(v.title)}</h3><p class="muted">${esc(proof(v).label)} · ${v.product_state ? "saved development data" : "source only"}</p>`;
    }
    const same = $("#compare-source").value === $("#compare-target").value;
    $("#borrow-form button").disabled = same || !data.operator;
    $("#compare-facts").textContent = same
      ? "Choose two different moments."
      : "Both original versions remain available. A completed agent task is checked independently.";
  };
  $("#compare-source").onchange = update;
  $("#compare-target").onchange = update;
  update();
  $("#borrow-form").onsubmit = safely(async (e) => {
    e.preventDefault();
    const f = new FormData(e.currentTarget),
      button = e.currentTarget.querySelector("button");
    button.disabled = true;
    try {
      const r = await action("studio.adapt", {
        source: $("#compare-source").value,
        target: $("#compare-target").value,
        prompt: f.get("prompt"),
        runtime: f.get("runtime"),
        kind: "borrow",
      });
      closeDialog();
      await refresh();
      select(r.revision);
      toast(
        "Adapting your feature in a new branch. The originals are preserved.",
      );
    } finally {
      button.disabled = false;
    }
  });
}
function versionOptions(chosen) {
  return data.versions
    .map(
      (v) =>
        `<option value="${v.id}" ${v.id === chosen ? "selected" : ""}>${esc(v.title)}</option>`,
    )
    .join("");
}
function adaptForm(v, kind) {
  showDialog(
    "Undo a feature, keep the rest",
    `<p class="dialog-intro">Go back on one decision.</p><p class="muted">Your agent will remove the requested feature in a new branch from ${esc(v.title)}. Other work and protected behaviors stay in scope.</p><form id="undo-form"><label class="field">What would you like to undo?<textarea name="prompt" placeholder="Remove the new sidebar, keeping our new colors and all saved issues." required maxlength="6000"></textarea></label><label class="field">Version where it was introduced<select name="source">${versionOptions(v.id)}</select></label><div class="form-bottom"><select name="runtime" class="button">${runtimeOptions()}</select><button class="button primary" ${data.operator ? "" : "disabled"}>Undo in a new branch ↗</button></div></form>`,
  );
  $("#undo-form").onsubmit = safely(async (e) => {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    const r = await action("studio.adapt", {
      target: v.id,
      source: f.get("source"),
      prompt: f.get("prompt"),
      kind,
      runtime: f.get("runtime"),
    });
    closeDialog();
    await refresh();
    select(r.revision);
  });
}
function flowDetails(v, id) {
  const f = v.flows.find((f) => f.id === id),
    run = v.protection.results.find((r) => r.id === id);
  showDialog(
    f.name,
    `${run?.video ? `<video class="video" src="${media(run.video)}" controls playsinline preload="metadata"></video>` : run?.screenshot ? `<img class="gallery-image" src="${media(run.screenshot)}" alt="Browser check result">` : '<p class="muted">This protected behavior has not produced a replay on this exact state yet.</p>'}<p class="muted">${run ? (run.passed ? "Passed in an independent copy of this saved state." : "This behavior needs attention on this saved state.") : "Inherited from its protected starting point."}</p>${run?.error ? `<div class="flow-error">${esc(run.error)}</div>` : ""}${(run?.steps || []).map((s) => `<div class="flow-step">${s.passed ? "✓" : "!"} Step ${s.step} · ${esc(s.action)} ${s.seconds !== undefined ? "· " + s.seconds + "s" : ""}</div>`).join("")}<button class="button" id="recheck" ${data.operator ? "" : "disabled"}>Replay checks again</button>`,
    "large",
  );
  $("#recheck").onclick = safely(async () => {
    await action("capture.refresh", { revision: v.id });
    closeDialog();
    toast("Replaying from a fresh copy of the saved code and data.");
    await refresh();
  });
}
async function openLive(v, record = false) {
  const address = v.product_state
    ? await action("runtime.open", { revision: v.id })
    : null;
  live = {
    version: v,
    instance: address,
    steps: [],
    recording: false,
    expecting: false,
  };
  showDialog(
    "An interactive copy · " + v.title,
    `<div class="live-main"><div class="live-bar"><span>Interactive copy · saved original preserved</span><button class="text-button" id="live-reload">↻ Reload</button></div><div class="live-loading"><span><span class="spinner"></span> Opening this saved product…</span></div></div><aside class="live-sidebar"><h3>Try it. Keep what works.</h3><p class="muted">Explore this version with its saved data. Changes here belong to this disposable copy.</p><button class="button wide" id="record-flow">● Record a behavior</button><button class="button wide" id="expect-flow" hidden>◇ Expect text to stay</button><ol id="recorded-steps" class="steps"></ol><button class="button primary wide" id="save-flow" hidden>Protect this behavior</button><div class="section" style="margin:24px 0 0"><p class="muted">Made something worth keeping in the app?</p><button class="button wide" id="save-data" ${address ? "" : "disabled"}>Save interactions as a version</button></div></aside>`,
    "live",
  );
  live = {
    version: v,
    instance: address,
    steps: [],
    recording: false,
    expecting: false,
  };
  const state = live;
  let timer;
  dialogCleanup = () => {
    clearTimeout(timer);
    live = null;
  };
  const mount = (url) => {
    if (live !== state) return;
    $(".live-loading")?.remove();
    const frame = document.createElement("iframe");
    frame.title = v.title + " — interactive copy";
    frame.sandbox = "allow-scripts allow-forms allow-same-origin";
    frame.src = url;
    $(".live-main").append(frame);
    frame.onload = () => {
      if (state.recording) sendRecord();
    };
  };
  function sendRecord() {
    const frame = $(".live-main iframe");
    if (frame && state.instance?.url)
      frame.contentWindow.postMessage(
        {
          type: "workgraph-control",
          recording: state.recording,
          asserting: state.expecting,
        },
        new URL(state.instance.url).origin,
      );
  }
  if (!address) {
    if (!v.preview_entry)
      throw Error("This version has no connected app or static page.");
    mount(data.preview_base + "/" + v.id + "/" + v.preview_entry);
  } else {
    const check = async () => {
      if (live !== state) return;
      const r = await action("runtime.touch", { instance: address.id });
      if (live !== state) return;
      state.instance = r;
      if (r.state === "ready" && !$(".live-main iframe")) mount(r.url);
      if (r.state === "failed") {
        ($(".live-loading") || $(".live-bar span")).textContent = r.error;
        return;
      }
      timer = setTimeout(
        () =>
          check().catch((e) => {
            if (live === state) toast(e.message, true);
          }),
        r.state === "ready" ? 10000 : 350,
      );
    };
    await check();
  }
  if (live !== state) return;
  if (!address) {
    $("#record-flow").disabled = true;
    $("#record-flow").title =
      "Connect a running app to record interactive behaviors.";
  }
  $("#live-reload").onclick = () => {
    if (state.recording) {
      state.steps.push({ action: "reload" });
      drawSteps();
    }
    const frame = $(".live-main iframe");
    if (frame && state.instance?.url)
      frame.contentWindow.postMessage(
        {
          type: "workgraph-control",
          command: "reload",
          recording: state.recording,
          asserting: false,
        },
        new URL(state.instance.url).origin,
      );
    else if (frame) frame.src = frame.src;
  };
  $("#record-flow").onclick = () => {
    state.recording = !state.recording;
    state.expecting = false;
    $("#record-flow").innerHTML = state.recording
      ? '<span class="record-dot"></span> Stop recording'
      : "● Record a behavior";
    $("#expect-flow").hidden = !state.recording;
    sendRecord();
  };
  $("#expect-flow").onclick = () => {
    state.expecting = !state.expecting;
    $("#expect-flow").textContent = state.expecting
      ? "Click the text to keep…"
      : "◇ Expect text to stay";
    sendRecord();
  };
  function drawSteps() {
    $("#recorded-steps").innerHTML = state.steps
      .map(
        (s) =>
          `<li>${esc(s.action)} ${esc(s.text || s.locator?.value || "")}</li>`,
      )
      .join("");
    $("#save-flow").hidden = !state.steps.some((s) => s.action === "expect");
  }
  const listener = (event) => {
    const frame = $(".live-main iframe");
    if (
      live !== state ||
      event.source !== frame?.contentWindow ||
      !state.instance?.url ||
      event.origin !== new URL(state.instance.url).origin ||
      event.data?.instance !== state.instance.id
    )
      return;
    const step = event.data.step;
    if (event.data.event === "redacted")
      return toast("Password fields are excluded from recordings.");
    if (!state.recording || !step) return;
    if (state.steps.length >= 30)
      return toast(
        "This recording has thirty steps. Protect it before starting another.",
      );
    if (
      step.action === "fill" &&
      state.steps.at(-1)?.action === "fill" &&
      JSON.stringify(step.locator) ===
        JSON.stringify(state.steps.at(-1).locator)
    )
      state.steps[state.steps.length - 1] = step;
    else state.steps.push(step);
    if (step.action === "expect") {
      state.expecting = false;
      $("#expect-flow").textContent = "◇ Expect text to stay";
      sendRecord();
    }
    drawSteps();
  };
  window.addEventListener("message", listener);
  const previous = dialogCleanup;
  dialogCleanup = () => {
    window.removeEventListener("message", listener);
    previous();
  };
  $("#save-flow").onclick = () => {
    const steps = structuredClone(state.steps),
      rect = $(".live-main iframe").getBoundingClientRect(),
      definition = {
        path: "/",
        viewport: {
          width: Math.max(320, Math.min(2000, Math.round(rect.width))),
          height: Math.max(320, Math.min(2000, Math.round(rect.height))),
        },
        steps,
      };
    showDialog(
      "Keep this behavior working",
      `<form id="flow-form"><p class="muted">${steps.length} recorded steps. Future branches inherit this expectation and replay it in an independent copy.</p><label class="quiet"><input type="checkbox" name="fresh" checked> Use fresh example text for each replay</label><p class="muted">Matching entered and expected text gets a unique mark each time.</p><label class="field">What should always work?<input name="name" placeholder="Comments stay saved after a refresh" required maxlength="120"></label><button class="button primary">Protect this behavior</button></form>`,
    );
    $("#flow-form").onsubmit = safely(async (e) => {
      e.preventDefault();
      const form = new FormData(e.currentTarget);
      if (form.get("fresh") === "on") {
        const texts = new Set(
          definition.steps
            .filter(
              (s) =>
                s.action === "fill" &&
                s.value?.length >= 6 &&
                !s.value.includes("@"),
            )
            .map((s) => s.value),
        );
        for (const text of texts) {
          if (
            definition.steps.some(
              (s) => s.action === "expect" && s.text === text,
            )
          ) {
            for (const step of definition.steps) {
              if (step.action === "fill" && step.value === text)
                step.value += " [wg-{run}]";
              if (step.action === "expect" && step.text === text)
                step.text += " [wg-{run}]";
            }
          }
        }
      }
      await action("behavior.protect", {
        revision: v.id,
        name: form.get("name"),
        definition,
      });
      closeDialog();
      await refresh();
      toast("Behavior protected. Replaying it on this saved version.");
    });
  };
  $("#save-data").onclick = safely(async () => {
    const button = $("#save-data");
    button.disabled = true;
    try {
      const r = await action("runtime.save", {
        instance: state.instance.id,
        name: "An interactive exploration",
      });
      const stillHere = live === state;
      if (stillHere) closeDialog();
      await refresh();
      if (stillHere) select(r.revision);
      toast("Interactions saved as a new version. Your original is preserved.");
    } finally {
      if (button.isConnected) button.disabled = false;
    }
  });
  if (record) $("#record-flow").click();
}
function renderJobs() {
  const jobs = data.jobs.slice(0, 3),
    sig = JSON.stringify(jobs);
  if (sig === jobsSignature) return;
  jobsSignature = sig;
  $("#activity").innerHTML = jobs.length
    ? '<div class="side-label" style="margin:0 6px 9px">AGENT ACTIVITY</div>' +
      jobs
        .map(
          (j) =>
            `<button class="task-card" data-job="${j.id}"><span>${["queued", "running"].includes(j.state) ? '<span class="spinner"></span> ' : j.state === "completed" ? "✓ " : ""}${esc(j.runtime)} · ${esc(j.state)}</span><b>${esc(pathFor(version(j.result_revision))?.name || j.prompt)}</b><small>${j.state === "completed" ? "View result and behavior checks →" : "Open task details →"}</small></button>`,
        )
        .join("")
    : "";
  $$("[data-job]").forEach(
    (b) => (b.onclick = () => jobDetails(b.dataset.job)),
  );
}
function jobDetails(id) {
  const j = data.jobs.find((j) => j.id === id);
  showDialog(
    "Your agent’s workspace",
    `<p class="dialog-intro">${esc(j.runtime)} · ${esc(j.state)}</p><p class="muted">${esc(j.prompt)}</p>${j.error ? `<div class="flow-error">${esc(j.error)}</div>` : ""}<pre class="job-output">${esc(j.output || "Waiting for the agent…")}</pre><div class="form-bottom"><button class="button" id="view-result">View saved result →</button>${["running", "queued"].includes(j.state) ? `<button class="button" id="stop-job" ${data.operator ? "" : "disabled"}>Stop task</button>` : ""}</div>`,
  );
  $("#view-result").onclick = () => {
    closeDialog();
    select(j.result_revision);
  };
  if ($("#stop-job"))
    $("#stop-job").onclick = safely(async () => {
      await action("studio.cancel", { job: j.id });
      await refresh();
      jobDetails(id);
    });
}
function search() {
  showDialog(
    "Find a saved moment",
    `<input class="search-input" aria-label="Find a saved moment" placeholder="Search moments, directions, or notes…"><div class="search-results"></div>`,
  );
  const render = () => {
    const q = $(".search-input").value.toLowerCase();
    $(".search-results").innerHTML =
      data.versions
        .filter((v) =>
          [v.title, pathFor(v)?.name, JSON.stringify(v.context)]
            .join(" ")
            .toLowerCase()
            .includes(q),
        )
        .map(
          (v) =>
            `<button class="search-result" data-result="${v.id}">${images(v)[0] ? `<img src="${media(images(v)[0].thumb)}" alt="">` : '<span class="path-dot" style="background:' + colors.get(v.path) + '"></span>'}<span><strong>${esc(v.title)}</strong><small>${esc(pathFor(v)?.name)} · ${esc(proof(v).label)}</small></span></button>`,
        )
        .join("") ||
      '<p class="muted">No moments found. Try a different word.</p>';
    $$("[data-result]").forEach(
      (b) =>
        (b.onclick = () => {
          closeDialog();
          filter = "all";
          select(b.dataset.result);
          const p = positions.get(selected),
            r = $("#canvas").getBoundingClientRect();
          camera.x = r.width / 2 - (p.x + 124) * camera.z;
          camera.y = r.height / 2 - p.y * camera.z;
          transform();
          remember();
        }),
    );
  };
  $(".search-input").oninput = render;
  render();
  $(".search-input").focus();
}
function help() {
  showDialog(
    "A few small things, done differently",
    `<p class="dialog-intro">Explore freely. Keep your bearings.</p><div class="menu-help"><p><strong>Open from your agent.</strong> Ask “open Workgraph” or run <code>workgraph open</code> in your project. It returns to this workspace without starting another task.</p><p><strong>Browse any moment.</strong> Each point has saved source, explicit context, and, when connected, a development database. Screenshots show the actual saved state.</p><p><strong>Continue from here.</strong> Start a focused task in that exact state. The existing conversation stays open. Results and independently replayed behaviors appear in the tree.</p><p><strong>Borrow what you love.</strong> Compare two moments and describe one feature to carry across. The agent adapts it in a fresh branch; the originals stay available.</p><p><strong>Come back tomorrow.</strong> Closing the tab doesn’t stop tasks. Reopening restores your selected moment and canvas position.</p></div><p class="muted">⌘ / Ctrl K · search &nbsp; F · fit tree &nbsp; Escape · close details<br>Browsing and chosen direction are separate. Choosing a version doesn’t overwrite your working files or publish it.</p>${data.operator ? '<button class="button" id="stop-workspace">Stop local workspace</button>' : ""}`,
  );
  if ($("#stop-workspace")) $("#stop-workspace").onclick = stopWorkspaceForm;
}
const refreshWaiters = [];
async function refresh() {
  if (workspaceStopped) return;
  if (polling) return new Promise((resolve) => refreshWaiters.push(resolve));
  polling = true;
  try {
    const next = await api("/api/studio");
    data = next;
    $("#connection").textContent = data.operator
      ? "Connected · private controls"
      : "Connected · viewing";
    $("#access-badge").textContent = data.operator
      ? "Local workspace"
      : "Viewing link";
    $("#new-direction").disabled = !data.operator;
    $("#project-name").textContent =
      data.sample?.kind === "fieldwork"
        ? "Fieldwork"
        : data.repository.split("/").pop();
    $(".project-mark").textContent =
      $("#project-name").textContent[0].toUpperCase();
    $("#sample-note").hidden = !data.example;
    if (first) {
      let saved;
      try {
        saved = JSON.parse(localStorage.getItem(localKey()));
      } catch {}
      selected = version(saved?.revision)
        ? saved.revision
        : version(data.focus?.revision)
          ? data.focus.revision
          : data.current || data.versions.at(-1)?.id;
      camera = saved?.camera || data.focus?.camera || camera;
      inspecting = !!saved?.inspecting;
      $("#inspector").hidden = !inspecting;
      document.body.classList.toggle("inspecting", inspecting);
      renderTree();
      if (saved?.camera || data.focus?.camera) transform();
      else fit();
      renderDetails();
      first = false;
    } else {
      const sig = JSON.stringify([
        data.current,
        data.paths.map((p) => [p.id, p.name, p.head]),
        data.versions.map((v) => [
          v.id,
          v.title,
          v.starred,
          v.protection.state,
          v.protection.updated,
        ]),
        Object.entries(data.artifacts).map(([id, a]) => [
          id,
          a.state,
          a.updated,
        ]),
      ]);
      if (sig !== signature) {
        signature = sig;
        renderTree();
        renderDetails();
      }
    }
    renderJobs();
  } catch (e) {
    $("#connection").textContent = "Reconnecting…";
    if (!data) {
      $("#empty").hidden = false;
      $("#empty").innerHTML =
        `<div class="empty-content"><h2>Let’s open your workspace.</h2><p>${esc(e.message)}</p><p class="muted">Run <code>workgraph open</code> from your project to reconnect.</p></div>`;
    }
  } finally {
    polling = false;
    if (refreshWaiters.length) {
      const waiting = refreshWaiters.splice(0);
      await refresh();
      waiting.forEach((resolve) => resolve());
    }
  }
}
$("#close-inspector").onclick = closeInspector;
$("#previous").onclick = () => {
  const v = version(selected);
  if (v.parent) select(v.parent);
};
$("#close-dialog").onclick = closeDialog;
$("#dialog").addEventListener("cancel", (e) => {
  e.preventDefault();
  closeDialog();
});
$("#dialog").addEventListener("click", (e) => {
  if (e.target === $("#dialog")) {
    const r = e.target.getBoundingClientRect();
    if (
      e.clientX < r.left ||
      e.clientX > r.right ||
      e.clientY < r.top ||
      e.clientY > r.bottom
    )
      closeDialog();
  }
});
$("#search").onclick = search;
$("#help").onclick = help;
$("#project").onclick = help;
$("#new-direction").onclick = () => {
  const v = version(selected) || version(data.current);
  if (v) agentForm(v);
  else $("#start-project")?.click();
};
$("#compare").onclick = () => compareForm();
$("#fit").onclick = $("#fit-top").onclick = fit;
$("#zoom-in").onclick = () => zoom(1.2);
$("#zoom-out").onclick = () => zoom(1 / 1.2);
$("#all-saves").onchange = () => {
  renderTree();
  fit();
};
$$(".nav-item").forEach(
  (b) =>
    (b.onclick = () => {
      filter = b.dataset.filter;
      renderTree();
    }),
);
$("#minimap").onclick = fit;
let drag = null,
  raf = 0;
const canvas = $("#canvas");
canvas.addEventListener(
  "wheel",
  (e) => {
    e.preventDefault();
    const r = canvas.getBoundingClientRect();
    zoom(Math.exp(-e.deltaY * 0.0015), e.clientX - r.left, e.clientY - r.top);
  },
  { passive: false },
);
canvas.addEventListener("pointerdown", (e) => {
  if (e.target.closest(".node,.zoom,#minimap") || e.button !== 0) return;
  drag = { x: e.clientX, y: e.clientY, cx: camera.x, cy: camera.y };
  canvas.setPointerCapture(e.pointerId);
});
canvas.addEventListener("pointermove", (e) => {
  if (!drag) return;
  camera.x = drag.cx + e.clientX - drag.x;
  camera.y = drag.cy + e.clientY - drag.y;
  if (!raf)
    raf = requestAnimationFrame(() => {
      transform();
      raf = 0;
    });
});
canvas.addEventListener("pointerup", () => {
  if (drag) {
    drag = null;
    remember();
  }
});
canvas.addEventListener("pointercancel", () => (drag = null));
document.addEventListener("keydown", (e) => {
  if ((e.metaKey || e.ctrlKey) && e.key === "k") {
    e.preventDefault();
    if (data) search();
    return;
  }
  if (e.target.closest("input,textarea,select")) return;
  if (e.key === "Escape" && !$("#dialog").open) closeInspector();
  if (e.key.toLowerCase() === "f" && !$("#dialog").open) fit();
});
window.addEventListener("pagehide", () => {
  remember();
  if (data?.operator && selected)
    fetch("/api/action", {
      method: "POST",
      keepalive: true,
      headers: {
        Authorization: "Bearer " + bearer,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        action: "studio.focus",
        revision: selected,
        camera,
      }),
    }).catch(() => {});
});
new ResizeObserver(() => {
  if (data) drawMini();
}).observe(canvas);
refresh();
setInterval(() => {
  if (!document.hidden) refresh();
}, 2400);
document.addEventListener("visibilitychange", () => {
  if (!document.hidden) refresh();
});
function connectForm(v) {
  showDialog(
    "Connect your development app",
    `<p class="dialog-intro">See the product at every moment.</p><p class="muted">Approve a local command once. Workgraph runs saved copies with separate data. Ask your agent for the argument list if you’re unsure.</p><form id="connect-form"><label class="field">App name<input name="name" value="${esc(data.repository.split("/").pop())}" required maxlength="100"></label><label class="field">Command arguments (JSON array, include {port})<input name="command" value='["npm","run","dev","--","--host","0.0.0.0","--port","{port}"]' required></label><label class="field">Preparation commands (JSON array of arrays)<input name="prepare" value='[["npm","ci","--ignore-scripts"]]'></label><label class="field">Readiness route<input name="health" value="/" required></label><label class="field">SQLite development databases (one per line, optional)<textarea name="files" style="min-height:55px" placeholder=".workgraph-data/app.db"></textarea></label><label class="quiet"><input name="import" type="checkbox"> Include the current project’s development data in this new version</label><p class="muted">Approved commands execute locally in a filesystem sandbox, with shared network access. Use non-secret development data. Hosted services, production databases, and process memory aren’t restored.</p><div class="form-bottom"><small>Creates a new connected version.</small><button class="button primary">Connect & capture ↗</button></div></form>`,
  );
  $("#connect-form").onsubmit = safely(async (e) => {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    let command, prepare;
    try {
      command = JSON.parse(f.get("command"));
      prepare = JSON.parse(f.get("prepare") || "[]");
    } catch {
      throw Error(
        "Command and preparation fields need valid JSON argument arrays.",
      );
    }
    const r = await action("app.configure", {
      revision: v.id,
      definition: {
        name: f.get("name"),
        command,
        prepare,
        health: f.get("health"),
        data_files: String(f.get("files"))
          .split("\n")
          .map((x) => x.trim())
          .filter(Boolean),
        screens: [
          { name: "Workspace", path: "/", width: 1280, height: 800 },
          { name: "On your phone", path: "/", width: 390, height: 844 },
        ],
      },
      import_data: f.get("import") === "on",
    });
    closeDialog();
    await refresh();
    select(r.revision);
    toast("App connected. Capturing real product views in the background.");
  });
}

function renamePathForm(path) {
  showDialog(
    "Name this direction",
    `<form id="path-form"><label class="field">Direction name<input name="name" maxlength="120" value="${esc(path.name)}" required></label><button class="button primary">Save name</button></form>`,
  );
  $("#path-form").onsubmit = safely(async (e) => {
    e.preventDefault();
    await action("studio.path.rename", {
      path: path.id,
      name: new FormData(e.currentTarget).get("name"),
    });
    closeDialog();
    await refresh();
    renderTree();
    renderDetails();
  });
}

function stopWorkspaceForm() {
  const active = data.jobs.filter((j) =>
    ["running", "queued"].includes(j.state),
  );
  showDialog(
    "Stop the local workspace",
    `<p class="muted">Saved history stays on this computer. ${active.length ? active.length + " agent task(s) will stop; their partial work is saved." : "There are no agent tasks running."} Ask your agent to open Workgraph when you want to return.</p><button class="button primary" id="confirm-stop">Stop workspace</button>`,
  );
  $("#confirm-stop").onclick = safely(async () => {
    await action("workspace.stop");
    workspaceStopped = true;
    closeDialog();
    $("#connection").textContent = "Workspace stopped";
    toast("History saved. Ask your agent to open Workgraph to return.");
  });
}
