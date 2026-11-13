import React, { useEffect, useRef, useState } from 'react';
import { Check, Copy, ExternalLink, QrCode, RotateCcw, X } from 'lucide-react';

export default function GuestMode({ token, onClose }) {
  const dialog = useRef(null);
  const [invite, setInvite] = useState(null), [error, setError] = useState('');
  const [copied, setCopied] = useState(false), [attempt, setAttempt] = useState(0);
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    const opener = document.activeElement;
    dialog.current.showModal();
    return () => { if (opener?.isConnected) opener.focus(); };
  }, []);
  useEffect(() => { setCopied(false); }, [invite?.url]);
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, []);
  useEffect(() => {
    let stopped = false, timer, controller;
    async function refresh() {
      controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), 8000);
      try {
        if (!token) throw new Error('Connect to this laptop’s dashboard before opening Guest mode.');
        const response = await fetch('http://127.0.0.1:8003/api/guest-invite', {
          headers: { Authorization: 'Bearer ' + token }, signal: controller.signal, cache: 'no-store'
        });
        if (!response.ok) throw new Error('Guest access could not be verified on this laptop. Check the host’s guest services, then try again.');
        const value = await response.json();
        if (!stopped) { setInvite(value); setError(''); }
      } catch (failure) {
        if (!stopped) { setInvite(null); setError(failure.message === 'Failed to fetch' || failure.name === 'AbortError'
          ? 'Guest access isn’t connected to this dashboard. Check the host’s guest services, then try again.' : failure.message); }
      } finally { clearTimeout(timeout); }
      if (!stopped) timer = setTimeout(refresh, 15000);
    }
    refresh();
    return () => { stopped = true; clearTimeout(timer); controller?.abort(); };
  }, [token, attempt]);
  const expired = invite?.expires_at && now >= invite.expires_at * 1000;
  const available = invite?.status === 'available' && !expired;
  async function copyLink() {
    if (!available) return;
    try { await navigator.clipboard.writeText(invite.url); setCopied(true); }
    catch { setError('Could not copy automatically. Select the invite link below and copy it.'); }
  }
  return <dialog className="guest-dialog" ref={dialog} aria-labelledby="guest-title" onClose={onClose}
    onClick={event=>{if(event.target === dialog.current) onClose();}}>
    <div className="guest-dialog-heading"><span className="device-icon"><QrCode size={23}/></span><button className="icon-button" aria-label="Close guest mode" onClick={onClose}><X size={20}/></button></div>
    <div className="eyebrow">INVITE SOMEONE TO TRY THE SWARM</div><h2 id="guest-title">Guest mode</h2>
    <p className="guest-intro">Scan on a phone. Send a prompt.<br/>Your shared laptops run the model.</p>
    {!invite && !error && <p className="guest-message" role="status">Checking guest access…</p>}
    {error && <p className="guest-message warning" role="alert">{error}</p>}
    {invite && !available && <p className="guest-message warning" role="status">{expired ? 'This guest pass has expired. The host needs to renew guest access.' : invite.message}</p>}
    {available && <>
      <div className="guest-qr"><img src={invite.qr} alt="Scan to open guest chat using the temporary guest pass"/></div>
      <div className="guest-availability"><span className={'status-dot '+(invite.ready ? 'lit' : '')}/>{invite.busy ? 'Swarm busy · guests can open the page' : invite.ready ? 'Guest gateway ready for requests' : 'Waiting for the swarm · guests can open the page'}</div>
      <div className="guest-limits"><span><b>{invite.remaining_jobs}</b> shared requests left</span><span>Expires <b>{new Date(invite.expires_at * 1000).toLocaleTimeString([], {hour:'numeric', minute:'2-digit'})}</b></span></div>
      <button className="button primary full guest-copy" aria-label={copied ? 'Invite link copied' : 'Copy invite link'} onClick={copyLink}>{copied ? <Check size={17}/> : <Copy size={17}/>}<span role="status">{copied ? 'Invite link copied' : 'Copy invite link'}</span></button>
      <label className="sr-only" htmlFor="guest-invite-link">Temporary guest invite link</label><input id="guest-invite-link" className="guest-link" readOnly value={invite.url} onFocus={event=>event.target.select()}/>
      <a className="guest-open" href={invite.url} target="_blank" rel="noopener noreferrer">Open guest page <ExternalLink size={13}/></a>
      <p className="guest-footnote">Works on cellular or another Wi-Fi. The temporary web relay must stay running. Phones submit requests; they don’t contribute compute. Use non-sensitive demo text.</p>
    </>}
    {(!available || error) && <button className="button secondary full" onClick={()=>{setInvite(null);setError('');setCopied(false);setAttempt(n=>n+1);}}><RotateCcw size={15}/>Check again</button>}
    <p className="guest-private">This QR grants temporary guest access. Share it with intended guests only.</p>
  </dialog>;
}
