const $ = id => document.getElementById(id);
const fragment = new URLSearchParams(location.hash.slice(1));
let pass = fragment.get('pass') || sessionStorage.getItem('swarm-guest-pass') || '';
if (fragment.has('pass')) {
  sessionStorage.setItem('swarm-guest-pass', pass);
  history.replaceState(null, '', location.pathname);
}
let state = null, jobId = sessionStorage.getItem('swarm-guest-job'), working = !!jobId, stopped = false;

function error(message) { $('error').textContent = message; $('error').hidden = !message; }
function controls() {
  $('run').disabled = working || !state?.ready || !state?.remaining_jobs || !$('prompt').value.trim();
  $('sample').disabled = working || !state?.sample_prompt;
  $('prompt').disabled = working;
  document.body.classList.toggle('running', working);
  $('count').textContent = `${$('prompt').value.length} / 2,000`;
}
async function api(path, options = {}) {
  const response = await fetch(path, {...options, headers: {Authorization: `Bearer ${pass}`, 'Content-Type': 'application/json'}});
  const data = await response.json();
  if (!response.ok) {
    if (response.status === 401 || response.status === 410) stopped = true;
    throw new Error(typeof data.detail === 'string' ? data.detail : 'Request failed. Please try again.');
  }
  return data;
}
async function refresh() {
  if (stopped) return;
  try {
    state = await api('/api/status');
    $('status').textContent = state.busy ? 'Working on a request' : state.ready ? 'Ready for your request' : 'Waiting for the host';
    document.querySelector('.pool').classList.toggle('ready', state.ready);
    $('model').textContent = state.model;
    $('peers').replaceChildren(...state.peers.map(name => {const badge = document.createElement('span'); badge.textContent = name; return badge;}));
    $('allowance').textContent = `${state.remaining_jobs} requests left on this shared pass · Replies up to ${state.max_output_tokens} tokens`;
  } catch (e) { state = null; error(e.message); $('status').textContent = stopped ? 'Guest pass unavailable' : 'Host unavailable'; }
  controls();
  if (!stopped) setTimeout(refresh, 2500);
}
async function pollJob() {
  if (!jobId || stopped) return;
  try {
    const job = await api('/api/jobs/' + encodeURIComponent(jobId));
    $('output').textContent = job.output || 'The laptops are working…';
    $('result-status').textContent = job.status === 'complete' ? 'COMPLETE' : job.status === 'failed' ? 'INCOMPLETE' : 'GENERATING';
    if (job.status !== 'running') {
      working = false;
      sessionStorage.removeItem('swarm-guest-job'); jobId = null;
      if (job.complete) {
        const seconds = value => value == null ? '—' : Number(value).toFixed(2) + 's';
        $('metrics').textContent = `First token ${seconds(job.first_token_seconds)} · Total ${seconds(job.elapsed_seconds)} · ${job.usage?.completion_tokens ?? '—'} output tokens. Computed with ${job.peers.join(' + ')}.`;
        $('metrics').hidden = false; $('copy').hidden = false;
      } else error(job.error || 'The request did not finish.');
      controls(); return;
    }
  } catch (e) { working = false; jobId = null; sessionStorage.removeItem('swarm-guest-job'); error(e.message); controls(); return; }
  setTimeout(pollJob, 1000);
}
$('prompt').addEventListener('input', controls);
$('sample').addEventListener('click', () => { $('prompt').value = state.sample_prompt; controls(); });
$('run').addEventListener('click', async () => {
  working = true; controls(); error(''); $('output').textContent = 'Sending your request…';
  $('metrics').hidden = true; $('copy').hidden = true; $('result-status').textContent = 'SUBMITTING';
  try {
    const job = await api('/api/jobs', {method: 'POST', body: JSON.stringify({prompt: $('prompt').value})});
    jobId = job.id; sessionStorage.setItem('swarm-guest-job', jobId); pollJob();
  } catch (e) { working = false; $('result-status').textContent = 'NOT STARTED'; error(e.message); controls(); }
});
$('copy').addEventListener('click', async () => {
  try { await navigator.clipboard.writeText($('output').textContent); $('copy').textContent = 'Copied'; }
  catch { error('Select the answer text to copy it.'); }
});
if (!pass) { stopped = true; error('Open the full guest link or scan the QR code supplied by the host.'); $('status').textContent = 'Guest pass required'; }
else { refresh(); if (jobId) pollJob(); }
