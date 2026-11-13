"""Read-only demo readiness check. Exit codes: 0 READY, 1 BUSY, 2 BLOCKED, 3 UNKNOWN.

Queries authenticated peer snapshots; never starts or stops a session.
Readiness is a point-in-time observation, not proof that inference will complete.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
import httpx
from pydantic import ValidationError
from swarm.config import load_settings
from swarm.peer import Manifest

EXIT_READY, EXIT_BUSY, EXIT_BLOCKED, EXIT_UNKNOWN = 0, 1, 2, 3
STATUS_READY, STATUS_BUSY, STATUS_BLOCKED, STATUS_UNKNOWN = "READY", "BUSY", "BLOCKED", "UNKNOWN"


def _redact(obj: Any, secrets=()) -> Any:
    """Redact credential fields and known secrets before either output format."""
    if isinstance(obj, dict):
        return {k: "***REDACTED***" if any(s in str(k).lower()
                for s in ("token", "pass", "secret", "credential"))
                else _redact(v, secrets) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_redact(v, secrets) for v in obj]
    if isinstance(obj, str):
        for secret in secrets:
            if secret:
                obj = obj.replace(secret, "***REDACTED***")
        obj = re.sub(r"(?i)(bearer\s+)\S+", r"\1***REDACTED***", obj)
        return re.sub(r"(?i)([?#&](?:pass|token)=)[^&\s]+", r"\1***REDACTED***", obj)
    return obj


def _fetch(base_url, token, path, timeout):
    try:
        response = httpx.get(base_url.rstrip("/") + path,
                              headers={"Authorization": "Bearer " + token},
                              timeout=timeout, follow_redirects=False, trust_env=False)
        if response.status_code != 200:
            return None, f"HTTP {response.status_code}"
        data = response.json()
        if not isinstance(data, dict):
            return None, "Malformed API response (expected an object)"
        return data, None
    except httpx.TimeoutException:
        return None, "timeout"
    except httpx.ConnectError:
        return None, "connection unavailable"
    except (httpx.HTTPError, ValueError):
        return None, "Invalid API response or transport failure"


def _fetch_state(base_url, token, timeout=8.0):
    return _fetch(base_url, token, "/api/state", timeout)


def _fetch_peer(base_url, token, timeout=4.0):
    return _fetch(base_url, token, "/api/peer", timeout)


def _unknown(message):
    detail = {"status": STATUS_UNKNOWN, "blockers": [message],
              "local": {}, "runtime": {}, "peers": [], "model": {}}
    return STATUS_UNKNOWN, detail["blockers"], detail


def analyse(state: Dict, remote_snapshots: List[Dict]) -> Tuple[str, List[str], Dict]:
    """Evaluate every required member using its most recent collected snapshot."""
    if not isinstance(state, dict) or not isinstance(state.get("local"), dict):
        return _unknown("Missing or malformed local peer data.")
    local = state["local"]
    if not isinstance(local.get("id"), str) or not local["id"]:
        return _unknown("Missing local peer identity.")
    peers = state.get("peers")
    if not isinstance(peers, list) or not isinstance(remote_snapshots, list):
        return _unknown("Missing or malformed peer list.")
    by_id = {}
    for peer in peers:
        if not isinstance(peer, dict) or not isinstance(peer.get("id"), str):
            return _unknown("Malformed peer snapshot.")
        if peer["id"] in by_id:
            return _unknown("Duplicate peer identity.")
        by_id[peer["id"]] = peer
    # /api/state collects local first, then peers. The latter may be newer.
    by_id.setdefault(local["id"], local)
    for peer in remote_snapshots:
        if not isinstance(peer, dict) or not isinstance(peer.get("id"), str):
            return _unknown("Malformed direct peer snapshot.")
        by_id[peer["id"]] = peer
    local = by_id[local["id"]]
    session = local.get("session")
    if session is not None:
        try:
            session = Manifest.model_validate(session).model_dump()
        except (ValidationError, TypeError):
            return _unknown("Malformed session manifest.")
        members = session["members"]
        if (len(members) not in (2, 3) or len(set(members)) != len(members)
                or local["id"] not in members or session["coordinator"] not in members):
            return _unknown("Invalid session membership.")
        if not set(members).issubset(by_id):
            return _unknown("Required session members are missing or the peer roster differs.")
    else:
        members = list(by_id)
    expected = state.get("expected_peers", len(members))
    if not isinstance(expected, int) or expected != len(members):
        return _unknown("Peer count does not match the configured roster.")

    blockers = []
    coordinator_id = session["coordinator"] if session else None
    coordinator = by_id.get(coordinator_id, {})
    for pid in members:
        peer = by_id[pid]
        name = str(peer.get("name") or pid)
        if peer.get("online") is not True:
            blockers.append(f"Peer unreachable: {name} ({peer.get('error') or 'offline'}).")
            continue
        if peer.get("sharing") is not True:
            blockers.append(f"Peer not sharing: {name}.")
        issues = peer.get("setup_issues", [])
        if not isinstance(issues, list) or any(not isinstance(s, str) for s in issues):
            return _unknown(f"Malformed setup status for {name}.")
        for issue in issues:
            coordinator_only = issue.startswith((
                "Model file missing on this laptop",
                "Set one coordinator device per peer",
                "The llama-server executable is missing",
            ))
            # Before a session, only this laptop's ability to initiate is relevant.
            if pid != (coordinator_id or local['id']) and coordinator_only:
                continue
            blockers.append(f"Setup issue ({name}): {issue}")
        if not session:
            continue
        if peer.get("session") != session:
            blockers.append(f"Session mismatch: {name}; manifests must agree.")
        runtime = peer.get("runtime")
        if not isinstance(runtime, dict):
            return _unknown(f"Missing native runtime data for {name}.")
        if runtime.get("running") is not True:
            blockers.append(f"Native runtime is not running on {name}.")
        expected_role = "coordinator" if pid == coordinator_id else "worker"
        if runtime.get("role") != expected_role:
            blockers.append(f"Native runtime role mismatch on {name}.")
        allowed = {"ready", "computing"} if pid == coordinator_id else {"worker_ready"}
        if peer.get("state") not in allowed:
            blockers.append(f"{name} is {peer.get('state')!r}, not ready ({peer.get('error') or 'awaiting runtime'}).")

    if not session:
        blockers.append("No active session. Start one from the coordinator.")
    else:
        placement = (coordinator.get("runtime") or {}).get("placement")
        if not isinstance(placement, dict) or any(not isinstance(v, str) for v in placement.values()):
            return _unknown("Missing or malformed native layer placement.")
        if len(set(placement.values())) < len(members):
            blockers.append("Native logs do not show model layers on every selected device.")
    status = STATUS_BLOCKED if blockers else (
        STATUS_BUSY if coordinator.get("state") == "computing" or coordinator.get("busy") is True
        else STATUS_READY
    )
    runtime = local.get("runtime") if isinstance(local.get("runtime"), dict) else {}
    model = state.get("model") if isinstance(state.get("model"), dict) else {}
    rss = runtime.get("rss_bytes")
    detail = {
        "status": status, "blockers": blockers,
        "local": {"peer_id": local["id"], "state": local.get("state"),
                  "sharing": local.get("sharing"), "session_id": session["id"] if session else None,
                  "coordinator": coordinator_id},
        "runtime": {key: runtime.get(key) for key in
                    ("running", "role", "graph_submissions", "placement", "memory_note")},
        "peers": [{"id": pid, "name": by_id[pid].get("name") or pid,
                   "online": by_id[pid].get("online"), "sharing": by_id[pid].get("sharing"),
                   "state": by_id[pid].get("state"),
                   "error": by_id[pid].get("error") if not by_id[pid].get("online") else None}
                  for pid in members],
        "model": {key: model.get(key) for key in ("name", "present", "file_bytes")},
        "note": "Point-in-time readiness only. RPC graphs count submissions, not tokens or completed kernels.",
    }
    detail["runtime"]["rss_bytes"] = rss if isinstance(rss, (int, float)) else None
    return status, blockers, detail


def format_report(status: str, blockers: List[str], detail: Dict) -> str:
    lines = []
    lines.append(f"Open Swarm demo readiness check")
    lines.append("=" * 40)

    status_symbols = {STATUS_READY: "✓", STATUS_BUSY: "⏳", STATUS_BLOCKED: "✗", STATUS_UNKNOWN: "?"}
    sym = status_symbols.get(status, "?")
    lines.append(f"Status: {sym} {status}")
    lines.append("")

    loc = detail.get("local", {})
    lines.append(f"Local peer : {loc.get('peer_id')}  state={loc.get('state')}  sharing={loc.get('sharing')}")
    if loc.get("session_id"):
        lines.append(f"Session    : {loc['session_id']}  coordinator={loc.get('coordinator')}")
    else:
        lines.append("Session    : none")

    rt = detail.get("runtime", {})
    lines.append(f"Runtime    : running={rt.get('running')}  role={rt.get('role')}  "
                 f"graphs={rt.get('graph_submissions')}")
    placement = rt.get("placement", {})
    if placement:
        label = "Placement" if rt.get('running') else "Last placement"
        lines.append(f"{label}  : {placement}  (layer→device, from native logs)")
    rss = rt.get("rss_bytes")
    if rss is not None:
        lines.append(f"RSS        : {rss / 1e9:.2f} GB  ({rt.get('memory_note', '')})")

    lines.append("")
    lines.append("Peers:")
    for p in detail.get("peers", []):
        online_sym = "✓" if p.get("online") else "✗"
        share_sym = "sharing" if p.get("sharing") else "not sharing"
        err = f"  [{p['error']}]" if p.get("error") else ""
        lines.append(f"  {online_sym} {p.get('name', p.get('id'))}  "
                     f"state={p.get('state')}  {share_sym}{err}")

    model = detail.get("model", {})
    lines.append("")
    lines.append(f"Model      : {model.get('name')}  present={model.get('present')}  "
                 f"size={model.get('file_bytes')}")

    if blockers:
        lines.append("")
        lines.append("Blockers:")
        for b in blockers:
            lines.append(f"  • {b}")

    lines.append(detail.get("note", ""))
    lines.append("")
    return "\n".join(lines)


def run(as_json: bool = False) -> int:
    try:
        settings = load_settings()
    except (OSError, ValueError):
        status, blockers, detail = _unknown("Could not read a valid local configuration.")
        settings = None
    if settings is not None:
        state, error = _fetch_state(f"http://127.0.0.1:{settings.api_port}", settings.token)
        if state is None:
            status, blockers, detail = _unknown(f"Cannot read local API: {error}. Is scripts/serve.py running?")
        elif not isinstance(state.get("local"), dict) or state["local"].get("id") != settings.peer_id:
            status, blockers, detail = _unknown("Local API identity does not match this configuration.")
        else:
            snapshots = []
            session = state['local'].get('session')
            members = session.get('members') if isinstance(session, dict) else None
            configured = [p.id for p in settings.peers]
            selected = members if isinstance(members, list) else configured
            for peer in settings.peers:
                if peer.id == settings.peer_id or peer.id not in selected:
                    continue
                snapshot, error = _fetch_peer(peer.url, settings.token)
                if snapshot is None or snapshot.get("id") != peer.id:
                    snapshot = {"id": peer.id, "name": peer.name, "online": False,
                                "error": error or "Peer identity does not match roster"}
                snapshots.append(snapshot)
            # The configured roster is authoritative, including on older API versions.
            state = {**state, "expected_peers": len(selected)}
            status, blockers, detail = analyse(state, snapshots)
            actual = {p.get("id") for p in detail["peers"]}
            if status in (STATUS_READY, STATUS_BUSY) and (actual != set(selected)
                    or selected != [pid for pid in configured if pid in selected]):
                status, blockers, detail = _unknown("API membership does not match the configured roster.")
    detail = _redact(detail, (settings.token,) if settings else ())
    print(json.dumps(detail, indent=2) if as_json else format_report(status, detail["blockers"], detail))
    return {STATUS_READY: EXIT_READY, STATUS_BUSY: EXIT_BUSY,
            STATUS_BLOCKED: EXIT_BLOCKED, STATUS_UNKNOWN: EXIT_UNKNOWN}[status]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    args = parser.parse_args()
    sys.exit(run(as_json=args.json))


if __name__ == "__main__":
    main()
