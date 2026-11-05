"use strict";

const $ = (selector) => document.querySelector(selector);
const esc = (value) => String(value ?? "").replace(/[&<>"']/g, ch => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[ch]));
const short = (value) => String(value || "").replace(/^[a-z]+_/, "").slice(0, 7);
const badge = (state, label) => `<span class="badge ${esc(state)}">${esc(label || state)}</span>`;
const fragment = new URLSearchParams(location.hash.slice(1));
const token = fragment.get("token") || sessionStorage.getItem("workgraph-token") || "";
if (token) sessionStorage.setItem("workgraph-token", token);
let data = null, tab = "work", selected = null, selectedAttempt = null, busy = false, signature = "";
let toastTimer;

function toast(message, error=false) {
  const element = $("#toast");
  element.textContent = message;
  element.className = "toast" + (error ? " error" : "");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => element.classList.add("hidden"), error ? 8000 : 4500);
}

async function request(action, values={}) {
  if (busy) return null;
  busy = true;
  document.body.classList.add("busy");
  document.querySelectorAll("button").forEach(button => button.disabled = true);
  try {
    const response = await fetch("/api/action", {method:"POST", headers:{"Authorization":"Bearer " + token,"Content-Type":"application/json"},
      body:JSON.stringify({action, ...values, request_id:crypto.randomUUID()})});
    const result = await response.json();
    if (!response.ok) throw new Error(result.message || result.error || "The operation did not complete.");
    await refresh(true);
    return result;
  } catch (error) {
    toast(error.message, true);
    return null;
  } finally {
    busy = false;
    document.body.classList.remove("busy");
    document.querySelectorAll("button").forEach(button => button.disabled = false);
    render();
  }
}

async function refresh(force=false) {
  try {
    const response = await fetch("/api/state", {headers:{Authorization:"Bearer " + token}});
    const result = await response.json();
    if (!response.ok) throw new Error(result.message || "Open the private URL printed by Workgraph.");
    const next = JSON.stringify(result);
    const priorPhase = data?.example?.phase;
    data = result;
    $("#connection").textContent = "Connected locally";
    const parts = result.repository.split("/").filter(Boolean);
    $("#repo-name").textContent = parts.at(-1) || result.repository;
    if (!selected && data.work.length) selected = data.work[0].id;
    if (result.example && result.example.phase !== priorPhase) {
      const phase = result.example.phase;
      if (phase >= 4) tab = "review";
      else {
        tab = "work";
        selected = phase === 3 ? result.example.client?.work : result.example.api?.work || selected;
        selectedAttempt = null;
      }
    }
    if (force || signature !== next) {
      signature = next;
      render();
    }
  } catch (error) {
    $("#connection").textContent = "Connection unavailable";
    if (!data) $("#content").innerHTML = `<div class="panel empty"><h3>Connect to your workspace</h3><p>${esc(error.message)}</p></div>`;
  }
}

function latestAttempt(workId) {
  const values = data.attempts.filter(attempt => attempt.work_id === workId);
  return values.filter(attempt => attempt.state === "active").at(-1) || values.filter(attempt => attempt.state !== "superseded").at(-1) || values.at(-1);
}

function workTitle(workId) { return data.work.find(work => work.id === workId)?.intent || "Related work"; }
function runtimeMark(runtime) { return ({hermes:"H",codex:"C",claude:"A",local:"L",mcp:"M"}[runtime] || runtime?.[0] || "L").toUpperCase(); }

function render() {
  if (!data) return;
  const attention = data.work.filter(work => {
    const attempt = latestAttempt(work.id);
    return attempt?.outdated_dependencies.length || attempt?.state === "interrupted";
  }).length;
  const ready = data.candidates.filter(candidate => candidate.state === "ready").length;
  $("#work-count").textContent = data.work.length;
  $("#review-count").textContent = ready;
  $("#metric-work").textContent = data.work.length;
  $("#metric-checkpoints").textContent = data.revisions.length;
  $("#metric-attention").textContent = attention;
  $("#metric-ready").textContent = ready;
  $("#page-title").textContent = ({work:"The work continues.",review:"Review the outcome.",timeline:"Nothing important gets lost."}[tab]);
  $("#page-subtitle").textContent = ({work:"Every attempt has a place. Every handoff has context.",review:"Exact compositions. Recorded checks. A deliberate acceptance.",timeline:"An inspectable record of work, handoffs, and decisions."}[tab]);
  document.querySelectorAll("[data-nav]").forEach(element => element.classList.toggle("active", element.dataset.nav === tab));
  $("#new-work").textContent = tab === "review" ? "＋ Compose candidate" : "＋ New work";
  const example = data.example;
  $("#tour").classList.toggle("hidden", !example);
  if (example) {
    $("#tour-index").textContent = String(example.phase + 1).padStart(2, "0");
    $("#tour-title").textContent = example.beat.title;
    $("#tour-body").textContent = example.beat.body;
    $("#tour-progress").style.width = (example.phase / (example.total - 1) * 100) + "%";
    $("#tour-next").classList.toggle("hidden", !example.beat.action);
    $("#tour-next").textContent = example.beat.action ? example.beat.action + " →" : "Complete";
    $("#footer-state").textContent = "Guided example · scripted edits, real repository operations";
  } else {
    $("#footer-state").textContent = "All state stays in your repository.";
  }
  if (tab === "work") renderWork();
  else if (tab === "review") renderReview();
  else renderTimeline();
  if (busy) document.querySelectorAll("button").forEach(button => button.disabled = true);
}

function renderWork() {
  const dependencies = data.work.flatMap(work => {
    const attempt = latestAttempt(work.id);
    return Object.entries(attempt?.dependencies || {}).map(([wid, revision]) => {
      const stale = attempt.outdated_dependencies.some(value => value.work === wid);
      return `<div class="dependency-map ${stale ? "changed" : ""}"><span>${esc(workTitle(wid))}</span><div><small>${stale ? "REVISION CHANGED" : "PINNED DEPENDENCY"}</small><i>⟶</i></div><span>${esc(work.intent)}</span></div>`;
    });
  }).join("");
  const cards = data.work.map(work => {
    const attempt = latestAttempt(work.id);
    const revisions = data.revisions.filter(revision => revision.work_id === work.id);
    const state = attempt?.outdated_dependencies.length ? "outdated" : attempt?.state || "active";
    const dots = revisions.slice(-6).map((revision, index, values) => `${index ? '<span class="revision-line"></span>' : ""}<span class="revision-dot ${index === values.length - 1 ? "latest" : ""}" title="${esc(revision.context.summary)}"></span>`).join("");
    const dependency = attempt?.outdated_dependencies[0];
    return `<article class="work-card ${work.id === selected ? "selected" : ""} ${dependency ? "attention" : ""}" data-work="${esc(work.id)}" tabindex="0" role="button" aria-label="Inspect ${esc(work.intent)}">
      <div class="work-title-line"><span class="work-title">${esc(work.intent)}</span>${badge(state, state === "outdated" ? "dependency changed" : state)}</div>
      <div class="runtime-row"><span class="runtime-dot ${esc(attempt?.runtime)}">${esc(runtimeMark(attempt?.runtime))}</span><span>${esc(attempt?.runtime || "local")} <span class="muted">/</span> ${esc(attempt?.session || "")}</span></div>
      <div class="revision-path">${dots || '<span class="revision-dot"></span>'}<span class="revision-path-label">${revisions.length} ${revisions.length === 1 ? "checkpoint" : "checkpoints"}</span></div>
      ${dependency ? `<div class="dependency-note">↳ ${esc(dependency.intent)} changed. This attempt still uses the earlier revision.</div>` : ""}
      <div class="work-meta"><span>${esc(attempt?.context.summary || "Workspace ready for its first checkpoint")}</span><span>↗</span></div></article>`;
  }).join("");
  const empty = `<div class="empty"><div class="empty-symbol">◈</div><h3>A place for your next idea.</h3><p>Open a piece of work. Your agents get isolated attempts, durable checkpoints, and a shared understanding.</p><button class="button primary" data-action="new">Open your first work</button></div>`;
  $("#content").innerHTML = `<div class="workspace-grid"><section class="panel"><div class="panel-heading"><h2>Work in progress</h2><span>${data.work.length} WORK ITEMS</span></div>${dependencies}${cards || empty}</section><aside class="panel" id="detail">${detail()}</aside></div>`;
}

function detail() {
  const work = data.work.find(value => value.id === selected);
  if (!work) return `<div class="panel-heading"><h2>Ready for the next agent</h2></div><div class="empty"><p>Select work to see the context an agent can pick up.</p></div>`;
  let attempt = data.attempts.find(value => value.id === selectedAttempt && value.work_id === work.id) || latestAttempt(work.id);
  if (!attempt) return "";
  const context = attempt.context;
  const list = (title, values, extra="") => values?.length ? `<section class="context-section ${extra}"><h3>${title}</h3><ul>${values.map(value => `<li>${esc(value)}</li>`).join("")}</ul></section>` : "";
  const attempts = data.attempts.filter(value => value.work_id === work.id);
  return `<div class="panel-heading"><h2>Ready for the next agent</h2><span>HANDOFF CONTEXT</span></div><div class="detail-inner"><div class="section-label">THE OUTCOME</div><h2 class="detail-title">${esc(work.intent)}</h2>
    <div class="pill-row">${badge(attempt.state)}<span class="badge">${esc(attempt.runtime)}</span>${attempt.head ? `<span class="badge" title="${esc(attempt.head)}">${esc(short(attempt.head))}</span>` : ""}</div>
    <section class="context-section"><h3>WHERE THINGS STAND</h3><p>${esc(context.summary || work.intent)}</p></section>
    ${list("NEXT STEPS", context.plan)}${list("DECISIONS ALREADY MADE", context.decisions)}${list("OPEN QUESTIONS", context.questions, "questions")}
    ${Object.keys(attempt.dependencies).length ? `<section class="context-section"><h3>BUILT ON</h3>${Object.entries(attempt.dependencies).map(([wid, revision]) => `<p>↳ ${esc(workTitle(wid))} <span class="badge" title="${esc(revision)}">${esc(short(revision))}</span></p>`).join("")}</section>` : ""}
    <div class="detail-actions">
      ${attempt.state === "active" ? `<button class="button small primary" data-action="checkpoint" data-attempt="${esc(attempt.id)}">Save context</button>` : ""}
      ${attempt.head && attempt.state !== "superseded" ? `<button class="button small" data-action="takeover" data-attempt="${esc(attempt.id)}">Hand off ↗</button>` : ""}
      ${attempt.outdated_dependencies.length ? `<button class="button small" data-action="reconcile" data-attempt="${esc(attempt.id)}">Reconcile</button>` : ""}
      ${attempt.head ? `<button class="button small ghost" data-action="fork" data-revision="${esc(attempt.head)}">Fork attempt</button><button class="button small ghost" data-action="diff" data-revision="${esc(attempt.head)}">View changes</button>` : ""}
    </div><div class="workspace-path" title="Managed workspace">${esc(attempt.workspace)}</div>
    <div class="attempt-list"><div class="section-label">PRESERVED ATTEMPTS</div>${attempts.map(value => `<div class="attempt-row"><button class="button small ghost" data-action="attempt" data-attempt="${esc(value.id)}">${esc(value.runtime)} · ${esc(value.session)}</button>${badge(value.state)}</div>`).join("")}</div></div>`;
}

function renderReview() {
  const cards = data.candidates.map((candidate, index) => {
    const titles = Object.keys(candidate.manifest).map(workTitle);
    const checks = Object.entries(candidate.checks).map(([name, state]) => {
      const evidence = candidate.evidence.find(value => value.check === name);
      return `<div class="check-row"><span>${state === "passed" ? "✓" : state === "failed" ? "×" : "○"}</span><span>${esc(name)}</span>${badge(state)}</div>${evidence?.output ? `<pre class="check-output">${esc(evidence.output)}</pre>` : ""}`;
    }).join("");
    return `<article class="candidate-card"><div class="candidate-heading"><div><h3>${esc(titles.join(" + "))}</h3><div class="candidate-subtitle">CANDIDATE ${esc(short(candidate.candidate))} <span class="muted">·</span> ${Object.keys(candidate.manifest).length} pieces of work</div></div>${badge(candidate.state, candidate.state === "landed" ? "accepted" : candidate.state)}</div>
      ${candidate.outdated_inputs.length ? `<div class="dependency-note">${candidate.outdated_inputs.map(value => esc(value.intent)).join(", ")} has a newer selected revision. This candidate needs reconciliation.</div>` : ""}
      ${candidate.conflict ? `<pre class="check-output">${esc(candidate.conflict)}</pre>` : ""}${checks || '<p class="body-copy">Configure an operator-owned check with the CLI before accepting this candidate.</p>'}
      <div class="candidate-actions">${!["landed", "conflicted", "stale"].includes(candidate.state) ? `<button class="button small" data-action="verify" data-candidate="${esc(candidate.candidate)}">Run checks</button>` : ""}
      ${candidate.state === "ready" ? `<button class="button small primary" data-action="accept" data-candidate="${esc(candidate.candidate)}">Accept checked candidate ↗</button>` : ""}
      <button class="button small ghost" data-action="diff" data-candidate="${esc(candidate.candidate)}">Inspect changes</button></div></article>`;
  }).join("");
  $("#content").innerHTML = `<div class="review-toolbar"><p>Acceptance applies to the exact composition and recorded checks shown here.</p><span class="count-label">${data.candidates.length} CANDIDATES</span></div>${cards || '<div class="panel empty"><div class="empty-symbol">▱</div><h3>Compose an outcome.</h3><p>Select saved revisions to inspect them together. Their original attempts stay intact.</p><button class="button primary" data-action="compose">Compose candidate</button></div>'}`;
}

const eventNames = {"repository.initialized":"Workspace initialized","attempt.opened":"An isolated attempt opened","checkpoint.created":"Code and context checkpointed","checkpoint.unchanged":"Checkpoint already current","attempt.interrupted":"Session interrupted; work preserved","attempt.paused":"Attempt paused","attempt.transferred":"Work handed to a new session","attempt.reconciled":"Dependency updates reconciled into a new attempt","candidate.composed":"An exact candidate composed","candidate.checked":"Candidate checked against operator policy","candidate.accepted":"Checked candidate accepted into Git","revision.selected":"Preferred revision selected","check.configured":"Operator check configured","repository.recovered":"Interrupted operations inspected"};
function renderTimeline() {
  $("#content").innerHTML = `<section class="panel"><div class="panel-heading"><h2>History of the work</h2><span>NEWEST FIRST</span></div>${data.events.map(event => `<div class="timeline-row"><span class="timeline-icon">${event.type.includes("accepted") ? "✓" : event.type.includes("transferred") ? "↗" : "·"}</span><div><div class="timeline-title">${esc(eventNames[event.type] || event.type)}</div><div class="timeline-detail">${esc(event.session || "workspace")} ${event.object_id ? "· " + esc(short(event.object_id)) : ""}</div></div><span class="timeline-time">${esc(new Date(event.created * 1000).toLocaleTimeString([], {hour:"2-digit",minute:"2-digit"}))}</span></div>`).join("")}</section>`;
}

function modal(html) { $("#modal-content").innerHTML = html; $("#modal").showModal(); }
function closeModal() { $("#modal").close(); }
function lines(id) { return $(id).value.split("\n").map(value => value.trim()).filter(Boolean); }
function modalButtons(label, action) { return `<div class="modal-buttons"><button class="button" value="cancel">Cancel</button><button type="button" class="button primary" data-action="${action}">${label}</button></div>`; }

function openNew() {
  modal(`<div class="eyebrow">A DURABLE OUTCOME</div><h2>Open a piece of work.</h2><p>Give the work an objective. The workspace and history belong to the work, even when its session changes.</p><label for="intent">What should change?</label><input id="intent" placeholder="Migrate the profile API" required><label for="runtime">First worker</label><select id="runtime"><option value="hermes">Hermes</option><option value="codex">Codex</option><option value="claude">Claude Code</option><option value="local">Local session</option></select>${modalButtons("Create isolated attempt", "create")}`);
  $("#intent").focus();
}

function openCompose() {
  const works = data.work.filter(work => work.selected_revision);
  modal(`<div class="eyebrow">EXACT REVISIONS</div><h2>Compose a candidate.</h2><p>Choose the work to consider together. Exact pinned dependencies are included automatically.</p>${works.map(work => `<label class="checkbox-row"><input type="checkbox" name="revision" value="${esc(work.selected_revision)}" checked><span>${esc(work.intent)}</span></label>`).join("") || '<p>Save a checkpoint first.</p>'}${modalButtons("Compose candidate", "create-candidate")}`);
}

async function act(element) {
  const action = element.dataset.action;
  if (action === "new") return openNew();
  if (action === "compose") return openCompose();
  if (action === "attempt") { selectedAttempt = element.dataset.attempt; return render(); }
  if (action === "create") {
    const intent = $("#intent").value.trim();
    if (!intent) return $("#intent").focus();
    const result = await request("open", {intent, runtime:$("#runtime").value, session:$("#runtime").value + "-session"});
    if (result) { selected = result.work; selectedAttempt = result.attempt; closeModal(); render(); toast("Workspace ready. Launch your agent in the displayed path."); }
  }
  if (action === "checkpoint") {
    const attempt = data.attempts.find(value => value.id === element.dataset.attempt);
    modal(`<div class="eyebrow">CONTEXT FOR THE NEXT SESSION</div><h2>Save the engineering situation.</h2><label for="summary">Where things stand</label><textarea id="summary">${esc(attempt.context.summary)}</textarea><label for="plan">Next steps · one per line</label><textarea id="plan">${esc((attempt.context.plan || []).join("\n"))}</textarea><label for="decisions">Decisions made · one per line</label><textarea id="decisions">${esc((attempt.context.decisions || []).join("\n"))}</textarea><label for="questions">Open questions · one per line</label><textarea id="questions">${esc((attempt.context.questions || []).join("\n"))}</textarea><input id="attempt-id" type="hidden" value="${esc(attempt.id)}">${modalButtons("Save checkpoint", "save-context")}`);
  }
  if (action === "save-context") {
    const result = await request("checkpoint", {attempt:$("#attempt-id").value, summary:$("#summary").value, plan:lines("#plan"), decisions:lines("#decisions"), questions:lines("#questions")});
    if (result) { closeModal(); toast("Code and explicit context saved together."); }
  }
  if (action === "takeover") {
    modal(`<div class="eyebrow">A NEW WORKER · THE SAME WORK</div><h2>Hand off this attempt.</h2><p>The replacement receives a fresh workspace and the saved engineering context. The old attempt remains inspectable and cannot publish new checkpoints.</p><label for="new-runtime">Replacement runtime</label><select id="new-runtime"><option value="codex">Codex</option><option value="hermes">Hermes</option><option value="claude">Claude Code</option><option value="local">Local session</option></select><input type="hidden" id="attempt-id" value="${esc(element.dataset.attempt)}">${modalButtons("Prepare replacement workspace", "transfer")}`);
  }
  if (action === "transfer") {
    const runtime = $("#new-runtime").value;
    const result = await request("takeover", {attempt:$("#attempt-id").value, runtime, session:runtime + "-replacement"});
    if (result) { selectedAttempt = result.attempt; closeModal(); render(); toast("Replacement workspace ready. Code, decisions, and questions are preserved."); }
  }
  if (action === "reconcile") {
    const result = await request("reconcile", {attempt:element.dataset.attempt});
    if (result) { selectedAttempt = result.attempt; render(); toast(result.state === "conflicted" ? "Text conflicts recorded. Original work is preserved." : "Updated view ready. Inspect the behavior and save a new checkpoint."); }
  }
  if (action === "fork") {
    const result = await request("fork", {revision:element.dataset.revision});
    if (result) { selectedAttempt = result.attempt; render(); toast("Alternative attempt opened. The original is unchanged."); }
  }
  if (action === "create-candidate") {
    const revisions = Array.from(document.querySelectorAll('input[name="revision"]:checked')).map(value => value.value);
    if (!revisions.length) return toast("Choose at least one saved revision.", true);
    const result = await request("propose", {revisions});
    if (result) { closeModal(); tab = "review"; render(); toast("Candidate composed from exact revisions."); }
  }
  if (action === "verify") {
    const required = data.checks.filter(check => check.required);
    if (!required.length) return toast("Configure an operator-owned check with workgraph set-check first.", true);
    for (const check of required) {
      const result = await request("verify", {candidate:element.dataset.candidate, check:check.name});
      if (!result) break;
      toast(result.passed ? `${check.name} passed for this candidate.` : `${check.name} failed. Acceptance remains blocked.`, !result.passed);
    }
  }
  if (action === "accept") {
    const result = await request("accept", {candidate:element.dataset.candidate});
    if (result) toast("Accepted as an ordinary Git commit. The full work history remains available.");
  }
  if (action === "diff") {
    const result = await request("diff", {revision:element.dataset.revision, candidate:element.dataset.candidate});
    if (result) modal(`<div class="eyebrow">SOURCE CHANGES</div><h2>Inspect the exact change.</h2><pre class="diff">${esc(result.patch || "No source changes.")}</pre>`);
  }
}

document.addEventListener("click", event => {
  const nav = event.target.closest("[data-nav]");
  if (nav) { tab = nav.dataset.nav; render(); }
  const work = event.target.closest("[data-work]");
  if (work) { selected = work.dataset.work; selectedAttempt = null; render(); }
  const element = event.target.closest("[data-action]");
  if (element) { event.preventDefault(); act(element); }
});
document.addEventListener("keydown", event => {
  if ((event.key === "Enter" || event.key === " ") && event.target.matches("[data-work]")) {
    event.preventDefault(); selected = event.target.dataset.work; selectedAttempt = null; render();
  }
});
$("#new-work").addEventListener("click", () => tab === "review" ? openCompose() : openNew());
$("#tour-next").addEventListener("click", () => request("example.advance", {phase:data.example.phase}));
$("#help-button").addEventListener("click", () => modal(`<div class="eyebrow">WORKGRAPH V1</div><h2>The work outlives the worker.</h2><div class="body-copy"><p><strong>Work</strong> keeps the objective. An <strong>attempt</strong> owns an isolated workspace. A <strong>checkpoint</strong> saves code and explicit context. A <strong>candidate</strong> composes exact revisions.</p><p>Native Hermes tools capture foreground changes automatically. Codex and Claude Code can use the shared MCP tools and local hook adapters.</p><p>Checks are configured by the operator and run against the exact candidate. Changed dependencies, code, or check definitions require current evidence. Acceptance writes an ordinary commit to <strong>workgraph/accepted</strong>.</p><p>V1 runs locally. Recorded notes are data, not new permissions. The system identifies exact recorded dependencies; it does not claim to discover every semantic relationship.</p></div>`));
$("#modal").addEventListener("click", event => { if (event.target === $("#modal")) closeModal(); });
refresh();
setInterval(() => { if (!busy) refresh(); }, 1500);
