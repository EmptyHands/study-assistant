// Study Assistant SPA - Main Application JavaScript
(function() {
'use strict';

var API_BASE = '/api/v1';
var APP = window.APP = {
  projects: [],
  currentProject: null,
  currentTab: 'content',
  feynmanSessionId: null,
  feynmanRound: 0
};

async function init() {
  await loadProjects();
  document.getElementById('btnAddProject').onclick = showImportModal;
  document.getElementById('btnUpdate').onclick = handleUpdate;
  setupImportModal();
  setupTabs();
}

async function loadProjects() {
  try {
    var r = await fetch(API_BASE + '/projects');
    var data = await r.json();
    APP.projects = data.projects || [];
    renderProjectList();
    if (APP.projects.length > 0 && !APP.currentProject) {
      await selectProject(APP.projects[0].id);
    }
  } catch(e) { toast('Failed to load projects: ' + e.message, 'error'); }
}

function renderProjectList() {
  var list = document.getElementById('projectList');
  var icons = { file: '\u{1F4C1}', git: '\u{1F5C4}', concept: '\u{1F4A1}' };
  list.innerHTML = APP.projects.map(function(p) {
    var icon = icons[p.source_type] || '\u{1F4C4}';
    var statusCls = 'status-' + (p.status || 'pending');
    var activeCls = (APP.currentProject && APP.currentProject.id === p.id) ? ' active' : '';
    return '<div class="project-item' + activeCls + '" data-id="' + p.id + '">' +
      '<span class="icon">' + icon + '</span>' +
      '<div class="info"><div class="name">' + esc(p.name) + '</div>' +
      '<div class="meta">' + esc(p.source_type || '') + '</div></div>' +
      '<span class="status-dot ' + statusCls + '"></span>' +
      '<button class="delete-btn" data-del="' + p.id + '">x</button></div>';
  }).join('');

  list.querySelectorAll('.project-item').forEach(function(item) {
    item.onclick = function(e) {
      if (e.target.closest('.delete-btn')) return;
      selectProject(item.dataset.id);
    };
  });
  list.querySelectorAll('.delete-btn').forEach(function(btn) {
    btn.onclick = function(e) { e.stopPropagation(); deleteProject(btn.dataset.del); };
  });
}

async function selectProject(id) {
  try {
    var r = await fetch(API_BASE + '/projects/' + id);
    var data = await r.json();
    APP.currentProject = data.project;
    renderProjectList();
    renderTopBar();
    switchTab(APP.currentTab);
    checkUpdateStatus();
  } catch(e) { toast('Failed to load project: ' + e.message, 'error'); }
}

async function deleteProject(id) {
  if (!confirm('Delete this project and all its learning data?')) return;
  try {
    await fetch(API_BASE + '/projects/' + id, { method: 'DELETE' });
    if (APP.currentProject && APP.currentProject.id === id) APP.currentProject = null;
    await loadProjects();
    if (!APP.currentProject && APP.projects.length > 0) await selectProject(APP.projects[0].id);
    if (!APP.currentProject) showEmptyState();
    toast('Project deleted', 'success');
  } catch(e) { toast('Delete failed: ' + e.message, 'error'); }
}

function showImportModal() { document.getElementById('importModal').classList.add('show'); switchModalTab('file'); }
function closeImportModal() { document.getElementById('importModal').classList.remove('show'); }

function setupImportModal() {
  document.getElementById('importModal').onclick = function(e) { if (e.target === this) closeImportModal(); };
  document.querySelectorAll('.modal-tab').forEach(function(btn) {
    btn.onclick = function() { switchModalTab(btn.dataset.tab); };
  });
  var drop = document.getElementById('fileDrop');
  drop.onclick = function() { document.getElementById('fileInput').click(); };
  drop.ondragover = function(e) { e.preventDefault(); drop.classList.add('dragover'); };
  drop.ondragleave = function() { drop.classList.remove('dragover'); };
  drop.ondrop = function(e) {
    e.preventDefault(); drop.classList.remove('dragover');
    if (e.dataTransfer.files.length > 0) handleFileUpload(e.dataTransfer.files[0]);
  };
  document.getElementById('fileInput').onchange = function(e) {
    if (e.target.files.length > 0) handleFileUpload(e.target.files[0]);
  };
  document.getElementById('btnImportGit').onclick = importGit;
  document.getElementById('btnImportConcept').onclick = importConcept;
}

function switchModalTab(tab) {
  document.querySelectorAll('.modal-tab').forEach(function(b) { b.classList.toggle('active', b.dataset.tab === tab); });
  document.querySelectorAll('.modal-panel').forEach(function(p) { p.classList.toggle('active', p.id === 'panel-' + tab); });
}

async function handleFileUpload(file) {
  var name = document.getElementById('fileName').value || file.name;
  var fd = new FormData();
  fd.append('file', file);
  fd.append('name', name);
  try {
    var r = await fetch(API_BASE + '/projects/import/file', { method: 'POST', body: fd });
    var data = await r.json();
    if (data.success) { closeImportModal(); await loadProjects(); await selectProject(data.project.id); startLearning(data.project.id); }
  } catch(e) { toast('Upload failed: ' + e.message, 'error'); }
}

async function importGit() {
  var url = document.getElementById('gitUrl').value.trim();
  var name = document.getElementById('gitName').value.trim();
  if (!url) { toast('Please enter a Git URL', 'error'); return; }
  try {
    var r = await fetch(API_BASE + '/projects/import/git', {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({ git_url: url, name: name || null })
    });
    var data = await r.json();
    if (data.success) { closeImportModal(); await loadProjects(); await selectProject(data.project.id); startLearning(data.project.id); }
  } catch(e) { toast('Import failed: ' + e.message, 'error'); }
}

async function importConcept() {
  var concept = document.getElementById('conceptText').value.trim();
  var name = document.getElementById('conceptName').value.trim();
  if (!concept) { toast('Please enter a concept', 'error'); return; }
  try {
    var r = await fetch(API_BASE + '/projects/import/concept', {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({ concept: concept, name: name || null })
    });
    var data = await r.json();
    if (data.success) { closeImportModal(); await loadProjects(); await selectProject(data.project.id); startLearning(data.project.id); }
  } catch(e) { toast('Import failed: ' + e.message, 'error'); }
}

async function startLearning(projectId) {
  document.getElementById('contentArea').innerHTML =
    '<div class="loading"><div class="spinner"></div><p>Agent analyzing learning project...</p></div>';
  try {
    var r = await fetch(API_BASE + '/learning/' + projectId + '/start', { method: 'POST' });
    var data = await r.json();
    if (data.success) {
      var result = data.result || {};
      if (result.is_learnable === false) {
        document.getElementById('contentArea').innerHTML =
          '<div class="empty-state"><div class="big-icon">\u{274C}</div><h3>Cannot Learn</h3><p>' +
          esc(result.learnability_reason || 'Not suitable for learning') + '</p></div>';
        await loadProjects(); renderProjectList();
      } else {
        await selectProject(projectId); switchTab('content');
        toast('Learning content generated!', 'success');
      }
    }
  } catch(e) { toast('Learning pipeline failed: ' + e.message, 'error'); showEmptyState(); }
}

async function handleUpdate() {
  if (!APP.currentProject) return;
  var btn = document.getElementById('btnUpdate');
  btn.disabled = true; btn.textContent = 'Updating...';
  try {
    var r = await fetch(API_BASE + '/learning/' + APP.currentProject.id + '/update', { method: 'POST' });
    var data = await r.json();
    toast(data.needs_update ? 'Supplemented ' + data.supplements_count + ' sections' : 'Content is up to date', 'success');
    await selectProject(APP.currentProject.id);
    switchTab('content');
  } catch(e) { toast('Update failed: ' + e.message, 'error'); }
  btn.disabled = false; btn.textContent = '\u{1F504} Update';
}

async function checkUpdateStatus() {
  if (!APP.currentProject) return;
  try {
    var r = await fetch(API_BASE + '/logs/' + APP.currentProject.id + '/check-update');
    var data = await r.json();
    var hint = document.getElementById('updateHint');
    if (data.update_needed) { hint.textContent = '\u{26A0} ' + data.reason; hint.style.display = 'flex'; }
    else { hint.style.display = 'none'; }
  } catch(e) { /* */ }
}

function setupTabs() {
  document.querySelectorAll('.tab-btn').forEach(function(btn) {
    btn.onclick = function() { switchTab(btn.dataset.tab); };
  });
}

function switchTab(tab) {
  APP.currentTab = tab;
  document.querySelectorAll('.tab-btn').forEach(function(b) { b.classList.toggle('active', b.dataset.tab === tab); });
  if (!APP.currentProject) { showEmptyState(); return; }
  switch(tab) { case 'content': renderContent(); break; case 'qa': renderQA(); break; case 'feynman': renderFeynman(); break; case 'logs': renderLogs(); break; }
}

function renderTopBar() {
  document.getElementById('projectTitle').textContent = APP.currentProject ? APP.currentProject.name : 'Study Assistant';
}

function showEmptyState() {
  document.getElementById('projectTitle').textContent = 'Study Assistant';
  document.getElementById('contentArea').innerHTML = '<div class="empty-state"><div class="big-icon">\u{1F4DA}</div><h3>Welcome</h3><p>Click "New Project" to import learning materials.</p></div>';
}

// CONTENT TAB
async function renderContent() {
  var area = document.getElementById('contentArea');
  var p = APP.currentProject;
  if (!p) { showEmptyState(); return; }
  if (p.status === 'pending' || p.status === 'processing') {
    area.innerHTML = '<div class="loading"><div class="spinner"></div><p>Processing...</p></div>'; return;
  }
  if (p.status === 'not_learnable') {
    area.innerHTML = '<div class="empty-state"><div class="big-icon">\u{274C}</div><h3>Not Learnable</h3><p>' + esc(p.learnability_reason || '') + '</p></div>'; return;
  }
  if (!p.learning_content || !p.learning_content.sq3r) {
    area.innerHTML = '<div class="empty-state"><h3>No content yet</h3><p>Learning content has not been generated.</p></div>'; return;
  }

  var c = p.learning_content;
  var sq3r = c.sq3r || {};
  var html = '<h1 style="font-size:1.6rem;margin-bottom:24px;">' + esc(c.title || p.name) + '</h1>';

  if (c.framework && c.framework.structure && c.framework.structure.length > 0) {
    html += '<div class="sq3r-section"><h2>Framework</h2><div class="framework-display">' + renderFrameworkNodes(c.framework.structure, 0) + '</div></div>';
  }
  if (sq3r.survey && sq3r.survey.content) {
    html += '<div class="sq3r-section"><h2>' + esc(sq3r.survey.title || 'Survey') + '</h2><div class="markdown-content">' + simpleMD(sq3r.survey.content) + '</div></div>';
  }
  if (sq3r.question && sq3r.question.questions && sq3r.question.questions.length > 0) {
    html += '<div class="question-box"><h3>Study Questions</h3>';
    if (sq3r.question.guidance) html += '<p style="color:#64748b;margin-bottom:12px;">' + esc(sq3r.question.guidance) + '</p>';
    html += '<ul>' + sq3r.question.questions.map(function(q) { return '<li>' + esc(q) + '</li>'; }).join('') + '</ul></div>';
  }
  if (sq3r.read && sq3r.read.sections && sq3r.read.sections.length > 0) {
    html += '<div class="sq3r-section"><h2>' + esc(sq3r.read.title || 'Read') + '</h2>';
    sq3r.read.sections.forEach(function(s) {
      html += '<h3>' + esc(s.heading || '') + '</h3><div class="markdown-content">' + simpleMD(s.content || '') + '</div>';
    });
    html += '</div>';
  }
  if (sq3r.recite) {
    html += '<div class="sq3r-section"><h2>' + esc(sq3r.recite.title || 'Recite') + '</h2>';
    if (sq3r.recite.key_points && sq3r.recite.key_points.length > 0) {
      html += '<ul>' + sq3r.recite.key_points.map(function(kp) { return '<li><strong>' + esc(kp) + '</strong></li>'; }).join('') + '</ul>';
    }
    if (sq3r.recite.summary) html += '<div class="markdown-content">' + simpleMD(sq3r.recite.summary) + '</div>';
    html += '</div>';
  }
  if (sq3r.review) {
    html += '<div class="sq3r-section"><h2>' + esc(sq3r.review.title || 'Review') + '</h2>';
    if (sq3r.review.suggestions && sq3r.review.suggestions.length > 0) {
      html += '<h3>Suggestions</h3><ul>' + sq3r.review.suggestions.map(function(s) { return '<li>' + esc(s) + '</li>'; }).join('') + '</ul>';
    }
    if (sq3r.review.exercises && sq3r.review.exercises.length > 0) {
      html += '<h3>Exercises</h3><ul>' + sq3r.review.exercises.map(function(e) { return '<li>' + esc(e) + '</li>'; }).join('') + '</ul>';
    }
    html += '</div>';
  }
  if (sq3r.supplements && sq3r.supplements.length > 0) {
    html += '<div class="sq3r-section"><h2>Supplements</h2>';
    sq3r.supplements.forEach(function(s) { html += '<h3>' + esc(s.section || '') + '</h3><div class="markdown-content">' + simpleMD(s.content || '') + '</div>'; });
    html += '</div>';
  }
  area.innerHTML = html;
}

function renderFrameworkNodes(nodes, depth) {
  return nodes.map(function(n) {
    var h = '<div class="framework-node" style="margin-left:' + (depth * 20) + 'px;">';
    h += '<div class="node-title">' + esc(n.title || '') + '</div>';
    if (n.description) h += '<div class="node-desc">' + esc(n.description) + '</div>';
    if (n.children && n.children.length > 0) h += '<div class="framework-children">' + renderFrameworkNodes(n.children, depth + 1) + '</div>';
    h += '</div>'; return h;
  }).join('');
}

// QA TAB
function renderQA() {
  var area = document.getElementById('contentArea');
  area.innerHTML = '<div class="chat-area"><div class="chat-messages" id="qaMessages"><div class="empty-state"><p>Ask a question!</p></div></div><div class="chat-input-area"><input type="text" id="qaInput" placeholder="Enter your question..." onkeydown="if(event.key===\'Enter\')APP.askQuestion()"><button class="btn-primary" id="qaSendBtn">Send</button></div></div>';
  document.getElementById('qaSendBtn').onclick = APP.askQuestion;
  loadQAHistory();
}

async function loadQAHistory() {
  if (!APP.currentProject) return;
  try {
    var r = await fetch(API_BASE + '/qa/' + APP.currentProject.id + '/history');
    var data = await r.json();
    var msgs = document.getElementById('qaMessages');
    if (data.records && data.records.length > 0) {
      msgs.innerHTML = data.records.map(function(rec) {
        return '<div class="chat-msg user"><div class="msg-content">' + esc(rec.question) + '</div></div>' +
          '<div class="chat-msg assistant"><div class="msg-content">' + simpleMD(rec.answer) + '</div><div class="msg-meta">Source: ' + esc(rec.source_type || '') + '</div></div>';
      }).join('');
      msgs.scrollTop = msgs.scrollHeight;
    }
  } catch(e) { /* */ }
}

APP.askQuestion = async function() {
  var input = document.getElementById('qaInput');
  if (!input) return;
  var question = input.value.trim();
  if (!question || !APP.currentProject) return;
  input.value = '';
  var msgs = document.getElementById('qaMessages');
  var emptyEl = msgs.querySelector('.empty-state');
  if (emptyEl) emptyEl.remove();
  msgs.innerHTML += '<div class="chat-msg user"><div class="msg-content">' + esc(question) + '</div></div>';
  msgs.innerHTML += '<div class="chat-msg assistant" id="tmpLoading"><div class="msg-content"><div class="spinner" style="width:20px;height:20px;margin:0;"></div></div></div>';
  msgs.scrollTop = msgs.scrollHeight;
  try {
    var r = await fetch(API_BASE + '/qa/' + APP.currentProject.id + '/ask', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({question: question}) });
    var data = await r.json();
    var tmp = document.getElementById('tmpLoading');
    if (tmp) { tmp.querySelector('.msg-content').innerHTML = simpleMD(data.answer); tmp.innerHTML += '<div class="msg-meta">Source: ' + esc(data.source_type || '') + '</div>'; tmp.removeAttribute('id'); }
    msgs.scrollTop = msgs.scrollHeight;
  } catch(e) {
    var tmpEl = document.getElementById('tmpLoading');
    if (tmpEl) { tmpEl.querySelector('.msg-content').innerHTML = 'Sorry, failed to answer: ' + esc(e.message); tmpEl.removeAttribute('id'); }
  }
};

// FEYNMAN TAB
function renderFeynman() {
  document.getElementById('contentArea').innerHTML = '<div class="feynman-dialogue" id="feynmanDialogue"><div class="empty-state"><h3>Feynman Learning Method</h3><p>AI acts as a curious student. You teach the concepts.</p><button class="btn-primary" id="btnStartFeynman" style="margin-top:16px;">Start Session</button></div></div>';
  document.getElementById('btnStartFeynman').onclick = APP.startFeynman;
}

APP.startFeynman = async function() {
  if (!APP.currentProject) return;
  try {
    var r = await fetch(API_BASE + '/feynman/' + APP.currentProject.id + '/start', { method: 'POST' });
    var data = await r.json();
    APP.feynmanSessionId = data.session_id;
    APP.feynmanRound = data.round || 1;
    var dlg = document.getElementById('feynmanDialogue');
    dlg.innerHTML = buildFeynmanUI(data.question, data.hint);
    var finput = document.getElementById('feynmanInput');
    if (finput) finput.focus();
  } catch(e) { toast('Failed to start: ' + e.message, 'error'); }
};

function buildFeynmanUI(question, hint) {
  return '<div class="feynman-bubble teacher"><div class="avatar">?</div><div class="bubble"><strong>Student (Round ' + APP.feynmanRound + '):</strong><br>' + esc(question) + (hint ? '<br><small style="color:#64748b;">Hint: ' + esc(hint) + '</small>' : '') + '</div></div><div id="feynmanEval"></div><div class="feynman-input-area"><input type="text" id="feynmanInput" placeholder="Explain in your own words..." onkeydown="if(event.key===\'Enter\')APP.submitFeynmanAnswer()"><button class="btn-primary" id="btnFAnswer">Answer</button><button class="btn-confused" id="btnFConfused">I don\'t know</button></div>';
}

function bindFeynmanButtons() {
  var ba = document.getElementById('btnFAnswer');
  var bc = document.getElementById('btnFConfused');
  if (ba) ba.onclick = APP.submitFeynmanAnswer;
  if (bc) bc.onclick = APP.submitFeynmanConfused;
}

APP.submitFeynmanAnswer = async function() {
  var input = document.getElementById('feynmanInput');
  if (!input) return;
  var answer = input.value.trim();
  if (!answer || !APP.feynmanSessionId) return;
  input.value = '';
  var dlg = document.getElementById('feynmanDialogue');
  dlg.innerHTML += '<div class="feynman-bubble user-answer"><div class="bubble">' + esc(answer) + '</div></div>';
  dlg.innerHTML += '<div class="loading" id="feynmanLoading"><div class="spinner" style="width:20px;height:20px;margin:0 auto;"></div></div>';
  try {
    var r = await fetch(API_BASE + '/feynman/' + APP.currentProject.id + '/answer', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({session_id: APP.feynmanSessionId, answer: answer, confused: false}) });
    var data = await r.json();
    removeFeynmanLoading();
    if (data.session_completed) { dlg.innerHTML += buildCompletionCard(data); APP.feynmanSessionId = null; generateLog(); }
    else {
      if (data.correction) dlg.innerHTML += '<div class="evaluation-card"><p><strong>Feedback:</strong> ' + esc(data.correction) + '</p></div>';
      APP.feynmanRound = data.round || (APP.feynmanRound + 1);
      dlg.innerHTML += buildFeynmanUI(data.next_question, data.hint);
      bindFeynmanButtons();
      var finput = document.getElementById('feynmanInput'); if (finput) finput.focus();
    }
  } catch(e) { removeFeynmanLoading(); toast('Submit failed: ' + e.message, 'error'); }
};

APP.submitFeynmanConfused = async function() {
  var dlg = document.getElementById('feynmanDialogue');
  dlg.innerHTML += '<div class="feynman-bubble user-answer"><div class="bubble" style="background:#fef3c7;color:#92400e;">I\'m not sure about this...</div></div>';
  dlg.innerHTML += '<div class="loading" id="feynmanLoading"><div class="spinner" style="width:20px;height:20px;margin:0 auto;"></div></div>';
  try {
    var r = await fetch(API_BASE + '/feynman/' + APP.currentProject.id + '/answer', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({session_id: APP.feynmanSessionId, answer: 'I don\'t know', confused: true}) });
    var data = await r.json();
    removeFeynmanLoading();
    if (data.correction) dlg.innerHTML += '<div class="evaluation-card"><p><strong>Explanation:</strong> ' + esc(data.correction) + '</p></div>';
    if (data.next_question) {
      APP.feynmanRound = data.round || (APP.feynmanRound + 1);
      dlg.innerHTML += buildFeynmanUI(data.next_question, data.hint);
      bindFeynmanButtons();
      var finput = document.getElementById('feynmanInput'); if (finput) finput.focus();
    }
  } catch(e) { removeFeynmanLoading(); toast('Submit failed: ' + e.message, 'error'); }
};

function removeFeynmanLoading() { var el = document.getElementById('feynmanLoading'); if (el) el.remove(); }

function buildCompletionCard(data) {
  return '<div class="evaluation-card"><h3>Session Complete</h3><p>' + esc(data.overall_assessment || '') + '</p>' + (data.weak_points || []).map(function(w) { return '<p class="eval-weak">\u{25CF} ' + esc(w) + '</p>'; }).join('') + '</div>';
}

// LOGS TAB
async function renderLogs() {
  if (!APP.currentProject) return;
  var area = document.getElementById('contentArea');
  area.innerHTML = '<div class="loading"><div class="spinner"></div></div>';
  try {
    var r = await fetch(API_BASE + '/logs/' + APP.currentProject.id);
    var data = await r.json();
    if (!data.logs || data.logs.length === 0) { area.innerHTML = '<div class="empty-state"><h3>No logs yet</h3><p>Logs are generated after Q&A or Feynman sessions.</p></div>'; return; }
    area.innerHTML = '<div class="log-timeline">' + data.logs.map(function(l) {
      return '<div class="log-entry"><div class="log-date">' + esc(l.log_date || '') + ' | Sessions: ' + (l.session_count || 0) + '</div>' +
        (l.knowledge_summary ? '<div class="log-section"><h4>Knowledge Summary</h4><div class="markdown-content">' + simpleMD(l.knowledge_summary) + '</div></div>' : '') +
        (l.weak_points ? '<div class="log-section"><h4>Weak Points</h4><div class="markdown-content">' + simpleMD(l.weak_points) + '</div></div>' : '') + '</div>';
    }).join('') + '</div><button class="btn-primary" id="btnGenLog" style="margin-top:16px;">Generate Today\'s Log</button>';
    document.getElementById('btnGenLog').onclick = generateLog;
  } catch(e) { area.innerHTML = '<div class="empty-state"><p>Failed to load logs</p></div>'; }
}

async function generateLog() {
  if (!APP.currentProject) return;
  try {
    var r = await fetch(API_BASE + '/logs/' + APP.currentProject.id + '/generate', { method: 'POST' });
    var data = await r.json();
    toast(data.message || 'Log generated', 'success');
    if (APP.currentTab === 'logs') renderLogs();
  } catch(e) { toast('Failed: ' + e.message, 'error'); }
}

// UTILS
function esc(s) { if (!s) return ''; var d = document.createElement('div'); d.textContent = s; return d.innerHTML; }

function simpleMD(text) {
  if (!text) return '';
  var h = esc(text);
  h = h.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
  h = h.replace(/\*(.+?)\*/g, '<em>$1</em>');
  h = h.replace(/`([^`]+)`/g, '<code>$1</code>');
  h = h.replace(/^### (.+)$/gm, '<h3>$1</h3>');
  h = h.replace(/^## (.+)$/gm, '<h2>$1</h2>');
  h = h.replace(/^# (.+)$/gm, '<h1>$1</h1>');
  h = h.replace(/^[\-\*] (.+)$/gm, '<li>$1</li>');
  h = h.replace(/((?:<li>.*<\/li>\n?)+)/g, '<ul>$1</ul>');
  h = h.replace(/```([\s\S]*?)```/g, '<pre><code>$1</code></pre>');
  h = h.split('\n\n').map(function(p) { return '<p>' + p + '</p>'; }).join('');
  h = h.replace(/<p>\s*<\/p>/g, '');
  return h;
}

function toast(msg, type) {
  var t = document.createElement('div');
  t.className = 'toast ' + (type || 'success');
  t.textContent = msg;
  document.body.appendChild(t);
  setTimeout(function() { t.remove(); }, 3000);
}

document.addEventListener('DOMContentLoaded', init);
})();
