from __future__ import annotations

import asyncio
import hmac
from contextlib import asynccontextmanager
from urllib.parse import urlparse
from typing import List, Optional

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .config import ROOT, load_settings
from .peer import Generation, Manifest, PeerService

SAMPLE_PROMPT = '''Extract each support message into a JSON array. Return JSON only, no markdown.
Each object must have exactly these keys: "case_id", "category", "order_id".
Allowed categories: "billing", "damage", "account". Use null when no order ID is supplied.
Do not invent order IDs.

1. Please send me the invoice for order A104.
2. Order B208 arrived with a broken screen.
3. I cannot sign in to my account.
'''


class Sharing(BaseModel):
    enabled: bool


class SessionStart(BaseModel):
    members: Optional[List[str]] = Field(default=None, min_length=2, max_length=3)


def create_app(settings=None, service=None):
    settings = settings or load_settings()
    service = service or PeerService(settings)

    @asynccontextmanager
    async def lifespan(app):
        service.monitor_task = asyncio.create_task(service.monitor())
        yield
        await service.close()

    app = FastAPI(title="Open Swarm", lifespan=lifespan, docs_url=None, redoc_url=None)
    app.state.peer = service

    async def authorize(request: Request):
        actual = request.headers.get("authorization", "")
        if not hmac.compare_digest(actual, "Bearer " + settings.token):
            raise HTTPException(401, "Peer token required")

    auth = [Depends(authorize)]

    @app.get("/api/bootstrap")
    async def bootstrap(request: Request):
        host = urlparse("http://" + request.headers.get("host", "")).hostname
        origin = request.headers.get("origin")
        if request.client.host not in ("127.0.0.1", "::1", "testclient") or host not in ("127.0.0.1", "localhost", "::1", "testserver"):
            raise HTTPException(403, "Open the dashboard on localhost on this laptop")
        if origin and urlparse(origin).netloc != request.headers.get("host"):
            raise HTTPException(403, "Cross-origin bootstrap is not allowed")
        return {"token": settings.token, "peer_id": settings.peer_id, "app": "Open Swarm"}

    @app.get("/api/peer", dependencies=auth)
    async def peer():
        return service.snapshot()

    @app.get("/api/state", dependencies=auth)
    async def state():
        return {"local": service.snapshot(), "peers": await service.peers_snapshot(),
                "expected_peers": len(service.manifest.members) if service.manifest else (len(settings.peers) if settings.peers else 2),
                "model": {"name": settings.model_name,
                          "file_bytes": settings.model.stat().st_size if settings.model.is_file() else None,
                          "present": settings.model.is_file()},
                "sample_prompt": SAMPLE_PROMPT,
                "notice": "Trusted LAN prototype · one active session · reference run deferred"}

    @app.post("/api/sharing", dependencies=auth)
    async def sharing(body: Sharing):
        return await service.share(body.enabled)

    @app.post("/api/session/start", dependencies=auth, status_code=202)
    async def start(body: Optional[SessionStart] = None):
        return await service.begin(body.members if body else None)

    @app.post("/api/session/stop", dependencies=auth)
    async def stop():
        await service.stop_all()
        return service.snapshot()

    @app.post("/api/reset", dependencies=auth)
    async def reset():
        return await service.reset()

    @app.post("/api/sessions/prepare", dependencies=auth)
    async def prepare(manifest: Manifest):
        return await service.prepare(manifest)

    @app.post("/api/sessions/commit", dependencies=auth)
    async def commit(manifest: Manifest):
        return await service.commit(manifest)

    @app.post("/api/sessions/{session_id}/stop", dependencies=auth)
    async def stop_local(session_id: str):
        return await service.stop_local(session_id)

    @app.post("/api/sessions/{session_id}/generate", dependencies=auth)
    async def generate(session_id: str, body: Generation):
        manifest = service.manifest
        if not manifest or manifest.id != session_id:
            raise HTTPException(409, "No matching session")
        if manifest.coordinator == settings.peer_id:
            await service.reserve_request(session_id)
            return StreamingResponse(service.generate(body, session_id), media_type="text/event-stream",
                                     headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
        coordinator = next(p for p in settings.peers if p.id == manifest.coordinator)
        upstream_request = service.client.build_request("POST", coordinator.url.rstrip("/") +
            f"/api/sessions/{session_id}/generate", headers={"Authorization": "Bearer " + settings.token},
            json=body.model_dump(), timeout=180)
        try:
            response = await service.client.send(upstream_request, stream=True)
        except httpx.HTTPError as exc:
            raise HTTPException(503, "Coordinator unreachable: " + str(exc))
        if response.is_error:
            message = (await response.aread()).decode(errors="replace")
            await response.aclose()
            raise HTTPException(response.status_code, message)
        async def forward():
            try:
                async for chunk in response.aiter_bytes():
                    yield chunk
            finally:
                await response.aclose()
        return StreamingResponse(forward(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})

    dist = ROOT / "frontend/dist"
    if (dist / "assets").exists():
        app.mount("/assets", StaticFiles(directory=str(dist / "assets")), name="assets")

    @app.get("/")
    async def index():
        if (dist / "index.html").exists():
            return FileResponse(dist / "index.html")
        return {"app": "Open Swarm", "status": "Build frontend first: npm --prefix frontend run build"}

    return app
