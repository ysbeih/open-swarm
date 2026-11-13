"""A separate, limited guest gateway. Never mount the peer control API here."""
from __future__ import annotations

import asyncio
import hmac
import json
import os
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from .config import ROOT


class GuestRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=2000)


class GuestGateway:
    def __init__(self, settings, pass_token, expires_at, max_jobs=20, client=None):
        self.settings = settings
        self.pass_token = pass_token
        self.expires_at = expires_at
        self.max_jobs = max_jobs
        self.jobs = {}
        self.tasks = set()
        self.busy = False
        self.lock = asyncio.Lock()
        self.base = f"http://127.0.0.1:{settings.api_port}"
        self.client = client or httpx.AsyncClient(trust_env=False, timeout=10)
        self.headers = {"Authorization": "Bearer " + settings.token}
        self.folder = settings.state_path / "guest-jobs"
        self.folder.mkdir(mode=0o700, exist_ok=True)

    async def authorize(self, request: Request):
        supplied = request.headers.get("authorization", "").encode()
        if not hmac.compare_digest(supplied, ("Bearer " + self.pass_token).encode()):
            raise HTTPException(401, "Open the full guest link supplied by the host.")
        if time.time() >= self.expires_at:
            raise HTTPException(410, "This guest pass has expired.")

    async def snapshot(self):
        try:
            response = await self.client.get(self.base + "/api/state", headers=self.headers)
            response.raise_for_status()
            return response.json()
        except (httpx.HTTPError, ValueError):
            raise HTTPException(503, "The host is unavailable. Try again shortly.")

    @staticmethod
    def coordinator(state):
        session = state["local"].get("session")
        if not session:
            return None
        return next((p for p in state["peers"] if p["id"] == session["coordinator"]
                     and (p.get("session") or {}).get("id") == session["id"]), None)

    async def status(self):
        state = await self.snapshot()
        coordinator = self.coordinator(state)
        session = state["local"].get("session")
        return {
            "ready": bool(coordinator and coordinator["state"] == "ready" and not self.busy),
            "busy": self.busy or bool(coordinator and coordinator.get("busy")),
            "model": session["model_name"] if session else state["model"]["name"],
            "peers": [p["name"] for p in state["peers"] if session and p["id"] in session["members"]
                      and p.get("online") and p.get("runtime", {}).get("running")],
            "remaining_jobs": max(0, self.max_jobs - len(self.jobs)),
            "expires_at": self.expires_at,
            "max_output_tokens": 128,
            "sample_prompt": state["sample_prompt"],
        }

    def save(self, job):
        path = self.folder / (job["id"] + ".json")
        # No credentials or request headers are included in this local record.
        with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w") as file:
            json.dump(job, file, indent=2)

    async def submit(self, prompt):
        if not prompt.strip():
            raise HTTPException(422, "Enter a test prompt.")
        async with self.lock:
            if self.busy:
                raise HTTPException(409, "The swarm is working on another request. Try again shortly.")
            if len(self.jobs) >= self.max_jobs:
                raise HTTPException(429, "This guest pass has used its request allowance.")
            state = await self.snapshot()
            coordinator = self.coordinator(state)
            if not coordinator or coordinator["state"] != "ready":
                raise HTTPException(409, "The swarm is busy or not ready. The host can check its dashboard.")
            session = state["local"]["session"]
            job = {"id": uuid.uuid4().hex, "status": "running", "complete": False,
                   "prompt": prompt, "output": "", "usage": None,
                   "model": session["model_name"], "session_id": session["id"],
                   "peers": [p["name"] for p in state["peers"] if p["id"] in session["members"]],
                   "started_at": datetime.now(timezone.utc).isoformat()}
            self.save(job)
            self.jobs[job["id"]] = job
            self.busy = True
            task = asyncio.create_task(self.run(job))
            self.tasks.add(task)
            task.add_done_callback(self.tasks.discard)
            return {"id": job["id"]}

    async def run(self, job):
        try:
            # Polling outside, native streaming inside: Quick Tunnels do not support SSE.
            async with self.client.stream("POST", self.base + f"/api/sessions/{job['session_id']}/generate",
                    headers=self.headers, json={"prompt": job["prompt"], "max_tokens": 128},
                    timeout=httpx.Timeout(190, connect=10)) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    event = json.loads(line[6:])
                    if event.get("type") == "token":
                        job["output"] += event["text"]
                    elif event.get("type") == "error":
                        raise RuntimeError(event.get("message", "Native inference failed"))
                    elif event.get("type") == "done" and event.get("complete"):
                        for key in ("output", "usage", "elapsed_seconds", "first_token_seconds", "request_id", "model_sha256"):
                            job[key] = event.get(key)
                        job.update(status="complete", complete=True)
            if not job["complete"]:
                raise RuntimeError("Stream ended without a completion event")
        except asyncio.CancelledError:
            job.update(status="failed", complete=False, error="The guest service stopped. Output is incomplete.")
            raise
        except Exception as exc:
            job.update(status="failed", complete=False,
                       error="This request did not finish. The host can inspect its local log.",
                       private_error=str(exc))
        finally:
            job["finished_at"] = datetime.now(timezone.utc).isoformat()
            self.busy = False
            self.save(job)

    def result(self, job_id):
        job = self.jobs.get(job_id)
        if not job:
            raise HTTPException(404, "Request not found.")
        allowed = ("id", "status", "complete", "output", "usage", "model", "peers", "error",
                   "elapsed_seconds", "first_token_seconds")
        return {key: job[key] for key in allowed if key in job}

    async def close(self):
        tasks = list(self.tasks)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await self.client.aclose()


def create_guest_app(gateway):
    @asynccontextmanager
    async def lifespan(app):
        yield
        await gateway.close()

    app = FastAPI(title="Open Swarm guest", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    auth = [Depends(gateway.authorize)]
    assets = ROOT / "guest"

    @app.middleware("http")
    async def response_headers(request, call_next):
        response = await call_next(request)
        response.headers.update({
            "Cache-Control": "no-store", "Referrer-Policy": "no-referrer",
            "X-Content-Type-Options": "nosniff", "X-Frame-Options": "DENY",
            "Content-Security-Policy": "default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'",
        })
        return response

    @app.get("/")
    async def index():
        return FileResponse(assets / "index.html")

    @app.get("/guest.js")
    async def script():
        return FileResponse(assets / "guest.js", media_type="text/javascript")

    @app.get("/guest.css")
    async def stylesheet():
        return FileResponse(assets / "guest.css", media_type="text/css")

    @app.get("/api/status", dependencies=auth)
    async def status():
        return await gateway.status()

    @app.post("/api/jobs", dependencies=auth, status_code=202)
    async def submit(request: Request):
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > 8192:
                raise HTTPException(413, "Request is too large.")
        try:
            data = GuestRequest.model_validate(json.loads(body))
        except ValueError:
            raise HTTPException(422, "Use a prompt between 1 and 2,000 characters.")
        return await gateway.submit(data.prompt)

    @app.get("/api/jobs/{job_id}", dependencies=auth)
    async def result(job_id: str):
        return gateway.result(job_id)

    return app
