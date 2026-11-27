/**
 * DocuMind — SPA JavaScript client
 * Communicates with the FastAPI RAG backend at the same origin.
 */

const API = '';  // same-origin; prefix all fetch calls with this

// ── State ──────────────────────────────────────────────────────────────────
const state = {
  documents: [],         // [{document_id, filename, file_type, chunk_count, page_count, ...}]
  selectedDocIds: new Set(),
  scopeEnabled: false,
  authToken: localStorage.getItem('dm_token') || null,
  currentUser: null,
  isSignup: false,
  thinking: false,
};

// ── DOM refs ───────────────────────────────────────────────────────────────
const $ = id => document.getElementById(id);

const els = {
  fileInput:       $('file-input'),
  dropzone:        $('dropzone'),
  docList:         $('doc-list'),
  docEmpty:        $('doc-empty'),
  docCount:        $('doc-count'),
  uploadProgress:  $('upload-progress'),
  progressFill:    $('progress-fill'),
  progressLabel:   $('progress-label'),
  scopeSection:    $('scope-section'),
  scopeToggle:     $('scope-toggle'),
  scopeList:       $('scope-list'),
  chatMessages:    $('chat-messages'),
  welcomeScreen:   $('welcome-screen'),
  questionInput:   $('question-input'),
  sendBtn:         $('send-btn'),
  sendIcon:        $('send-icon'),
  sendSpinner:     $('send-spinner'),
  charCount:       $('char-count'),
  latencyBadge:    $('latency-badge'),
  modelBadge:      $('model-badge'),
  chunksList:      $('chunks-list'),
  metricsBtn:      $('metrics-btn'),
  metricsModal:    $('metrics-modal'),
  closeMetrics:    $('close-metrics'),
  authBtn:         $('auth-btn'),
  authModal:       $('auth-modal'),
  closeAuth:       $('close-auth'),
  authForm:        $('auth-form'),
  authEmail:       $('auth-email'),
  authPassword:    $('auth-password'),
  authUsername:    $('auth-username'),
  authSubmit:      $('auth-submit'),
  authError:       $('auth-error'),
  authSuccess:     $('auth-success'),
  authSuccessMsg:  $('auth-success-msg'),
  authToggle:      $('auth-toggle'),
  authSwitchText:  $('auth-switch-text'),
  authModalTitle:  $('auth-modal-title'),
  usernameGroup:   $('username-group'),
};

// ── Helpers ────────────────────────────────────────────────────────────────
function authHeaders() {
  const h = { 'Content-Type': 'application/json' };
  if (state.authToken) h['Authorization'] = `Bearer ${state.authToken}`;
  return h;
}

function fileIcon(type) {
  const map = { pdf: '📕', docx: '📘', txt: '📄', md: '📝', pptx: '📊' };
  return map[type?.toLowerCase()] || '📄';
}

function fmtBytes(b) {
  if (b < 1024) return `${b} B`;
  if (b < 1048576) return `${(b/1024).toFixed(1)} KB`;
  return `${(b/1048576).toFixed(1)} MB`;
}

function fmtDate(iso) {
  const d = new Date(iso);
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
}

function scoreClass(s) {
  if (s >= 0.75) return 'score-high';
  if (s >= 0.5)  return 'score-mid';
  return 'score-low';
}

function escHtml(s) {
  return String(s)
    .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
    .replace(/"/g,'&quot;');
}

// ── Document list ──────────────────────────────────────────────────────────
async function loadDocuments() {
  try {
    const r = await fetch(`${API}/api/documents`, { headers: authHeaders() });
    if (!r.ok) return;
    const data = await r.json();
    state.documents = data.documents || [];
    renderDocList();
  } catch (_) {}
}

function renderDocList() {
  const docs = state.documents;
  els.docCount.textContent = docs.length;
  els.docEmpty.style.display = docs.length ? 'none' : '';
  els.scopeSection.style.display = docs.length ? '' : 'none';

  // Keep existing items; rebuild cleanly
  Array.from(els.docList.children).forEach(c => { if (c !== els.docEmpty) c.remove(); });

  docs.forEach(doc => {
    const item = document.createElement('div');
    item.className = 'doc-item';
    item.dataset.id = doc.document_id;
    if (state.selectedDocIds.has(doc.document_id)) item.classList.add('selected');

    item.innerHTML = `
      <span class="doc-icon">${fileIcon(doc.file_type)}</span>
      <div class="doc-info">
        <div class="doc-name" title="${escHtml(doc.filename)}">${escHtml(doc.filename)}</div>
        <div class="doc-meta">${doc.chunk_count} chunks · ${fmtBytes(doc.file_size_bytes)}</div>
      </div>
      <button class="doc-delete" data-id="${doc.document_id}" title="Delete document">🗑</button>
    `;
    item.querySelector('.doc-delete').addEventListener('click', e => {
      e.stopPropagation();
      deleteDocument(doc.document_id, doc.filename);
    });
    item.addEventListener('click', () => toggleDocSelect(doc.document_id, item));
    els.docList.appendChild(item);
  });

  renderScopeList();
}

function toggleDocSelect(id, el) {
  if (state.selectedDocIds.has(id)) {
    state.selectedDocIds.delete(id);
    el.classList.remove('selected');
  } else {
    state.selectedDocIds.add(id);
    el.classList.add('selected');
  }
  renderScopeList();
}

function renderScopeList() {
  els.scopeList.innerHTML = '';
  if (!state.scopeEnabled) return;
  state.documents.forEach(doc => {
    const label = document.createElement('label');
    label.className = 'scope-item';
    label.innerHTML = `
      <input type="checkbox" value="${doc.document_id}" ${state.selectedDocIds.has(doc.document_id) ? 'checked' : ''} />
      ${escHtml(doc.filename)}
    `;
    label.querySelector('input').addEventListener('change', e => {
      e.target.checked ? state.selectedDocIds.add(doc.document_id) : state.selectedDocIds.delete(doc.document_id);
    });
    els.scopeList.appendChild(label);
  });
}

// ── Upload ─────────────────────────────────────────────────────────────────
async function uploadFiles(files) {
  if (!files.length) return;
  const show = msg => {
    els.uploadProgress.classList.remove('hidden');
    els.progressLabel.textContent = msg;
  };
  const setProgress = pct => { els.progressFill.style.width = `${pct}%`; };

  for (let i = 0; i < files.length; i++) {
    const file = files[i];
    show(`Uploading ${file.name} (${i+1}/${files.length})…`);
    setProgress(((i / files.length) * 100));

    const fd = new FormData();
    fd.append('file', file);
    try {
      const r = await fetch(`${API}/api/documents/upload`, {
        method: 'POST',
        headers: state.authToken ? { Authorization: `Bearer ${state.authToken}` } : {},
        body: fd,
      });
      const data = await r.json();
      if (r.status === 201) {
        showToast(`✅ ${file.name} ingested (${data.document.chunk_count} chunks)`);
      } else if (r.status === 409) {
        showToast(`⚠️ ${file.name} already uploaded`, 'warn');
      } else {
        showToast(`❌ ${file.name}: ${data.detail || r.status}`, 'error');
      }
    } catch (err) {
      showToast(`❌ Upload failed: ${err.message}`, 'error');
    }
  }
  setProgress(100);
  show('Done!');
  setTimeout(() => els.uploadProgress.classList.add('hidden'), 1200);
  await loadDocuments();
}

// ── Delete ─────────────────────────────────────────────────────────────────
async function deleteDocument(id, name) {
  if (!confirm(`Delete "${name}"? This will remove all its vectors.`)) return;
  try {
    const r = await fetch(`${API}/api/documents/${id}`, {
      method: 'DELETE',
      headers: authHeaders(),
    });
    if (r.status === 204) {
      state.selectedDocIds.delete(id);
      showToast(`🗑 ${name} deleted`);
      await loadDocuments();
    } else {
      const d = await r.json();
      showToast(`❌ ${d.detail || 'Delete failed'}`, 'error');
    }
  } catch (err) {
    showToast(`❌ ${err.message}`, 'error');
  }
}

// ── Chat ───────────────────────────────────────────────────────────────────
function showWelcome(visible) {
  els.welcomeScreen.style.display = visible ? '' : 'none';
  els.chatMessages.style.display  = visible ? 'none' : '';
}

function appendMessage(role, html, opts = {}) {
  showWelcome(false);
  const wrap = document.createElement('div');
  wrap.className = `message ${role}${opts.abstained ? ' abstained' : ''}${opts.error ? ' error' : ''}`;

  const avatar = document.createElement('div');
  avatar.className = 'msg-avatar';
  avatar.textContent = role === 'user' ? '👤' : '🤖';

  const body = document.createElement('div');
  body.className = 'msg-body';

  const bubble = document.createElement('div');
  bubble.className = 'msg-bubble';
  bubble.innerHTML = html;
  body.appendChild(bubble);

  if (opts.citations?.length) {
    const pills = document.createElement('div');
    pills.className = 'msg-citations';
    opts.citations.forEach(c => {
      const p = document.createElement('span');
      p.className = 'citation-pill';
      p.textContent = `${c.filename} · ${c.page_or_section}`;
      p.title = `Chunk ${c.chunk_id}`;
      pills.appendChild(p);
    });
    body.appendChild(pills);
  }

  if (opts.meta) {
    const m = document.createElement('div');
    m.className = 'msg-meta';
    m.textContent = opts.meta;
    body.appendChild(m);
  }

  wrap.appendChild(avatar);
  wrap.appendChild(body);
  els.chatMessages.appendChild(wrap);
  els.chatMessages.scrollTop = els.chatMessages.scrollHeight;
  return wrap;
}

function appendThinking() {
  showWelcome(false);
  const wrap = document.createElement('div');
  wrap.className = 'message assistant';
  wrap.id = 'thinking-bubble';
  wrap.innerHTML = `
    <div class="msg-avatar">🤖</div>
    <div class="msg-body">
      <div class="thinking"><div class="dot"></div><div class="dot"></div><div class="dot"></div></div>
    </div>`;
  els.chatMessages.appendChild(wrap);
  els.chatMessages.scrollTop = els.chatMessages.scrollHeight;
  return wrap;
}

function removeThinking() {
  const t = $('thinking-bubble');
  if (t) t.remove();
}

function renderChunks(chunks) {
  if (!chunks?.length) {
    els.chunksList.innerHTML = '<div class="empty-state">No chunks retrieved.</div>';
    return;
  }
  els.chunksList.innerHTML = '';
  chunks.forEach((c, i) => {
    const pct = Math.round(c.similarity_score * 100);
    const cls = scoreClass(c.similarity_score);
    const card = document.createElement('div');
    card.className = 'chunk-card';
    card.innerHTML = `
      <div class="chunk-header">
        <span class="chunk-score ${cls}">${pct}%</span>
        <span class="chunk-source">${escHtml(c.filename)} · ${escHtml(c.page_or_section)}</span>
      </div>
      <div class="chunk-text">${escHtml(c.text)}</div>
    `;
    els.chunksList.appendChild(card);
  });
}

async function sendQuestion() {
  const q = els.questionInput.value.trim();
  if (!q || state.thinking) return;

  appendMessage('user', escHtml(q));
  els.questionInput.value = '';
  els.charCount.textContent = '0 / 1000';
  autoResizeTextarea();

  state.thinking = true;
  els.sendBtn.disabled = true;
  els.sendIcon.classList.add('hidden');
  els.sendSpinner.classList.remove('hidden');

  const thinkEl = appendThinking();

  const body = { question: q };
  if (state.scopeEnabled && state.selectedDocIds.size) {
    body.document_ids = [...state.selectedDocIds];
  }

  try {
    const r = await fetch(`${API}/api/chat/ask`, {
      method: 'POST',
      headers: authHeaders(),
      body: JSON.stringify(body),
    });

    removeThinking();
    const data = await r.json();

    if (!r.ok) {
      const detail = typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail);
      appendMessage('assistant', `⚠️ ${escHtml(detail)}`, { error: true });
      renderChunks([]);
      return;
    }

    // Update latency badge
    const ms = data.latency_ms || 0;
    els.latencyBadge.textContent = `${ms.toFixed(0)} ms`;
    els.latencyBadge.classList.remove('hidden');

    // Model badge
    if (data.model_used) els.modelBadge.textContent = data.model_used;

    // Render answer
    const metaStr = `${ms.toFixed(0)} ms · ${data.retrieved_count} chunks · req ${data.request_id}`;
    appendMessage(
      'assistant',
      `<span style="white-space:pre-wrap">${escHtml(data.answer)}</span>`,
      {
        abstained: !data.answered,
        citations: data.citations,
        meta: metaStr,
      }
    );

    // Render chunks panel
    renderChunks(data.retrieved_chunks);

  } catch (err) {
    removeThinking();
    appendMessage('assistant', `❌ Network error: ${escHtml(err.message)}`, { error: true });
  } finally {
    state.thinking = false;
    els.sendBtn.disabled = false;
    els.sendIcon.classList.remove('hidden');
    els.sendSpinner.classList.add('hidden');
  }
}

// ── Metrics ────────────────────────────────────────────────────────────────
async function openMetrics() {
  els.metricsModal.classList.remove('hidden');
  try {
    const r = await fetch(`${API}/api/metrics/summary`, { headers: authHeaders() });
    if (!r.ok) { $('metrics-content').innerHTML = '<p style="color:var(--text-muted)">Metrics unavailable.</p>'; return; }
    const d = await r.json();
    $('m-total').textContent   = d.total_requests;
    $('m-ask').textContent     = d.ask_requests;
    $('m-err').textContent     = `${(d.error_rate * 100).toFixed(1)}%`;
    $('m-p50').textContent     = `${d.p50_latency_ms} ms`;
    $('m-p95').textContent     = `${d.p95_latency_ms} ms`;
    $('m-tokens').textContent  = (d.total_prompt_tokens + d.total_completion_tokens).toLocaleString();
    $('m-cost').textContent    = `$${d.total_estimated_cost_usd.toFixed(6)}`;

    const tbody = $('traces-body');
    tbody.innerHTML = '';
    (d.recent_traces || []).forEach(t => {
      const ok = t.status_code < 400;
      const tr = document.createElement('tr');
      tr.innerHTML = `
        <td>${escHtml(t.endpoint)}</td>
        <td class="${ok ? 'status-ok' : 'status-err'}">${t.status_code}</td>
        <td>${t.latency_ms} ms</td>
        <td>${t.prompt_tokens + t.completion_tokens}</td>
        <td>${fmtDate(t.created_at)}</td>
      `;
      tbody.appendChild(tr);
    });
  } catch (err) {
    $('metrics-content').innerHTML = `<p style="color:var(--danger)">Error: ${escHtml(err.message)}</p>`;
  }
}

// ── Auth ───────────────────────────────────────────────────────────────────
function openAuth() {
  els.authModal.classList.remove('hidden');
  els.authError.classList.add('hidden');
  els.authSuccess.classList.add('hidden');
  els.authForm.style.display = '';
  els.authEmail.value = '';
  els.authPassword.value = '';
  els.authUsername.value = '';
  updateAuthMode();
}

function updateAuthMode() {
  els.usernameGroup.style.display = state.isSignup ? '' : 'none';
  els.authModalTitle.textContent   = state.isSignup ? '📝 Sign Up' : '🔐 Sign In';
  els.authSubmit.textContent       = state.isSignup ? 'Create Account' : 'Sign In';
  els.authSwitchText.textContent   = state.isSignup ? 'Already have an account?' : "Don't have an account?";
  els.authToggle.textContent       = state.isSignup ? 'Sign In' : 'Sign Up';
}

async function submitAuth(e) {
  e.preventDefault();
  els.authError.classList.add('hidden');
  const endpoint = state.isSignup ? '/api/auth/signup' : '/api/auth/login';
  const body     = {
    email:    els.authEmail.value,
    password: els.authPassword.value,
    ...(state.isSignup ? { username: els.authUsername.value } : {}),
  };
  try {
    const r    = await fetch(`${API}${endpoint}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
    const data = await r.json();
    if (!r.ok) {
      els.authError.textContent = data.detail || 'Authentication failed.';
      els.authError.classList.remove('hidden');
      return;
    }
    state.authToken    = data.access_token;
    state.currentUser  = data.user;
    localStorage.setItem('dm_token', state.authToken);
    els.authBtn.textContent = `👤 ${data.user.username}`;
    els.authForm.style.display = 'none';
    els.authSuccess.classList.remove('hidden');
    els.authSuccessMsg.textContent = `Welcome, ${data.user.username}!`;
    setTimeout(() => els.authModal.classList.add('hidden'), 1800);
    await loadDocuments();
  } catch (err) {
    els.authError.textContent = err.message;
    els.authError.classList.remove('hidden');
  }
}

// ── Toast ──────────────────────────────────────────────────────────────────
function showToast(msg, type = 'info') {
  const t = document.createElement('div');
  const colors = { info: '#22c55e', warn: '#f59e0b', error: '#ef4444' };
  Object.assign(t.style, {
    position: 'fixed', bottom: '20px', right: '20px',
    background: '#1a1e2e', border: `1px solid ${colors[type] || colors.info}`,
    color: '#f1f5f9', padding: '10px 16px', borderRadius: '8px',
    fontSize: '0.82rem', zIndex: '9999', maxWidth: '320px',
    animation: 'slideUp 0.2s ease', boxShadow: '0 4px 16px rgba(0,0,0,0.5)',
  });
  t.textContent = msg;
  document.body.appendChild(t);
  setTimeout(() => t.remove(), 3200);
}

// ── Textarea auto-resize ───────────────────────────────────────────────────
function autoResizeTextarea() {
  const ta = els.questionInput;
  ta.style.height = 'auto';
  ta.style.height = `${Math.min(ta.scrollHeight, 160)}px`;
}

// ── Helper: set question from chip ────────────────────────────────────────
function setQuestion(text) {
  els.questionInput.value = text;
  els.questionInput.focus();
  autoResizeTextarea();
  updateCharCount();
}
window.setQuestion = setQuestion;

function updateCharCount() {
  const len = els.questionInput.value.length;
  els.charCount.textContent = `${len} / 1000`;
  els.charCount.classList.toggle('warn', len > 850);
}

// ── Drag & drop ────────────────────────────────────────────────────────────
function setupDropzone() {
  els.dropzone.addEventListener('click', () => els.fileInput.click());
  els.fileInput.addEventListener('change', e => uploadFiles([...e.target.files]));

  ['dragenter','dragover'].forEach(ev => {
    els.dropzone.addEventListener(ev, e => { e.preventDefault(); els.dropzone.classList.add('drag-over'); });
  });
  ['dragleave','drop'].forEach(ev => {
    els.dropzone.addEventListener(ev, e => { e.preventDefault(); els.dropzone.classList.remove('drag-over'); });
  });
  els.dropzone.addEventListener('drop', e => {
    const files = [...e.dataTransfer.files];
    uploadFiles(files);
  });
}

// ── Event wiring ───────────────────────────────────────────────────────────
function init() {
  setupDropzone();
  showWelcome(true);

  els.questionInput.addEventListener('input', () => { autoResizeTextarea(); updateCharCount(); });
  els.questionInput.addEventListener('keydown', e => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendQuestion(); }
  });
  els.sendBtn.addEventListener('click', sendQuestion);

  els.scopeToggle.addEventListener('change', e => {
    state.scopeEnabled = e.target.checked;
    renderScopeList();
  });

  els.metricsBtn.addEventListener('click', openMetrics);
  els.closeMetrics.addEventListener('click', () => els.metricsModal.classList.add('hidden'));
  els.metricsModal.addEventListener('click', e => { if (e.target === els.metricsModal) els.metricsModal.classList.add('hidden'); });

  els.authBtn.addEventListener('click', openAuth);
  els.closeAuth.addEventListener('click', () => els.authModal.classList.add('hidden'));
  els.authModal.addEventListener('click', e => { if (e.target === els.authModal) els.authModal.classList.add('hidden'); });
  els.authToggle.addEventListener('click', () => { state.isSignup = !state.isSignup; updateAuthMode(); els.authError.classList.add('hidden'); });
  els.authForm.addEventListener('submit', submitAuth);

  // Load documents on start
  loadDocuments();
}

document.addEventListener('DOMContentLoaded', init);
