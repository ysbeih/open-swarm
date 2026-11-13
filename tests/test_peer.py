import asyncio
import json
from types import SimpleNamespace

import httpx
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from swarm.app import create_app
from swarm.config import Peer, Settings
from swarm.peer import Generation, Manifest, PeerService
from swarm.runtime import NativeRuntime, inference_command


class FakeRuntime:
    """Lifecycle test double only. Never imported by the application."""
    def __init__(self):
        self.running = False
        self.stops = 0
        self.process = None
        self.placement = {}
        self.rss_bytes = 0
        self.start_error = None

    async def start(self, argv, role, session_id):
        if self.start_error:
            raise RuntimeError(self.start_error)
        self.running = True
        self.process = SimpleNamespace(pid=999999999)

    async def stop(self):
        self.running = False
        self.stops += 1

    def sample(self):
        pass

    def snapshot(self):
        return {"running": self.running, "logs": [], "placement": self.placement}


@pytest.fixture
def settings(tmp_path):
    binary = tmp_path / "bin"
    binary.mkdir()
    (binary / "ggml-rpc-server").touch()
    (binary / "llama-server").touch()
    model = tmp_path / "model.gguf"
    model.write_bytes(b"unit test artifact; not an actual model")
    return Settings(token="test-token-" * 4, runtime_bin=str(binary), model_path=str(model),
                    state_dir=str(tmp_path / "state"), devices=["Metal", "RPC0", "RPC1"],
                    peers=[Peer(id=key, name=key, url=f"http://127.0.0.{i+1}:8000", rpc_host=f"127.0.0.{i+1}")
                           for i,key in enumerate("abc")])


@pytest.fixture
def manifest():
    return Manifest(id="a" * 32, coordinator="a", members=list("abc"), model_name="Test artifact", model_sha256="b" * 64)


async def test_consent_required(settings, manifest):
    peer = PeerService(settings, FakeRuntime())
    with pytest.raises(HTTPException) as error:
        await peer.prepare(manifest)
    assert error.value.status_code == 409
    assert peer.manifest is None
    await peer.close()


def health_test_peer(settings, manifest):
    runtime = FakeRuntime()
    runtime.running = True
    peer = PeerService(settings, runtime)
    peer.manifest, peer.state = manifest, 'computing'
    snapshots = [{'id': key, 'name': key, 'online': True, 'sharing': True,
                  'state': 'worker_ready', 'runtime': {'running': True},
                  'session': manifest.model_dump()} for key in 'bc']
    async def read():
        return snapshots
    peer.peers_snapshot = read
    return peer, snapshots


async def test_transient_health_miss_preserves_native_inference(settings, manifest):
    peer, snapshots = health_test_peer(settings, manifest)
    try:
        snapshots[0]['online'] = False
        await peer.check_required_peers()
        await peer.check_required_peers()
        assert peer.runtime.running and peer.runtime.stops == 0
        assert peer.state == 'computing'
        snapshots[0]['online'] = True
        await peer.check_required_peers()
        snapshots[0]['online'] = False
        await peer.check_required_peers()
        assert peer.runtime.running and peer.runtime.stops == 0
    finally:
        await peer.client.aclose()


async def test_three_consecutive_health_misses_stop_native_inference(settings, manifest):
    peer, snapshots = health_test_peer(settings, manifest)
    try:
        snapshots[0]['online'] = False
        for _ in range(3):
            await peer.check_required_peers()
        assert not peer.runtime.running and peer.runtime.stops == 1
        assert peer.state == 'failed'
        assert 'b: unavailable for 3 consecutive' in peer.error
    finally:
        await peer.client.aclose()


@pytest.mark.parametrize('change', [
    {'sharing': False}, {'runtime': {'running': False}}, {'state': 'failed'},
    {'session': None},
])
async def test_explicit_peer_failure_or_withdrawal_stops_immediately(settings, manifest, change):
    peer, snapshots = health_test_peer(settings, manifest)
    try:
        snapshots[0].update(change)
        await peer.check_required_peers()
        assert not peer.runtime.running and peer.runtime.stops == 1
        assert peer.state == 'failed' and 'b:' in peer.error
    finally:
        await peer.client.aclose()


async def test_health_failure_counts_do_not_cross_sessions(settings, manifest):
    peer, snapshots = health_test_peer(settings, manifest)
    try:
        snapshots[0]['online'] = False
        await peer.check_required_peers()
        await peer.check_required_peers()
        peer.manifest = manifest.model_copy(update={'id': 'c' * 32})
        snapshots[1]['session'] = peer.manifest.model_dump()
        await peer.check_required_peers()
        assert peer.runtime.running and peer.runtime.stops == 0
    finally:
        await peer.client.aclose()


async def test_stale_health_result_cannot_stop_replacement_session(settings, manifest):
    peer, snapshots = health_test_peer(settings, manifest)
    try:
        async def read():
            peer.manifest = manifest.model_copy(update={'id': 'c' * 32})
            snapshots[0]['state'] = 'failed'
            return snapshots
        peer.peers_snapshot = read
        await peer.check_required_peers()
        assert peer.runtime.running and peer.runtime.stops == 0
    finally:
        await peer.client.aclose()


async def test_two_peer_manifest_and_native_route(settings, manifest):
    settings.peers = settings.peers[:2]
    settings.devices = ["Metal", "RPC0"]
    settings.tensor_split = [1, 1]
    manifest = manifest.model_copy(update={"members": ["a", "b"]})
    peer = PeerService(settings, FakeRuntime())
    await peer.share(True)
    await peer.prepare(manifest)
    assert peer.manifest.members == ["a", "b"]
    argv = inference_command(settings)
    assert argv[argv.index("--rpc") + 1] == "127.0.0.2:50052"
    assert argv[argv.index("--device") + 1] == "Metal,RPC0"
    assert argv[argv.index("--tensor-split") + 1] == "1.0,1.0" or argv[argv.index("--tensor-split") + 1] == "1,1"
    await peer.stop_local(manifest.id)
    await peer.close()


async def test_conflicting_start_and_stale_stop_preserve_incumbent(settings, manifest):
    peer = PeerService(settings, FakeRuntime())
    await peer.share(True)
    await peer.prepare(manifest)
    await peer.prepare(manifest)
    contender = manifest.model_copy(update={"id":"c" * 32, "coordinator":"b"})
    with pytest.raises(HTTPException):
        await peer.prepare(contender)
    result = await peer.stop_local(contender.id)
    assert not result["stopped"]
    assert peer.manifest == manifest
    assert peer.runtime.stops == 0
    await peer.stop_local(manifest.id)
    assert peer.manifest is None and not peer.marker.exists()
    await peer.close()


async def test_commit_cannot_change_reserved_model(settings, manifest):
    peer = PeerService(settings, FakeRuntime())
    await peer.share(True)
    await peer.prepare(manifest)
    changed = manifest.model_copy(update={"model_sha256":"c" * 64})
    with pytest.raises(HTTPException):
        await peer.commit(changed)
    assert not peer.runtime.running
    await peer.stop_local(manifest.id)
    await peer.close()


async def test_immutable_manifest_and_roster_checks(settings, manifest):
    settings.model_sha256 = "d" * 64
    peer = PeerService(settings, FakeRuntime())
    await peer.share(True)
    with pytest.raises(HTTPException):
        await peer.prepare(manifest)
    with pytest.raises(HTTPException):
        await peer.prepare(manifest.model_copy(update={"members":["a","c","b"]}))
    assert peer.manifest is None
    await peer.close()


async def test_simultaneous_reservations_allow_one_owner(settings, manifest):
    peer = PeerService(settings, FakeRuntime())
    await peer.share(True)
    other = manifest.model_copy(update={"id":"e" * 32})
    results = await asyncio.gather(peer.prepare(manifest), peer.prepare(other), return_exceptions=True)
    assert sum(isinstance(r, HTTPException) for r in results) == 1
    assert peer.manifest.id in (manifest.id, other.id)
    await peer.stop_local(peer.manifest.id)
    await peer.close()


async def test_failed_worker_start_never_reports_ready(settings, manifest):
    settings.peer_id = "b"
    runtime = FakeRuntime()
    runtime.start_error = "unsupported backend"
    peer = PeerService(settings, runtime)
    await peer.share(True)
    await peer.prepare(manifest)
    with pytest.raises(HTTPException):
        await peer.commit(manifest)
    assert peer.state == "failed" and not runtime.running
    assert peer.manifest == manifest
    await peer.stop_local(manifest.id)
    await peer.close()


async def test_stop_acknowledges_only_after_process_exit(settings, manifest):
    runtime = FakeRuntime()
    stopped = asyncio.Event()
    async def slow_stop():
        await stopped.wait()
        runtime.running = False
    runtime.stop = slow_stop
    peer = PeerService(settings, runtime)
    await peer.share(True)
    await peer.prepare(manifest)
    runtime.running = True
    stop = asyncio.create_task(peer.stop_local(manifest.id))
    await asyncio.sleep(0)
    assert peer.state == "stopping" and peer.manifest is not None
    assert not stop.done()
    stopped.set()
    assert (await stop)["stopped"]
    assert not runtime.running and peer.manifest is None
    await peer.close()


async def test_generation_stream_completion_and_truncation(settings, manifest):
    runtime = FakeRuntime()
    runtime.running = True
    peer = PeerService(settings, runtime)
    peer.manifest, peer.state = manifest, "ready"
    pieces = [{"choices":[{"delta":{"content":"hello"},"finish_reason":None}]},
              {"choices":[{"delta":{},"finish_reason":"stop"}],"usage":{"completion_tokens":1}}]
    def handler(request):
        content = "".join("data: " + json.dumps(piece) + "\n\n" for piece in pieces) + "data: [DONE]\n\n"
        return httpx.Response(200, text=content)
    await peer.client.aclose()
    peer.client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    await peer.reserve_request(manifest.id)
    with pytest.raises(HTTPException):
        await peer.reserve_request(manifest.id)
    events = [json.loads(raw[6:]) async for raw in peer.generate(Generation(prompt="hello"), manifest.id)]
    assert events[-1]["type"] == "done" and events[-1]["output"] == "hello"
    assert peer.state == "ready" and not peer.busy
    pieces[-1]["choices"][0]["finish_reason"] = "length"
    await peer.reserve_request(manifest.id)
    events = [json.loads(raw[6:]) async for raw in peer.generate(Generation(prompt="hello"), manifest.id)]
    assert events[-1]["type"] == "error" and not events[-1]["complete"]
    assert peer.request_count == 1
    await peer.stop_local(manifest.id)
    await peer.client.aclose()


def test_auth_and_local_bootstrap(settings):
    app = create_app(settings)
    with TestClient(app) as client:
        assert client.get("/api/peer").status_code == 401
        assert client.get("/api/bootstrap", headers={"Host":"attacker.example"}).status_code == 403
        assert client.get("/api/bootstrap", headers={"Origin":"https://attacker.example"}).status_code == 403
        token = client.get("/api/bootstrap").json()["token"]
        assert token == settings.token
        headers = {"Authorization":"Bearer " + token}
        assert client.get("/api/peer", headers=headers).status_code == 200
        assert client.post("/api/session/start", headers=headers).status_code == 409


def test_native_evidence_parser(settings):
    runtime = NativeRuntime(settings)
    runtime.inspect_line("load_tensors: layer  14 assigned to device RPC0, is_swa = 0")
    runtime.inspect_line("[graph_compute] device: 0, uid: 123, n_nodes: 42, n_tensors: 50")
    runtime.inspect_line("[graph_recompute] device: 0, uid: 124")
    runtime.inspect_line("[graph_recompute] device: 0, graph with uid 12 not found")
    assert runtime.placement == {14:"RPC0"}
    assert runtime.graph_submissions == 2


def test_native_command_selects_exact_members_and_disables_automatic_fit(settings):
    argv = inference_command(settings)
    assert argv[argv.index("--rpc") + 1] == "127.0.0.2:50052,127.0.0.3:50052"
    assert argv[argv.index("--device") + 1] == "Metal,RPC0,RPC1"
    assert argv[argv.index("--fit") + 1] == "off"
    assert argv[argv.index("--reasoning") + 1] == "off"
    assert "--api-key" not in argv
