import sys
import socket
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

import uvicorn
from swarm.config import load_settings
from swarm.app import create_app

if __name__ == "__main__":
    settings = load_settings()
    print(f"Open Swarm dashboard: http://localhost:{settings.api_port}")
    # One server/lifespan, two listening sockets: LAN peer traffic and a localhost-only UI bootstrap.
    hosts = list(dict.fromkeys(["127.0.0.1", settings.bind_host]))
    sockets = []
    try:
        for host in hosts:
            listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            listener.bind((host, settings.api_port))
            listener.listen(128)
            listener.setblocking(False)
            sockets.append(listener)
        server = uvicorn.Server(uvicorn.Config(create_app(settings), proxy_headers=False))
        server.run(sockets=sockets)
    finally:
        for listener in sockets:
            listener.close()
