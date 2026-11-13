"""Tests for scripts/check_demo.py – analysis logic only.

These tests use only the analyse() function and helpers from check_demo.
They never make real network connections, never read config/local.json,
and never start or stop any service.

All tests are clearly separate from physical cluster observations.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Allow importing check_demo from scripts/ without installing
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from check_demo import (
    EXIT_BLOCKED,
    EXIT_BUSY,
    EXIT_READY,
    EXIT_UNKNOWN,
    STATUS_BLOCKED,
    STATUS_BUSY,
    STATUS_READY,
    STATUS_UNKNOWN,
    _redact,
    analyse,
    format_report,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SESSION = {
    "id": "a" * 32,
    "coordinator": "a",
    "members": ["a", "b"],
    "model_name": "Test model",
    "model_sha256": "c" * 64,
    "runtime_revision": "5676dfbe01e7ebe0387913680eee0ed39bf4a363",
    "context": 2048,
}

RUNTIME_READY = {
    "running": True,
    "role": "coordinator",
    "graph_submissions": 42,
    "placement": {"0": "MTL0", "1": "RPC0"},
    "rss_bytes": 3_200_000_000,
    "memory_note": "Sampled RSS; not a hard cap.",
}

RUNTIME_IDLE = {
    "running": False,
    "role": None,
    "graph_submissions": 0,
    "placement": {},
    "rss_bytes": None,
    "memory_note": "Sampled RSS; not a hard cap.",
}


def make_state(
    *,
    local_state: str = "ready",
    sharing: bool = True,
    session=SESSION,
    runtime=RUNTIME_READY,
    peer_b_online: bool = True,
    peer_b_sharing: bool = True,
    peer_b_state: str = "worker_ready",
    peer_b_session=SESSION,
    setup_issues=None,
) -> dict:
    return {
        "local": {
            "id": "a",
            "name": "M4 Pro",
            "state": local_state,
            "sharing": sharing,
            "session": session,
            "runtime": runtime,
            "setup_issues": setup_issues or [],
            "error": None,
            "busy": local_state == "computing",
        },
        "peers": [
            {
                "id": "a",
                "name": "M4 Pro",
                "online": True,
                "sharing": sharing,
                "state": local_state,
                "session": session,
                "error": None,
            },
            {
                "id": "b",
                "name": "M3 Pro",
                "online": peer_b_online,
                "sharing": peer_b_sharing,
                "state": peer_b_state,
                "session": peer_b_session,
                "error": None if peer_b_online else "connection refused",
            },
        ],
        "model": {
            "name": "Granite 4.2 8B",
            "present": True,
            "file_bytes": 5_354_000_000,
        },
    }


# ---------------------------------------------------------------------------
# Test: healthy two-peer session
# ---------------------------------------------------------------------------

def test_healthy_two_peer_ready():
    """Both peers online, sharing, coordinator ready, session agrees."""
    state = make_state()
    status, blockers, detail = analyse(state, [])
    assert status == STATUS_READY
    assert blockers == []
    assert detail["local"]["state"] == "ready"
    assert detail["runtime"]["running"] is True
    assert detail["runtime"]["graph_submissions"] == 42


# ---------------------------------------------------------------------------
# Test: peer B unreachable
# ---------------------------------------------------------------------------

def test_peer_b_unreachable():
    state = make_state(peer_b_online=False, peer_b_sharing=False, peer_b_state="offline",
                       peer_b_session=None)
    status, blockers, detail = analyse(state, [])
    assert status == STATUS_BLOCKED
    assert any("unreachable" in b for b in blockers)


# ---------------------------------------------------------------------------
# Test: peer B online but not sharing
# ---------------------------------------------------------------------------

def test_peer_b_not_sharing():
    state = make_state(peer_b_sharing=False, peer_b_state="off", peer_b_session=None)
    status, blockers, detail = analyse(state, [])
    assert status == STATUS_BLOCKED
    assert any("not sharing" in b for b in blockers)


# ---------------------------------------------------------------------------
# Test: session ID mismatch between peers
# ---------------------------------------------------------------------------

def test_session_mismatch():
    different_session = {**SESSION, "id": "b" * 32}
    state = make_state(peer_b_session=different_session)
    status, blockers, detail = analyse(state, [])
    assert status == STATUS_BLOCKED
    assert any("mismatch" in b.lower() for b in blockers)


# ---------------------------------------------------------------------------
# Test: coordinator is loading (model not yet ready)
# ---------------------------------------------------------------------------

def test_coordinator_loading():
    state = make_state(local_state="loading", runtime=RUNTIME_IDLE,
                       peer_b_state="worker_ready")
    status, blockers, detail = analyse(state, [])
    assert status == STATUS_BLOCKED
    assert any("loading" in b for b in blockers)


# ---------------------------------------------------------------------------
# Test: coordinator is busy (computing)
# ---------------------------------------------------------------------------

def test_coordinator_busy():
    state = make_state(local_state="computing")
    status, blockers, detail = analyse(state, [])
    assert status == STATUS_BUSY


# ---------------------------------------------------------------------------
# Test: coordinator failed runtime
# ---------------------------------------------------------------------------

def test_coordinator_failed_runtime():
    failed_runtime = {**RUNTIME_IDLE, "running": False}
    state = make_state(local_state="failed", runtime=failed_runtime)
    # App sets error on failure
    state["local"]["error"] = "Native runtime exited unexpectedly"
    status, blockers, detail = analyse(state, [])
    assert status == STATUS_BLOCKED
    assert any("failed" in b for b in blockers)


# ---------------------------------------------------------------------------
# Test: local native process not running during active session
# ---------------------------------------------------------------------------

def test_native_process_not_running():
    state = make_state(local_state="ready", runtime={**RUNTIME_READY, "running": False})
    status, blockers, detail = analyse(state, [])
    assert status == STATUS_BLOCKED
    assert any("not running" in b for b in blockers)


# ---------------------------------------------------------------------------
# Test: local peer not sharing
# ---------------------------------------------------------------------------

def test_local_not_sharing():
    state = make_state(sharing=False, session=None, runtime=RUNTIME_IDLE,
                       local_state="off")
    status, blockers, detail = analyse(state, [])
    assert status == STATUS_BLOCKED
    assert any("not sharing" in b.lower() for b in blockers)


# ---------------------------------------------------------------------------
# Test: setup issues propagate as blockers
# ---------------------------------------------------------------------------

def test_setup_issues_become_blockers():
    state = make_state(
        setup_issues=["Build the pinned llama.cpp RPC runtime.", "Model file missing on this laptop."]
    )
    status, blockers, detail = analyse(state, [])
    assert status == STATUS_BLOCKED
    assert any("llama.cpp" in b for b in blockers)
    assert any("Model file" in b for b in blockers)


# ---------------------------------------------------------------------------
# Test: no active session
# ---------------------------------------------------------------------------

def test_no_session_blocked():
    state = make_state(session=None, local_state="offered", runtime=RUNTIME_IDLE)
    status, blockers, detail = analyse(state, [])
    assert status == STATUS_BLOCKED
    assert any("session" in b.lower() for b in blockers)


# ---------------------------------------------------------------------------
# Test: malformed / missing data never becomes READY
# ---------------------------------------------------------------------------

def test_malformed_state_is_unknown_or_blocked():
    """An empty / structurally invalid state must not produce READY."""
    status, blockers, detail = analyse({}, [])
    assert status != STATUS_READY
    assert len(blockers) > 0


def test_missing_local_key():
    status, blockers, detail = analyse({"peers": [], "model": {}}, [])
    assert status != STATUS_READY


def test_none_values_in_runtime():
    state = make_state()
    state["local"]["runtime"] = None
    status, blockers, detail = analyse(state, [])
    # Should not raise; state depends on session being present
    assert status in (STATUS_READY, STATUS_BLOCKED, STATUS_BUSY, STATUS_UNKNOWN)


# ---------------------------------------------------------------------------
# Test: remote snapshot enriches peer picture
# ---------------------------------------------------------------------------

def test_remote_snapshot_updates_peer_state():
    """A direct peer snapshot showing 'worker_ready' should not add blockers."""
    state = make_state(peer_b_state="offered")  # stale state from /api/state
    remote_b = {
        "id": "b", "name": "M3 Pro", "online": True, "sharing": True,
        "state": "worker_ready", "session": SESSION, "error": None,
    }
    status, blockers, detail = analyse(state, [remote_b])
    assert status == STATUS_READY
    assert blockers == []


# ---------------------------------------------------------------------------
# Test: redaction never leaks credentials
# ---------------------------------------------------------------------------

def test_redact_removes_token_keys():
    obj = {
        "token": "super-secret",
        "nested": {"control_token": "also-secret"},
        "safe_key": "visible",
        "list": [{"token": "hidden"}, "plain"],
    }
    result = _redact(obj)
    assert result["token"] == "***REDACTED***"
    assert result["nested"]["control_token"] == "***REDACTED***"
    assert result["safe_key"] == "visible"
    assert result["list"][0]["token"] == "***REDACTED***"
    assert result["list"][1] == "plain"


def test_redact_does_not_modify_non_token_keys():
    obj = {"peer_id": "b", "state": "ready", "sharing": True}
    result = _redact(obj)
    assert result == obj


# ---------------------------------------------------------------------------
# Test: format_report contains key fields and no token-like strings
# ---------------------------------------------------------------------------

def test_format_report_basic():
    state = make_state()
    status, blockers, detail = analyse(state, [])
    report = format_report(status, blockers, detail)
    assert "READY" in report
    assert "peer_id" not in report  # internal key, not label
    assert "M4 Pro" in report or "M3 Pro" in report
    # Must not contain anything that looks like our test session id
    assert "token" not in report.lower()


def test_format_report_shows_blockers():
    state = make_state(peer_b_online=False, peer_b_sharing=False,
                       peer_b_state="offline", peer_b_session=None)
    status, blockers, detail = analyse(state, [])
    report = format_report(status, blockers, detail)
    assert "Blockers" in report
    assert "unreachable" in report.lower()
