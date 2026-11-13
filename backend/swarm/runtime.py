from __future__ import annotations

import asyncio
import os
import re
import time
from collections import deque
from pathlib import Path
from typing import Optional

import psutil

from .config import RUNTIME_REVISION, Settings


class NativeRuntime:
    """Own only the native process started by this peer; never kill by process name."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.process: Optional[asyncio.subprocess.Process] = None
        self.reader = None
        self.log = deque(maxlen=160)
        self.placement = {}
        self.graph_submissions = 0
        self.peak_rss_bytes = 0
        self.rss_bytes = 0
        self.cpu_percent = None
        self.role = None
        self.log_path = None
        self._tracked = {}

    @property
    def running(self):
        return self.process is not None and self.process.returncode is None

    def inspect_line(self, line):
        self.log.append(line)
        match = re.search(r"layer\s+(\d+)\s+assigned to device\s+([^\s,]+)", line)
        if match:
            self.placement[int(match.group(1))] = match.group(2)
        # These are real native graph submissions, not completed kernels or tokens.
        if "[graph_compute]" in line or "[graph_recompute]" in line:
            if "device:" in line and "uid:" in line and "not found" not in line:
                self.graph_submissions += 1

    async def start(self, argv, role, session_id):
        if self.running:
            raise RuntimeError("A native process is already active")
        executable = Path(argv[0])
        if not executable.is_file():
            raise RuntimeError(f"Runtime missing: {executable.name}. Run scripts/build_runtime.py first.")
        self.role = role
        self.log.clear()
        self.placement.clear()
        self.graph_submissions = 0
        self.peak_rss_bytes = 0
        self._tracked.clear()
        self.log_path = self.settings.state_path / f"{session_id}-{role}.log"
        env = os.environ.copy()
        env.update(GGML_RPC_DEBUG="1", GGML_RPC_NO_RDMA="1", LLAMA_CACHE=str(self.settings.state_path / "cache"))
        self.process = await asyncio.create_subprocess_exec(
            *map(str, argv), stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
            env=env, cwd=str(self.settings.state_path),
        )
        self.reader = asyncio.create_task(self._read())

    async def _read(self):
        with self.log_path.open("a", encoding="utf-8") as file:
            while True:
                raw = await self.process.stdout.readline()
                if not raw:
                    break
                line = raw.decode(errors="replace").rstrip()
                file.write(line + "\n")
                file.flush()
                self.inspect_line(line)

    async def stop(self):
        if self.running:
            try:
                self.process.terminate()
            except ProcessLookupError:
                pass
            try:
                await asyncio.wait_for(self.process.wait(), timeout=8)
            except asyncio.TimeoutError:
                self.process.kill()
                await self.process.wait()
        if self.reader:
            await self.reader
        self.sample()
        self.role = None

    def sample(self):
        processes = []
        try:
            processes.append(psutil.Process(os.getpid()))
            if self.running:
                root = psutil.Process(self.process.pid)
                processes.extend([root] + root.children(recursive=True))
        except psutil.Error:
            pass
        rss, cpu, measured = 0, 0.0, False
        for process in processes:
            try:
                tracked = self._tracked.setdefault(process.pid, process)
                rss += tracked.memory_info().rss
                cpu += tracked.cpu_percent()
                measured = True
            except psutil.Error:
                pass
        self.rss_bytes = rss if measured else None
        self.cpu_percent = round(cpu, 1) if measured else None
        if measured:
            self.peak_rss_bytes = max(self.peak_rss_bytes, rss)

    def snapshot(self):
        return {
            "running": self.running, "role": self.role,
            "pid": self.process.pid if self.running else None,
            "rss_bytes": self.rss_bytes, "peak_rss_bytes": self.peak_rss_bytes,
            "cpu_percent": self.cpu_percent, "graph_submissions": self.graph_submissions,
            "placement": self.placement, "logs": list(self.log)[-30:],
            "revision": RUNTIME_REVISION,
            "memory_note": "Sampled process RSS (agent + native process tree). Not a hard cap; GPU allocation and OS memory pressure need separate validation.",
        }


def worker_command(settings):
    command = [str(settings.binary("ggml-rpc-server")), "--host", settings.bind_host,
               "--port", str(settings.rpc_port), "--threads", "4"]
    if settings.worker_device:
        command += ["--device", settings.worker_device]
    return command


def inference_command(settings):
    remote = [p.endpoint for p in settings.peers if p.id != settings.peer_id]
    if len(settings.devices) != len(settings.peers) or len(settings.tensor_split) != len(settings.devices):
        raise RuntimeError("Configure one measured runtime device and a positive split for each peer")
    return [str(settings.binary("llama-server")), "--model", str(settings.model),
            "--host", "127.0.0.1", "--port", str(settings.inference_port),
            "--rpc", ",".join(remote), "--device", ",".join(settings.devices),
            "--tensor-split", ",".join(map(str, settings.tensor_split)),
            "--split-mode", "layer", "--n-gpu-layers", "all", "--fit", "off",
            "--load-mode", "none", "--lazy-mode", "off", "--ctx-size", "2048",
            "--parallel", "1", "--batch-size", "128", "--ubatch-size", "64",
            "--cache-type-k", "f16", "--cache-type-v", "f16", "--flash-attn", "off",
            "--jinja", "--reasoning", "off", "--threads", "4", "-lv", "5"]
