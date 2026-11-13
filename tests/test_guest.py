import asyncio
import json
import time

import httpx
import pytest

from swarm.config import Settings
from swarm.guest import GuestGateway, create_guest_app


class ControlledStream(httpx.AsyncByteStream):
    def __init__(self, release, complete):
        self.release, self.complete = release, complete

    async def __aiter__(self):
        yield b'data: {"type":"token","text":"hello"}\n\n'
        await self.release.wait()
        if self.complete:
            event = {"type": "done", "complete": True, "output": "hello", "request_id": "native-result",
                     "elapsed_seconds": 1.2, "first_token_seconds": .2,
                     "usage": {"prompt_tokens": 4, "completion_tokens": 1, "total_tokens": 5}}
            yield ("data: " + json.dumps(event) + "\n\n").encode()


def setup_gateway(tmp_path, *, complete=True, max_jobs=2):
    settings = Settings(token="private-control-token-" * 3, state_dir=str(tmp_path))
    release = asyncio.Event()
    calls = []
    session = {"id": "a" * 32, "coordinator": "a", "members": ["a", "b"], "model_name": "Test model"}
    state = {"local": {"session": session}, "model": {"name": "Test model"}, "sample_prompt": "sample",
             "peers": [{"id": key, "name": "Laptop " + key, "online": True, "state": "ready", "busy": False,
                        "session": session, "runtime": {"running": True, "logs": ["PRIVATE LOG"], "pid": 123}}
                       for key in ("a", "b")]}

    async def transport(request):
        calls.append(request)
        assert request.url.host == "127.0.0.1"
        assert request.headers["authorization"] == "Bearer " + settings.token
        if request.url.path == "/api/state":
            return httpx.Response(200, json=state)
        if request.url.path.endswith("/generate"):
            assert json.loads(request.content)["max_tokens"] == 128
            return httpx.Response(200, stream=ControlledStream(release, complete))
        raise AssertionError("Unexpected control API request")

    gateway = GuestGateway(settings, "guest-only-pass", time.time() + 60, max_jobs,
                           httpx.AsyncClient(transport=httpx.MockTransport(transport)))
    app = create_guest_app(gateway)
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://guest.test",
                              headers={"Authorization": "Bearer guest-only-pass"})
    return gateway, client, release, calls, state


async def test_guest_access_does_not_expose_controls_or_private_state(tmp_path):
    gateway, client, release, calls, state = setup_gateway(tmp_path)
    try:
        for method, path in (("GET", "/api/guest-invite"), ("GET", "/api/bootstrap"), ("GET", "/api/peer"), ("GET", "/api/state"),
                             ("POST", "/api/session/start"), ("POST", "/api/sharing"),
                             ("GET", "/openapi.json"), ("GET", "/config/local.json")):
            assert (await client.request(method, path)).status_code == 404
        assert not calls
        response = await client.get("/api/status", headers={"Authorization": "Bearer wrong"})
        assert response.status_code == 401 and not calls
        response = await client.get("/api/status")
        assert response.status_code == 200 and response.json()["peers"] == ["Laptop a", "Laptop b"]
        assert "PRIVATE LOG" not in response.text and "pid" not in response.text and gateway.settings.token not in response.text
        assert response.headers["referrer-policy"] == "no-referrer"
        gateway.expires_at = time.time() - 1
        assert (await client.post("/api/jobs", json={"prompt": "hello"})).status_code == 410
    finally:
        await client.aclose()
        await gateway.close()


async def test_guest_stream_busy_limit_usage_and_private_record(tmp_path):
    gateway, client, release, calls, state = setup_gateway(tmp_path, max_jobs=1)
    try:
        response = await client.post("/api/jobs", json={"prompt": "a real input", "max_tokens": 999999})
        assert response.status_code == 202
        job_id = response.json()["id"]
        assert (await client.post("/api/jobs", json={"prompt": "second"})).status_code == 409
        release.set()
        await asyncio.gather(*list(gateway.tasks))
        result = (await client.get("/api/jobs/" + job_id)).json()
        assert result["complete"] and result["output"] == "hello"
        assert result["usage"]["completion_tokens"] == 1
        assert "prompt" not in result and "private_error" not in result
        assert (await client.post("/api/jobs", json={"prompt": "second"})).status_code == 429
        assert (await client.get("/api/jobs/" + job_id, headers={"Authorization": ""})).status_code == 401
        record = tmp_path / "guest-jobs" / (job_id + ".json")
        saved = json.loads(record.read_text())
        assert saved["prompt"] == "a real input" and saved["usage"] == result["usage"]
        assert gateway.pass_token not in record.read_text() and gateway.settings.token not in record.read_text()
        assert record.stat().st_mode & 0o777 == 0o600
    finally:
        await client.aclose()
        await gateway.close()


async def test_guest_rejects_oversize_and_unready_requests(tmp_path):
    gateway, client, release, calls, state = setup_gateway(tmp_path)
    try:
        assert (await client.post("/api/jobs", content=b"x" * 9000)).status_code == 413
        assert (await client.post("/api/jobs", json={"prompt": "x" * 2001})).status_code == 422
        assert (await client.post("/api/jobs", json={"prompt": "   "})).status_code == 422
        assert not calls
        state["peers"][0]["session"] = None
        assert not (await client.get("/api/status")).json()["ready"]
        assert (await client.post("/api/jobs", json={"prompt": "hello"})).status_code == 409
        assert not gateway.jobs
    finally:
        await client.aclose()
        await gateway.close()


async def test_guest_incomplete_stream_is_not_reported_complete(tmp_path):
    gateway, client, release, calls, state = setup_gateway(tmp_path, complete=False)
    try:
        response = await client.post("/api/jobs", json={"prompt": "hello"})
        release.set()
        await asyncio.gather(*list(gateway.tasks))
        result = (await client.get("/api/jobs/" + response.json()["id"])).json()
        assert result["status"] == "failed" and not result["complete"]
        assert result["output"] == "hello" and "private_error" not in result
        assert not gateway.busy
    finally:
        await client.aclose()
        await gateway.close()
