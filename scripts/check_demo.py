"""Read-only demo readiness checker for Open Swarm.

Queries the authenticated peer API and reports whether the local peer and
its configured counterparts are ready to accept a new inference request.

Exit codes:
  0  READY   – every peer online, sharing, session active and coordinator ready
  1  BUSY    – session exists but coordinator is currently computing
  2  BLOCKED – reachable peers but something prevents a new request
  3  UNKNOWN – cannot determine state (timeout, auth failure, missing data)

Usage:
  .venv/bin/python scripts/check_demo.py [--json]

Never prints credentials or guest pass tokens.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Allow running from repo root without installing the package.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

import httpx

from swarm.config import load_settings

# ---------------------------------------------------------------------------
# Exit code constants
# ---------------------------------------------------------------------------
EXIT_READY = 0
EXIT_BUSY = 1
EXIT_BLOCKED = 2
EXIT_UNKNOWN = 3

STATUS_READY = "READY"
STATUS_BUSY = "BUSY"
STATUS_BLOCKED = "BLOCKED"
STATUS_UNKNOWN = "UNKNOWN"

READY_STATES = {"ready", "worker_ready"}
ACTIVE_STATES = {"ready", "worker_ready", "computing", "loading", "reserved"}


def _redact(obj: Any, _depth: int = 0) -> Any:
    """Recursively remove any key containing 'token' or 'pass'."""
    if _depth > 10:
        return obj
    if isinstance(obj, dict):
        return {
            k: "***REDACTED***"
            if any(word in k.lower() for word in ("token", "pass", "secret", "credential"))
            else _redact(v, _depth + 1)
            for k, v in obj.items()
        }
    if isinstance(obj, list):
        return [_redact(i, _depth + 1) for i in obj]
    return obj


# ---------------------------------------------------------------------------
# Data collection
# ---------------------------------------------------------------------------

def _fetch_state(base_url: str, token: str, timeout: float = 4.0) -> Tuple[Optional[Dict], Optional[str]]:
    """Return (state_dict, error_string). Never raises."""
    try:
        response = httpx.get(
            base_url.rstrip("/") + "/api/state",
            headers={"Authorization": "Bearer " + token},
            timeout=timeout,
            follow_redirects=False,
        )
        if response.status_code == 401:
            return None, "authentication failure (401) – token mismatch"
        if response.status_code == 403:
            return None, "forbidden (403) – request not from localhost"
        if response.is_error:
            return None, f"HTTP {response.status_code}"
        return response.json(), None
    except httpx.ConnectError:
        return None, "connection refused"
    except httpx.TimeoutException:
        return None, "timeout"
    except Exception as exc:  # pragma: no cover
        return None, str(exc)


def _fetch_peer(base_url: str, token: str, timeout: float = 4.0) -> Tuple[Optional[Dict], Optional[str]]:
    """Return (peer_dict, error_string). Never raises."""
    try:
        response = httpx.get(
            base_url.rstrip("/") + "/api/peer",
            headers={"Authorization": "Bearer " + token},
            timeout=timeout,
            follow_redirects=False,
        )
        if response.status_code == 401:
            return None, "authentication failure (401)"
        if response.is_error:
            return None, f"HTTP {response.status_code}"
        return response.json(), None
    except httpx.ConnectError:
        return None, "connection refused"
    except httpx.TimeoutException:
        return None, "timeout"
    except Exception as exc:  # pragma: no cover
        return None, str(exc)


# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------

def analyse(state: Dict, remote_snapshots: List[Dict]) -> Tuple[str, List[str], Dict]:
    """
    Return (status, blockers, detail_dict).

    status   – one of READY / BUSY / BLOCKED / UNKNOWN
    blockers – human-readable list of reasons why we are not READY
    detail   – structured data for --json output (no credentials)
    """
    blockers: List[str] = []

    local = state.get("local", {})
    peers_in_state = state.get("peers", [])
    model_info = state.get("model", {})

    local_state = local.get("state", "")
    local_sharing = local.get("sharing", False)
    local_session = local.get("session")
    local_runtime = local.get("runtime") or {}
    setup_issues = local.get("setup_issues", [])

    # --- local sharing ---
    if not local_sharing:
        blockers.append("Local peer is not sharing (click 'Share this laptop').")

    # --- setup issues reported by the app ---
    for issue in setup_issues:
        blockers.append(f"Setup issue: {issue}")

    # --- session and state analysis ---
    coordinator_id = (local_session or {}).get("coordinator") if local_session else None

    # Identify coordinator peer data from the full peers list
    coordinator_peer = None
    for p in peers_in_state:
        if p.get("id") == coordinator_id:
            coordinator_peer = p
            break

    # Merge remote snapshots (may have fresher data for other peers)
    remote_by_id = {r["id"]: r for r in remote_snapshots if isinstance(r, dict) and "id" in r}

    # Build combined peer picture
    all_peers: List[Dict] = []
    seen_ids: set = set()
    for p in peers_in_state:
        pid = p.get("id")
        if pid in remote_by_id:
            merged = {**p, **remote_by_id[pid]}
        else:
            merged = p
        all_peers.append(merged)
        seen_ids.add(pid)
    for pid, p in remote_by_id.items():
        if pid not in seen_ids:
            all_peers.append(p)

    # --- peer reachability and sharing ---
    offline_peers = []
    not_sharing = []
    for p in all_peers:
        pid = p.get("id")
        if pid == local.get("id"):
            continue  # local already checked
        if not p.get("online", False):
            offline_peers.append(p.get("name", pid) + f" ({p.get('error', 'offline')})")
        elif not p.get("sharing", False):
            not_sharing.append(p.get("name", pid))

    for name in offline_peers:
        blockers.append(f"Peer unreachable: {name}")
    for name in not_sharing:
        blockers.append(f"Peer not sharing: {name}")

    # --- session agreement ---
    if local_session:
        session_id = local_session.get("id")
        for p in all_peers:
            if p.get("id") == local.get("id"):
                continue
            peer_session = (p.get("session") or {})
            peer_session_id = peer_session.get("id") if peer_session else None
            if p.get("online") and peer_session_id != session_id:
                blockers.append(
                    f"Session mismatch: {p.get('name', p.get('id'))} has session "
                    f"{peer_session_id!r}, coordinator has {session_id!r}."
                )

    # --- coordinator state ---
    if local_session is None:
        # No active session yet — only blocked if we also have sharing issues
        if not blockers:
            blockers.append("No active session. Start one from the coordinator.")
    else:
        coord_state = (coordinator_peer or local).get("state", "")
        if coord_state == "failed":
            coord_error = (coordinator_peer or local).get("error", "unknown error")
            blockers.append(f"Coordinator is in failed state: {coord_error}")
        elif coord_state == "loading":
            blockers.append("Coordinator is still loading the model.")
        elif coord_state == "reserved":
            blockers.append("Session is reserved but commit not yet complete.")
        elif coord_state == "computing":
            # This is BUSY not BLOCKED
            pass
        elif coord_state not in READY_STATES:
            blockers.append(f"Coordinator state is '{coord_state}' (expected ready or worker_ready).")

    # --- native runtime ---
    runtime_running = local_runtime.get("running", False)
    runtime_role = local_runtime.get("role")
    placement = local_runtime.get("placement", {})
    graph_submissions = local_runtime.get("graph_submissions", 0)

    if local_session and not runtime_running:
        blockers.append("Local native runtime process is not running.")

    # --- determine final status ---
    # BUSY if coordinator is computing and no other blockers except busy
    coord_state_final = (coordinator_peer or local).get("state", "")
    if coord_state_final == "computing" and not any("failed" in b or "mismatch" in b or "unreachable" in b
                                                     or "not sharing" in b or "Setup issue" in b
                                                     or "not running" in b
                                                     for b in blockers):
        status = STATUS_BUSY
    elif blockers:
        status = STATUS_BLOCKED
    else:
        # Everything looks good
        if local_session and coord_state_final in READY_STATES and not blockers:
            status = STATUS_READY
        else:
            status = STATUS_BLOCKED
            if not blockers:
                blockers.append("No active session or coordinator not ready.")

    # --- build detail dict (no credentials) ---
    detail = {
        "status": status,
        "blockers": blockers,
        "local": {
            "peer_id": local.get("id"),
            "state": local_state,
            "sharing": local_sharing,
            "session_id": (local_session or {}).get("id"),
            "coordinator": coordinator_id,
            "setup_issues": setup_issues,
        },
        "runtime": {
            "running": runtime_running,
            "role": runtime_role,
            "graph_submissions": graph_submissions,
            "placement": {str(k): v for k, v in (placement or {}).items()},
            "rss_bytes": local_runtime.get("rss_bytes"),
            "memory_note": local_runtime.get("memory_note"),
        },
        "peers": [
            {
                "id": p.get("id"),
                "name": p.get("name"),
                "online": p.get("online"),
                "sharing": p.get("sharing"),
                "state": p.get("state"),
                "session_id": (p.get("session") or {}).get("id") if p.get("session") else None,
                "error": p.get("error") if not p.get("online") else None,
            }
            for p in all_peers
        ],
        "model": {
            "name": model_info.get("name"),
            "present": model_info.get("present"),
            "file_bytes": model_info.get("file_bytes"),
        },
    }

    return status, blockers, detail


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------

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
        lines.append(f"Placement  : {placement}  (layer→device, from native logs)")
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

    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def run(as_json: bool = False) -> int:
    settings = load_settings()
    local_url = f"http://127.0.0.1:{settings.api_port}"

    state, err = _fetch_state(local_url, settings.token)
    if state is None:
        result = {
            "status": STATUS_UNKNOWN,
            "blockers": [f"Could not reach local API at {local_url}: {err}"],
            "local": {}, "runtime": {}, "peers": [], "model": {},
        }
        if as_json:
            print(json.dumps(result, indent=2))
        else:
            print(f"UNKNOWN – Cannot reach local API ({err})")
            print(f"  Tried: {local_url}")
            print("  Is scripts/serve.py running?")
        return EXIT_UNKNOWN

    # Fetch remote peer snapshots directly for cross-checking
    remote_snapshots: List[Dict] = []
    for peer in settings.peers:
        if peer.id == settings.peer_id:
            continue
        snap, _ = _fetch_peer(peer.url, settings.token)
        if snap:
            remote_snapshots.append(snap)

    status, blockers, detail = analyse(state, remote_snapshots)

    if as_json:
        print(json.dumps(detail, indent=2))
    else:
        print(format_report(status, blockers, detail))

    exit_map = {STATUS_READY: EXIT_READY, STATUS_BUSY: EXIT_BUSY,
                STATUS_BLOCKED: EXIT_BLOCKED, STATUS_UNKNOWN: EXIT_UNKNOWN}
    return exit_map.get(status, EXIT_UNKNOWN)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON instead of human text")
    args = parser.parse_args()
    sys.exit(run(as_json=args.json))


if __name__ == "__main__":
    main()
