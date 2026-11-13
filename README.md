# Open Swarm

Run one IBM Granite model across laptops that contribute spare memory and compute. Each laptop runs the same peer app; one temporarily coordinates a session. A React dashboard shows live peer status, observed process memory, native layer assignments and RPC graph submissions.

**Status:** physical two-Mac inference completed with Granite 4.2 8B Q4_K_M on November 13, 2026, using Metal on the M4 and an RPC Metal worker on the M3. The first completed request used 120 input tokens and 69 output tokens in 11.354 seconds after model loading. This is one measured run, not a benchmark. Memory fit within the owners' full budgets, three-host 30B execution and physical failure recovery remain unverified. The 8B run validates distribution, not that 8B needs multiple machines.

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

The first physical test used `"tensor_split": [9, 1]` over a private phone hotspot to reduce the initial transfer to B. Native logs reported 37 assignments on MTL0 and 4 on RPC0, including the output stage; this was an intentionally uneven split. An earlier equal-split load was stopped before generation because cold loading was slow. Copying the GGUF onto a worker does not bypass RPC tensor transfer.

New worker launches enable the native disk tensor cache (`--cache`), stored under ignored `.state/cache/rpc/`. The first load still transfers weights; subsequent loads can reuse cached tensors. The coordinator disables saved-prompt RAM caching (`--cache-ram 0`) after a physical run spent 51.7 seconds saving/restoring prompt state. This preserves the active attention KV cache. Restart the peer apps and shared session to apply these settings; existing native processes keep their original flags. In one physical two-Mac sequence, the initial cache-populating load took 241.8 seconds and the repeat load was observed ready at 39.7 seconds. A sample request after switching prompts took 9.0 seconds versus 63.8 seconds before the change. These are individual hotspot observations, not general benchmarks. Evidence and limits are recorded in `PROJECT_CONTEXT.md`.

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

The dashboard also displays the coordinator's latest completed answer after a page refresh or an API-initiated run, marked as a saved answer. A new dashboard request streams live. Saved answers do not re-run the prompt currently in the editor, and their original checks are not reconstructed without the original prompt.

## What this prototype proves

- A single selected 8B model executed across two physical Macs, with native placement and RPC activity recorded.
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

To record a request against an already active session, run `.venv/bin/python scripts/record_test.py` (or add `--prompt-file /path/to/prompt.txt`). It waits for readiness and saves the exact input, streamed output, reported token usage, timings, peer snapshots and native coordinator log under `.state/test-runs/`. It does not start a session. This helper records completion; the dashboard owns the built-in sample's correctness checks. These private logs are not committed or uploaded.

The separate IBM watsonx.ai reference run and provided IBM Cloud account usage remain deferred until the core distributed demo works.

## Sources

- [Pinned llama.cpp runtime](https://github.com/ggml-org/llama.cpp/tree/5676dfbe01e7ebe0387913680eee0ed39bf4a363)
- [IBM Granite 4.2 8B GGUF](https://huggingface.co/ibm-granite/granite-4.2-8b-GGUF)
- [IBM Granite 4.2 30B GGUF](https://huggingface.co/ibm-granite/granite-4.2-30b-GGUF)
