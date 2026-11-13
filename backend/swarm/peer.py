from __future__ import annotations

import asyncio
import hashlib
import json
import time
import uuid
from collections import deque
from datetime import datetime, timezone
from typing import List, Optional

import httpx
import psutil
from fastapi import HTTPException
from pydantic import BaseModel, Field

from .config import RUNTIME_REVISION, Settings
from .runtime import NativeRuntime, inference_command, worker_command


class Manifest(BaseModel):
    id: str = Field(pattern=r"^[a-f0-9]{32}$")
    coordinator: str
    members: List[str]
    model_name: str
    model_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    runtime_revision: str = RUNTIME_REVISION
    context: int = 2048


class Generation(BaseModel):
    prompt: str = Field(min_length=1, max_length=6000)
    max_tokens: int = Field(default=128, ge=1, le=256)


def model_hash(path):
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class PeerService:
    def __init__(self, settings: Settings, runtime=None):
        self.settings = settings
        self.runtime = runtime or NativeRuntime(settings)
        self.manifest: Optional[Manifest] = None
        self.state = "off"
        self.sharing = False
        self.error = None
        self.lock = asyncio.Lock()
        self.busy = False
        self.events = deque(maxlen=60)
        self.client = httpx.AsyncClient(timeout=httpx.Timeout(5), trust_env=False)
        self.monitor_task = None
        self.start_task = None
        self.request_count = 0
        self.last_result = None
        self._health_session_id = None
        self._peer_health_misses = {}
        self.marker = settings.state_path / "session.json"
        self.unclean = None
        if self.marker.exists():
            self.state = "failed"
            self.error = "Previous session did not shut down cleanly. Reset before sharing."
            self.unclean = json.loads(self.marker.read_text())

    def event(self, message, kind="info"):
        self.events.append({"at": datetime.now(timezone.utc).isoformat(), "message": message, "kind": kind})

    def persist(self):
        if self.manifest:
            record = {"manifest": self.manifest.model_dump(), "pid": None, "created": None}
            if self.runtime.running:
                record["pid"] = self.runtime.process.pid
                try:
                    record["created"] = psutil.Process(record["pid"]).create_time()
                except psutil.Error:
                    pass
            temporary = self.marker.with_suffix(".tmp")
            temporary.write_text(json.dumps(record))
            temporary.replace(self.marker)

    def setup_issues(self):
        issues = []
        if len(self.settings.peers) not in (2, 3):
            issues.append("Configure two or three peers in config/local.json.")
        if not self.settings.binary("ggml-rpc-server").is_file():
            issues.append("Build the pinned llama.cpp RPC runtime.")
        if not self.settings.binary("llama-server").is_file():
            issues.append("The llama-server executable is missing.")
        if not self.settings.model.is_file():
            issues.append("Model file missing on this laptop; it can contribute after setup, but cannot coordinate yet.")
        if not self.settings.devices or len(self.settings.devices) != len(self.settings.peers):
            issues.append("Set one coordinator device per peer after running device discovery.")
        return issues

    def snapshot(self):
        return {
            "id": self.settings.peer_id, "name": self.settings.name,
            "state": self.state, "sharing": self.sharing, "online": True,
            "offer_bytes": self.settings.offer_bytes,
            "session": self.manifest.model_dump() if self.manifest else None,
            "error": self.error, "busy": self.busy, "runtime": self.runtime.snapshot(),
            "setup_issues": self.setup_issues(), "events": list(self.events),
            "request_count": self.request_count, "last_result": self.last_result,
        }

    async def call(self, peer, method, path, **kwargs):
        response = await self.client.request(method, peer.url.rstrip("/") + path,
                                             headers={"Authorization": "Bearer " + self.settings.token}, **kwargs)
        if response.is_error:
            try:
                message = response.json().get("detail", response.text)
            except ValueError:
                message = response.text
            raise RuntimeError(f"{peer.name}: {message}")
        return response.json()

    async def peers_snapshot(self):
        async def read(peer):
            if peer.id == self.settings.peer_id:
                return self.snapshot()
            try:
                state = await self.call(peer, "GET", "/api/peer")
                if state.get("id") != peer.id:
                    raise RuntimeError("Peer identity does not match roster")
                return state
            except (httpx.HTTPError, RuntimeError) as exc:
                return {"id": peer.id, "name": peer.name, "online": False, "state": "offline", "error": str(exc)}
        if not self.settings.peers:
            return [self.snapshot()]
        return list(await asyncio.gather(*(read(p) for p in self.settings.peers)))

    async def share(self, enabled):
        if enabled:
            async with self.lock:
                if self.state == "failed":
                    raise HTTPException(409, "Reset the failed session before sharing")
                self.sharing = True
                if not self.manifest:
                    self.state = "offered"
                self.event(f"This laptop offers up to {self.settings.offer_bytes / 1e9:.1f} GB for the next session.")
        else:
            # Revoke consent before the stop broadcast, so a competing start cannot reserve it.
            async with self.lock:
                self.sharing = False
            await self.stop_all()
            self.state = "off"
            self.event("Contribution withdrawn; native work stopped.")
        return self.snapshot()

    async def prepare(self, manifest):
        async with self.lock:
            if not self.sharing or self.unclean:
                raise HTTPException(409, "Owner has not enabled sharing, or reset is required")
            if manifest.members != [p.id for p in self.settings.peers]:
                raise HTTPException(409, "Peer rosters differ; use the same ordered roster on all laptops")
            if len(manifest.members) not in (2, 3) or manifest.coordinator not in manifest.members:
                raise HTTPException(400, "This demo requires two or three members and a member coordinator")
            if manifest.runtime_revision != RUNTIME_REVISION or manifest.context != 2048:
                raise HTTPException(409, "Runtime or context configuration mismatch")
            if self.settings.model_sha256 and manifest.model_sha256 != self.settings.model_sha256:
                raise HTTPException(409, "Model hash differs from this peer's configured artifact")
            if self.manifest:
                if self.manifest == manifest:
                    return self.snapshot()
                raise HTTPException(409, "Already reserved by another session")
            if self.state == "failed" or self.runtime.running:
                raise HTTPException(409, "Reset before starting another session")
            if not self.settings.binary("ggml-rpc-server").is_file():
                raise HTTPException(409, "RPC runtime is not built")
            self.manifest = manifest
            self.state = "reserved"
            self.error = None
            self.persist()
            self.event("Reserved for session " + manifest.id[:8])
            return self.snapshot()

    async def commit(self, manifest):
        async with self.lock:
            if self.manifest != manifest:
                raise HTTPException(409, "Commit must match the reserved manifest")
            if self.state != "reserved":
                if self.state in ("worker_ready", "loading", "ready", "computing"):
                    return self.snapshot()
                raise HTTPException(409, "Session is not reserved")
            try:
                if manifest.coordinator != self.settings.peer_id:
                    await self.runtime.start(worker_command(self.settings), "worker", manifest.id)
                    self.persist()
                    await self.wait_worker()
                    self.state = "worker_ready"
                else:
                    self.state = "loading"
                return self.snapshot()
            except Exception as exc:
                await self.runtime.stop()
                self.state, self.error = "failed", str(exc)
                raise HTTPException(500, self.error)

    async def wait_worker(self):
        for _ in range(80):
            if not self.runtime.running:
                raise RuntimeError("RPC worker exited; inspect its native logs")
            try:
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(self.settings.bind_host, self.settings.rpc_port), 1)
                writer.close()
                await writer.wait_closed()
                return
            except (OSError, asyncio.TimeoutError):
                await asyncio.sleep(0.1)
        raise RuntimeError("RPC worker did not open its configured port")

    async def begin(self):
        if self.start_task and not self.start_task.done():
            raise HTTPException(409, "Session start already in progress")
        if self.manifest or self.state == "failed":
            raise HTTPException(409, "Stop/reset the current session first")
        if not self.sharing:
            raise HTTPException(409, "Enable your contribution first")
        issues = self.setup_issues()
        if issues:
            raise HTTPException(409, " ".join(issues))
        self.start_task = asyncio.create_task(self._start())
        return {"status": "starting"}

    async def _start(self):
        manifest = None
        try:
            self.event("Verifying model SHA-256 before loading.")
            digest = await asyncio.to_thread(model_hash, self.settings.model)
            if self.settings.model_sha256 and digest != self.settings.model_sha256:
                raise RuntimeError("Downloaded model does not match the configured SHA-256")
            manifest = Manifest(id=uuid.uuid4().hex, coordinator=self.settings.peer_id,
                                members=[p.id for p in self.settings.peers],
                                model_name=self.settings.model_name, model_sha256=digest)
            await self.prepare(manifest)
            for peer in self.settings.peers:
                if peer.id != self.settings.peer_id:
                    await self.call(peer, "POST", "/api/sessions/prepare", json=manifest.model_dump())
            for peer in self.settings.peers:
                if peer.id != self.settings.peer_id:
                    await self.call(peer, "POST", "/api/sessions/commit", json=manifest.model_dump(), timeout=15)
            await self.commit(manifest)
            async with self.lock:
                if self.manifest != manifest or not self.sharing:
                    raise RuntimeError("Session was stopped before model loading")
                await self.runtime.start(inference_command(self.settings), "coordinator", manifest.id)
                self.persist()
            self.event("All peers acknowledged. Loading model across the configured devices.")
            deadline = time.monotonic() + self.settings.model_load_timeout_seconds
            while time.monotonic() < deadline:
                if self.manifest != manifest or not self.runtime.running:
                    raise RuntimeError("Model process exited or session stopped; inspect native logs")
                try:
                    response = await self.client.get(self.native_url + "/health", timeout=2)
                    if response.status_code == 200:
                        # Never mark all peers as contributors merely because they are connected.
                        placements = self.runtime.placement.values()
                        missing = [device for device in self.settings.devices if device not in placements]
                        if missing:
                            raise RuntimeError("No native layer assignment observed for: " + ", ".join(missing))
                        async with self.lock:
                            if self.manifest != manifest:
                                raise RuntimeError("Session changed during readiness check")
                            self.state = "ready"
                        self.event("Model ready. Native logs show layers assigned to every selected device.")
                        return
                except httpx.HTTPError:
                    pass
                await asyncio.sleep(0.5)
            raise RuntimeError(f"Model load exceeded the {self.settings.model_load_timeout_seconds}-second setup timeout")
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            reason = str(exc)
            if manifest:
                await self._stop_manifest(manifest)
            self.state, self.error = "failed", reason
            self.event(reason, "error")

    @property
    def native_url(self):
        return f"http://127.0.0.1:{self.settings.inference_port}"

    async def stop_local(self, session_id):
        async with self.lock:
            if not self.manifest or self.manifest.id != session_id:
                return {"stopped": False, "reason": "Session does not own this peer"}
            self.state = "stopping"
            await self.runtime.stop()
            self.manifest = None
            self.busy = False
            self.state = "offered" if self.sharing else "off"
            self.marker.unlink(missing_ok=True)
            self.event("Session stopped and owned native process exited.")
            return {"stopped": True}

    async def _stop_manifest(self, manifest):
        async def stop(peer):
            if peer.id == self.settings.peer_id:
                return await self.stop_local(manifest.id)
            try:
                return await self.call(peer, "POST", f"/api/sessions/{manifest.id}/stop", timeout=15)
            except (httpx.HTTPError, RuntimeError):
                self.event(f"Could not confirm stop on {peer.name}. Reset that laptop before retrying.", "error")
        await asyncio.gather(*(stop(peer) for peer in self.settings.peers))

    async def stop_all(self):
        if self.start_task and not self.start_task.done() and self.start_task != asyncio.current_task():
            self.start_task.cancel()
            try:
                await self.start_task
            except asyncio.CancelledError:
                pass
        if self.manifest:
            await self._stop_manifest(self.manifest)

    async def reset(self):
        if self.unclean and self.unclean.get("pid"):
            try:
                process = psutil.Process(self.unclean["pid"])
                if process.create_time() == self.unclean.get("created"):
                    raise HTTPException(409, "A native process from the previous run is still alive. Stop it on this laptop before resetting.")
            except psutil.NoSuchProcess:
                pass
            except psutil.AccessDenied:
                raise HTTPException(409, "Cannot verify that the previous native process exited")
        await self.stop_all()
        self.unclean = None
        self.marker.unlink(missing_ok=True)
        self.error = None
        self.state = "offered" if self.sharing else "off"
        return self.snapshot()

    async def check_required_peers(self):
        current = self.manifest
        if not current or current.coordinator != self.settings.peer_id:
            return
        snapshots = await self.peers_snapshot()
        if self.manifest != current or self.state not in ("ready", "computing"):
            return
        if self._health_session_id != current.id:
            self._health_session_id = current.id
            self._peer_health_misses.clear()
        by_id = {p["id"]: p for p in snapshots}
        failures = []
        for member in current.members:
            if member == self.settings.peer_id:
                continue
            peer = by_id.get(member, {})
            name = peer.get("name", member)
            if not peer.get("online"):
                misses = self._peer_health_misses.get(member, 0) + 1
                self._peer_health_misses[member] = misses
                if misses == 1:
                    self.event(f"Health check missed for {name}; retrying before stopping the session.", "warning")
                if misses >= 3:
                    failures.append(f"{name}: unavailable for 3 consecutive health checks")
                continue
            self._peer_health_misses.pop(member, None)
            # A reachable peer's explicit failure or withdrawal is authoritative.
            if (not peer.get("sharing") or peer.get("state") != "worker_ready"
                    or not (peer.get("runtime") or {}).get("running")
                    or peer.get("session") != current.model_dump()):
                failures.append(f"{name}: sharing, native runtime or session no longer valid")
        if failures:
            await self.runtime.stop()
            if self.manifest == current:
                self.state = "failed"
                self.error = "; ".join(failures) + ". Stop/reset before retrying."
                self.event(self.error, "error")

    async def monitor(self):
        while True:
            self.runtime.sample()
            if self.manifest and self.runtime.running and self.runtime.rss_bytes is not None:
                if self.runtime.rss_bytes > self.settings.offer_bytes:
                    reason = "Observed process RSS exceeded the owner's contribution; stopping."
                    await self.runtime.stop()
                    self.state, self.error = "failed", reason
                    self.event(reason, "error")
            if self.manifest and self.state in ("ready", "computing", "worker_ready"):
                if not self.runtime.running:
                    self.state, self.error = "failed", "Native runtime exited unexpectedly"
                    self.event(self.error, "error")
                elif self.manifest.coordinator == self.settings.peer_id:
                    await self.check_required_peers()
            await asyncio.sleep(1)

    async def reserve_request(self, session_id):
        async with self.lock:
            if not self.manifest or self.manifest.id != session_id or self.state != "ready":
                raise HTTPException(409, "The requested distributed session is not ready")
            if self.manifest.coordinator != self.settings.peer_id:
                raise HTTPException(409, "Send generation to the current coordinator")
            if self.busy:
                raise HTTPException(409, "Another request is active")
            self.busy = True
            self.state = "computing"

    async def generate(self, request, session_id):
        request_id = uuid.uuid4().hex
        started = time.monotonic()
        first_token = None
        output = ""
        completed = False
        usage = None
        self.event("Running request " + request_id[:8])
        def event(payload):
            return "data: " + json.dumps(payload) + "\n\n"
        try:
            async with self.client.stream("POST", self.native_url + "/v1/chat/completions", timeout=180,
                json={"messages": [{"role": "user", "content": request.prompt}],
                      "temperature": 0, "seed": 42, "max_tokens": request.max_tokens,
                      "stream": True, "stream_options": {"include_usage": True}}) as response:
                if response.status_code != 200:
                    raise RuntimeError((await response.aread()).decode(errors="replace")[:600])
                yield event({"type": "start", "request_id": request_id})
                async for line in response.aiter_lines():
                    if not self.manifest or self.manifest.id != session_id or self.state == "failed":
                        raise RuntimeError("Distributed session became unavailable; output is incomplete")
                    if not line.startswith("data: "):
                        continue
                    raw = line[6:]
                    if raw == "[DONE]":
                        completed = True
                        break
                    item = json.loads(raw)
                    if item.get("usage"):
                        usage = item["usage"]
                    choices = item.get("choices", [])
                    if choices:
                        choice = choices[0]
                        chunk = choice.get("delta", {}).get("content") or ""
                        if chunk:
                            if first_token is None:
                                first_token = time.monotonic() - started
                            output += chunk
                            yield event({"type": "token", "text": chunk})
                        if choice.get("finish_reason") == "length":
                            raise RuntimeError("Output limit reached; the result is incomplete")
                if not completed:
                    raise RuntimeError("Native stream ended without its completion marker")
            self.request_count += 1
            self.last_result = {"request_id": request_id, "output": output, "complete": True,
                                "elapsed_seconds": round(time.monotonic() - started, 3),
                                "first_token_seconds": round(first_token, 3) if first_token is not None else None,
                                "usage": usage, "model_sha256": self.manifest.model_sha256}
            (self.settings.state_path / f"{request_id}-result.json").write_text(json.dumps(self.last_result, indent=2))
            yield event({"type": "done", **self.last_result})
            self.event("Completed request " + request_id[:8])
        except asyncio.CancelledError:
            self.event("Request cancelled; any partial output is incomplete.", "error")
            raise
        except Exception as exc:
            self.event("Request failed: " + str(exc), "error")
            yield event({"type": "error", "message": str(exc), "complete": False})
        finally:
            async with self.lock:
                self.busy = False
                if self.manifest and self.manifest.id == session_id and self.state == "computing":
                    self.state = "ready" if self.runtime.running else "failed"

    async def close(self):
        if self.monitor_task:
            self.monitor_task.cancel()
            try:
                await self.monitor_task
            except asyncio.CancelledError:
                pass
        await self.stop_all()
        await self.runtime.stop()
        await self.client.aclose()
