"""Run a temporary worker for discovery, or list the coordinator's local/remote devices."""
import argparse
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from swarm.config import load_settings
from swarm.runtime import worker_command

parser = argparse.ArgumentParser()
parser.add_argument("--worker", action="store_true")
args = parser.parse_args()
settings = load_settings()
environment = os.environ.copy()
environment["GGML_RPC_NO_RDMA"] = "1"
environment["LLAMA_CACHE"] = str(settings.state_path / "cache")
if args.worker:
    print("Temporary discovery worker. Stop with Ctrl+C BEFORE starting a session in the app.", flush=True)
    command = worker_command(settings)
else:
    remotes = ",".join(p.endpoint for p in settings.peers if p.id != settings.peer_id)
    command = [str(settings.binary("llama-server"))]
    if remotes:
        command += ["--rpc", remotes]
    command += ["--list-devices"]
subprocess.run(command, env=environment, check=True)
