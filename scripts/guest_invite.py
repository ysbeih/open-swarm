"""Serve the local dashboard's Guest mode button without restarting inference."""
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

import uvicorn
from swarm.config import load_settings
from swarm.guest_invite import create_invite_app

if __name__ == "__main__":
    config = Path(os.environ.get("SWARM_CONFIG", str(ROOT / "config/local.json")))
    if not config.is_file():
        raise SystemExit("Use the existing guest host configuration; no configuration or tokens were created.")
    settings = load_settings()
    if 8003 in (settings.api_port, settings.rpc_port, settings.inference_port):
        raise SystemExit("Port 8003 conflicts with this peer's configured ports.")
    print("Guest invite helper: localhost:8003 (local dashboard only; never tunnel this port)", flush=True)
    uvicorn.run(create_invite_app(settings), host="127.0.0.1", port=8003,
                proxy_headers=False, access_log=False)
