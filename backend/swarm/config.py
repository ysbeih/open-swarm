from __future__ import annotations

import json
import os
import secrets
from pathlib import Path
from typing import List
from urllib.parse import urlparse

from pydantic import BaseModel, Field, model_validator

ROOT = Path(__file__).resolve().parents[2]
RUNTIME_REVISION = "5676dfbe01e7ebe0387913680eee0ed39bf4a363"


class Peer(BaseModel):
    id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,32}$")
    name: str = Field(max_length=80)
    url: str
    rpc_host: str
    rpc_port: int = Field(default=50052, ge=1024, le=65535)

    @model_validator(mode="after")
    def valid_address(self):
        address = urlparse(self.url)
        if address.scheme != "http" or not address.hostname or address.username or address.password:
            raise ValueError("Peer URL must be an HTTP LAN address without credentials")
        if address.path not in ("", "/") or address.query or address.fragment:
            raise ValueError("Peer URL must contain only host and port")
        if any(c in self.rpc_host for c in " /\\,\n\r"):
            raise ValueError("Invalid RPC host")
        return self

    @property
    def endpoint(self):
        return f"{self.rpc_host}:{self.rpc_port}"


class Settings(BaseModel):
    peer_id: str = "a"
    name: str = "This laptop"
    bind_host: str = "127.0.0.1"
    api_port: int = Field(default=8000, ge=1024, le=65535)
    rpc_port: int = Field(default=50052, ge=1024, le=65535)
    inference_port: int = Field(default=8081, ge=1024, le=65535)
    token: str = Field(min_length=32)
    offer_bytes: int = Field(default=8_000_000_000, ge=1_000_000_000, le=8_000_000_000)
    runtime_bin: str = ".tools/llama.cpp/build/bin"
    model_path: str = "models/granite-4.2-8b-Q4_K_M.gguf"
    model_name: str = "Granite 4.2 8B · Q4_K_M"
    model_sha256: str = ""
    worker_device: str = ""
    devices: List[str] = Field(default_factory=list)
    tensor_split: List[float] = Field(default_factory=lambda: [1, 1, 1])
    model_load_timeout_seconds: int = Field(default=600, ge=60, le=1800)
    peers: List[Peer] = Field(default_factory=list)
    state_dir: str = ".state"

    @model_validator(mode="after")
    def validate_roster(self):
        ids = [peer.id for peer in self.peers]
        if len(ids) != len(set(ids)):
            raise ValueError("Peer IDs must be unique")
        if self.peers and self.peer_id not in ids:
            raise ValueError("Roster must include this laptop")
        if self.model_sha256 and (len(self.model_sha256) != 64 or any(c not in "0123456789abcdef" for c in self.model_sha256)):
            raise ValueError("model_sha256 must be a lowercase SHA-256 digest")
        if any(n <= 0 for n in self.tensor_split):
            raise ValueError("Every device must receive a positive split")
        return self

    def resolve(self, value):
        path = Path(value).expanduser()
        return path if path.is_absolute() else ROOT / path

    @property
    def model(self):
        return self.resolve(self.model_path)

    @property
    def state_path(self):
        path = self.resolve(self.state_dir)
        path.mkdir(parents=True, exist_ok=True)
        return path

    def binary(self, name):
        return self.resolve(self.runtime_bin) / (name + (".exe" if os.name == "nt" else ""))


def load_settings():
    path = Path(os.environ.get("SWARM_CONFIG", str(ROOT / "config/local.json")))
    if path.exists():
        return Settings.model_validate_json(path.read_text())
    # A local-only setup screen is safe to start before the LAN roster exists.
    token_file = ROOT / ".state/local-token"
    token_file.parent.mkdir(exist_ok=True)
    if not token_file.exists():
        token_file.write_text(secrets.token_urlsafe(32))
        token_file.chmod(0o600)
    return Settings(token=token_file.read_text().strip())
