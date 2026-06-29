// ====== 调试模式 ======
var DEBUG = true;
function debugLog(tag, data) {
  if (!DEBUG) return;
  var ts = new Date().toISOString().split('T')[1].slice(0,12);
  console.log('[' + ts + '][' + tag + ']', data);
  if (!window._debugLogs) window._debugLogs = [];
  window._debugLogs.push({ts:ts, tag:tag, data:data});
  if (window._debugLogs.length > 200) window._debugLogs = window._debugLogs.slice(-100);
}

// ====== 应用启动 ======
var API_BASE = "/api/v1";
var APP = { projects: [], currentProject: null, currentTab: "content", feynmanSessionId: null, feynmanRound: 0, feynmanHistory: [], feynmanSaved: null };

document.addEventListener("DOMContentLoaded", function() {
  loadProjects();
  document.getElementById("btnNewProject").addEventListener("click", showImportModal);
  document.getElementById("btnUpdate").addEventListener("click", handleUpdate);
  document.getElementById("btnModalClose").addEventListener("click", closeImportModal);
  document.getElementById("btnCancelGit").addEventListener("click", closeImportModal);
  document.getElementById("btnCancelConcept").addEventListener("click", closeImportModal);
  document.getElementById("btnImportGit").addEventListener("click", importGit);
  document.getElementById("btnImportConcept").addEventListener("click", importConcept);
  setupFileDrop();
  setupTabs();
  document.getElementById("importModal").addEventListener("click", function(e) {
    if (e.target === document.getElementById("importModal")) closeImportModal();
  });
  var quickBtn = document.getElementById("btnQuickImport");
  if (quickBtn) quickBtn.addEventListener("click", showImportModal);
});

function loadProjects() {
  return fetch(API_BASE + "/projects").then(function(r) { return r.json(); }).then(function(d) {
    APP.projects = d.projects || []; renderProjectList();
    if (APP.projects.length > 0 && !APP.currentProject) selectProject(APP.projects[0].id);
  }).catch(function(e) { toast("加载项目列表失败", "error"); });
}

function renderProjectList() {
  var list = document.getElementById("projectList");
  var icons = { file: "\u{1F4C1}", git: "\u{1F5C4}", concept: "\u{1F4A1}" };
  var typeNames = { file: "文件", git: "Git仓库", concept: "概念" };
  if (!APP.projects.length) { list.innerHTML = "<div class=\"project-list-empty\">还没有项目<br>点击 + 导入一个吧</div>"; return; }
  list.innerHTML = APP.projects.map(function(p) {
    var icon = icons[p.source_type] || "\u{1F4C4}";
    var cls = "p-status " + (p.status || "pending");
    var act = (APP.currentProject && APP.currentProject.id === p.id) ? " active" : "";
    return "<div class=\"project-item" + act + "\" data-pid=\"" + p.id + "\">" +
      "<span class=\"p-icon\">" + icon + "</span>" +
      "<div class=\"p-info\"><div class=\"p-name\">" + esc(p.name) + "</div>" +
      "<div class=\"p-meta\">" + esc(typeNames[p.source_type] || p.source_type || "") + "</div></div>" +
      "<span class=\"" + cls + "\"></span>" +
      "<button class=\"p-delete\" data-del=\"" + p.id + "\">x</button></div>";
  }).join("");
  list.querySelectorAll(".project-item").forEach(function(item) {
    item.addEventListener("click", function(e) {
      if (e.target.closest(".p-delete")) return; selectProject(item.dataset.pid);
    });
  });
  list.querySelectorAll(".p-delete").forEach(function(btn) {
    btn.addEventListener("click", function(e) { e.stopPropagation(); deleteProject(btn.dataset.del); });
  });
}

function selectProject(id) {
  return fetch(API_BASE + "/projects/" + id).then(function(r) { return r.json(); }).then(function(d) {
    APP.currentProject = d.project;
    APP.feynmanSessionId = null; APP.feynmanRound = 0; APP.feynmanSaved = null;
    renderProjectList(); renderTopBar();
    checkUpdateStatus();
    switchTab(APP.currentTab);
  }).catch(function(e) { toast("加载项目失败", "error"); });
}

function deleteProject(id) {
  if (!confirm("确定要删除这个项目吗？")) return;
  fetch(API_BASE + "/projects/" + id, { method: "DELETE" }).then(function() {
    if (APP.currentProject && APP.currentProject.id === id) APP.currentProject = null;
    return loadProjects();
  }).then(function() {
    if (!APP.currentProject && APP.projects.length > 0) selectProject(APP.projects[0].id);
    if (!APP.currentProject) showWelcome();
  }).catch(function(e) { toast("删除失败", "error"); });
}

function showImportModal() { debugLog("modal", "打开导入弹窗"); document.getElementById("importModal").classList.add("show"); switchModalTab("file"); }
function closeImportModal() { debugLog("modal", "关闭导入弹窗"); document.getElementById("importModal").classList.remove("show"); }

function switchModalTab(tab) {
  document.querySelectorAll(".modal-tab").forEach(function(b) { b.classList.toggle("active", b.dataset.mtab === tab); });
  document.querySelectorAll(".modal-panel").forEach(function(p) { p.classList.toggle("active", p.id === "panel-" + tab); });
}

function setupFileDrop() {
  document.querySelectorAll(".modal-tab").forEach(function(btn) { btn.addEventListener("click", function() { switchModalTab(btn.dataset.mtab); }); });
  var drop = document.getElementById("dropZone");
  drop.addEventListener("click", function() { document.getElementById("fileInput").click(); });
  drop.addEventListener("dragover", function(e) { e.preventDefault(); drop.classList.add("drag-over"); });
  drop.addEventListener("dragleave", function() { drop.classList.remove("drag-over"); });
  drop.addEventListener("drop", function(e) { e.preventDefault(); drop.classList.remove("drag-over"); if (e.dataTransfer.files.length > 0) handleFileUpload(e.dataTransfer.files[0]); });
  document.getElementById("fileInput").addEventListener("change", function(e) { if (e.target.files.length > 0) handleFileUpload(e.target.files[0]); });
}

function handleFileUpload(file) { debugLog("upload", "handleFileUpload called, file=" + (file ? file.name + " size=" + file.size : "NULL"));
  var name = document.getElementById("fileName").value || file.name; debugLog("upload", "name=" + name);
  var fd = new FormData(); fd.append("file", file); fd.append("name", name);
  debugLog("upload", "调用 /projects/import/file..."); fetch(API_BASE + "/projects/import/file", { method: "POST", body: fd })
    .then(function(r) { debugLog("file", "响应状态=" + r.status); return r.json(); }).then(function(d) { debugLog("file", "结果=" + JSON.stringify(d).slice(0,200)); if (d.success) { closeImportModal(); loadProjects().then(function() { return selectProject(d.project.id); }).then(function() { startLearning(d.project.id); }); } else { toast("上传失败", "error"); } })
    .catch(function(e) { toast("上传失败: " + e.message, "error"); });
}

function importGit() { debugLog("git", "importGit 被调用"); var url = document.getElementById("gitUrl").value.trim();
  var name = document.getElementById("gitName").value.trim();
  if (!url) { toast("请输入 Git 仓库地址", "error"); return; }
  fetch(API_BASE + "/projects/import/git", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ git_url: url, name: name || "" }) })
    .then(function(r) { return r.json(); })
    .then(function(d) { debugLog('git','API 响应: '+JSON.stringify(d).slice(0,300)); if (d.success) { closeImportModal(); loadProjects().then(function() { return selectProject(d.project.id); }).then(function() { startLearning(d.project.id); }); } else { var msg = d.detail || '导入失败'; if (Array.isArray(d.detail)) { msg = d.detail.map(function(e){return e.msg||e.type;}).join(', '); } toast('导入失败: ' + msg, 'error'); } })
    .catch(function(e) { toast("导入失败: " + e.message, "error"); });
}

function importConcept() { debugLog("concept", "importConcept 被调用"); var concept = document.getElementById("conceptText").value.trim();
  var name = document.getElementById("conceptName").value.trim();
  debugLog("concept", "concept=" + concept.slice(0,50)); if (!concept) { toast("请输入一个概念", "error"); return; }
  fetch(API_BASE + "/projects/import/concept", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ concept: concept, name: name || "" }) })
    .then(function(r) { return r.json(); })
    .then(function(d) { debugLog('concept','API 响应: '+JSON.stringify(d).slice(0,300)); if (d.success) { closeImportModal(); loadProjects().then(function() { return selectProject(d.project.id); }).then(function() { startLearning(d.project.id); }); } else { var msg = d.detail || '导入失败'; if (Array.isArray(d.detail)) { msg = d.detail.map(function(e){return e.msg||e.type;}).join(', '); } toast('导入失败: ' + msg, 'error'); } })
    .catch(function(e) { toast("导入失败: " + e.message, "error"); });
}

function startLearning(projectId) { debugLog("learn", "startLearning 被调用，项目ID=" + projectId);
  document.getElementById("contentArea").innerHTML =
    "<div class=\"loading-state\">" +
    "<div class=\"spinner\"></div>" +
    "<p id=\"progressText\">准备中...</p>" +
    "<div style=\"width:300px;height:8px;background:var(--paper-dark);border-radius:4px;margin:12px auto;overflow:hidden;\">" +
    "<div id=\"progressBar\" style=\"width:0%;height:100%;background:var(--blue-pen);border-radius:4px;transition:width .3s;\"></div>" +
    "</div></div>";
  var stages = { parsing: "正在解析内容", checking: "正在检查可学习性", framework: "正在分析知识框架", explaining: "正在生成讲解内容", saving: "正在保存结果", done: "完成" };
  var poll = setInterval(function() {
    fetch(API_BASE + "/learning/" + projectId + "/progress").then(function(r) { return r.json(); }).then(function(p) {
      var bar = document.getElementById("progressBar"); if (bar) bar.style.width = (p.progress || 0) + "%";
      var txt = document.getElementById("progressText"); if (txt) txt.textContent = stages[p.stage] || p.stage || "处理中...";
      if (p.stage === "done") clearInterval(poll);
    }).catch(function() {});
  }, 600);
  fetch(API_BASE + "/learning/" + projectId + "/start", { method: "POST" })
    .then(function(r) { return r.json(); })
    .then(function(d) {
      clearInterval(poll);
      var bar = document.getElementById("progressBar"); if (bar) bar.style.width = "100%";
      var txt = document.getElementById("progressText"); if (txt) txt.textContent = "完成啦！";
      if (d.success) {
        var r = d.result || {};
        if (r.is_learnable === false) {
          document.getElementById("contentArea").innerHTML = "<div class=\"empty-state\"><h3>暂不适合学习</h3><p>" + esc(r.learnability_reason || "") + "</p></div>";
          loadProjects().then(function() { renderProjectList(); });
        } else { selectProject(projectId).then(function() { switchTab("content"); toast("学习内容已生成！", "success"); }); }
      }
    })
    .catch(function(e) { clearInterval(poll); toast("学习流程失败: " + e.message, "error"); showWelcome(); });
}

function handleUpdate() {
  if (!APP.currentProject) return;
  var btn = document.getElementById("btnUpdate"); btn.disabled = true; btn.textContent = "更新中...";
  fetch(API_BASE + "/learning/" + APP.currentProject.id + "/update", { method: "POST" })
    .then(function(r) { return r.json(); })
    .then(function(d) { toast(d.needs_update ? "已更新" : "已是最新", "success"); return selectProject(APP.currentProject.id); })
    .then(function() { switchTab("content"); }).catch(function() {})
    .finally(function() { btn.disabled = false; btn.textContent = "\u{21BB} 更新"; });
}

function checkUpdateStatus() {
  if (!APP.currentProject) return;
  fetch(API_BASE + "/logs/" + APP.currentProject.id + "/check-update").then(function(r) { return r.json(); }).then(function(d) {
    var n = document.getElementById("updateNudge");
    if (d.update_needed) { n.textContent = "⚠ " + d.reason; n.style.display = "flex"; } else { n.style.display = "none"; }
  }).catch(function() {});
}

function setupTabs() { document.querySelectorAll(".tab").forEach(function(btn) { btn.addEventListener("click", function() { switchTab(btn.dataset.tab); }); }); }

function switchTab(tab) { debugLog("tab", "switchTab(" + tab + "), 当前项目=" + (APP.currentProject ? APP.currentProject.name : "无"));
  APP.currentTab = tab;
  document.querySelectorAll(".tab").forEach(function(b) { b.classList.toggle("active", b.dataset.tab === tab); });
  if (!APP.currentProject) { showWelcome(); return; }
  if (tab === "content") renderContent(); else if (tab === "qa") renderQA();
  else if (tab === "feynman") renderFeynman(); else if (tab === "logs") renderLogs();
}

function renderTopBar() {
  document.getElementById("projectTitle").textContent = APP.currentProject ? APP.currentProject.name : "欢迎回来";
  document.getElementById("btnUpdate").disabled = !APP.currentProject;
}

function showWelcome() {
  document.getElementById("projectTitle").textContent = "欢迎回来";
  document.getElementById("contentArea").innerHTML = "<div class=\"welcome-state\"><div class=\"welcome-icon\">&#x1F4DA;</div><h2>欢迎使用学习助手</h2><p>导入 PDF、Git 仓库，或者写下一个概念，开始你的学习之旅吧。</p><div class=\"quick-actions\"><button class=\"quick-action\" id=\"btnQuickImport\">&#x1F4E5; 导入学习资料</button></div></div>";
  var quickBtn = document.getElementById("btnQuickImport");
  if (quickBtn) quickBtn.addEventListener("click", showImportModal);
}

function renderContent() {
  var area = document.getElementById("contentArea"), p = APP.currentProject;
  if (!p) { showWelcome(); return; }
  if (p.status === "pending" || p.status === "processing") { area.innerHTML = "<div class=\"loading-state\"><div class=\"spinner\"></div><p>处理中...</p></div>"; return; }
  if (p.status === "not_learnable") { area.innerHTML = "<div class=\"empty-state\"><h3>暂不适合学习</h3><p>" + esc(p.learnability_reason || "") + "</p></div>"; return; }
  if (!p.learning_content || !p.learning_content.sq3r) { area.innerHTML = "<div class=\"empty-state\"><h3>暂无内容</h3><p>学习内容尚未生成。</p></div>"; return; }
  var c = p.learning_content, sq3r = c.sq3r || {}, html = "";
  html += "<h1 style=\"font-size:1.5rem;margin-bottom:24px;font-family:var(--font-title);letter-spacing:.04em;\">" + esc(c.title || p.name) + "</h1>";
  if (c.framework && c.framework.structure && c.framework.structure.length > 0) { html += "<div class=\"sq3r-card\"><h2>知识框架</h2>" + renderFramework(c.framework.structure) + "</div>"; }
  if (sq3r.survey && sq3r.survey.content) { html += "<div class=\"sq3r-card\"><h2>" + esc(sq3r.survey.title || "概览") + "</h2><div class=\"md-content\">" + simpleMD(sq3r.survey.content) + "</div></div>"; }
  if (sq3r.question && sq3r.question.questions && sq3r.question.questions.length > 0) {
    html += "<div class=\"question-card\"><h3>" + esc(sq3r.question.title || "思考题") + "</h3>";
    if (sq3r.question.guidance) html += "<p style=\"font-family:var(--font-hand);color:var(--ink-faded);\">" + esc(sq3r.question.guidance) + "</p>";
    html += "<ul>" + sq3r.question.questions.map(function(q) { return "<li>" + esc(q) + "</li>"; }).join("") + "</ul></div>";
  }
  if (sq3r.read && sq3r.read.sections && sq3r.read.sections.length > 0) {
    html += "<div class=\"sq3r-card\"><h2>" + esc(sq3r.read.title || "精读") + "</h2>";
    sq3r.read.sections.forEach(function(s) { html += "<h3>" + esc(s.heading || "") + "</h3><div class=\"md-content\">" + simpleMD(s.content || "") + "</div>"; });
    html += "</div>";
  }
  if (sq3r.recite) {
    html += "<div class=\"sq3r-card\"><h2>" + esc(sq3r.recite.title || "复述") + "</h2>";
    if (sq3r.recite.key_points && sq3r.recite.key_points.length > 0) { html += "<ul>" + sq3r.recite.key_points.map(function(k) { return "<li><strong>" + esc(k) + "</strong></li>"; }).join("") + "</ul>"; }
    if (sq3r.recite.summary) html += "<div class=\"md-content\">" + simpleMD(sq3r.recite.summary) + "</div>";
    html += "</div>";
  }
  if (sq3r.review) {
    html += "<div class=\"sq3r-card\"><h2>" + esc(sq3r.review.title || "复习") + "</h2>";
    if (sq3r.review.suggestions && sq3r.review.suggestions.length > 0) { html += "<h3>学习建议</h3><ul>" + sq3r.review.suggestions.map(function(s) { return "<li>" + esc(s) + "</li>"; }).join("") + "</ul>"; }
    if (sq3r.review.exercises && sq3r.review.exercises.length > 0) { html += "<h3>练习</h3><ul>" + sq3r.review.exercises.map(function(e) { return "<li>" + esc(e) + "</li>"; }).join("") + "</ul>"; }
    html += "</div>";
  }
  if (sq3r.supplements && sq3r.supplements.length > 0) { html += "<div class=\"sq3r-card\"><h2>补充材料</h2>"; sq3r.supplements.forEach(function(s) { html += "<h3>" + esc(s.section || "") + "</h3><div class=\"md-content\">" + simpleMD(s.content || "") + "</div>"; }); html += "</div>"; }
  area.innerHTML = html;
}

function renderFramework(nodes) {
  return (nodes || []).map(function(n) {
    var h = "<div class=\"framework-node\"><div class=\"fn-title\">" + esc(n.title || n.name || "") + "</div>";
    if (n.description) h += "<div class=\"fn-desc\">" + esc(n.description) + "</div>";
    if (n.children && n.children.length > 0) h += "<div class=\"framework-children\">" + renderFramework(n.children) + "</div>";
    h += "</div>"; return h;
  }).join("");
}

function renderQA() {
  document.getElementById("contentArea").innerHTML =
    "<div class=\"chat-container\"><div class=\"chat-messages\" id=\"qaMessages\"><div class=\"empty-state\"><h3>提出问题</h3><p>关于这个项目，你有什么想问的？</p></div></div>" +
    "<div class=\"chat-input-row\"><input type=\"text\" id=\"qaInput\" placeholder=\"输入你的问题...\"><button id=\"qaSendBtn\">发送</button></div></div>";
  document.getElementById("qaSendBtn").addEventListener("click", askQuestion);
  var inp = document.getElementById("qaInput"); if (inp) inp.addEventListener("keydown", function(e) { if (e.key === "Enter") askQuestion(); });
  loadQAHistory();
}
function loadQAHistory() {
  if (!APP.currentProject) return;
  fetch(API_BASE + "/qa/" + APP.currentProject.id + "/history").then(function(r) { return r.json(); }).then(function(d) {
    var msgs = document.getElementById("qaMessages");
    if (d.records && d.records.length > 0) { msgs.innerHTML = d.records.map(function(r) { return "<div class=\"chat-msg user\"><div class=\"msg-bubble\">" + esc(r.question) + "</div></div><div class=\"chat-msg assistant\"><div class=\"msg-bubble\">" + simpleMD(r.answer) + "</div><div class=\"msg-source\">来源: " + esc(r.source_type || "") + "</div></div>"; }).join(""); msgs.scrollTop = msgs.scrollHeight; }
  }).catch(function() {});
}
function askQuestion() {
  var input = document.getElementById("qaInput"); if (!input || !APP.currentProject) return;
  var question = input.value.trim(); if (!question) return; input.value = "";
  var msgs = document.getElementById("qaMessages"); var empty = msgs.querySelector(".empty-state"); if (empty) empty.remove();
  msgs.innerHTML += "<div class=\"chat-msg user\"><div class=\"msg-bubble\">" + esc(question) + "</div></div>";
  msgs.innerHTML += "<div class=\"chat-msg assistant\" id=\"tmpLoading\"><div class=\"msg-bubble\"><div class=\"spinner\"></div></div></div>";
  msgs.scrollTop = msgs.scrollHeight;
  fetch(API_BASE + "/qa/" + APP.currentProject.id + "/ask", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ question: question }) })
    .then(function(r) { return r.json(); }).then(function(d) { var tmp = document.getElementById("tmpLoading"); if (tmp) { tmp.querySelector(".msg-bubble").innerHTML = simpleMD(d.answer); tmp.innerHTML += "<div class=\"msg-source\">来源: " + esc(d.source_type || "") + "</div>"; tmp.removeAttribute("id"); } msgs.scrollTop = msgs.scrollHeight; })
    .catch(function(e) { var tmp = document.getElementById("tmpLoading"); if (tmp) { tmp.querySelector(".msg-bubble").innerHTML = "出错了: " + esc(e.message); tmp.removeAttribute("id"); } });
}

function renderFeynman() { if (APP.feynmanSaved) { document.getElementById("contentArea").innerHTML = APP.feynmanSaved; bindFeynmanButtons(); var fi = document.getElementById("feynmanInput"); if (fi) fi.focus(); return; }
  document.getElementById("contentArea").innerHTML = "<div class=\"feynman-stage\" id=\"feynmanStage\"><div class=\"empty-state\"><h3>费曼学习法</h3><p>AI 会扮演一个好奇的学生来向你提问。</p><button class=\"btn-primary\" id=\"btnStartFeynman\" style=\"margin-top:16px;\">开始学习</button></div></div>";
  document.getElementById("btnStartFeynman").addEventListener("click", startFeynman);
}
function startFeynman() {
  if (!APP.currentProject) return;
  fetch(API_BASE + "/feynman/" + APP.currentProject.id + "/start", { method: "POST" }).then(function(r) { return r.json(); }).then(function(d) {
    APP.feynmanSessionId = d.session_id; APP.feynmanRound = d.round || 1;
    document.getElementById("feynmanStage").innerHTML = buildFeynmanUI(d.question, d.hint); setTimeout(function(){ APP.feynmanSaved = document.getElementById("feynmanStage").parentElement.innerHTML; }, 100);
    bindFeynmanButtons(); var fi = document.getElementById("feynmanInput"); if (fi) fi.focus();
  }).catch(function(e) { toast("启动失败", "error"); });
}
function buildFeynmanUI(question, hint) {
  return "<div class=\"feynman-turn ai\"><div class=\"feynman-avatar\">?</div><div class=\"feynman-bubble\"><strong>学生（第 " + APP.feynmanRound + " 轮）：</strong><br>" + esc(question) + (hint ? "<br><small style=\"color:var(--ink-faded);\">提示: " + esc(hint) + "</small>" : "") + "</div></div>" +
    "<div id=\"feynmanEval\"></div><div class=\"feynman-input-row\"><input type=\"text\" id=\"feynmanInput\" placeholder=\"用你自己的话解释...\"><button class=\"btn-primary\" id=\"btnFAnswer\">回答</button><button class=\"btn-cancel btn-confused\" id=\"btnFConfused\">我不太确定</button></div>";
}
function bindFeynmanButtons() {
  var ba = document.getElementById("btnFAnswer"), bc = document.getElementById("btnFConfused");
  if (ba) ba.addEventListener("click", submitFeynmanAnswer); if (bc) bc.addEventListener("click", submitFeynmanConfused);
  var fi = document.getElementById("feynmanInput"); if (fi) fi.addEventListener("keydown", function(e) { if (e.key === "Enter") submitFeynmanAnswer(); });
}
function removeOldFeynmanUI() {
  var oldEval = document.getElementById("feynmanEval"); if (oldEval) oldEval.remove();
  var oldRow = document.querySelector("#feynmanStage .feynman-input-row"); if (oldRow) oldRow.remove();
}
function submitFeynmanAnswer() {
  var input = document.getElementById("feynmanInput"); if (!input || !APP.feynmanSessionId) return;
  var answer = input.value.trim(); if (!answer) return; input.value = "";
  var stage = document.getElementById("feynmanStage");
  removeOldFeynmanUI();
  stage.innerHTML += "<div class=\"feynman-turn user\"><div class=\"feynman-bubble\">" + esc(answer) + "</div></div>";
  stage.innerHTML += "<div class=\"loading-state\" id=\"feynmanLoading\"><div class=\"spinner\"></div></div>";
  sendFeynmanAnswer(answer, false);
}
function submitFeynmanConfused() {
  var stage = document.getElementById("feynmanStage");
  removeOldFeynmanUI();
  stage.innerHTML += "<div class=\"feynman-turn user\"><div class=\"feynman-bubble\" style=\"background:var(--sticky-pink);color:var(--red-pen);border-color:#e8c0b0;\">我不太确定这部分...</div></div>";
  stage.innerHTML += "<div class=\"loading-state\" id=\"feynmanLoading\"><div class=\"spinner\"></div></div>";
  sendFeynmanAnswer("我不太确定", true);
}
function sendFeynmanAnswer(answer, confused) {
  fetch(API_BASE + "/feynman/" + APP.currentProject.id + "/answer", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ session_id: APP.feynmanSessionId, answer: answer, confused: confused }) })
    .then(function(r) { return r.json(); }).then(function(d) {
      var loading = document.getElementById("feynmanLoading"); if (loading) loading.remove();
      if (d.session_completed) {
        document.getElementById("feynmanStage").innerHTML += "<div class=\"evaluation-card\"><h3 style=\"font-family:var(--font-title);margin-bottom:8px;\">学习完成！</h3><p>" + esc(d.overall_assessment || "") + "</p>" + (d.weak_points || []).map(function(w) { return "<p class=\"eval-weak\">\u{25CF} " + esc(w) + "</p>"; }).join("") + "</div>";
        APP.feynmanSessionId = null; APP.feynmanSaved = null; generateLog();
      } else {
        removeOldFeynmanUI();
        if (d.correction) { document.getElementById("feynmanStage").innerHTML += "<div class=\"evaluation-card\"><p><strong>反馈:</strong> " + esc(d.correction) + "</p></div>"; }
        APP.feynmanRound = d.round || (APP.feynmanRound + 1);
        document.getElementById("feynmanStage").innerHTML += buildFeynmanUI(d.next_question, d.hint);
        bindFeynmanButtons(); var fi = document.getElementById("feynmanInput"); if (fi) fi.focus();
        APP.feynmanSaved = document.getElementById("feynmanStage").parentElement.innerHTML;
      }
    }).catch(function() { var l = document.getElementById("feynmanLoading"); if (l) l.remove(); });
}

function renderLogs() {
  if (!APP.currentProject) return;
  document.getElementById("contentArea").innerHTML = "<div class=\"loading-state\"><div class=\"spinner\"></div></div>";
  fetch(API_BASE + "/logs/" + APP.currentProject.id).then(function(r) { return r.json(); }).then(function(d) {
    if (!d.logs || d.logs.length === 0) { document.getElementById("contentArea").innerHTML = "<div class=\"empty-state\"><h3>暂无日志</h3><p>完成问答或费曼学习后会生成日志。</p></div>"; return; }
    var html = "<div class=\"log-timeline\">" + d.logs.map(function(l) { return "<div class=\"log-entry\"><div class=\"log-date\">" + esc(l.log_date || "") + " | " + (l.session_count || 0) + " 次学习</div>" + (l.knowledge_summary ? "<div class=\"log-block\"><h4>掌握知识点</h4><div class=\"md-content\">" + simpleMD(l.knowledge_summary) + "</div></div>" : "") + (l.weak_points ? "<div class=\"log-block\"><h4>薄弱环节</h4><div class=\"md-content\">" + simpleMD(l.weak_points) + "</div></div>" : "") + "</div>"; }).join("") + "</div><button class=\"btn-primary\" id=\"btnGenLog\" style=\"margin-top:16px;\">生成日志</button>";
    document.getElementById("contentArea").innerHTML = html; document.getElementById("btnGenLog").addEventListener("click", generateLog);
  }).catch(function() { document.getElementById("contentArea").innerHTML = "<div class=\"empty-state\"><p>加载日志失败</p></div>"; });
}
function generateLog() {
  if (!APP.currentProject) return;
  fetch(API_BASE + "/logs/" + APP.currentProject.id + "/generate", { method: "POST" }).then(function(r) { return r.json(); }).then(function(d) { toast(d.message || "日志已生成", "success"); if (APP.currentTab === "logs") renderLogs(); }).catch(function() {});
}

function esc(s) { if (!s) return ""; var d = document.createElement("div"); d.textContent = s; return d.innerHTML; }
function simpleMD(t) { if (!t) return ""; var h = esc(t); h = h.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>"); h = h.replace(/\*(.+?)\*/g, "<em>$1</em>"); h = h.replace(/`([^`]+)`/g, "<code>$1</code>"); h = h.replace(/^### (.+)$/gm, "<h3>$1</h3>"); h = h.replace(/^## (.+)$/gm, "<h2>$1</h2>"); h = h.replace(/^# (.+)$/gm, "<h1>$1</h1>"); h = h.replace(/^[\-\*] (.+)$/gm, "<li>$1</li>"); h = h.replace(/((?:<li>.*<\/li>\s*)+)/g, "<ul>$1</ul>"); h = h.replace(/```([\s\S]*?)```/g, "<pre><code>$1</code></pre>"); h = h.split("\n\n").map(function(p) { return "<p>" + p + "</p>"; }).join(""); h = h.replace(/<p>\s*<\/p>/g, ""); return h; }
function toast(msg, type) { var t = document.createElement("div"); t.className = "toast " + (type || "success"); t.textContent = msg; document.body.appendChild(t); setTimeout(function() { t.remove(); }, 3000); }
