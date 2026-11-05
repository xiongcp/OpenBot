import { emptyTrace, mergeTrace, effectStage, totals } from './projection.js';
import { translate } from './i18n.js';

const $ = id => document.getElementById(id);
let locale = 'zh-CN', snapshot = null, selectedTask = null, selectedEvent = null;
let trace = emptyTrace(), view = 'runs', connected = false, polling = false, busy = false;
let preview = null, settingsDirty = false, renderedSettingsRevision = null, renderKey = '';
const t = key => translate(locale, key);
const text = (id, value) => { $(id).textContent = value ?? '—'; };
const el = (tag, value, cls) => { const node = document.createElement(tag); if (value != null) node.textContent = value; if (cls) node.className = cls; return node; };
const invoke = (command, args = {}) => {
  if (!globalThis.__TAURI__?.core?.invoke) return Promise.reject(Error('NATIVE_CLIENT_REQUIRED'));
  return globalThis.__TAURI__.core.invoke(command, args);
};
function banner(message) { text('banner', message); $('banner').hidden = !message; }
function localize() {
  document.documentElement.lang = locale;
  document.querySelectorAll('[data-i18n]').forEach(node => { node.textContent = t(node.dataset.i18n); });
}
function mutationState() {
  document.querySelectorAll('[data-mutation]').forEach(node => { node.disabled = !connected || busy; });
}
async function action(fn) {
  if (busy || !connected) return;
  busy = true; mutationState();
  try { banner(''); await fn(); await refresh(true); }
  catch (error) { banner(`${t(String(error).includes('CONFLICT') ? 'stale' : 'failed')} · ${String(error).slice(0, 100)}`); }
  finally { busy = false; mutationState(); }
}
function selectTask(id) { if (selectedTask === id) return; selectedTask = id; selectedEvent = null; trace = emptyTrace(); renderKey = ''; render(true); refresh(); }
function switchView(next) {
  view = next;
  document.querySelectorAll('.view').forEach(node => { node.hidden = node.id !== `view-${view}`; });
  document.querySelectorAll('.nav').forEach(node => node.classList.toggle('active', node.dataset.view === view));
  render(true);
}
function renderGraph() {
  const graph = $('graph'); graph.replaceChildren();
  $('timeline-list').replaceChildren();
  if (!trace.events.length) { graph.append(el('p', t(selectedTask && !trace.runId ? 'legacy' : 'noTrace'), 'graph-empty')); graph.style.height = '300px'; return; }
  const width = Math.max(570, $('graph-scroll').clientWidth), columns = 3, card = 164;
  const gap = (width - columns * card) / 4, rowHeight = 100;
  const points = new Map();
  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  const defs = document.createElementNS(svg.namespaceURI, 'defs'), marker = document.createElementNS(svg.namespaceURI, 'marker'), arrow = document.createElementNS(svg.namespaceURI, 'path');
  marker.setAttribute('id', 'causal-arrow'); marker.setAttribute('viewBox', '0 0 8 8'); marker.setAttribute('refX', '8'); marker.setAttribute('refY', '4'); marker.setAttribute('markerWidth', '5'); marker.setAttribute('markerHeight', '5'); marker.setAttribute('orient', 'auto'); arrow.setAttribute('d', 'M0 0 L8 4 L0 8'); arrow.setAttribute('fill', '#9bb58e'); marker.append(arrow); defs.append(marker); svg.append(defs);
  svg.setAttribute('width', width); svg.setAttribute('height', Math.ceil(trace.events.length / 3) * rowHeight + 20); graph.append(svg);
  trace.events.forEach((event, i) => {
    const row = Math.floor(i / columns), col = row % 2 ? 2 - i % 3 : i % 3;
    points.set(event.event_id, { x: gap + col * (card + gap), y: 22 + row * rowHeight });
  });
  for (const event of trace.events) {
    const p = points.get(event.parent_event_id), q = points.get(event.event_id);
    if (!p || !q) continue;
    const line = document.createElementNS(svg.namespaceURI, 'path');
    let path;
    if (p.y === q.y) { const forward = p.x < q.x; path = `M ${p.x + (forward ? card : 0)} ${p.y + 33} L ${q.x + (forward ? 0 : card)} ${q.y + 33}`; }
    else path = `M ${p.x + card / 2} ${p.y + 66} L ${q.x + card / 2} ${q.y}`;
    line.setAttribute('marker-end', 'url(#causal-arrow)'); line.setAttribute('d', path); line.setAttribute('fill', 'none'); line.setAttribute('stroke', '#b2c8a6'); line.setAttribute('stroke-width', '1.3'); svg.append(line);
  }
  trace.events.forEach((event, i) => {
    const p = points.get(event.event_id), node = el('button', null, `graph-node ${effectStage(event)}`);
    node.style.left = `${p.x}px`; node.style.top = `${p.y}px`;
    node.classList.toggle('active', event.event_id === selectedEvent);
    node.append(el('span', `STEP ${String(i + 1).padStart(2, '0')}`, 'ordinal'), el('strong', t(event.kind)), el('small', event.kind === 'WAITING_APPROVAL' ? '◇' : '•'));
    node.addEventListener('click', () => { selectedEvent = event.event_id; renderGraph(); renderDetails(); }); graph.append(node);
    const item = el('li'), button = el('button', `${new Date(event.occurred_at_ms).toLocaleTimeString()} · ${t(event.kind)}`);
    button.addEventListener('click', () => { selectedEvent = event.event_id; renderGraph(); renderDetails(); }); item.append(button); $('timeline-list').append(item);
  });
  graph.style.height = `${Math.ceil(trace.events.length / 3) * rowHeight + 20}px`;
}
function renderDetails() {
  const target = $('details'); target.replaceChildren();
  const event = trace.events.find(e => e.event_id === selectedEvent);
  if (!event) { target.append(el('p', t('detailsHint'))); return; }
  target.append(el('div', t(effectStage(event)), 'detail-tag'), el('h3', t(event.kind)));
  const list = el('dl');
  for (const [key, value] of Object.entries({ event_id: event.event_id, run_id: event.run_id, config_revision: event.config_revision, parent_event_id: event.parent_event_id, ...event.data })) {
    if (value == null || key === 'text') continue;
    list.append(el('dt', t(key)), el('dd', String(value)));
  }
  target.append(list);
  if (event.data.text) target.append(el('pre', event.data.text));
}
function renderPairing() {
  const info = snapshot?.feishu, target = $('feishu-candidates'); target.replaceChildren();
  text('feishu-stage', `${info?.app_id || '—'} · ${t(info?.stage || 'NOT_CONNECTED')}`);
  if (!info?.candidates?.length) target.append(el('p', t('noCandidates'), 'muted'));
  for (const candidate of info?.candidates || []) {
    const card = el('article', null, 'approval-card'), list = el('dl');
    for (const key of ['tenant_key','app_id','open_id','chat_id']) list.append(el('dt',t(key)),el('dd',candidate[key]));
    const confirm = el('button',t('confirmPair'),'primary'); confirm.dataset.mutation = '';
    confirm.addEventListener('click', () => action(() => invoke('client_confirm_pair', { candidateId: candidate.candidate_id })));
    card.append(list,confirm); target.append(card);
  }
}
function renderApprovals() {
  const list = $('approvals-list'); list.replaceChildren();
  const approvals = snapshot?.approvals?.approvals || [];
  if (!approvals.length) list.append(el('p', t('noApprovals'), 'muted'));
  approvals.forEach(approval => {
    const card = el('article', null, 'panel approval-card');
    card.append(el('h2', approval.tool_name), el('p', `${t('effect')}: ${approval.effect} · ${approval.data_class}`), el('p', approval.destination_summary), el('pre', approval.args_preview), el('p', approval.binding_hash));
    const expired = Date.now() >= approval.expires_at_ms, controls = el('div', null, 'approval-actions');
    for (const decision of ['APPROVE','DENY']) {
      const button = el('button', t(expired ? 'expired' : decision === 'APPROVE' ? 'approve' : 'deny'), decision === 'APPROVE' ? 'primary' : 'secondary');
      button.disabled = expired || busy || !connected;
      button.addEventListener('click', () => action(async () => { await invoke('client_decide', { approvalId: approval.approval_id, decision, expectedVersion: approval.version, bindingHash: approval.binding_hash }); }));
      controls.append(button);
    }
    card.append(controls); list.append(card);
  });
}
function renderSettings() {
  if (!snapshot) return;
  const settings = snapshot.settings, form = $('settings-form');
  text('settings-revision', `${t('revision')} ${settings.revision}`);
  if (settingsDirty || renderedSettingsRevision === settings.revision) return;
  for (const [key, value] of Object.entries(settings.config)) {
    const input = form.elements.namedItem(key);
    if (typeof value === 'boolean') input.checked = value; else input.value = value;
  }
  renderedSettingsRevision = settings.revision;
}
function renderInventory() {
  const list = $('inventory-list'); list.replaceChildren();
  for (const [name, enabled, used, description] of [
    ['demo-summary · 1.0.0', snapshot?.settings.config.skill_enabled, trace.events.some(e => e.kind === 'SKILL_LOADED'), 'PROJECT_SOURCE · read-only instruction'],
    ['openbot-demo-read · 1.0.0', snapshot?.settings.config.mcp_enabled, trace.events.some(e => e.kind === 'TOOL_DISPATCHED'), 'JSON-RPC · pinned image · network=none · demo.txt'],
  ]) {
    const card = el('article', null, 'panel inventory-card'), tags = el('div', null, 'tags');
    tags.append(el('span', t('admitted')), el('span', t(enabled ? 'enabled' : 'disabled')), el('span', t(used ? 'used' : 'notUsed')));
    card.append(el('h2', name), el('p', description), tags); list.append(card);
  }
}
function render(force = false) {
  const key = JSON.stringify([locale, selectedTask, selectedEvent, trace.lastSeq, snapshot, connected]);
  if (!force && key === renderKey) return; renderKey = key;
  localize(); mutationState();
  const runs = snapshot?.runs?.runs || [], run = runs.find(r => r.task_id === selectedTask);
  const taskList = $('task-list'); taskList.replaceChildren();
  for (const item of runs) {
    const button = el('button', null, `task-item${item.task_id === selectedTask ? ' selected' : ''}`);
    button.append(el('strong', item.goal), el('small', t(item.state))); button.addEventListener('click', () => selectTask(item.task_id)); taskList.append(button);
  }
  text('run-title', run?.goal || t('empty'));
  text('run-subtitle', run ? `${t('revision')} ${run.config_revision ?? '—'} · ${trace.events.find(e => e.kind === 'MODEL_REQUESTED')?.data.model || '—'}` : t('emptyHelp'));
  text('run-state', run ? t(run.state) : '—'); text('run-id', run?.run_id || '—');
  $('start-task').hidden = !run || run.state !== 'QUEUED' || !!run.run_id;
  renderPairing();
  $('cancel-task').hidden = !run || ['SUCCEEDED','FAILED','CANCELLED','PARTIAL'].includes(run.state);
  text('run-notice', run?.state === 'RECONCILING' ? t('unknown') : trace.missingParents.length ? t('missing') : t('reconcile'));
  $('run-notice').hidden = !run?.requires_reconciliation && !trace.missingParents.length && run?.state !== 'RECONCILING';
  const n = totals(trace.events); text('token-total', trace.events.length ? (n.input + n.output).toLocaleString() : '—');
  text('token-split', n.estimated ? t('estimate') : `${t('input')} ${n.input} / ${t('output')} ${n.output}`); text('tool-total', n.calls); text('event-count', trace.events.length);
  const health = snapshot?.health || {}, healthList = $('health-list'); healthList.replaceChildren();
  for (const [name, ready] of [['daemon',connected],['model',health.credentials_configured],['isolation',health.executor_available],['feishu',health.gateway === 'CONNECTED']]) {
    const row = el('div', null, 'health-row'); row.append(el('span', t(name)), el('span', t(ready ? 'ready' : 'unavailable'), ready ? 'ready' : 'unavailable')); healthList.append(row);
  }
  text('approval-count', snapshot?.approvals.approvals.length || 0);
  const result = trace.events.findLast(e => e.kind === 'OUTCOME_VERIFIED'); $('result-section').hidden = !result; text('result-text', result?.data.text);
  renderGraph(); renderDetails(); renderApprovals(); renderSettings(); renderInventory();
}
async function refresh(force = false) {
  if (polling) return; polling = true;
  try {
    snapshot = await invoke('client_snapshot'); connected = true;
    locale = snapshot.settings.config.locale;
    const runs = snapshot.runs.runs;
    if (!selectedTask && runs.length) selectedTask = runs[0].task_id;
    const task = selectedTask;
    if (task) {
      let batch;
      try { batch = await invoke('client_trace', { taskId: task, afterSeq: trace.lastSeq }); }
      catch (error) {
        if (!String(error).includes('EVENT_CURSOR_EXPIRED')) throw error;
        trace = emptyTrace(); batch = await invoke('client_trace', { taskId: task, afterSeq: 0 });
      }
      if (task === selectedTask) {
        trace = mergeTrace(trace, batch);
        if (!selectedEvent) selectedEvent = trace.events.findLast(e => e.kind === 'OUTCOME_VERIFIED')?.event_id || trace.events.at(-1)?.event_id;
      }
    }
    if (force) banner(''); render(force);
  } catch (error) { connected = false; banner(`${t('disconnected')} · ${t('connectHelp')} (${String(error).slice(0,90)})`); render(true); }
  finally { polling = false; }
}

document.querySelectorAll('[data-view]').forEach(button => button.addEventListener('click', () => switchView(button.dataset.view)));
$('reconnect').addEventListener('click', async () => { preview = null; settingsDirty = false; renderedSettingsRevision = null; $('settings-preview').hidden = true; try { await invoke('client_reconnect'); } catch {} await refresh(true); });
$('new-task').addEventListener('click', () => { $('goal').value = t('defaultGoal'); $('task-dialog').showModal(); });
$('close-dialog').addEventListener('click', () => $('task-dialog').close());
$('task-form').addEventListener('submit', event => { event.preventDefault(); action(async () => {
  const created = await invoke('client_create', { goal: $('goal').value });
  $('task-dialog').close(); selectedTask = created.task_id; selectedEvent = null; trace = emptyTrace(); switchView('runs');
  await invoke('client_start', { taskId: created.task_id });
}); });
$('start-task').addEventListener('click', () => action(() => invoke('client_start', { taskId: selectedTask })));
$('cancel-task').addEventListener('click', () => action(async () => {
  const run = snapshot.runs.runs.find(r => r.task_id === selectedTask);
  await invoke('client_cancel', { taskId: selectedTask, expectedVersion: run.version });
}));
$('language').addEventListener('click', () => action(async () => {
  const p = await invoke('client_preview_settings', { expectedRevision: snapshot.settings.revision, config: { ...snapshot.settings.config, locale: locale === 'en' ? 'zh-CN' : 'en' } });
  await invoke('client_apply_settings', { preview: { ...p, confirm: true } });
}));
$('settings-form').addEventListener('input', () => { settingsDirty = true; preview = null; $('settings-preview').hidden = true; });
$('settings-form').addEventListener('submit', event => { event.preventDefault(); action(async () => {
  const data = new FormData($('settings-form')), config = Object.fromEntries(['locale','model','mode'].map(k => [k,data.get(k)]));
  config.max_steps = Number(data.get('max_steps'));
  for (const key of ['skill_enabled','mcp_enabled','feishu_enabled']) config[key] = data.has(key);
  preview = await invoke('client_preview_settings', { expectedRevision: renderedSettingsRevision, config });
  text('settings-diff', preview.changes.map(k => `${t(k === 'max_steps' ? 'steps' : k)}: ${snapshot.settings.config[k]} → ${preview.config[k]}`).join('\n') || '—');
  $('settings-preview').hidden = false;
}); });
$('apply-settings').addEventListener('click', () => action(async () => {
  if (!preview) return;
  await invoke('client_apply_settings', { preview: { ...preview, confirm: true } });
  preview = null; settingsDirty = false; renderedSettingsRevision = null; $('settings-preview').hidden = true;
}));
window.addEventListener('resize', () => renderGraph());
localize(); render(true); refresh(); setInterval(refresh, 1800);
