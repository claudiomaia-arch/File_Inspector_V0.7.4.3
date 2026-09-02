let currentResults = [];

document.querySelectorAll(".nav-item").forEach(btn => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".nav-item").forEach(x => x.classList.remove("active"));
    document.querySelectorAll(".view").forEach(x => x.classList.remove("active-view"));
    btn.classList.add("active");
    document.getElementById(btn.dataset.view).classList.add("active-view");
  });
});

function goMonitor(){
  document.querySelectorAll(".nav-item").forEach(x => x.classList.toggle("active", x.dataset.view === "monitor"));
  document.querySelectorAll(".view").forEach(x => x.classList.toggle("active-view", x.id === "monitor"));
}

async function scanCorporate(){
  goMonitor();
  const body = document.getElementById("result-body");
  body.innerHTML = '<tr><td colspan="10" class="empty">Analisando estrutura e datasheets...</td></tr>';
  const res = await fetch("/api/scan");
  const data = await res.json();
  if(!res.ok){
    body.innerHTML = `<tr><td colspan="10" class="empty">${data.error || "Erro na análise"}</td></tr>`;
    return;
  }
  currentResults = data.results || [];
  document.getElementById("scan-subtitle").textContent = `${data.environment_name} • ${data.folder_path}`;
  renderResults(currentResults);
  saveLocalProcessSnapshot(
    "usinagem", data.environment_name, data.folder_path, currentResults
  );
  persistSnapshotFromBrowser(
    "usinagem", data.environment_name, data.folder_path, currentResults
  );
  updateStats(currentResults);
  updateMachiningOverviewStats(currentResults);
  if(data.summary){
    setOverviewSummary("mach", data.summary);
  }
  refreshOverviewSummaries();
}

function yes(v){ return v ? "✓" : "—"; }

function firstAction(r){
  if(!r.actions || !r.actions.length) return "Nenhuma";
  if(r.actions.length===1) return r.actions[0];
  return `${r.actions[0]} (+${r.actions.length-1})`;
}

function renderResults(rows){
  const body = document.getElementById("result-body");
  if(!rows.length){
    body.innerHTML = '<tr><td colspan="10" class="empty">Nenhuma pasta encontrada para o filtro atual.</td></tr>';
    return;
  }
  body.innerHTML = rows.map((r,i)=>{
    const realIndex=currentResults.indexOf(r);
    return `
    <tr class="row-click" onclick="showDetails(${realIndex})">
      <td><strong>${escapeHtml(r.folder_name)}</strong><br><small>${escapeHtml((r.codes||[]).join(" • "))}</small></td>
      <td class="center">${yes(r.folder_pattern_ok)}</td>
      <td class="center">${yes(r.pdf)}</td>
      <td class="center">${yes(r.drawing)}</td>
      <td class="center">${yes(r.step)}</td>
      <td class="center">${yes(r.part)}</td>
      <td class="center">${yes(r.machining_dir)}</td>
      <td class="center">${yes(r.nc)}</td>
      <td><span class="status ${r.status}">${statusText(r.status)}</span></td>
      <td style="min-width:260px">${escapeHtml(firstAction(r))}</td>
    </tr>`}).join("");
}

function updateStats(rows){
  document.getElementById("stat-total").textContent = rows.length;
  document.getElementById("stat-ok").textContent = rows.filter(r=>r.status==="conforme").length;
  document.getElementById("stat-warning").textContent = rows.filter(r=>r.status==="atencao" || r.status==="verificado").length;
  document.getElementById("stat-bad").textContent = rows.filter(r=>r.status==="incompleto").length;
}

function statusText(s){
  return ({conforme:"CONFORME",atencao:"ATENÇÃO",incompleto:"INCOMPLETO",verificado:"VERIFICADO"})[s] || s;
}


function renameSuggestionButtons(r, processKey){
  let suggestions=r.rename_suggestions||[];

  // Defesa adicional no frontend. O backend/scanner já filtra,
  // mas máscaras e destinos incompletos nunca devem virar botão executável.
  suggestions=suggestions.filter(s=>{
    const expected=String(s.expected_name||"").trim().toUpperCase();

    if(s.kind==="folder"){
      if(processKey==="corte_laser") return /^CRT\d{6}$/.test(expected);
      if(processKey==="usinagem") return /^(USI|PRE)\d{6}$/.test(expected);
      return false;
    }

    if(s.kind==="file" && s.label==="Nome do datasheet"){
      return /^CNC-RT-\d{3}-DTS\.PDF$/.test(expected);
    }

    return false;
  });

  if(!suggestions.length) return "";

  // Mantém somente as sugestões seguras também no objeto ativo.
  r.rename_suggestions=suggestions;

  return `<div class="assisted-fixes">
    <h4>Correções sugeridas pelo sistema</h4>
    ${suggestions.map((s,idx)=>`<div class="assisted-fix">
      <div><strong>${escapeHtml(s.label)}</strong>
      <span>${escapeHtml(s.current_name)} → ${escapeHtml(s.expected_name)}</span></div>
      <button class="btn primary" onclick="event.stopPropagation();approveRename('${processKey}',${idx})">Aprovar e corrigir</button>
    </div>`).join("")}
    <small>O sistema só oferece correções quando o destino é conhecido com segurança. Conflitos são bloqueados e a alteração é registrada na auditoria.</small>
  </div>`;
}

async function approveRename(processKey,idx){
  const results=processKey==="corte_laser"?(window.laserResults||[]):currentResults;
  const active=processKey==="corte_laser"?window.activeLaserDetail:window.activeMachiningDetail;
  if(active==null||!results[active]) return;
  const s=(results[active].rename_suggestions||[])[idx];
  if(!s) return;
  if(!confirm(`Aprovar correção?\n\n${s.current_name}\n→ ${s.expected_name}\n\nA alteração será registrada na auditoria.`)) return;
  const form=new FormData();
  form.append("source_path",s.source_path); form.append("expected_name",s.expected_name); form.append("kind",s.kind);
  const res=await fetch("/api/approved-rename",{method:"POST",body:form});
  const data=await res.json();
  if(!res.ok){ alert(data.error||"Não foi possível executar a correção."); return; }
  showToast(data.message||"Correção executada.","success");
  if(processKey==="corte_laser") await scanLaser(); else await scanCorporate();
}

function showDetails(i){
  window.activeMachiningDetail=i;
  const r=currentResults[i];
  const panel=document.getElementById("details-panel");
  panel.classList.remove("hidden");
  const issues=(r.problems||[]).map((x,idx)=>`
    <div class="issue"><strong>${escapeHtml(x)}</strong><br>
    <span style="color:#596579">→ ${escapeHtml((r.actions||[])[idx] || "")}</span></div>`).join("") || "<p>Nenhuma inconsistência detectada.</p>";
  panel.innerHTML=`
    <button class="icon-btn" style="float:right" onclick="this.parentElement.classList.add('hidden')">×</button>
    <h3>${escapeHtml(r.folder_name)}</h3>
    <p><strong>Padrão esperado da pasta:</strong><br>${escapeHtml(r.folder_expected)}</p>
    <p><strong>Códigos da pasta:</strong> ${escapeHtml((r.codes||[]).join(", ") || "-")}</p>
    <hr style="border:0;border-top:1px solid #e6eaf0">
    <p><strong>Datasheet:</strong> ${escapeHtml(r.datasheet_file || "-")}<br>
    <strong>USIs no datasheet:</strong> ${escapeHtml((r.datasheet_codes||[]).join(", ") || "-")}<br>
    <strong>Código CNC:</strong> ${escapeHtml(r.cnc_code || "-")}<br>
    <strong>Nome esperado:</strong> ${escapeHtml(r.expected_datasheet || "-")}<br>
    <strong>Processo Usinagem Interna:</strong> ${r.process_ok ? "✓" : "—"}</p>
    <p><strong>STEP mais recente:</strong> ${escapeHtml(r.step_date)}<br>
    <strong>NC mais recente:</strong> ${escapeHtml(r.nc_date)}</p>
    ${r.verified ? `<div class="verified-box"><strong>✓ Validado por ${escapeHtml(r.verified_by || "usuário")}</strong><br>${escapeHtml(r.verified_at || "")}<br><small>${escapeHtml(r.verified_note || "")}</small></div>` : ""}
    <h4>O que precisa ser adequado (${r.adjustment_count || 0})</h4>${issues}
    ${renameSuggestionButtons(r,"usinagem")}
    <div class="details-actions"><button class="btn secondary" onclick="openFolder(i)">📂 Abrir pasta</button>
      <button class="btn secondary" onclick="openFolder(${i})">Abrir pasta</button>
      ${r.problems && r.problems.length ? `<button class="btn primary" onclick="verifyIssue(${i})">Validar / OK</button>` : ""}
    </div>`;
}

async function verifyIssue(i){
  const r=currentResults[i];
  const note=prompt("Justificativa da validação:", "Verificado manualmente. Sem impacto para a usinagem.");
  if(note===null) return;
  const form=new FormData();
  form.append("folder_path",r.folder_path);
  form.append("signature",r.signature);
  form.append("note",note);
  const res=await fetch("/api/verify",{method:"POST",body:form});
  if(res.ok){
    const data=await res.json();
    r.status="verificado";r.verified=true;
    r.verified_by=data.validator_name;r.verified_at=data.validated_at;r.verified_note=note;
    renderResults(currentResults);updateStats(currentResults);showDetails(i);
  } else alert("Não foi possível registrar a validação.");
}


async function openFolderPath(path){
  if(!path){
    alert("Caminho da pasta não disponível.");
    return;
  }
  const form=new FormData();
  form.append("path",path);
  const res=await fetch("/api/open-folder",{method:"POST",body:form});
  const data=await res.json();
  if(!res.ok) alert(data.error || "Não foi possível abrir a pasta.");
}

async function openFolder(i){
  const r=currentResults[i];
  if(!r) return;
  await openFolderPath(r.folder_path);
}

function filterRows(){
  const q=(document.getElementById("search")?.value || "").toLowerCase().trim();
  const s=(document.getElementById("status-filter")?.value || "");
  const filtered=currentResults.filter(r =>
    (!s || r.status===s) &&
    (!q || r.folder_name.toLowerCase().includes(q) ||
    (r.codes||[]).join(" ").toLowerCase().includes(q) ||
    (r.cnc_code||"").toLowerCase().includes(q) ||
    (r.actions||[]).join(" ").toLowerCase().includes(q))
  );
  renderResults(filtered);
}

function escapeHtml(v){
  return String(v ?? "").replace(/[&<>"']/g,m=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#039;"}[m]));
}

async function scanLaser(){
  const body=document.getElementById("laser-body");
  body.innerHTML='<tr><td colspan="6" class="empty">Analisando Corte a Laser...</td></tr>';
  const res=await fetch("/api/scan-laser");
  const data=await res.json();
  if(!res.ok){
    body.innerHTML=`<tr><td colspan="6" class="empty">${escapeHtml(data.error||"Erro na análise")}</td></tr>`;
    return;
  }
  window.laserResults=data.results||[];
  updateLaserOverviewStats(window.laserResults);
  if(data.summary){
    setOverviewSummary("laser", data.summary);
  }
  document.getElementById("laser-subtitle").textContent=`${data.environment_name} • ${data.folder_path}`;
  renderLaser(window.laserResults);
  saveLocalProcessSnapshot(
    "corte_laser", data.environment_name, data.folder_path, window.laserResults
  );
  persistSnapshotFromBrowser(
    "corte_laser", data.environment_name, data.folder_path, window.laserResults
  );
  refreshOverviewSummaries();
}

function renderLaser(rows){
  const body=document.getElementById("laser-body");
  if(!rows.length){
    body.innerHTML='<tr><td colspan="6" class="empty">Nenhuma subpasta encontrada.</td></tr>';
    return;
  }
  body.innerHTML=rows.map((r,i)=>`
    <tr class="row-click" onclick="showLaserDetails(${i})">
      <td><strong>${escapeHtml(r.folder_name)}</strong><br><small>${escapeHtml((r.codes||[]).join(" • "))}</small></td>
      <td class="center">${r.folder_pattern_ok?"✓":"—"}</td>
      <td class="center">${r.dxf?"✓":"—"}</td>
      <td class="center">${r.pdf?"✓":"—"}</td>
      <td><span class="status ${r.status}">${statusText(r.status)}</span></td>
      <td>${escapeHtml(r.actions&&r.actions.length?(r.actions[0]+(r.actions.length>1?` (+${r.actions.length-1})`:"")):"Nenhuma")}</td>
    </tr>`).join("");
}

function showLaserDetails(i){
  window.activeLaserDetail=i;
  const r=(window.laserResults||[])[i];

  // V0.7.3.1 — regra conservadora:
  // Só há correção executável quando existe um CRT concreto e inequívoco.
  // Máscaras (CRT######) e códigos de outras famílias (PRE/USI/etc.) nunca
  // são convertidos automaticamente para CRT.
  if(r){
    r.rename_suggestions=[];
    const detectedCodes = Array.isArray(r.codes) ? r.codes : [];
    const crtCodes = detectedCodes
      .map(c => String(c || "").trim().toUpperCase())
      .filter(c => /^CRT\d{6}$/.test(c));

    if(!r.folder_pattern_ok && crtCodes.length === 1){
      const concreteCrt = crtCodes[0];
      r.rename_suggestions=[{
        kind:"folder",
        label:"Nome da pasta",
        current_name:r.folder_name,
        expected_name:concreteCrt,
        source_path:r.folder_path
      }];
    }
  }
  const panel=document.getElementById("laser-details-panel");
  panel.classList.remove("hidden");
  const issues=(r.problems||[]).map((x,idx)=>`
    <div class="issue"><strong>${escapeHtml(x)}</strong><br>
    <span style="color:#596579">→ ${escapeHtml((r.actions||[])[idx]||"")}</span></div>
  `).join("") || "<p>Nenhuma inconsistência detectada.</p>";
  panel.innerHTML=`
    <button class="icon-btn" style="float:right" onclick="this.parentElement.classList.add('hidden')">×</button>
    <h3>${escapeHtml(r.folder_name)}</h3>
    <p><strong>Padrão esperado:</strong> ${escapeHtml(r.folder_expected)}</p>
    <p><strong>DXF:</strong> ${r.dxf?"✓":"—"}<br><strong>Datasheet PDF:</strong> ${r.pdf?"✓":"—"}</p>
    <h4>O que precisa ser adequado (${r.adjustment_count||0})</h4>${issues}
    ${renameSuggestionButtons(r,"corte_laser")}<div class="details-actions"><button class="btn secondary" onclick="openFolderPath(${JSON.stringify(r.folder_path||"")})">📂 Abrir pasta</button></div>`;
}

(function(){
  const titles = {
    overview: "File Inspector",
    monitor: "Usinagem Interna",
    laser: "Corte a Laser",
    history: "Histórico",
    evidence: "Evidências",
    people: "Envolvidos",
    audit: "Auditoria"
  };

  function updatePageTitle(view){
    const el=document.getElementById("page-title");
    if(el) el.textContent=titles[view] || "File Inspector";
  }

  document.querySelectorAll(".nav-item[data-view]").forEach(btn=>{
    btn.addEventListener("click", ()=>updatePageTitle(btn.dataset.view));
  });

  const params=new URLSearchParams(window.location.search);
  if(params.get("view")==="laser"){
    const laserBtn=document.querySelector('.nav-item[data-view="laser"]');
    if(laserBtn) laserBtn.click();
    updatePageTitle("laser");
  }

  if(params.get("saved")==="1"){
    setTimeout(()=>alert("Pasta do Corte a Laser configurada com sucesso."),50);
  }
  if(params.get("error")==="pasta_invalida"){
    setTimeout(()=>alert("O caminho informado não foi encontrado pelo computador que executa o File Inspector. Verifique o caminho e tente novamente."),50);
  }
})();

function activateView(view){
  document.querySelectorAll(".nav-item").forEach(x => x.classList.toggle("active", x.dataset.view === view));
  document.querySelectorAll(".view").forEach(x => x.classList.toggle("active-view", x.id === view));
  const titles = {
    overview:"File Inspector",
    monitor:"Usinagem Interna",
    laser:"Corte a Laser",
    structure:"Estrutura do Produto",
    history:"Histórico",
    evidence:"Evidências",
    people:"Envolvidos",
    audit:"Auditoria"
  };
  const title=document.getElementById("page-title");
  if(title) title.textContent=titles[view] || "File Inspector";
  if(view==="overview"){
    refreshOverviewSummaries();
  }
}

async function scanLaserFromOverview(){
  activateView("laser");
  await scanLaser();
}

document.addEventListener("DOMContentLoaded", ()=>{
  document.querySelectorAll(".nav-item[data-view]").forEach(btn=>{
    btn.addEventListener("click", ()=>activateView(btn.dataset.view));
  });

  const params=new URLSearchParams(window.location.search);
  const view=params.get("view");
  if(view) activateView(view);
  else activateView("overview");

  if(params.get("saved")==="1"){
    setTimeout(()=>alert("Pasta do Corte a Laser configurada com sucesso."),50);
  }
  if(params.get("error")==="pasta_invalida"){
    setTimeout(()=>alert("O caminho informado não foi encontrado no computador servidor. Copie o caminho completo pelo Explorador do Windows e tente novamente."),50);
  }
});





document.addEventListener("DOMContentLoaded", ()=>{
  const params=new URLSearchParams(window.location.search);
  if(params.get("saved")==="1"){
    const p=params.get("process");
    const name=p==="corte_laser" ? "Corte a Laser" : "Usinagem Interna";
    setTimeout(()=>alert(`Pasta de ${name} configurada com sucesso.`),50);
  }
});

function toggleProcessConfig(processKey, show=true){
  ["usinagem","corte_laser"].forEach(function(key){
    const panel=document.getElementById("config-"+key);
    if(!panel) return;
    if(key===processKey && show){
      panel.classList.remove("hidden");
    }else{
      panel.classList.add("hidden");
    }
  });
}

function setText(id, value){
  const el=document.getElementById(id);
  if(el) el.textContent=value;
}

function updateMachiningOverviewStats(rows){
  const total=rows.length;
  const ok=rows.filter(r=>r.status==="conforme").length;
  const bad=rows.filter(r=>r.status==="incompleto").length;
  const warning=rows.filter(r=>r.status!=="conforme" && r.status!=="incompleto").length;
  setText("mach-total",total);
  setText("mach-ok",ok);
  setText("mach-warning",warning);
  setText("mach-bad",bad);
}

function updateLaserOverviewStats(rows){
  const total=rows.length;
  const ok=rows.filter(r=>r.status==="conforme").length;
  const bad=rows.filter(r=>r.status==="incompleto").length;
  const warning=rows.filter(r=>r.status!=="conforme" && r.status!=="incompleto").length;
  setText("laser-total",total);
  setText("laser-ok",ok);
  setText("laser-warning",warning);
  setText("laser-bad",bad);
}

function applyLaserFilters(){
  const status=document.getElementById("laser-status-filter")?.value || "all";
  const term=(document.getElementById("laser-search")?.value || "").trim().toLowerCase();
  const source=Array.isArray(window.laserResults) ? window.laserResults : [];

  const rows=source.filter(r=>{
    const statusOk=status==="all" || r.status===status;
    const hay=[
      r.folder_name || "",
      ...(r.codes || []),
      ...(r.problems || []),
      ...(r.actions || [])
    ].join(" ").toLowerCase();
    const textOk=!term || hay.includes(term);
    return statusOk && textOk;
  });

  renderLaser(rows);
}

function setOverviewSummary(prefix, summary){
  const map={total:"total",ok:"ok",warning:"warning",bad:"bad"};
  Object.keys(map).forEach(function(key){
    const el=document.getElementById(prefix+"-"+map[key]);
    if(el) el.textContent=summary[key] ?? 0;
  });
}

async function refreshOverviewSummaries(){
  try{
    const res=await fetch("/api/process-summaries", {cache:"no-store"});
    if(!res.ok) return;
    const data=await res.json();
    if(data.usinagem) setOverviewSummary("mach", data.usinagem);
    if(data.corte_laser) setOverviewSummary("laser", data.corte_laser);

    const machLast=document.getElementById("mach-last-analysis");
    const laserLast=document.getElementById("laser-last-analysis");
    if(machLast && data.usinagem?.analyzed_at){
      machLast.textContent="Última análise: "+data.usinagem.analyzed_at;
      machLast.classList.remove("hidden");
    }
    if(laserLast && data.corte_laser?.analyzed_at){
      laserLast.textContent="Última análise: "+data.corte_laser.analyzed_at;
      laserLast.classList.remove("hidden");
    }
  }catch(e){
    console.warn("Não foi possível atualizar os indicadores da visão geral.", e);
  }
}

document.addEventListener("DOMContentLoaded", function(){
  refreshOverviewSummaries();
});

function filterStructureRows(){
  const filter=document.getElementById("structure-filter")?.value || "all";
  const term=(document.getElementById("structure-search")?.value || "").trim().toLowerCase();
  document.querySelectorAll(".structure-row").forEach(function(row){
    const text=(row.dataset.search || "").toLowerCase();
    const prefix=row.dataset.prefix || "";
    const origin=row.dataset.origin || "";
    const monitorStatus=row.dataset.monitorStatus || "";
    const filterOk=filter==="all" || prefix===filter || origin===filter || monitorStatus===filter;
    const textOk=!term || text.includes(term);
    row.style.display=(filterOk && textOk) ? "" : "none";
  });
}

async function refreshStructureCrosscheck(){
  const btn=document.querySelector('[onclick="refreshStructureCrosscheck()"]');
  const originalText=btn ? btn.textContent : "";
  if(btn){
    btn.disabled=true;
    btn.textContent="Atualizando...";
  }
  showToast("Atualizando e registrando cruzamento...", "info");

  try{
    const res=await fetch("/api/structure-crosscheck/save", {
      method:"POST",
      cache:"no-store"
    });
    if(!res.ok){
      showToast("Não foi possível registrar o cruzamento.", "error");
      return;
    }
    const data=await res.json();
    showToast(`Cruzamento registrado às ${data.updated_at}.`, "success");
    setTimeout(()=>window.location.reload(), 700);
  }catch(e){
    console.warn("Falha ao registrar cruzamento.", e);
    showToast("Erro ao atualizar o cruzamento.", "error");
  }finally{
    if(btn){
      btn.disabled=false;
      btn.textContent=originalText || "Atualizar e registrar cruzamento";
    }
  }
}
function renderStructureCrosscheck(rows){
  const body=document.getElementById("structure-body");
  if(!body) return;
  if(!rows.length){ body.innerHTML='<tr><td colspan="8" class="empty">Nenhuma estrutura analisada.</td></tr>'; return; }
  body.innerHTML=rows.map(function(item){
    const found=item.monitor_status==="fora_escopo" ? '<span class="status-pill neutral">—</span>' : (item.found ? '<span class="status-pill ok">✓ Encontrado</span>' : '<span class="status-pill bad">✕ Não encontrado</span>');
    let status='<span class="status-pill neutral">FORA DO ESCOPO</span>';
    if(item.monitor_status==="conforme") status='<span class="status conforme">CONFORME</span>';
    else if(item.monitor_status==="incompleto" || item.monitor_status==="verificado") status='<span class="status incompleto">'+escapeHtml(item.monitor_status.toUpperCase())+'</span>';
    else if(item.monitor_status==="nao_encontrado") status='<span class="status incompleto">NÃO ENCONTRADO</span>';
    let pending="—";
    if((item.monitor_actions||[]).length) pending=escapeHtml(item.monitor_actions[0])+((item.monitor_actions||[]).length>1 ? ` (+${item.monitor_actions.length-1})` : "");
    else if(item.monitor_status==="nao_encontrado") pending="Código não localizado no último monitoramento do processo.";
    const search=[item.code,item.family,item.internal_external,item.monitor_process,item.source_name,(item.monitor_actions||[]).join(" ")].join(" ");
    return `<tr class="structure-row" data-search="${escapeHtml(search)}" data-prefix="${escapeHtml(item.prefix||"")}" data-origin="${escapeHtml(item.internal_external||"")}" data-monitor-status="${escapeHtml(item.monitor_status||"")}">
      <td><strong>${escapeHtml(item.code)}</strong></td><td>${escapeHtml(item.family||"")}</td><td>${escapeHtml(item.internal_external||"")}</td><td>${escapeHtml(item.monitor_process||"")}</td><td>${found}</td><td>${status}</td><td>${pending}</td><td>${escapeHtml(item.source_name||"")}</td></tr>`;
  }).join("");
  filterStructureRows();
}

document.addEventListener("DOMContentLoaded", function(){
  const params=new URLSearchParams(window.location.search);
  if(params.get("replaced")==="1"){
    setTimeout(()=>alert("Estrutura reanalisada. O registro anterior foi atualizado, sem duplicação."),50);
  }
  if(params.get("deleted")==="1"){
    setTimeout(()=>alert("Estrutura excluída do módulo Estrutura do Produto."),50);
  }
  if(params.get("cleared")==="1"){
    setTimeout(()=>alert("Registros da Estrutura do Produto foram limpos."),50);
  }
});

async function restoreLastProcessScans(){
  try{
    const [machRes, laserRes] = await Promise.all([
      fetch("/api/last-scan/usinagem", {cache:"no-store"}),
      fetch("/api/last-scan/corte_laser", {cache:"no-store"})
    ]);

    if(machRes.ok){
      const mach=await machRes.json();
      if(mach.has_snapshot && (mach.results||[]).length){
        applyProcessSnapshot("usinagem", mach);
      }
    }

    if(laserRes.ok){
      const laser=await laserRes.json();
      if(laser.has_snapshot && (laser.results||[]).length){
        // Só aplica se houver resultado persistido real.
        // Nunca limpa a tabela já renderizada pelo backend.
        applyProcessSnapshot("corte_laser", laser);
      }
    }
  }catch(e){
    console.warn("Falha ao consultar snapshots; mantendo os dados renderizados pelo servidor.", e);
  }
}

document.addEventListener("DOMContentLoaded", function(){
  restoreLastProcessScans();
});

async function persistSnapshotFromBrowser(processKey, environmentName, folderPath, results){
  try{
    await fetch(`/api/save-snapshot/${processKey}`, {
      method:"POST",
      headers:{"Content-Type":"application/json"},
      body:JSON.stringify({
        environment_name:environmentName || "",
        folder_path:folderPath || "",
        results:results || []
      })
    });
  }catch(e){
    console.warn("Falha ao persistir snapshot.", e);
  }
}

function showToast(message, type="info"){
  let area=document.getElementById("toast-area");
  if(!area){
    area=document.createElement("div");
    area.id="toast-area";
    area.className="toast-area";
    document.body.appendChild(area);
  }
  const toast=document.createElement("div");
  toast.className=`toast toast-${type}`;
  toast.textContent=message;
  area.appendChild(toast);
  requestAnimationFrame(()=>toast.classList.add("show"));
  setTimeout(()=>{
    toast.classList.remove("show");
    setTimeout(()=>toast.remove(),250);
  },2600);
}

function saveLocalProcessSnapshot(processKey, environmentName, folderPath, results, analyzedAt=null){
  try{
    localStorage.setItem(
      "file_inspector_snapshot_"+processKey,
      JSON.stringify({
        process_key:processKey,
        environment_name:environmentName || "",
        folder_path:folderPath || "",
        results:results || [],
        analyzed_at:analyzedAt || new Date().toLocaleString("pt-BR")
      })
    );
  }catch(e){
    console.warn("Não foi possível salvar snapshot local.", e);
  }
}

function loadLocalProcessSnapshot(processKey){
  try{
    const raw=localStorage.getItem("file_inspector_snapshot_"+processKey);
    return raw ? JSON.parse(raw) : null;
  }catch(e){
    return null;
  }
}

function applyProcessSnapshot(processKey, snapshot){
  if(!snapshot || !Array.isArray(snapshot.results) || !snapshot.results.length) return false;

  if(processKey==="usinagem"){
    currentResults=snapshot.results || [];
    const subtitle=document.getElementById("scan-subtitle");
    if(subtitle){
      subtitle.textContent =
        `${snapshot.environment_name || "Usinagem Interna"} • ${snapshot.folder_path || ""}` +
        (snapshot.analyzed_at ? ` • Última análise: ${snapshot.analyzed_at}` : "");
    }
    renderResults(currentResults);
    updateStats(currentResults);
    updateMachiningOverviewStats(currentResults);
    return true;
  }

  if(processKey==="corte_laser"){
    window.laserResults=snapshot.results || [];
    const subtitle=document.getElementById("laser-subtitle");
    if(subtitle){
      subtitle.textContent =
        `${snapshot.environment_name || "Corte a Laser"} • ${snapshot.folder_path || ""}` +
        (snapshot.analyzed_at ? ` • Última análise: ${snapshot.analyzed_at}` : "");
    }
    renderLaser(window.laserResults);
    updateLaserOverviewStats(window.laserResults);
    return true;
  }
  return false;
}

function restoreBootstrapSnapshots(){
  let data=null;
  try{
    const el=document.getElementById("process-snapshot-bootstrap");
    if(el) data=JSON.parse(el.textContent || "{}");
  }catch(e){
    console.warn("Bootstrap de snapshots inválido.", e);
  }

  const mach=(data && data.usinagem) || loadLocalProcessSnapshot("usinagem");
  const laser=(data && data.corte_laser) || loadLocalProcessSnapshot("corte_laser");

  if(mach) applyProcessSnapshot("usinagem", mach);
  if(laser) applyProcessSnapshot("corte_laser", laser);
}

document.addEventListener("DOMContentLoaded", function(){
  restoreBootstrapSnapshots();
});

let activeCrosscheckItem=null;
function crossStatusText(status){return ({conforme:"CONFORME",incompleto:"INCOMPLETO",nao_encontrado:"NÃO ENCONTRADO",fora_escopo:"FORA DO ESCOPO",atencao:"ATENÇÃO",verificado:"VERIFICADO"})[status]||status||"—";}
function showCrosscheckDetails(item){
  activeCrosscheckItem=item; const panel=document.getElementById("crosscheck-details"); if(!panel)return;
  document.getElementById("cross-detail-title").textContent=`${item.code} — ${item.monitor_process||"Estrutura"}`;
  document.getElementById("cross-detail-meta").innerHTML=`<div><strong>Status</strong><span>${escapeHtml(crossStatusText(item.monitor_status))}</span></div><div><strong>Encontrado</strong><span>${item.found?"Sim":"Não"}</span></div><div><strong>Pasta</strong><span>${escapeHtml(item.monitor_folder||"—")}</span></div><div><strong>Última análise</strong><span>${escapeHtml(item.monitor_analyzed_at||"—")}</span></div><div class="wide"><strong>Caminho</strong><span>${escapeHtml(item.monitor_folder_path||"—")}</span></div>`;
  const entries=Object.entries(item.monitor_requirements||{});
  document.getElementById("cross-detail-requirements").innerHTML=entries.length?entries.map(([n,ok])=>`<div class="requirement-item ${ok?"ok":"bad"}"><span>${ok?"✓":"✕"}</span><strong>${escapeHtml(n)}</strong></div>`).join(""):'<div class="empty-inline">Sem requisitos avaliáveis nesta versão.</div>';
  const actions=item.monitor_actions||[], problems=item.monitor_problems||[], pend=document.getElementById("cross-detail-pendencies");
  if(item.monitor_status==="nao_encontrado") pend.innerHTML='<div class="detail-issue"><strong>Código não localizado no monitoramento.</strong><span>Verifique se a pasta existe, se o código está correto ou se a análise do processo precisa ser atualizada.</span></div>';
  else if(actions.length) pend.innerHTML=actions.map((a,i)=>`<div class="detail-issue"><strong>${escapeHtml(problems[i]||`Pendência ${i+1}`)}</strong><span>→ ${escapeHtml(a)}</span></div>`).join("");
  else if(item.monitor_status==="conforme") pend.innerHTML='<div class="detail-ok">✓ Nenhuma pendência identificada no último monitoramento.</div>';
  else pend.innerHTML='<div class="empty-inline">Sem pendências disponíveis.</div>';
  panel.classList.remove("hidden");
}
function closeCrosscheckDetails(){document.getElementById("crosscheck-details")?.classList.add("hidden");}
function openCrosscheckMonitor(){if(!activeCrosscheckItem)return; const p=activeCrosscheckItem.monitor_process, c=activeCrosscheckItem.code||""; if(p==="Usinagem Interna"){activateView("monitor");const s=document.getElementById("search");if(s){s.value=c;filterRows();}} else if(p==="Corte a Laser"){activateView("laser");const s=document.getElementById("laser-search");if(s){s.value=c;applyLaserFilters();}} closeCrosscheckDetails();}

// V0.7.4.0 — Biblioteca CAD
function renderLibrary(rows){
  const body=document.getElementById('library-body'); if(!body) return;
  if(!rows.length){ body.innerHTML='<tr><td colspan="8" class="empty">Nenhuma pasta encontrada para o filtro atual.</td></tr>'; return; }
  body.innerHTML=rows.map((r,i)=>`<tr class="row-click" onclick="showLibraryDetails(${(window.libraryResults||[]).indexOf(r)})"><td>${escapeHtml(r.type_name)}</td><td><strong>${escapeHtml(r.folder_name)}</strong><br><small>${escapeHtml(r.code||'Código não identificado')}</small></td><td class="center">${yes(r.folder_pattern_ok)}</td><td class="center">${yes(r.part3d)}</td><td class="center">${yes(r.drawing2d)}</td><td class="center">${yes(r.pdf)}</td><td><span class="status ${r.status}">${statusText(r.status)}</span></td><td>${escapeHtml(firstAction(r))}</td></tr>`).join('');
}
function filterLibrary(){
  const q=(document.getElementById('library-search')?.value||'').toLowerCase().trim(); const st=document.getElementById('library-status-filter')?.value||'';
  renderLibrary((window.libraryResults||[]).filter(r=>(!st||r.status===st)&&(!q||[r.type_name,r.folder_name,r.code,r.piece_name,(r.problems||[]).join(' ')].join(' ').toLowerCase().includes(q))));
}
async function scanLibrary(){
  const body=document.getElementById('library-body'); body.innerHTML='<tr><td colspan="8" class="empty">Analisando Biblioteca CAD...</td></tr>';
  const res=await fetch('/api/scan-library'); const data=await res.json();
  if(!res.ok){body.innerHTML=`<tr><td colspan="8" class="empty">${escapeHtml(data.error||'Erro na análise')}</td></tr>`;return;}
  window.libraryResults=data.results||[]; renderLibrary(window.libraryResults);
  document.getElementById('library-subtitle').textContent=`${data.environment_name} • ${data.folder_path} • STEP ignorado nesta versão`;
  if(data.summary){ ['total','ok','warning','bad'].forEach(k=>{const el=document.getElementById('library-'+k); if(el) el.textContent=data.summary[k]??0;}); }
  showToast('Biblioteca CAD analisada.','success');
}
function showLibraryDetails(i){
  const r=(window.libraryResults||[])[i]; if(!r) return; const p=document.getElementById('library-details-panel'); p.classList.remove('hidden');
  const issues=(r.problems||[]).map((x,j)=>`<div class="issue"><strong>${escapeHtml(x)}</strong><br><span style="color:#596579">→ ${escapeHtml((r.actions||[])[j]||'')}</span></div>`).join('')||'<p>Nenhuma inconsistência detectada.</p>';
  p.innerHTML=`<button class="icon-btn" style="float:right" onclick="this.parentElement.classList.add('hidden')">×</button><h3>${escapeHtml(r.folder_name)}</h3><p><strong>Tipo:</strong> ${escapeHtml(r.type_name)}<br><strong>Código:</strong> ${escapeHtml(r.code||'-')}<br><strong>Nome:</strong> ${escapeHtml(r.piece_name||'-')}</p><p><strong>3D editável:</strong> ${escapeHtml((r.part3d_files||[]).join(', ')||'-')}<br><strong>2D editável:</strong> ${escapeHtml((r.drawing2d_files||[]).join(', ')||'-')}<br><strong>PDF:</strong> ${escapeHtml((r.pdf_files||[]).join(', ')||'-')}</p>${(r.ignored_step_files||[]).length?`<p><small>STEP/STP encontrado e ignorado nesta versão: ${escapeHtml(r.ignored_step_files.join(', '))}</small></p>`:''}<h4>Pendências</h4>${issues}<div class="details-actions"><button class="btn secondary" onclick="openFolderPath(${JSON.stringify(r.folder_path||'')})">📂 Abrir pasta</button></div>`;
}
document.addEventListener('DOMContentLoaded',()=>{ if(window.libraryResults?.length) renderLibrary(window.libraryResults); });


// V0.7.4.1 — configuração robusta dos monitoramentos.
// Usa delegação de eventos para não depender de onclick inline no HTML.
window.toggleProcessConfig = function(processKey, show=true){
  ["usinagem","corte_laser","biblioteca_cad"].forEach(function(key){
    const panel=document.getElementById("config-"+key);
    if(!panel) return;
    panel.classList.toggle("hidden", !(key===processKey && show));
  });
  if(show){
    const panel=document.getElementById("config-"+processKey);
    const input=panel?.querySelector('input[name="path"]');
    if(input) setTimeout(()=>input.focus(),0);
  }
};

document.addEventListener("click", function(event){
  const openBtn=event.target.closest("[data-config-process]");
  if(openBtn){
    event.preventDefault();
    window.toggleProcessConfig(openBtn.dataset.configProcess, true);
    return;
  }
  const closeBtn=event.target.closest("[data-close-config]");
  if(closeBtn){
    event.preventDefault();
    window.toggleProcessConfig(closeBtn.dataset.closeConfig, false);
    return;
  }
  const overlay=event.target.closest(".inline-config");
  if(overlay && event.target===overlay){
    overlay.classList.add("hidden");
  }
});

document.addEventListener("keydown", function(event){
  if(event.key!=="Escape") return;
  document.querySelectorAll(".inline-config").forEach(p=>p.classList.add("hidden"));
});
