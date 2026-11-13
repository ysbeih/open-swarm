"""Read-only, loopback-only access to this host's existing guest invitation.

Separate from the public guest gateway and peer lifecycle so it can be started
without interrupting a loaded native model. Never mount this on the guest app.
"""
from __future__ import annotations

import base64
import hmac
import io
import json
import math
import re
import time
from contextlib import asynccontextmanager
from urllib.parse import parse_qs, urlparse

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware


def read_invite(settings):
    try:
        access = json.loads((settings.state_path / "guest-pass.json").read_text())
        link = (settings.state_path / "guest-url.txt").read_text().strip()
        token, expires, port = access["token"], float(access["expires_at"]), access["port"]
        url = urlparse(link)
        valid = (isinstance(token, str) and re.fullmatch(r"[A-Za-z0-9_-]{32,128}", token)
                 and math.isfinite(expires) and type(port) is int and 1024 <= port <= 65535
                 and port not in (settings.api_port, settings.rpc_port, settings.inference_port, 8003)
                 and len(link) < 2048 and not any(c.isspace() for c in link)
                 and url.scheme == "https" and url.hostname and not url.username and not url.password
                 and url.path in ("", "/") and not url.query
                 and parse_qs(url.fragment, keep_blank_values=True) == {"pass": [token]})
        if not valid:
            raise ValueError()
        if expires <= time.time():
            return {"status": "expired", "message": "This guest pass has expired. The host needs to renew guest access."}
        return {"url": link, "token": token, "expires_at": expires, "port": port}
    except FileNotFoundError:
        return {"status": "missing", "message": "No guest invite on this laptop. Open Guest mode on the laptop hosting guest access."}
    except (ValueError, TypeError, KeyError, OSError, AttributeError):
        return {"status": "invalid", "message": "The saved invite does not match the current guest pass. The host needs to update the invite."}


async def invite_snapshot(settings, client):
    invite = read_invite(settings)
    if "url" not in invite:
        return invite
    try:
        response = await client.get(f"http://127.0.0.1:{invite['port']}/api/status",
                                    headers={"Authorization": "Bearer " + invite["token"]}, timeout=5)
        if response.status_code in (401, 410):
            return {"status": "expired", "message": "The gateway no longer accepts this pass. The host needs to renew guest access."}
        response.raise_for_status()
        status = response.json()
        if (not isinstance(status, dict) or type(status.get("remaining_jobs")) is not int
                or type(status.get("ready")) is not bool or type(status.get("busy")) is not bool
                or float(status.get("expires_at", 0)) != invite["expires_at"]):
            raise ValueError()
        if invite["expires_at"] <= time.time():
            return {"status": "expired", "message": "This guest pass has expired. The host needs to renew guest access."}
        if status["remaining_jobs"] <= 0:
            return {"status": "exhausted", "message": "This shared pass has no requests left. The host needs to renew guest access."}
    except (httpx.HTTPError, ValueError, TypeError):
        return {"status": "offline", "message": "The guest gateway could not be verified. Check the host's guest service and try again."}
    try:
        import qrcode
        from qrcode.image.pure import PyPNGImage
        image = io.BytesIO()
        qrcode.make(invite["url"], image_factory=PyPNGImage, box_size=7, border=4).save(image)
    except ImportError:
        return {"status": "setup", "message": "QR support is not installed on the guest host. Check the guest setup instructions."}
    # The QR is derived from the validated link, never a potentially stale image.
    return {"status": "available", "url": invite["url"], "expires_at": invite["expires_at"],
            "qr": "data:image/png;base64," + base64.b64encode(image.getvalue()).decode(),
            "ready": status["ready"], "busy": status["busy"], "remaining_jobs": status["remaining_jobs"]}


def create_invite_app(settings, client=None):
    client = client or httpx.AsyncClient(trust_env=False, follow_redirects=False)

    @asynccontextmanager
    async def lifespan(app):
        yield
        await client.aclose()

    app = FastAPI(title="Open Swarm local guest invite", lifespan=lifespan,
                  docs_url=None, redoc_url=None, openapi_url=None)
    origins = [f"http://localhost:{settings.api_port}", f"http://127.0.0.1:{settings.api_port}"]
    app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=["GET"],
                       allow_headers=["Authorization"])

    @app.middleware("http")
    async def protect_response(request, call_next):
        response = await call_next(request)
        response.headers.update({"Cache-Control": "no-store", "Referrer-Policy": "no-referrer",
                                 "X-Content-Type-Options": "nosniff"})
        return response

    @app.get("/api/guest-invite")
    async def guest_invite(request: Request):
        host = urlparse("http://" + request.headers.get("host", "")).hostname
        if not request.client or request.client.host not in ("127.0.0.1", "::1") or host not in ("localhost", "127.0.0.1", "::1"):
            raise HTTPException(403, "Open Guest mode on the host's local dashboard")
        origin = request.headers.get("origin")
        if origin and origin not in origins:
            raise HTTPException(403, "Local dashboard origin required")
        actual = request.headers.get("authorization", "").encode()
        if not hmac.compare_digest(actual, ("Bearer " + settings.token).encode()):
            raise HTTPException(401, "Peer token required")
        return await invite_snapshot(settings, client)

    return app
