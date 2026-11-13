"""Run a temporary, limited guest web gateway on localhost. Tunnel ONLY this port."""
import argparse
import json
import os
from pathlib import Path
import secrets
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

import uvicorn
from swarm.config import load_settings
from swarm.guest import GuestGateway, create_guest_app


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8002)
    parser.add_argument("--minutes", type=int, default=120)
    parser.add_argument("--max-jobs", type=int, default=20)
    args = parser.parse_args()
    if not 1 <= args.minutes <= 180 or not 1 <= args.max_jobs <= 50 or not 1024 <= args.port <= 65535:
        parser.error("Use 1–180 minutes, 1–50 jobs, and an unprivileged port.")
    settings = load_settings()
    if args.port in (settings.api_port, settings.rpc_port, settings.inference_port):
        parser.error("The guest port must be separate from peer and native ports.")
    token = secrets.token_urlsafe(32)
    expires = time.time() + args.minutes * 60
    path = settings.state_path / "guest-pass.json"
    with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w") as file:
        json.dump({"token": token, "expires_at": expires, "port": args.port, "pid": os.getpid()}, file)
    print(f"Guest gateway: http://127.0.0.1:{args.port}", flush=True)
    print(f"Private guest pass saved to {path}. Limit: {args.max_jobs} requests / {args.minutes} minutes.", flush=True)
    print("Expose ONLY this guest port. Never tunnel the peer API or native RPC.", flush=True)
    gateway = GuestGateway(settings, token, expires, args.max_jobs)
    uvicorn.run(create_guest_app(gateway), host="127.0.0.1", port=args.port, proxy_headers=False)


if __name__ == "__main__":
    main()
