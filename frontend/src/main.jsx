import React, { useEffect, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { ArrowUpRight, Check, ChevronDown, Circle, Cpu, Layers3, Laptop, Network, Play, Power, RotateCcw, Square, Terminal, Wifi, X } from 'lucide-react';
import './style.css';

const gb = bytes => bytes == null ? '—' : `${(bytes / 1e9).toFixed(2)} GB`;
const names = { off: 'Not sharing', offered: 'Available', reserved: 'Reserved', worker_ready: 'Worker ready', loading: 'Loading model', ready: 'Model ready', computing: 'Computing', failed: 'Needs attention', offline: 'Offline', stopping: 'Stopping' };
const time = value => value == null ? '—' : `${value.toFixed(2)} s`;

function evaluate(text) {
  try {
    const records = JSON.parse(text.trim().replace(/^```(?:json)?\s*/,'').replace(/\s*```$/,''));
    const expected = [['billing','A104'],['damage','B208'],['account',null]];
    return expected.map(([category, id], i) => ({ name: ['Invoice request','Damaged shipment','Missing order ID'][i],
      pass: Array.isArray(records) && records.length === 3 && records[i]?.category === category && records[i]?.order_id === id &&
      Number(records[i]?.case_id) === i + 1 && Object.keys(records[i] || {}).sort().join(',') === 'case_id,category,order_id' }));
  } catch { return [{ name: 'Valid JSON output', pass: false }]; }
}

function App() {
  const [data, setData] = useState(null), [token, setToken] = useState('');
  const [connectionError, setConnectionError] = useState(''), [actionError, setActionError] = useState('');
  const [prompt, setPrompt] = useState(''), [output, setOutput] = useState('');
  const [running, setRunning] = useState(false), [pending, setPending] = useState('');
  const [result, setResult] = useState(null), [checks, setChecks] = useState(null);
  const [details, setDetails] = useState(false);
  const abortRef = useRef(null), tokenRef = useRef('');

  async function api(path, method = 'GET', body) {
    const response = await fetch('/api' + path, { method, headers: { Authorization: 'Bearer ' + tokenRef.current, ...(body ? {'Content-Type':'application/json'} : {}) }, body: body ? JSON.stringify(body) : undefined });
    const value = await response.json();
    if (!response.ok) throw new Error(typeof value.detail === 'string' ? value.detail : JSON.stringify(value.detail));
    return value;
  }

  useEffect(() => {
    let stopped = false, timer;
    async function poll() {
      try {
        if (!tokenRef.current) {
          const response = await fetch('/api/bootstrap');
          const bootstrap = await response.json();
          if (!response.ok) throw new Error(bootstrap.detail || 'Cannot connect to local peer');
          tokenRef.current = bootstrap.token;
          if (!stopped) setToken(bootstrap.token);
        }
        const next = await api('/state');
        if (!stopped) { setData(next); setConnectionError(''); }
      } catch (error) { if (!stopped) setConnectionError(error.message); }
      if (!stopped) timer = setTimeout(poll, 1500);
    }
    poll();
    return () => { stopped = true; clearTimeout(timer); abortRef.current?.abort(); };
  }, []);

  async function action(path, body = {}) {
    setPending(path); setActionError('');
    try { await api(path, 'POST', body); setData(await api('/state')); }
    catch (error) { setActionError(error.message); }
    finally { setPending(''); }
  }

  const local = data?.local, peers = data?.peers || [];
  const coordinator = peers.find(p => p.session?.coordinator === p.id && p.session?.id === local?.session?.id);
  const ready = coordinator?.state === 'ready' && !connectionError;
  const targetPeers = data?.expected_peers || 2;
  const online = peers.filter(p => p.online).length;
  const offered = peers.filter(p => p.online && p.sharing).reduce((n,p) => n + p.offer_bytes, 0);
  const issues = local?.setup_issues || [];
  const placements = coordinator?.runtime?.placement || {};
  const placementCount = Object.keys(placements).length;

  async function run() {
    setRunning(true); setActionError(''); setOutput(''); setResult(null); setChecks(null);
    const controller = new AbortController(); abortRef.current = controller;
    let assembled = '', completed = false;
    try {
      const response = await fetch(`/api/sessions/${local.session.id}/generate`, { method: 'POST', signal: controller.signal,
        headers: { Authorization: 'Bearer ' + token, 'Content-Type':'application/json' }, body: JSON.stringify({ prompt, max_tokens: 256 }) });
      if (!response.ok) { const error = await response.json(); throw new Error(error.detail || 'Request failed'); }
      const reader = response.body.getReader(), decoder = new TextDecoder();
      let buffer = '';
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const blocks = buffer.split('\n\n'); buffer = blocks.pop();
        for (const block of blocks) {
          const line = block.split('\n').find(line => line.startsWith('data: '));
          if (!line) continue;
          const event = JSON.parse(line.slice(6));
          if (event.type === 'token') { assembled += event.text; setOutput(assembled); }
          if (event.type === 'error') throw new Error(event.message);
          if (event.type === 'done') { completed = true; setResult(event); if (prompt === data.sample_prompt) setChecks(evaluate(assembled)); }
        }
      }
      if (!completed) throw new Error('Connection ended. Partial output is incomplete.');
    } catch (error) { setActionError(error.name === 'AbortError' ? 'Cancelled. Partial output is incomplete.' : error.message); }
    finally { setRunning(false); abortRef.current = null; }
  }

  return <div className="app-shell">
    <aside className="sidebar">
      <a className="brand" href="/" aria-label="Open Swarm home"><span className="brand-symbol"><Network size={23}/></span><span>open<span className="brand-light">swarm</span><small>COMPUTE, TOGETHER.</small></span></a>
      <div className="sidebar-label">WORKSPACE</div>
      <div className="nav-item active"><Network size={18}/> Your swarm <span>01</span></div>
      <div className="sidebar-note"><span className="status-dot"/> TRUSTED LAN SESSION<p>Your computers.<br/>One shared model.</p></div>
      <div className="sidebar-bottom"><span className="avatar">{(local?.name || 'OS').slice(0,2).toUpperCase()}</span><div>{local?.name || 'Connecting…'}<small>Local peer · {local?.id || '—'}</small></div></div>
    </aside>
    <main>
      <header><div className="breadcrumb">Workspace <span>/</span> Your swarm</div><span className="prototype"><span className="status-dot"/> LIVE PROTOTYPE</span></header>
      <div className="page-heading"><div className="eyebrow">SHARED INFERENCE NETWORK</div><h1>Small machines.<br/><span>Shared possibilities.</span></h1><p>Bring your spare capacity. Run one Granite model together.</p></div>
      {(connectionError || actionError || local?.error) && <div role="alert" className="error-banner"><X size={18}/><span>{connectionError || actionError || local.error}</span></div>}
      <section className="overview" aria-label="Swarm overview">
        <div><span className="metric-label">CONNECTED PEERS</span><strong>{online}<small> / {targetPeers}</small></strong><span className="metric-note">{online === targetPeers ? 'All configured peers reachable' : 'Waiting for your other laptops'}</span></div>
        <div><span className="metric-label">OFFERED MEMORY</span><strong>{(offered / 1e9).toFixed(1)}<small> GB</small></strong><span className="metric-note">Shared budgets, including runtime overhead</span></div>
        <div><span className="metric-label">SHARED MODEL</span><strong className="model-metric">{local?.session?.model_name || data?.model?.name || 'Granite'}</strong><span className="metric-note">{ready ? 'Ready for a new request' : names[coordinator?.state || local?.state] || 'Connecting to local agent'}</span></div>
      </section>
      <div className="section-title"><h2>Your compute pool <span>{peers.length} known</span></h2><span className="subtle"><Wifi size={14}/> Manual membership · local network</span></div>
      <section className="peers" style={{'--peer-count':targetPeers}} aria-label="Peer contributions">
        {peers.map(peer => <article className={'peer-card ' + (peer.id === local?.id ? 'self' : '')} key={peer.id}>
          <div className="peer-top"><div className="device-icon"><Laptop size={22}/></div><span className={'pill ' + (peer.online && peer.sharing ? 'green' : '')}><span className="status-dot"/>{names[peer.state] || peer.state}</span></div>
          <h3>{peer.name}{peer.id === local?.id && <span>You</span>}</h3>
          <p className="role">{peer.session?.coordinator === peer.id ? 'Session coordinator + contributor' : peer.runtime?.role === 'worker' ? 'RPC compute contributor' : 'No active model assignment'}</p>
          <div className="memory-label"><span>Observed process memory</span><b>{gb(peer.runtime?.rss_bytes)}</b></div>
          <div className="memory-track"><span style={{width: Math.min(100, (peer.runtime?.rss_bytes || 0) / (peer.offer_bytes || 8e9) * 100) + '%'}}/></div>
          <div className="peer-stats"><span>Offer <b>{peer.sharing ? gb(peer.offer_bytes) : 'Off'}</b></span><span>Peak <b>{gb(peer.runtime?.peak_rss_bytes)}</b></span></div>
          <div className="peer-footer"><Cpu size={13}/><span>CPU {peer.runtime?.cpu_percent == null ? '—' : peer.runtime.cpu_percent + '%'}</span><span>RPC graph submissions <b>{peer.runtime?.graph_submissions ?? '—'}</b></span></div>
        </article>)}
        {Array.from({length: Math.max(0, targetPeers - peers.length)}, (_,i) => <article className="peer-card empty" key={'empty'+i}><div className="empty-icon"><Laptop size={28}/></div><h3>Add a laptop</h3><p>Start the peer app on another laptop<br/>with the same peer roster.</p><span>Not configured</span></article>)}
      </section>
      <div className="contribution"><div><Power size={18}/><div><b>Your contribution</b><span>Up to 8 GB · advisory target with a sampled stop guard</span></div></div><button className={'button ' + (local?.sharing ? 'secondary' : 'primary')} disabled={!local || !!pending || !!connectionError} onClick={() => action('/sharing',{enabled:!local.sharing})}>{local?.sharing ? 'Stop sharing' : 'Share this laptop'}<ArrowUpRight size={16}/></button></div>
      <section className="work-area">
        <div className="run-panel"><div className="section-title"><h2>Try the shared model</h2><span className="small-label">ONE REQUEST AT A TIME</span></div><p className="panel-description">Test the model you want to use, on the capacity you share.</p>
          <label htmlFor="prompt">Your test prompt</label><textarea id="prompt" maxLength={6000} value={prompt} onChange={e=>setPrompt(e.target.value)} placeholder="What do you want to test with Granite?" disabled={running}/>
          <div className="prompt-actions"><button className="text-button" disabled={!data || running} onClick={()=>setPrompt(data.sample_prompt)}>Load 3-case JSON test <ArrowUpRight size={13}/></button><span>{prompt.length}/6000</span></div>
          <div className="run-actions"><span className="subtle"><Layers3 size={15}/>{placementCount ? `${placementCount} native layer assignments observed` : 'Model has not been loaded'}</span>{running ? <button className="button secondary" onClick={()=>abortRef.current?.abort()}><Square size={14}/>Cancel</button> : <button className="button primary" disabled={!ready || !prompt.trim() || !!pending} onClick={run}><Play size={15}/>Run on swarm</button>}</div>
          <div className="result-header"><b>Model output</b><span className={'pill '+(result ? 'green':'')}>{running ? 'Streaming' : result ? 'Complete' : output ? 'Incomplete' : 'Awaiting a run'}</span></div>
          <pre className={'output ' + (!output ? 'placeholder' : '')} aria-live="polite">{output || 'Your model’s live response will appear here.'}{running && <span className="cursor">▌</span>}</pre>
          {checks && <div className="checks">{checks.map(check=><span className={check.pass?'pass':'fail'} key={check.name}>{check.pass?<Check size={14}/>:<X size={14}/>} {check.name}</span>)}</div>}
          {result && <div className="timings"><span>First token <b>{time(result.first_token_seconds)}</b></span><span>Total <b>{time(result.elapsed_seconds)}</b></span><span>Output tokens <b>{result.usage?.completion_tokens ?? '—'}</b></span></div>}
        </div>
        <aside className="session-panel"><div className="section-title"><h2>Session</h2><span className={'status-dot '+(ready?'lit':'')}/></div><div className="session-value">{names[coordinator?.state || local?.state] || 'Connecting…'}</div><p>{local?.session ? `Coordinated by ${coordinator?.name || local.session.coordinator}. Requests can originate from any peer.` : 'All participating owners enable sharing. One peer coordinates this session.'}</p>
          <button className="button primary full" disabled={!local?.sharing || !!local?.session || !!pending || issues.length > 0 || !!connectionError} onClick={()=>action('/session/start')}><Play size={14}/>Start shared session</button>
          <div className="session-buttons"><button className="button secondary" disabled={!local?.session || !!pending} onClick={()=>action('/session/stop')}><Square size={13}/>Stop session</button><button className="button secondary" disabled={!local || !!pending} onClick={()=>action('/reset')}><RotateCcw size={13}/>Reset</button></div>
          {issues.length > 0 && <div className="setup"><b>Before your first run</b>{issues.map((issue,i)=><p key={issue}><span>{String(i+1).padStart(2,'0')}</span>{issue}</p>)}</div>}
          <div className="session-details"><span>Context window <b>2,048 tokens</b></span><span>Generation limit <b>256 tokens</b></span><span>Model on this laptop <b>{data?.model?.present?'Downloaded':'Not downloaded'}</b></span><span>Artifact size <b>{gb(data?.model?.file_bytes)}</b></span></div>
          <div className="evidence-note"><Circle size={14}/><p>Activity comes from the peer agents and native logs. CPU use and graph submissions are supporting evidence—not token counts.</p></div>
        </aside>
      </section>
      <section className="diagnostics"><button className="diagnostic-toggle" aria-expanded={details} onClick={()=>setDetails(!details)}><Terminal size={16}/><span>Native logs & execution details</span><ChevronDown size={16}/></button>{details && <div className="diagnostic-body"><p>RSS does not establish total physical or GPU memory use. Validate native allocation logs and OS memory pressure before claiming the 8 GB budget fits.</p><pre>{local?.runtime?.logs?.join('\n') || 'No native runtime has started.'}</pre><p>Layer → device assignments reported by coordinator</p><pre>{Object.keys(placements).length ? JSON.stringify(placements,null,2) : 'No assignments observed.'}</pre></div>}</section>
      <footer><span>OPEN SWARM <span className="footer-dot">·</span> Built with IBM Granite</span><span>Shared capacity. One model. Actual work.</span></footer>
    </main>
  </div>;
}

createRoot(document.getElementById('root')).render(<App/>);
