import React, { useEffect, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { QrCode, ArrowUp, MessageSquare, Plus, Menu, Copy, ArrowUpRight, Check, ChevronDown, Circle, Cpu, Layers3, Laptop, Network, Play, Power, RotateCcw, Square, Terminal, Wifi, X } from 'lucide-react';
import './style.css';
import GuestMode from './GuestMode.jsx';
import { CHAT_KEY, chatTitle, conversationPrompt, newChat, readChats, loadDeviceChats, mergeChats } from './chat.js';

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
  const [initial] = useState(() => { try { return loadDeviceChats(localStorage); } catch { return null; } });
  const [chats, setChats] = useState(() => initial?.chats.length ? initial.chats : [newChat()]);
  const [activeId, setActiveId] = useState(() => initial?.activeId || null);
  const [view, setView] = useState('chat'), [menuOpen, setMenuOpen] = useState(false);
  const [runningTurn, setRunningTurn] = useState(null), [pending, setPending] = useState('');
  const running = !!runningTurn;
  const [storageError, setStorageError] = useState(''), [copied, setCopied] = useState('');
  const [details, setDetails] = useState(false);
  const [guestOpen, setGuestOpen] = useState(false);
  const abortRef = useRef(null), tokenRef = useRef('');
  const conversationRef = useRef(null), followBottom = useRef(true);
  const chat = chats.find(c => c.id === activeId) || chats[0];
  const prompt = chat.draft;
  const updateChat = (id, update) => setChats(all => all.map(c => c.id === id ? {...update(c), updatedAt: Date.now()} : c));
  const setPrompt = value => updateChat(chat.id, c => ({...c, draft: value, draftUpdatedAt: Date.now()}));
  const updateTurn = (chatId, turnId, patch) => updateChat(chatId, c => ({...c,
    turns: c.turns.map(t => t.id === turnId ? {...t, ...patch, updatedAt: Date.now()} : t)}));
  function selectChat(id) { setActiveId(id); setView('chat'); setMenuOpen(false); followBottom.current = true; }
  function createChat() {
    const empty = chats.find(c => !c.turns.length && !c.draft.trim());
    if (empty) { selectChat(empty.id); return; }
    const next = newChat(); setChats(all => [next, ...all]); selectChat(next.id);
  }
  function navigate(next) { setView(next); setMenuOpen(false); }
  useEffect(() => {
    try { const stored = readChats(localStorage, CHAT_KEY, false);
      const merged = mergeChats(chats, stored?.chats || []);
      const serialized = JSON.stringify({chats: merged, activeId: chat.id});
      if (localStorage.getItem(CHAT_KEY) !== serialized) localStorage.setItem(CHAT_KEY, serialized);
      setStorageError(''); }
    catch { setStorageError('Browser storage is unavailable or full. New chat history will last only while this page is open.'); }
  }, [chats, chat.id]);
  useEffect(() => {
    function sync(event) {
      if (event.key !== CHAT_KEY) return;
      const saved = readChats(localStorage, CHAT_KEY, false);
      if (saved) setChats(all => {
        const merged = mergeChats(all, saved.chats);
        return JSON.stringify(merged) === JSON.stringify(all) ? all : merged;
      });
    }
    window.addEventListener('storage', sync);
    return () => window.removeEventListener('storage', sync);
  }, []);
  useEffect(() => {
    const el = conversationRef.current;
    if (el && followBottom.current) el.scrollTop = el.scrollHeight;
  }, [chat, view]);
  useEffect(() => {
    const close = event => { if (event.key === 'Escape') setMenuOpen(false); };
    document.addEventListener('keydown', close);
    return () => document.removeEventListener('keydown', close);
  }, []);
  async function copy(turn) {
    try { await navigator.clipboard.writeText(turn.output); setCopied(turn.id); }
    catch { setActionError('Select the answer text to copy it.'); }
  }

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
  const ready = coordinator?.state === 'ready' && !coordinator?.busy && !connectionError;
  const targetPeers = data?.expected_peers || 2;
  const online = peers.filter(p => p.online).length;
  const offered = peers.filter(p => p.online && p.sharing).reduce((n,p) => n + p.offer_bytes, 0);
  const issues = local?.setup_issues || [];
  const placements = coordinator?.runtime?.placement || {};
  const placementCount = Object.keys(placements).length;

  const modelName = local?.session?.model_name || data?.model?.name || 'Checking model…';
  const context = conversationPrompt(chat.turns, prompt, 6000, data?.sample_prompt);

  async function run() {
    if (abortRef.current || !ready || !prompt.trim() || pending) return;
    const chatId = chat.id, turnId = crypto.randomUUID(), input = prompt;
    const patch = value => updateTurn(chatId, turnId, value);
    followBottom.current = true;
    updateChat(chatId, c => ({...c, title: c.turns.length ? c.title : chatTitle(input), draft: '', draftUpdatedAt: Date.now(),
      turns: [...c.turns, {id: turnId, prompt: input, output: '', status: 'streaming', model: modelName, createdAt: Date.now(), updatedAt: Date.now()}]}));
    setRunningTurn(turnId); setActionError('');
    const controller = new AbortController(); abortRef.current = controller;
    let assembled = '', completed = false;
    try {
      const response = await fetch(`/api/sessions/${local.session.id}/generate`, { method: 'POST', signal: controller.signal,
        headers: { Authorization: 'Bearer ' + token, 'Content-Type':'application/json' }, body: JSON.stringify({ prompt: context.prompt, max_tokens: 256 }) });
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
          if (event.type === 'token') { assembled += event.text; patch({output: assembled}); }
          if (event.type === 'error') throw new Error(event.message);
          if (event.type === 'done') { completed = true; patch({output: event.output ?? assembled, result: event, status: 'complete', checks: input === data.sample_prompt ? evaluate(assembled) : null}); }
        }
      }
      if (!completed) throw new Error('Connection ended. Partial output is incomplete.');
    } catch (error) { if (!completed) patch({status: 'incomplete', error: error.name === 'AbortError' ? 'Cancelled. Partial output is incomplete.' : error.message}); }
    finally { setRunningTurn(null); abortRef.current = null; }
  }

  return <div className="app-shell">
    {guestOpen && <GuestMode token={token} onClose={()=>setGuestOpen(false)}/>}
    {menuOpen && <button className="sidebar-scrim" aria-label="Close navigation" onClick={()=>setMenuOpen(false)}/>}
    <aside className={'sidebar '+(menuOpen ? 'open' : '')} aria-label="Workspace navigation">
      <a className="brand" href="/" aria-label="Open Swarm home"><span className="brand-symbol"><Network size={23}/></span><span>open<span className="brand-light">swarm</span><small>COMPUTE, TOGETHER.</small></span></a>
      <button className="new-chat" onClick={createChat}><Plus size={18}/> New chat</button>
      <nav><button className={'nav-item '+(view === 'chat' ? 'active' : '')} onClick={()=>navigate('chat')}><MessageSquare size={18}/> Chat</button>
      <button className={'nav-item '+(view === 'models' ? 'active' : '')} onClick={()=>navigate('models')}><Layers3 size={18}/> Models</button>
      <button className={'nav-item '+(view === 'swarm' ? 'active' : '')} onClick={()=>navigate('swarm')}><Network size={18}/> Your swarm <span>{online}/{targetPeers}</span></button>
      <button className="nav-item" onClick={()=>{setMenuOpen(false);setGuestOpen(true);}}><QrCode size={18}/> Guest mode</button></nav>
      <div className="sidebar-label">YOUR CHATS</div>
      <div className="chat-list">{chats.map(c => <button key={c.id} title={c.title} className={view === 'chat' && c.id === chat.id ? 'selected' : ''} aria-current={view === 'chat' && c.id === chat.id ? 'page' : undefined} onClick={()=>selectChat(c.id)}><MessageSquare size={14}/><span>{c.title}</span>{c.turns.some(t=>t.id === runningTurn) && <span className="status-dot"/>}</button>)}</div>
      <p className="history-note">Chats stay on this device.<br/>Saved in this browser only.</p>
      <div className="sidebar-bottom"><span className="avatar">{(local?.name || 'OS').slice(0,2).toUpperCase()}</span><div>{local?.name || 'Connecting…'}<small>Local peer · {local?.id || '—'}</small></div></div>
    </aside>
    <main className={'workspace '+(view === 'chat' ? 'chat-view' : '')}>
      <header><div className="header-left"><button className="menu-button" aria-label="Toggle navigation" aria-expanded={menuOpen} onClick={()=>setMenuOpen(!menuOpen)}><Menu size={21}/></button>{view === 'chat' ? <button className="model-picker" onClick={()=>navigate('models')}>{modelName}<ChevronDown size={16}/></button> : <div className="breadcrumb">Workspace <span>/</span> {view === 'models' ? 'Models' : 'Your swarm'}</div>}</div><div className="header-actions"><button className="guest-mode-button" aria-label="Guest mode" onClick={()=>setGuestOpen(true)}><QrCode size={16}/><span>Guest mode</span></button><button className="live-status" onClick={()=>navigate('swarm')}><span className={'status-dot '+(ready ? 'lit' : '')}/>{running || coordinator?.busy ? 'Swarm working' : ready ? `${online} peers connected` : 'Check swarm'}</button></div></header>
      {(connectionError || actionError || local?.error || storageError) && <div role="alert" className="error-banner"><X size={18}/><span>{connectionError || actionError || local?.error || storageError}</span></div>}
      {view === 'chat' && <section className="chat-workspace" aria-label="Chat">
        <div className="conversation" ref={conversationRef} onScroll={e=>{const el=e.currentTarget; followBottom.current=el.scrollHeight-el.scrollTop-el.clientHeight<100;}}>
          {!chat.turns.length ? <div className="chat-welcome"><span className="welcome-symbol"><Network size={32}/></span><div className="eyebrow">SMALL MACHINES. SHARED POSSIBILITIES.</div><h1>What shall we try?</h1><p>One Granite model. Your laptops, working together.</p><div className="suggestions"><button disabled={!data || running} onClick={()=>setPrompt(data.sample_prompt)}><span>Extract structured data</span><small>Try the three-case JSON check</small><ArrowUpRight size={17}/></button><button onClick={()=>setPrompt('Explain distributed inference in three short sentences.')}><span>Explore shared compute</span><small>Ask how one model runs across laptops</small><ArrowUpRight size={17}/></button></div></div> : <div className="message-list"><div className="conversation-title">{chat.title}</div>{chat.turns.map(turn=><React.Fragment key={turn.id}>
            {turn.prompt && <article className="message user-message"><span className="message-label">You</span><div>{turn.prompt}</div></article>}
            <article className="message assistant-message"><div className="message-label"><Network size={17}/>{turn.model || 'IBM Granite'}<span className="pill">{turn.id === runningTurn ? 'Generating' : turn.status === 'complete' ? 'Complete' : 'Incomplete'}</span></div>
              {turn.status === 'streaming' && turn.id !== runningTurn && <p className="saved-note">Saved partial response. Live streaming is only available in the tab that sent this message.</p>}
              <pre className="message-output" aria-live={turn.id === runningTurn ? 'polite' : 'off'}>{turn.output || (turn.id === runningTurn ? 'Waiting for the shared model…' : 'No output received.')}</pre>
              {turn.error && <p className="turn-error" role="alert">{turn.error}</p>}
              {turn.checks && <div className="checks">{turn.checks.map(check=><span className={check.pass?'pass':'fail'} key={check.name}>{check.pass?<Check size={14}/>:<X size={14}/>} {check.name}</span>)}</div>}
              {turn.result && <div className="timings"><span>First token <b>{time(turn.result.first_token_seconds)}</b></span><span>Total <b>{time(turn.result.elapsed_seconds)}</b></span><span>Tokens <b>{turn.result.usage?.prompt_tokens ?? '—'} in / {turn.result.usage?.completion_tokens ?? '—'} out</b></span></div>}
              {turn.output && <button className="copy-button" onClick={()=>copy(turn)}><Copy size={13}/>{copied === turn.id ? 'Copied' : 'Copy answer'}</button>}
            </article></React.Fragment>)}</div>}
        </div>
        <div className="composer-wrap"><div className="composer"><label className="sr-only" htmlFor="prompt">Message the shared model</label><textarea id="prompt" rows="2" maxLength={6000} value={prompt} onChange={e=>setPrompt(e.target.value)} placeholder="Message the shared model…" onKeyDown={e=>{if(e.key==='Enter' && !e.shiftKey && !e.nativeEvent.isComposing){e.preventDefault();run();}}}/><div className="composer-tools"><button className="text-button" disabled={!data || running} onClick={()=>setPrompt(data.sample_prompt)}>Try sample <ArrowUpRight size={13}/></button><span>{prompt.length.toLocaleString()} / 6,000</span>{running ? <button className="send-button" aria-label="Cancel generation" onClick={()=>abortRef.current?.abort()}><Square size={17}/></button> : <button className="send-button" aria-label="Send message" disabled={!ready || !prompt.trim() || !!pending} onClick={run}><ArrowUp size={20}/></button>}</div></div>
          <p className="composer-note">{running ? 'One request at a time. You can browse your other chats.' : !ready ? 'Waiting for the swarm to be ready.' : context.omitted ? 'Older turns omitted to fit the request limit. The sample runs independently.' : 'Recent complete turns included within the request limit.'} <span>Shift + Enter for a new line · 256-token replies</span></p>
        </div>
      </section>}
      {view === 'models' && <section className="models-view"><div className="page-heading"><div className="eyebrow">RUN ON SHARED CAPACITY</div><h1>Your models</h1><p>The active session determines the model for every chat.</p></div><article className="model-card current"><div className="model-card-top"><span className="device-icon"><Layers3 size={25}/></span><span className="pill green">Current session model</span></div><h2>{modelName}</h2><p>IBM Granite · native llama.cpp RPC</p><div className="model-facts"><span>Status<b>{names[coordinator?.state || local?.state] || 'Connecting…'}</b></span><span>Context<b>2,048 tokens</b></span><span>Artifact<b>{gb(data?.model?.file_bytes)}</b></span><span>Native assignments<b>{placementCount || '—'} observed</b></span></div><button className="button primary" onClick={()=>navigate('chat')}>Back to chat <ArrowUpRight size={15}/></button></article><article className="model-card unavailable"><div className="model-card-top"><Layers3 size={23}/><span className="pill">Unverified · unavailable</span></div><h2>Granite 4.2 30B</h2><p>Planned for a future three-laptop test. Execution and memory fit have not been verified.</p><button className="button secondary" disabled>Not available in this session</button></article><p className="model-explainer">Model switching requires a new native session. This demo keeps the loaded model warm; browsing models does not change it.</p></section>}
      {view === 'swarm' && <><div className="page-heading"><div className="eyebrow">SHARED INFERENCE NETWORK</div><h1>Your swarm</h1><p>Live measurements from the computers running your model.</p></div>
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
      <p className="measurement-note">Process RSS is incomplete GPU / unified-memory accounting. RPC graph submissions are not tokens or completed kernels.</p>
      <div className="contribution"><div><Power size={18}/><div><b>Your contribution</b><span>Up to 8 GB · advisory target with a sampled stop guard</span></div></div><button className={'button ' + (local?.sharing ? 'secondary' : 'primary')} disabled={!local || !!pending || !!connectionError} onClick={() => action('/sharing',{enabled:!local.sharing})}>{local?.sharing ? 'Stop sharing' : 'Share this laptop'}<ArrowUpRight size={16}/></button></div>
      <section className="session-area">
        <aside className="session-panel"><div className="section-title"><h2>Session</h2><span className={'status-dot '+(ready?'lit':'')}/></div><div className="session-value">{names[coordinator?.state || local?.state] || 'Connecting…'}</div><p>{local?.session ? `Coordinated by ${coordinator?.name || local.session.coordinator}. Requests can originate from any peer.` : 'All participating owners enable sharing. One peer coordinates this session.'}</p>
          <button className="button primary full" disabled={!local?.sharing || !!local?.session || !!pending || issues.length > 0 || !!connectionError} onClick={()=>action('/session/start')}><Play size={14}/>Start shared session</button>
          <div className="session-buttons"><button className="button secondary" disabled={!local?.session || !!pending} onClick={()=>action('/session/stop')}><Square size={13}/>Stop session</button><button className="button secondary" disabled={!local || !!pending} onClick={()=>action('/reset')}><RotateCcw size={13}/>Reset</button></div>
          {issues.length > 0 && <div className="setup"><b>Before your first run</b>{issues.map((issue,i)=><p key={issue}><span>{String(i+1).padStart(2,'0')}</span>{issue}</p>)}</div>}
          <div className="session-details"><span>Context window <b>2,048 tokens</b></span><span>Generation limit <b>256 tokens</b></span><span>Model on this laptop <b>{data?.model?.present?'Downloaded':'Not downloaded'}</b></span><span>Artifact size <b>{gb(data?.model?.file_bytes)}</b></span></div>
          <div className="evidence-note"><Circle size={14}/><p>Activity comes from the peer agents and native logs. CPU use and graph submissions are supporting evidence—not token counts.</p></div>
        </aside>
      </section>
      <section className="diagnostics"><button className="diagnostic-toggle" aria-expanded={details} onClick={()=>setDetails(!details)}><Terminal size={16}/><span>Native logs & execution details</span><ChevronDown size={16}/></button>{details && <div className="diagnostic-body"><p>RSS does not establish total physical or GPU memory use. Validate native allocation logs and OS memory pressure before claiming the 8 GB budget fits.</p><pre>{local?.runtime?.logs?.join('\n') || 'No native runtime has started.'}</pre><p>Layer → device assignments reported by coordinator</p><pre>{Object.keys(placements).length ? JSON.stringify(placements,null,2) : 'No assignments observed.'}</pre></div>}</section>
      </>}
      {view !== 'chat' && <footer><span>OPEN SWARM <span className="footer-dot">·</span> Built with IBM Granite</span><span>Shared capacity. One model. Actual work.</span></footer>}
    </main>
  </div>;
}

createRoot(document.getElementById('root')).render(<App/>);
