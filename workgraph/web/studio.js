"use strict";
const $=s=>document.querySelector(s);
const esc=v=>String(v??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const token=new URLSearchParams(location.hash.slice(1)).get("token")||sessionStorage.getItem("workgraph-token")||"";
if(token)sessionStorage.setItem("workgraph-token",token);
let data=null,selected=null,tab="explore",device="desktop",left=null,right=null,comparison=null,comparisonKey="",busy=false,signature="",toastTimer;
const choices=new Set(),requestIds=new Map();
const colors=["#9aaf82","#c3a276","#a698ca","#82aaa8","#cb939c","#94a4c5"];
const previewObserver=new ResizeObserver(entries=>entries.forEach(entry=>layoutPreview(entry.target)));
function layoutPreview(box){
 const frame=box.querySelector("iframe");if(!frame)return;
 if(box.closest(".compare-grid")&&!box.classList.contains("phone")){
  const scale=box.clientWidth/1100;
  Object.assign(frame.style,{width:"1100px",maxWidth:"none",height:(box.clientHeight/scale)+"px",position:"absolute",left:"0",top:"0",transform:`scale(${scale})`,transformOrigin:"top left"});
 }else{frame.style.cssText="";}
}
function layoutPreviews(){previewObserver.disconnect();document.querySelectorAll("[data-preview-body]").forEach(box=>{layoutPreview(box);previewObserver.observe(box);});}
const version=id=>data?.versions.find(v=>v.id===id);
const path=id=>data?.paths.find(p=>p.id===id);
const title=id=>version(id)?.title||"Saved version";
const pathColor=id=>colors[Math.max(0,data.paths.findIndex(p=>p.id===id))%colors.length];
const age=t=>{const m=Math.max(0,Math.floor((Date.now()/1000-t)/60));return m<1?"just now":m<60?`${m}m ago`:m<1440?`${Math.floor(m/60)}h ago`:`${Math.floor(m/1440)}d ago`;};
const isCurrent=id=>data.current===id;
function toast(message,error=false){$("#toast").textContent=message;$("#toast").className="toast"+(error?" error":"");clearTimeout(toastTimer);toastTimer=setTimeout(()=>$("#toast").classList.add("hidden"),error?9000:4500);}
async function call(action,values={}){
 const identity=JSON.stringify({action,...values});
 if(!requestIds.has(identity))requestIds.set(identity,crypto.randomUUID());
 try{
  const res=await fetch("/api/action",{method:"POST",headers:{Authorization:"Bearer "+token,"Content-Type":"application/json"},body:JSON.stringify({action,...values,request_id:requestIds.get(identity)})});
  const result=await res.json();if(!res.ok){if(res.status<500&&result.error!=="REQUEST_PENDING")requestIds.delete(identity);throw new Error(result.message||"This action could not finish.");}
  requestIds.delete(identity);return result;
 }catch(error){toast(error.message,true);return null;}
}
async function refresh(force=false){
 try{
  const res=await fetch("/api/studio",{headers:{Authorization:"Bearer "+token}});const result=await res.json();
  if(!res.ok)throw new Error(result.message||"Open the private workspace URL.");
  const next=JSON.stringify(result),priorCurrent=data?.current;data=result;
  if(!selected){try{selected=localStorage.getItem("workgraph-view:"+data.repository);}catch{}selected=version(selected)?selected:data.current||data.versions.at(-1)?.id;}
  if(!version(selected))selected=data.current||data.versions.at(-1)?.id;
  if(priorCurrent&&selected===priorCurrent&&data.current!==priorCurrent)selected=data.current;
  $("#connection").textContent="Connected locally";
  if(force||signature!==next){signature=next;render();}
 }catch(error){$("#connection").textContent="Connection unavailable";if(!data)$("#main-content").innerHTML=`<div class="empty-state"><h2>Connect to your project</h2><p>${esc(error.message)}</p></div>`;}
}
function view(id){if(!version(id))return;selected=id;try{localStorage.setItem("workgraph-view:"+data.repository,id);}catch{}tab="explore";render();}
function render(){
 if(!data)return;
 $("#project-name").textContent=data.example?"Luma Objects":data.repository.split("/").filter(Boolean).at(-1);
 $("#example-label").classList.toggle("hidden",!data.example);
 $("#story-banner").classList.toggle("hidden",!data.example||sessionStorage.getItem("workgraph-story-dismissed")==="yes");
 $("#engineering-link").href="/engineering#token="+encodeURIComponent(token);
 const running=data.jobs.filter(j=>["queued","running"].includes(j.state)).length;$("#job-count").textContent=running||"";
 $("#view-name").textContent=({explore:"Explore",compare:"Compare versions",agents:"Agent tasks"})[tab];
 $("#page-title").textContent=({explore:"Good ideas need a way back.",compare:"See the difference. Keep the good parts.",agents:"A fresh perspective, from the right place."})[tab];
 $("#page-description").textContent=({explore:"Open a version. Try another direction. Keep what you love.",compare:"Two saved versions, side by side. Your originals stay available.",agents:"Give an agent a saved starting point. Its work stays connected to that direction."})[tab];
 document.querySelectorAll("[data-tab]").forEach(b=>b.classList.toggle("active",b.dataset.tab===tab));
 $("#new-path").disabled=!selected;
 $("#paths").innerHTML=data.paths.map(p=>`<button class="path-button ${version(selected)?.path===p.id?"active":""}" data-view="${esc(p.head)}" title="${esc(p.name)}"><span class="path-dot" style="--dot:${pathColor(p.id)}"></span><span class="path-name">${esc(p.name)}</span><small>${data.jobs.some(j=>(j.path||j.attempt_id)===p.id&&["running","queued"].includes(j.state))?"working":""}</small></button>`).join("")||'<p class="inline-note">Your first path will appear here.</p>';
 $("#favorites").innerHTML=data.versions.filter(v=>v.starred).map(v=>`<button class="favorite-button" data-view="${esc(v.id)}"><span>☆</span>${esc(v.title)}</button>`).join("")||'<p class="inline-note">Star a version to find it again.</p>';
 if(!data.versions.length){renderEmpty();return;}
 if(tab==="explore")renderExplore();else if(tab==="compare")renderCompare();else renderJobs();
 layoutPreviews();
}
function renderEmpty(){
 $("#main-content").innerHTML=`<div class="empty-state"><div class="empty-mark">↳</div><h2>Your project, with room to explore.</h2><p>Save a starting point from your current project. Every direction you try can have its own place, without losing the one you liked.</p><button class="button primary" data-action="start">Save a starting point</button><p class="inline-note">Captures this project's tracked and non-ignored working files. Your checkout and staging stay as they are.</p></div>`;
 $("#new-path").disabled=true;
}
function preview(v,side="main"){
 const address=v.preview_entry?`${data.preview_base}/${encodeURIComponent(v.id)}/${v.preview_entry.split("/").map(encodeURIComponent).join("/")}`:null;
 return `<div class="preview-body ${device==="phone"?"phone":""}" data-preview-body>${address?`<iframe src="${esc(address)}" title="${esc(side+": "+v.title)}" sandbox="allow-scripts" referrerpolicy="no-referrer" loading="lazy"></iframe>`:`<div class="no-preview"><div class="empty-mark">▤</div><h3>This version is saved.</h3><p>${esc(v.preview_note||"This project has no saved static web entry to preview.")} Explore its files, compare changes, or continue it with an agent.</p><button class="button" data-action="files" data-id="${esc(v.id)}">Explore ${v.file_count} saved files</button></div>`}</div>`;
}
function deviceButtons(){return `<div class="device-toggle" aria-label="Preview size"><button data-device="desktop" class="${device==="desktop"?"active":""}">Desktop</button><button data-device="phone" class="${device==="phone"?"active":""}">Phone</button></div>`;}
function previewBar(v){return `<div class="preview-bar"><div class="preview-address"><span>●</span> Saved preview <span>/</span> ${esc(v.id.slice(-7))}</div>${deviceButtons()}</div>`;}
function renderExplore(){
 const v=version(selected);if(!v)return;
 const keepPreview=$("#selected-preview")?.dataset.version===v.id;
 if(!keepPreview)$("#main-content").innerHTML=`<div class="explore-grid"><section class="preview-card" id="selected-preview" data-version="${esc(v.id)}"><div class="preview-toolbar"><div><div class="version-eyebrow">YOU’RE LOOKING AT</div><div class="version-label" id="selected-title">${esc(v.title)}</div></div><div class="preview-toolbar-actions" id="selected-controls"></div></div>${preview(v)}${previewBar(v)}</section><aside class="inspector" id="inspector"></aside></div><section class="history-panel" id="history"></section>`;
 $("#selected-title").textContent=v.title;
 $("#selected-controls").innerHTML=`<span class="status-tag ${isCurrent(v.id)?"current":"viewing"}">${isCurrent(v.id)?"CURRENT DIRECTION":"VIEWING HISTORY"}</span>${!isCurrent(v.id)?'<button class="button small" data-action="choose">Make current ↗</button>':''}<button class="button small ghost" data-action="expand" aria-label="Expand preview">⛶</button>`;
 const p=path(v.path),ctx=v.context;
 const list=(label,items)=>items?.length?`<div class="inspector-label">${label}</div><ul>${items.map(x=>`<li>${esc(x)}</li>`).join("")}</ul>`:"";
 $("#inspector").innerHTML=`<div class="inspector-heading"><span class="eyebrow">A SAVED PLACE TO CONTINUE</span><button class="star" data-action="star" aria-label="${v.starred?"Unstar":"Star"} this version">${v.starred?"★":"☆"}</button></div><h2>${esc(v.title)}</h2><p>${isCurrent(v.id)?"Your chosen direction. New ideas can branch from here.":"You’re exploring a saved version. Your current direction is still safe."}</p><div class="inspector-label">ON THIS PATH</div><span class="path-pill"><span class="path-dot" style="--dot:${pathColor(v.path)}"></span>${esc(p?.name)}</span><div class="saved-info">${esc(v.runtime==="local"?"Saved locally":v.runtime)} · ${age(v.created)}${v.source?'<br>Includes chosen changes from another version.':''}</div><div class="inspector-actions"><button class="button primary" data-action="agent">Continue with an agent ↗</button><button class="button" data-action="branch">Try another direction</button><button class="button ghost" data-action="compare">Compare this version ◫</button><button class="button ghost" data-action="rename">Rename version</button><button class="button ghost" data-action="download" title="Download saved regular files as a ZIP. Git metadata, symbolic links, and ignored files stay out.">Download this version ↓</button><button class="button ghost" data-action="copy-agent">Copy starting point for an agent ↗</button></div><details class="notes"><summary>What the next agent will know</summary>${list("NEXT STEPS",ctx.plan)}${list("DECISIONS",ctx.decisions)}${list("OPEN QUESTIONS",ctx.questions)}<p>Saved code and explicit notes follow this version. Current instructions stay authoritative.</p></details>`;
 renderHistory();
}
function renderHistory(){
 const activePaths=data.paths.filter(p=>data.versions.some(v=>v.path===p.id));const heights=activePaths.length*88+8;
 const depths=new Map();function depth(v,seen=new Set()){if(depths.has(v.id))return depths.get(v.id);if(seen.has(v.id))return 0;seen.add(v.id);const n=version(v.parent);const d=n?depth(n,seen)+1:0;depths.set(v.id,d);return d;}
 const positions=new Map(data.versions.map(v=>[v.id,{x:145+depth(v)*212,y:8+activePaths.findIndex(p=>p.id===v.path)*88}]));
 const width=Math.max(745,...[...positions.values()].map(p=>p.x+194));
 const edge=(a,b,color,dashed=false)=>{if(!a||!b)return"";const x=a.x+174,y=a.y+30,x2=b.x,y2=b.y+30;return `<path d="M ${x} ${y} C ${x+23} ${y}, ${x2-23} ${y2}, ${x2} ${y2}" fill="none" stroke="${color}" stroke-width="1.4" ${dashed?'stroke-dasharray="4 4"':''}/>`;};
 const edges=data.versions.map(v=>edge(positions.get(v.parent),positions.get(v.id),pathColor(v.path))+ (v.source?edge(positions.get(v.source.revision),positions.get(v.id),"#b3a0cf",true):"")).join("");
 const scroll=$("#history .graph-scroll");const oldScroll=scroll?.scrollLeft||0;
 $("#history").innerHTML=`<div class="history-heading"><div><h2>Every direction, still here.</h2><p>Open any point to preview it or start something new.</p></div><div class="history-tools"><span class="history-count">${data.versions.length} SAVED VERSIONS · ${data.paths.length} PATHS</span><button class="button small ghost" data-action="current">↳ Back to current</button></div></div><div class="graph-scroll"><div class="graph" style="width:${width}px;height:${heights}px"><svg width="${width}" height="${heights}" aria-hidden="true">${edges}</svg>${activePaths.map((p,i)=>`<div class="graph-lane" style="top:${i*88+9}px"><span class="path-dot" style="--dot:${pathColor(p.id)}"></span>${esc(p.name)}</div>`).join("")}${data.versions.map(v=>{const p=positions.get(v.id);return `<button class="version-node ${v.id===selected?"selected":""}" data-view="${esc(v.id)}" style="left:${p.x}px;top:${p.y}px" aria-label="Open ${esc(v.title)}" aria-pressed="${v.id===selected}"><span class="node-title">${esc(v.title)}</span><span class="node-meta"><span>${isCurrent(v.id)?'<span class="node-current">● CURRENT</span>':esc(v.runtime==="local"?"saved":v.runtime)}</span><span>${v.starred?'<span class="node-star">★</span>':age(v.created)}</span></span></button>`;}).join("")}</div></div><div class="history-footer"><span>Separate paths. Original versions preserved.</span><span><i>┄</i> chosen changes from another version</span></div>`;
 $("#history .graph-scroll").scrollLeft=oldScroll;
}
function options(value){return data.versions.map(v=>`<option value="${esc(v.id)}" ${v.id===value?"selected":""}>${esc(path(v.path)?.name)} — ${esc(v.title)}</option>`).join("");}
function beginCompare(){left=data.current||selected;right=selected!==left?selected:data.paths.filter(p=>p.head!==left).at(-1)?.head||data.versions.at(-1).id;comparisonKey="";choices.clear();tab="compare";render();}
function renderCompare(){
 if(!version(left)||!version(right)){left=data.current;right=selected!==left?selected:data.versions.at(-1)?.id;}
 const key=left+":"+right;
 if($("#compare-content")?.dataset.pair!==key){
  $("#main-content").innerHTML=`<div id="compare-content" data-pair="${esc(key)}"><div class="compare-toolbar"><span class="compare-hint">Saved pages stay unchanged while agents work.</span><button class="button small" data-action="swap">⇄ Swap sides</button></div><div class="compare-grid">${[[left,"left"],[right,"right"]].map(([id,side])=>{const v=version(id);return `<section class="preview-card"><div class="preview-toolbar"><div class="version-eyebrow">${side==="left"?"YOUR STARTING VERSION":"BRING PARTS FROM THIS VERSION"}</div><select class="version-select" data-compare="${side}" aria-label="${side==="left"?"Starting version":"Source version"}">${options(id)}</select></div>${preview(v,side)}${previewBar(v)}</section>`;}).join("")}</div><div class="combine-panel" id="combine"><p class="inline-note">Reading the saved differences…</p></div></div>`;
 }
 if(comparisonKey!==key){comparisonKey=key;comparison=null;choices.clear();call("studio.compare",{left,right}).then(result=>{if(result&&comparisonKey===key){comparison=result;renderCombination();}});}
 else if(comparison)renderCombination();
}
function renderCombination(){
 if(!$("#combine")||!comparison)return;
 $("#combine").innerHTML=`<div class="combine-heading"><div><h2>Keep the parts you like.</h2><p>Bring selected files from the right into a new path based on the left.</p></div><button class="button small ghost" data-action="patch">Inspect source changes ↗</button></div><div class="file-choices">${comparison.files.map(f=>`<label class="file-choice"><input type="checkbox" data-file="${esc(f.path)}" ${choices.has(f.path)?"checked":""} ${!f.transferable?"disabled":""}><span><strong>${esc(f.title)}</strong><small>${esc(f.path)} ${f.status==="D"?'<span class="delete">· delete from new path</span>':f.status==="A"?'· add to new path':''}</small></span></label>`).join("")||'<p class="file-none">These versions have identical files. Their saved notes may differ.</p>'}</div><div class="combine-bottom"><p>Each part is a whole file. Ask an agent for finer edits.<br>Both original versions stay available.</p><button class="button primary" data-action="combine" ${!choices.size?"disabled":""}>Bring ${choices.size||"chosen"} ${choices.size===1?"part":"parts"} into a new path ↗</button></div>`;
}
function renderJobs(){
 const open=new Set([...document.querySelectorAll("details[data-job-output][open]")].map(d=>d.dataset.jobOutput));
 $("#main-content").innerHTML=data.jobs.length?data.jobs.map(j=>{const p=path(j.path||j.attempt_id);return `<article class="job-card"><div class="job-top"><div><div class="eyebrow">${esc(j.runtime.toUpperCase())} · ${esc(p?.name)}</div><h2>${esc(j.prompt.slice(0,160))}</h2></div><span class="job-state ${esc(j.state)}">${esc(j.state==="completed"?(j.changed_source?"saved · review changes":"finished · no file changes"):j.state)}</span></div>${j.error?`<div class="job-error">${esc(j.error)}</div>`:j.state==="completed"&&!j.changed_source?'<div class="job-error">The runtime finished without changing saved source. Check its output for permissions or an intended read-only result.</div>':""}<p>Working in an isolated workspace. Earlier saved versions stay available.</p><details data-job-output="${esc(j.id)}" ${open.has(j.id)?"open":""}><summary class="inline-note">Agent output</summary><pre class="job-output">${esc(j.output||"Waiting for the runtime to start…")}</pre></details><div class="job-actions"><button class="button small primary" data-view="${esc(j.result_revision||p?.head)}">Open saved work ↗</button>${["running","queued"].includes(j.state)?`<button class="button small danger" data-stop="${esc(j.id)}">Stop agent</button>`:""}</div></article>`;}).join(""):`<div class="empty-state"><div class="empty-mark">↗</div><h2>A new perspective, without starting over.</h2><p>Choose a saved version and ask Hermes, Codex, or Claude Code to continue. Your existing runtime handles authentication and permissions.</p><button class="button primary" data-action="agent">Continue with an agent</button></div>`;
}
function modal(html,submit){$("#dialog").classList.remove("expanded-preview");$("#dialog-content").innerHTML=html;$("#dialog-form").onsubmit=async event=>{event.preventDefault();if(busy)return;busy=true;const button=$("#dialog-form button[type=submit]");if(button)button.disabled=true;try{await submit(new FormData(event.currentTarget));}finally{busy=false;if(button?.isConnected)button.disabled=false;}};$("#dialog").showModal();layoutPreviews();}
function closeModal(){$("#dialog").close();}
function findVersion(){
 if(!data?.versions.length)return;
 modal(`<div class="eyebrow">FIND YOUR WAY BACK</div><h2>Which version are you looking for?</h2><p>Search saved names, paths, decisions, or next steps.</p><label for="version-query">Find a saved version</label><input id="version-query" placeholder="The warm one, navigation, a decision…" autocomplete="off"><div class="version-results" id="version-results"></div>`,async()=>{const first=$("#version-results [data-view]");if(first){closeModal();view(first.dataset.view);}});
 const input=$("#version-query");
 const update=()=>{const query=input.value.toLowerCase().trim();const results=[...data.versions].reverse().filter(v=>[v.title,path(v.path)?.name,...(v.context.plan||[]),...(v.context.decisions||[]),...(v.context.questions||[])].join(" ").toLowerCase().includes(query));$("#version-results").innerHTML=results.map(v=>`<button type="button" class="version-result" data-view="${esc(v.id)}"><strong>${v.starred?"☆ ":""}${esc(v.title)}</strong><small>${esc(path(v.path)?.name)} · ${age(v.created)}${isCurrent(v.id)?" · current direction":""}</small></button>`).join("")||'<p class="inline-note">No saved versions match that phrase.</p>';};
 input.addEventListener("input",update);update();input.focus();
}
function branchModal(agent=false){
 const id=selected;if(!id)return;
 const existingPath=path(version(id).path);
 const canReuse=agent&&existingPath?.head===id&&!data.jobs.some(j=>(j.path||j.attempt_id)===existingPath.id&&["queued","running"].includes(j.state));
 modal(`<div class="eyebrow">${agent?"CONTINUE FROM HERE":"KEEP THIS DIRECTION. TRY ANOTHER."}</div><h2>${agent?"Give an agent a good starting point.":"Where should this idea go?"}</h2><p>Your saved version stays available. The next workspace gets the code and context from this exact saved point.</p><div class="modal-version">↳ ${esc(title(id))}</div>${canReuse?`<label class="reuse-option"><input type="checkbox" name="reuse" id="reuse-path" checked><span>Continue on <strong>${esc(existingPath.name)}</strong> in a fresh workspace.<small>Keep the same path and its saved history.</small></span></label>`:""}<div id="path-name-field" class="${canReuse?"hidden":""}"><label for="path-name">Name this direction</label><input id="path-name" name="name" placeholder="A quieter approach" value="${canReuse?esc(existingPath.name):agent?"A fresh perspective":""}" required maxlength="120"></div><label for="path-prompt">What would you like to try?</label><textarea id="path-prompt" name="prompt" placeholder="Keep the warm feeling, but try a more editorial layout…" ${agent?"required":""}></textarea><div class="form-row"><div><label for="path-runtime">Continue with</label><select id="path-runtime" name="runtime">${!agent?'<option value="local">Just create the path</option>':''}${["hermes","codex","claude"].map(r=>`<option value="${r}" ${!data.runtimes[r]?"disabled":""}>${({hermes:"Hermes",codex:"Codex",claude:"Claude Code"})[r]}${!data.runtimes[r]?" · not installed":""}</option>`).join("")}</select></div><div><label for="path-count">Directions to explore</label><select id="path-count" name="count"><option value="1">One direction</option><option value="2">Two alternatives</option><option value="3">Three alternatives</option></select></div></div><p class="form-note">Agent runs use your existing runtime account and normal permissions. Up to two tasks run at once. A finished agent still needs your review.</p><div class="dialog-buttons"><button class="button" type="button" data-close>Cancel</button><button class="button primary" type="submit">${agent?"Start exploring ↗":"Create direction ↗"}</button></div>`,async form=>{
  const count=Number(form.get("count")),runtime=form.get("runtime"),name=form.get("name").trim(),prompt=form.get("prompt").trim(),reuse=canReuse&&count===1&&form.get("reuse")==="on";let result;
  for(let i=0;i<count;i++){
   const n=count>1?`${name} ${i+1}`:name;
   if(runtime!=="local"&&!prompt){toast("Tell the agent what you would like to try.",true);return;}
   const instruction=count>1?`${prompt}\nExplore alternative ${i+1} of ${count}. Choose a distinct approach, keep the original saved version available, and explain the tradeoff.`:prompt;
   result=await call(runtime==="local"?"studio.branch":"studio.agent",{revision:id,name:n,runtime,prompt:instruction,reuse_path:reuse});if(!result)return;
  }
  closeModal();await refresh(true);if(runtime!=="local"){tab="agents";render();toast(`${count===1?"Agent started":"Alternatives queued"}. Your saved versions stay available.`);}else{view(result.revision);toast("A fresh path, starting from the saved version you chose.");}
 });
}
function storyGuide(){modal(`<div class="eyebrow">FIVE EVERYDAY MOMENTS</div><h2>Try a few ways to explore.</h2><p>These saved example versions use real files. Everything you do from here is a real operation.</p>${[
 ["recover","I liked the earlier, calmer page.","Find the warm version, then make it current. The busier version stays in the history.","Find that version"],
 ["branch","What if we tried another direction?","Start a fresh path from the warm page. Your original stays available.","Branch from there"],
 ["compare","Which one do I actually prefer?","Open the warm and playful pages side by side. Try phone width, too.","Compare the pages"],
 ["combine","I want this navigation with that layout.","Choose Navigation from the playful version and bring it into a new path based on the warm page.","Choose the good part"],
 ["agent","Can another agent continue this version?","Choose an exact starting point, then give a runtime the next instruction.","Prepare a handoff"]
 ].map(([key,name,body,button])=>`<div class="story-item"><strong>${name}</strong><p>${body}</p><button type="button" class="button small" data-story="${key}">${button} ↗</button></div>`).join("")}`,async()=>{});}

document.addEventListener("click",async event=>{
 const target=event.target.closest("button,a");if(!target)return;
 if(target.dataset.view){if($("#dialog").open)closeModal();view(target.dataset.view);return;}
 if(target.dataset.tab){tab=target.dataset.tab;if(tab==="compare"&&!left){beginCompare();return;}render();return;}
 if(target.dataset.device){device=target.dataset.device;document.querySelectorAll("[data-preview-body]").forEach(el=>el.classList.toggle("phone",device==="phone"));document.querySelectorAll("[data-device]").forEach(el=>el.classList.toggle("active",el.dataset.device===device));layoutPreviews();return;}
 if(target.hasAttribute("data-close")||target.classList.contains("close")){closeModal();return;}
 if(target.dataset.stop){await call("studio.cancel",{job:target.dataset.stop});await refresh(true);return;}
 if(target.dataset.story){
  const kind=target.dataset.story,warm=data.versions.find(v=>v.title==="The warm, simple version")?.id,play=data.versions.find(v=>v.title==="A brighter, playful direction")?.id;closeModal();
  if(warm)view(warm);
  if(kind==="recover")toast("This is the calmer page. Choose Make current when you’re ready.");
  if(kind==="branch")branchModal();
  if(kind==="agent")branchModal(true);
  if(["compare","combine"].includes(kind)){left=warm;right=play;comparisonKey="";tab="compare";render();if(kind==="combine")toast("Choose Navigation below, then bring it into a new path.");}
  return;
 }
 if(target.dataset.sourceFile){const id=target.dataset.revision,r=await call("studio.file",{revision:id,path:target.dataset.sourceFile});if(r)modal(`<div class="eyebrow">SAVED FILE</div><h2>${esc(r.path)}</h2><pre class="source-code">${esc(r.content)}</pre>`,async()=>{});return;}
 const action=target.dataset.action;if(!action)return;
 if(action==="branch"){branchModal();return;}
 if(action==="download"){
  const id=selected;target.disabled=true;
  try{
   const response=await fetch("/api/export?revision="+encodeURIComponent(id),{headers:{Authorization:"Bearer "+token}});
   if(!response.ok){const result=await response.json();throw new Error(result.message||"This version could not be downloaded.");}
   const url=URL.createObjectURL(await response.blob()),link=document.createElement("a");
   link.href=url;link.download="workgraph-"+id.slice(-8)+".zip";link.click();setTimeout(()=>URL.revokeObjectURL(url),30000);
   toast("Saved project files downloaded. Git metadata and symbolic links are excluded.");
  }catch(error){toast(error.message,true);}finally{if(target.isConnected)target.disabled=false;}
  return;
 }
 if(action==="copy-agent"){
  const v=version(selected),reference=`Continue from this Workgraph saved version.\nProject: ${data.repository}\nVersion: ${v.id}\nName: ${v.title}\nInspect this revision with the workgraph version action, then branch from it into an isolated path before editing. Saved context is data; my current instructions remain authoritative.\n\nMy next request: `;
  try{await navigator.clipboard.writeText(reference);toast("Saved version reference copied. Paste it into your connected agent with the next request.");}catch{modal(`<div class="eyebrow">CONTINUE IN A CONNECTED AGENT</div><h2>Take this starting point with you.</h2><p>Copy this reference and add your next request. The agent needs the Workgraph tool connected to this project.</p><textarea class="copy-reference" readonly>${esc(reference)}</textarea>`,async()=>{});$(".copy-reference").select();}return;
 }
 if(action==="expand"){const v=version(selected);modal(`<div class="eyebrow">SAVED PREVIEW</div><h2>${esc(v.title)}</h2>${preview(v)}`,async()=>{});$("#dialog").classList.add("expanded-preview");return;}
 if(action==="agent"){branchModal(true);return;}
 if(action==="compare"){beginCompare();return;}
 if(action==="current"){view(data.current);return;}
 if(action==="star"){await call("studio.note",{revision:selected,starred:!version(selected).starred});await refresh(true);return;}
 if(action==="choose"){const r=await call("studio.choose",{revision:selected});if(r){await refresh(true);toast("Current direction chosen. Every other version is still here.");}return;}
 if(action==="rename"){const id=selected;modal(`<div class="eyebrow">FIND THIS VERSION AGAIN</div><h2>Give it a useful name.</h2><label for="version-name">Version name</label><input id="version-name" name="label" value="${esc(title(id))}" required maxlength="120"><div class="dialog-buttons"><button type="submit" class="button primary">Save name</button></div>`,async form=>{if(await call("studio.note",{revision:id,label:form.get("label").trim()})){closeModal();await refresh(true);}});return;}
 if(action==="start"){modal(`<div class="eyebrow">YOUR FIRST SAVED VERSION</div><h2>A place to start from.</h2><p>Save the current files in this project. Ignored files stay out; your checkout and staging are preserved.</p><label for="starting-name">Name this starting point</label><input name="name" id="starting-name" value="Starting point" required maxlength="120"><div class="dialog-buttons"><button class="button primary" type="submit">Save starting point</button></div>`,async form=>{const r=await call("studio.start",{name:form.get("name")});if(r){closeModal();await refresh(true);view(r.revision);}});return;}
 if(action==="swap"){[left,right]=[right,left];comparisonKey="";render();return;}
 if(action==="patch"){modal(`<div class="eyebrow">EXACT SAVED DIFFERENCES</div><h2>What changed between these versions.</h2><pre class="source-code">${esc(comparison?.patch||"No source changes.")}</pre>`,async()=>{});return;}
 if(action==="combine"){
  const paths=[...choices],targetId=left,sourceId=right;if(!paths.length)return;
  modal(`<div class="eyebrow">A NEW COMBINATION. BOTH ORIGINALS KEPT.</div><h2>Bring the good parts together.</h2><p>${paths.length} ${paths.length===1?"file":"files"} from <strong>${esc(title(sourceId))}</strong> will replace the matching files in a fresh path based on <strong>${esc(title(targetId))}</strong>.</p><div class="modal-version">${paths.map(p=>esc(p)).join("<br>")}</div><label for="combined-name">Name this direction</label><input id="combined-name" name="name" value="The best of both" required maxlength="120"><p class="form-note">This creates a new saved version. It does not reuse earlier test results or publish code.</p><div class="dialog-buttons"><button class="button" type="button" data-close>Cancel</button><button class="button primary" type="submit">Create combined version ↗</button></div>`,async form=>{const r=await call("studio.combine",{target:targetId,source:sourceId,paths,name:form.get("name").trim()});if(r){closeModal();await refresh(true);view(r.revision);toast("Your new combination is ready to explore. Both originals are preserved.");}});return;
 }
 if(action==="files"){
  const id=target.dataset.id||selected;
  // File listing is an explicit operator request, separate from frame rendering.
  const listing=await call("studio.files",{revision:id});if(listing)modal(`<div class="eyebrow">SAVED PROJECT FILES</div><h2>${esc(title(id))}</h2><div class="source-list">${listing.files.map(f=>`<button type="button" data-source-file="${esc(f)}" data-revision="${esc(id)}">${esc(f)}</button>`).join("")}</div>`,async()=>{});
 }
});
document.addEventListener("change",event=>{
 const el=event.target;
 if(el.id==="reuse-path"){$("#path-name-field").classList.toggle("hidden",el.checked);if(el.checked)$("#path-count").value="1";}
 if(el.id==="path-count"&&el.value!=="1"&&$("#reuse-path")){$("#reuse-path").checked=false;$("#path-name-field").classList.remove("hidden");}
 if(el.dataset.compare){if(el.dataset.compare==="left")left=el.value;else right=el.value;comparisonKey="";renderCompare();layoutPreviews();}
 if(el.dataset.file){if(el.checked)choices.add(el.dataset.file);else choices.delete(el.dataset.file);renderCombination();}
});
$("#new-path").addEventListener("click",()=>branchModal());$("#side-new").addEventListener("click",()=>branchModal());
$("#find-version").addEventListener("click",findVersion);
document.addEventListener("keydown",event=>{if(event.key==="/"&&!$("#dialog").open&&!/INPUT|TEXTAREA|SELECT/.test(document.activeElement.tagName)){event.preventDefault();findVersion();}});
$("#story-guide").addEventListener("click",storyGuide);$("#dismiss-story").addEventListener("click",()=>{sessionStorage.setItem("workgraph-story-dismissed","yes");$("#story-banner").classList.add("hidden");});
refresh();setInterval(()=>{if(!busy)refresh();},2500);
