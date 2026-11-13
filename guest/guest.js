const $ = id => document.getElementById(id);
const fragment = new URLSearchParams(location.hash.slice(1));
function stored(key) { try { return sessionStorage.getItem(key); } catch { return null; } }
function store(key, value) {
  try { if (value === null) sessionStorage.removeItem(key); else sessionStorage.setItem(key, value); }
  catch { $('storage-error').textContent = 'Browser storage is unavailable. Keep this page open to retain chats and guest access.'; $('storage-error').hidden = false; }
}
let pass = fragment.get('pass') || stored('swarm-guest-pass') || '';
if (fragment.has('pass')) { store('swarm-guest-pass', pass); history.replaceState(null, '', location.pathname); }
const CHAT_KEY = 'swarm-guest-chats-v1';
const newChat = () => ({ id: crypto.randomUUID(), title: 'New chat', draft: '', turns: [] });
let chats, activeId;
try {
  const saved = JSON.parse(stored(CHAT_KEY));
  if (!saved?.chats?.length || !saved.chats.every(c => typeof c.id === 'string' && typeof c.title === 'string' && typeof c.draft === 'string' && Array.isArray(c.turns) && c.turns.every(t => typeof t.id === 'string' && typeof t.output === 'string'))) throw Error();
  chats = saved.chats; activeId = saved.activeId;
} catch { chats = [newChat()]; }
let state = null, jobId = stored('swarm-guest-job'), working = !!jobId, stopped = false;
let activeTurn = null, view = 'chat';
for (const chat of chats) for (const turn of chat.turns) {
  if (jobId && turn.jobId === jobId) activeTurn = turn;
  else if (turn.status === 'running') { turn.status = 'incomplete'; turn.error = 'Submission interrupted. The host may have a saved result.'; }
}
if (jobId && !activeTurn) {
  const recovered = newChat(); recovered.title = 'Recovered guest request';
  activeTurn = {id: crypto.randomUUID(), jobId, output: '', status: 'running', restored: true};
  recovered.turns.push(activeTurn); chats.unshift(recovered); activeId = recovered.id;
}
function current() { return chats.find(c => c.id === activeId) || chats[0]; }
function save() { store(CHAT_KEY, JSON.stringify({chats, activeId: current().id})); }
function error(message) { $('error').textContent = message; $('error').hidden = !message; }
// Same bounded transcript format as the dashboard; the guest API stays prompt-only.
function conversationPrompt(turns, prompt, limit, sample) {
  if (prompt === sample) return { prompt, included: 0, omitted: turns.length };
  const pairs = turns.filter(t => t.prompt && t.status === 'complete' && t.output);
  const prefix = 'Continue this conversation. Answer the latest user message.\n\n';
  const suffix = `User: ${prompt}\nAssistant:`;
  let history = '', included = 0;
  for (const turn of [...pairs].reverse()) {
    const pair = `User: ${turn.prompt}\nAssistant: ${turn.output}\n\n`;
    if ((prefix + pair + history + suffix).length > limit) break;
    history = pair + history; included++;
  }
  return { prompt: included ? prefix + history + suffix : prompt, included, omitted: pairs.length - included };
}
function controls() {
  $('run').disabled = working || stopped || !state?.ready || state?.busy || !state?.remaining_jobs || !$('prompt').value.trim();
  $('sample').disabled = $('welcome-sample').disabled = working || !state?.sample_prompt || stopped;
  $('count').textContent = `${$('prompt').value.length.toLocaleString()} / 2,000`;
  const context = conversationPrompt(current().turns, $('prompt').value, 2000, state?.sample_prompt);
  $('context-note').textContent = working ? 'The swarm is working. You can browse your other chats.' : context.omitted ? 'Older turns omitted to fit the limit. The sample runs independently.' : 'Recent complete turns included within the 2,000-character request limit.';
}
function element(tag, className, text) { const el = document.createElement(tag); el.className = className; if (text != null) el.textContent = text; return el; }
function renderList() {
  $('chat-list').replaceChildren(...chats.map(c => {
    const button = element('button', current().id === c.id && view === 'chat' ? 'selected' : '', c.title);
    button.title = c.title;
    if (current().id === c.id && view === 'chat') button.setAttribute('aria-current', 'page');
    button.addEventListener('click', () => { activeId = c.id; showView('chat'); $('prompt').value = c.draft; renderMessages(true); controls(); save(); });
    return button;
  }));
}
function renderMessages(forceScroll = false) {
  const container = $('conversation'), atBottom = container.scrollHeight - container.scrollTop - container.clientHeight < 100;
  const chat = current(); $('welcome').hidden = !!chat.turns.length;
  $('messages').replaceChildren(...chat.turns.map(turn => {
    const group = element('div', 'exchange');
    if (turn.prompt) { const user = element('article', 'user-message'); user.append(element('span', 'message-label', 'You'), element('div', '', turn.prompt)); group.append(user); }
    const answer = element('article', 'assistant-message');
    const label = element('div', 'message-label', turn.model || state?.model || 'IBM Granite');
    label.append(element('span', 'badge', turn.status === 'running' ? 'GENERATING' : turn.status === 'complete' ? 'COMPLETE' : 'INCOMPLETE'));
    answer.append(label);
    if (turn.restored) answer.append(element('p', 'context-note', 'Recovered guest request. Original prompt unavailable in this tab.'));
    answer.append(element('pre', '', turn.output || (turn.status === 'running' ? 'The laptops are working…' : 'No output received.')));
    if (turn.error) answer.append(element('p', 'turn-error', turn.error));
    if (turn.result?.complete) {
      const job = turn.result, seconds = value => value == null ? '—' : Number(value).toFixed(2) + 's';
      answer.append(element('div', 'metrics', `First token ${seconds(job.first_token_seconds)} · Total ${seconds(job.elapsed_seconds)} · ${job.usage?.prompt_tokens ?? '—'} in / ${job.usage?.completion_tokens ?? '—'} out tokens. Computed with ${(job.peers || []).join(' + ')}.`));
    }
    if (turn.output) {
      const copy = element('button', 'text-button', 'Copy answer');
      copy.addEventListener('click', async () => { try { await navigator.clipboard.writeText(turn.output); copy.textContent = 'Copied'; } catch { error('Select the answer text to copy it.'); } });
      answer.append(copy);
    }
    group.append(answer); return group;
  }));
  if (atBottom || forceScroll) container.scrollTop = container.scrollHeight;
}
function menu(open) { $('sidebar').classList.toggle('open', open); $('scrim').hidden = !open; $('menu').setAttribute('aria-expanded', String(open)); }
function showView(next) {
  view = next; $('chat-view').hidden = view !== 'chat'; $('models-view').hidden = view !== 'models';
  $('chat-tab').classList.toggle('active', view === 'chat'); $('models-tab').classList.toggle('active', view === 'models');
  menu(false); renderList();
}
async function api(path, options = {}) {
  const response = await fetch(path, {...options, headers: {Authorization: `Bearer ${pass}`, 'Content-Type': 'application/json'}});
  const data = await response.json();
  if (!response.ok) {
    if (response.status === 401 || response.status === 410) stopped = true;
    const failure = new Error(typeof data.detail === 'string' ? data.detail : 'Request failed. Please try again.');
    failure.status = response.status; throw failure;
  }
  return data;
}
async function refresh() {
  if (stopped) return;
  try {
    state = await api('/api/status');
    $('status').textContent = state.busy ? 'Working on a request' : state.ready ? 'Ready for your request' : 'Waiting for the host';
    $('connection-status').textContent = $('status').textContent;
    document.querySelector('.pool').classList.toggle('ready', state.ready);
    $('model').textContent = $('model-title').textContent = state.model;
    $('peers').replaceChildren(...state.peers.map(name => element('span', '', name)));
    $('allowance').textContent = `${state.remaining_jobs} requests left on this shared pass`;
  } catch (e) { state = null; error(e.message); $('status').textContent = $('connection-status').textContent = stopped ? 'Guest pass unavailable' : 'Host unavailable'; }
  controls();
  if (!stopped) setTimeout(refresh, 2500);
}
async function pollJob() {
  if (!jobId) return;
  if (stopped) {
    working = false; activeTurn.status = 'incomplete';
    activeTurn.error = 'Guest access ended before completion could be confirmed. The host may have a saved result.';
    jobId = null; store('swarm-guest-job', null); save(); renderMessages(); controls(); return;
  }
  try {
    const job = await api('/api/jobs/' + encodeURIComponent(jobId));
    Object.assign(activeTurn, {output: job.output || '', model: job.model, status: job.status === 'failed' ? 'incomplete' : job.status, result: job.complete ? job : null, error: job.error || ''});
    if (job.status !== 'running') { working = false; store('swarm-guest-job', null); jobId = null; }
    save(); renderMessages(); controls();
    if (!jobId) return;
  } catch (e) {
    error(e.message);
    if (stopped || e.status === 404) {
      working = false; activeTurn.status = 'incomplete'; activeTurn.error = e.message;
      jobId = null; store('swarm-guest-job', null); save(); renderMessages(); controls(); return;
    }
    // A lost polling response must not release the one-generation guard.
  }
  setTimeout(pollJob, 1000);
}
$('prompt').addEventListener('input', () => { current().draft = $('prompt').value; save(); controls(); });
function sample() { if (!state?.sample_prompt || working) return; current().draft = $('prompt').value = state.sample_prompt; save(); controls(); $('prompt').focus(); }
$('sample').addEventListener('click', sample); $('welcome-sample').addEventListener('click', sample);
async function send() {
  if ($('run').disabled || working) return;
  const chat = current(), input = $('prompt').value;
  const context = conversationPrompt(chat.turns, input, 2000, state.sample_prompt);
  activeTurn = {id: crypto.randomUUID(), prompt: input, output: '', status: 'running', model: state.model};
  const turn = activeTurn;
  if (!chat.turns.length) chat.title = input.trim().replace(/\s+/g, ' ').slice(0, 46);
  chat.turns.push(turn); chat.draft = ''; $('prompt').value = '';
  working = true; controls(); error(''); save(); renderList(); renderMessages(true);
  try {
    const job = await api('/api/jobs', {method: 'POST', body: JSON.stringify({prompt: context.prompt})});
    jobId = job.id; turn.jobId = jobId; store('swarm-guest-job', jobId); save(); pollJob();
  } catch (e) { working = false; turn.status = 'incomplete'; turn.error = e.message; error(e.message); save(); renderMessages(); controls(); }
}
$('run').addEventListener('click', send);
$('prompt').addEventListener('keydown', e => { if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) { e.preventDefault(); send(); } });
$('new-chat').addEventListener('click', () => { let chat = chats.find(c => !c.turns.length && !c.draft.trim()); if (!chat) { chat = newChat(); chats.unshift(chat); } activeId = chat.id; $('prompt').value = ''; showView('chat'); renderMessages(true); save(); controls(); $('prompt').focus(); });
$('chat-tab').addEventListener('click', () => showView('chat'));
for (const id of ['models-tab', 'model-picker']) $(id).addEventListener('click', () => showView('models'));
$('back-to-chat').addEventListener('click', () => showView('chat'));
$('menu').addEventListener('click', () => menu(!$('sidebar').classList.contains('open')));
$('scrim').addEventListener('click', () => menu(false));
document.addEventListener('keydown', e => { if (e.key === 'Escape') menu(false); });
$('prompt').value = current().draft; renderList(); renderMessages(true); controls();
if (!pass) { stopped = true; error('Open the full guest link or scan the QR code supplied by the host.'); $('status').textContent = $('connection-status').textContent = 'Guest pass required'; }
else { refresh(); if (jobId) pollJob(); }
