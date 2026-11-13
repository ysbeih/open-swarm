# Open Swarm

Run one IBM Granite model across laptops that contribute spare memory and compute. Each laptop runs the same peer app; one temporarily coordinates a session. A React dashboard shows live peer status, observed process memory, native layer assignments and RPC graph submissions.

**Status:** working local dashboard, automated lifecycle/API tests, and compiled native runtime. Physical two-laptop inference and memory fit are not yet verified. Start with two Macs and Granite 4.2 8B Q4_K_M; add a third laptop before attempting 30B Q4_K_M. The 8B run validates distribution, not that 8B needs multiple machines.

## First setup on each Mac

Prerequisites: Git, Python 3.9 or newer (3.12 recommended), Node 22.12+ or 24, CMake 3.24+, Apple command-line developer tools. If Homebrew is already installed:

```bash
brew install cmake python@3.12 node@22
export PATH="$(brew --prefix node@22)/bin:$PATH"
git clone https://github.com/ysbeih/open-swarm.git
cd open-swarm
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
npm --prefix frontend ci
npm --prefix frontend run build
.venv/bin/python scripts/build_runtime.py
```

The last command builds the pinned llama.cpp revision with Metal and RPC. Keep the checkout in the same folder after building. If the compiler is missing, run `xcode-select --install` and complete Apple's installer, then retry the build. If Homebrew is unavailable or starts a long source build on older macOS, resolve that prerequisite before continuing; do not upgrade the OS for the demo.

## Configure the two laptops

Both computers must be on a trusted LAN that permits peer connections. Find each Wi-Fi address with `ipconfig getifaddr en0` (use the active network interface if different). On **one** laptop, substitute the real addresses:

```bash
.venv/bin/python scripts/configure.py --a 192.168.1.10 --b 192.168.1.11
```

This generates `config/peer-a.json` and `config/peer-b.json` with a shared control token. Transfer B's file directly to B, for example with AirDrop. On each laptop copy its own file to `config/local.json`. Never commit or paste these files publicly. Do not generate independent tokens on the two laptops. The script refuses to overwrite existing configurations.

Start a temporary discovery worker on **B**:

```bash
.venv/bin/python scripts/devices.py --worker
```

While it is running, list the devices from **A**:

```bash
.venv/bin/python scripts/devices.py
```

Use the exact names shown by the pinned runtime. The M4 Pro is confirmed as `MTL0` from a normal Terminal. A typical two-Mac configuration on A is `"devices": ["MTL0", "RPC0"]` and `"tensor_split": [1, 1]`. Verify that MTL0 is the local Mac and RPC0 is B. Do not invent names if discovery fails. B can leave `devices` empty when contributing only; it needs discovery and the model file before it can coordinate a later session.

Stop B's temporary discovery worker with **Ctrl+C** before starting the app-managed session. This releases its RPC port.

## Download the integration model on A only

```bash
.venv/bin/python scripts/download_model.py --size 8b
```

The downloader fetches the official IBM GGUF at an immutable revision, verifies its SHA-256 and writes metadata beside it. The 8B Q4_K_M download is approximately 5.35 GB. Only the coordinator needs the complete model file on disk; remote RPC workers receive their tensors from it. This is not per-peer torrent downloading.

## Run the demo

On **each** laptop:

```bash
.venv/bin/python scripts/serve.py
```

Open **http://localhost:8000** in that laptop's browser. The API also listens on the configured LAN address; dashboard token bootstrap accepts localhost only.

Launch the app from a normal Terminal if a coding agent's restricted shell cannot see Metal. The native child process inherits the environment of the app launcher. Device enumeration alone does not prove model execution.

1. Both owners select **Share this laptop**. Check that both peers appear online.
2. On A, select **Start shared session**. Loading can take time over Wi-Fi. A ready state requires native model health and layer assignments on every selected device.
3. Run the built-in three-case extraction prompt. The model's streamed JSON is checked against actual expected values. Editing the prompt disables that specific check.
4. Show native layer assignments, live memory and worker graph activity. An online peer alone is not proof of model execution.
5. Stop sharing on B. The session must become unavailable; partial output must not be presented as a completed result. Reset and restart for another demonstration.

If macOS asks about incoming connections, allow the project processes on the trusted demo network. Do not disable the firewall. API port: 8000; native RPC port: 50052; coordinator inference: localhost 8081. Network isolation on event Wi-Fi can prevent peer access.

## What this prototype proves

- A single selected model can be placed across native devices, subject to the pending physical test.
- Participants explicitly enable and withdraw their contribution.
- Any configured peer can submit to the active session. A different coordinator requires a cold reload and its own model file/device configuration.
- There is no permanent tracker, hosted answer service, credit ledger or automatic failover.

The native data path is a star through the session coordinator. Workers do not directly pass activations to one another. Raw llama.cpp RPC is experimental and unauthenticated: use trusted LAN peers and synthetic inputs only. The control API's token does not protect the native RPC protocol.

Each peer offers at most 8,000,000,000 bytes. The sampled RSS stop guard includes the Python agent and its native process tree, but is not a hard quota and does not fully account for GPU/unified memory. Split ratios are placement preferences, not memory guarantees. Graph submissions are not completed kernels or token counts.

30B Q4_K_M weights alone are approximately 17.7 GB, exceeding two 8 GB contributions. Three-host fit still needs actual measurement of weights, cache, loading buffers and runtime overhead. We make no unmeasured speed, quality, cost or energy claim.

## Development and verification

```bash
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m pytest -q
npm --prefix frontend run build
```

Tests cover consent, two-peer routing, immutable reservations, competing starts, stale stop requests, process shutdown, failed workers, API authorization, stream completion and native log parsing. Test doubles are restricted to tests. Passing these checks does not establish physical distributed inference.

Native logs and completed request evidence are saved under `.state/`; all local configuration, tokens, runtime binaries and weights are ignored by Git. The model SHA-256 accompanies successful results. See `PROJECT_CONTEXT.md` for current scope and remaining validation.

The separate IBM watsonx.ai reference run and provided IBM Cloud account usage remain deferred until the core distributed demo works.

## Sources

- [Pinned llama.cpp runtime](https://github.com/ggml-org/llama.cpp/tree/5676dfbe01e7ebe0387913680eee0ed39bf4a363)
- [IBM Granite 4.2 8B GGUF](https://huggingface.co/ibm-granite/granite-4.2-8b-GGUF)
- [IBM Granite 4.2 30B GGUF](https://huggingface.co/ibm-granite/granite-4.2-30b-GGUF)
