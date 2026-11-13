# Open Swarm

Run one IBM Granite model across laptops that contribute spare memory and compute. Each laptop runs the same peer app; one temporarily coordinates a session. A React dashboard shows live peer status, observed process memory, native layer assignments and RPC graph submissions.

**Status:** physical three-laptop inference completed with Granite 4.2 8B Q4_K_M on November 13, 2026: Metal on M4 and M3, plus a Windows CPU worker. A roughly equal split assigned 14 native stages to M4, 14 to Windows and 13 to M3, including the output stage. The three-case sample passed in 16.233 seconds after loading, with 120 input tokens and 69 output tokens. This is one measured run, not a general benchmark. Equal partitioning does not imply equal utilization or speed. Memory fit within the owners' full budgets, 30B execution and physical failure recovery remain unverified. The 8B run validates distribution, not that 8B needs multiple machines.

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

- A single selected 8B model executed across two physical Macs and a Windows laptop, with roughly equal native placement and actual RPC activity recorded.
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

## Temporary phone access

The optional guest gateway lets a phone submit a test without joining the laptops' LAN. The model still executes on the private compute peers. This is guest access to inference, not internet membership in the compute pool.

Keep the normal peer app and a working shared session running. In another terminal on the coordinator:

```bash
.venv/bin/python -m pip install -r requirements-guest.txt
.venv/bin/python scripts/guest.py --port 8002 --minutes 120 --max-jobs 20
```

This creates a separate pass in ignored `.state/guest-pass.json` and binds a guest-only web service to localhost. It accepts one request at a time, at most 2,000 prompt characters and 128 output tokens, with a shared 20-request allowance. The pass expires after two hours. It does not serve the peer control API, bootstrap credentials, native logs, model files or RPC. Inputs, outputs and usage are recorded privately under `.state/guest-jobs/`. Windows uses `.venv\Scripts\python.exe` for these commands.

After approving Cloudflare as the relay for non-sensitive demo prompts and outputs, use its official `cloudflared` binary in a separate terminal:

```bash
cloudflared tunnel --no-autoupdate --url http://127.0.0.1:8002 --protocol http2
```

Tunnel **only port 8002**. Do not tunnel port 8000, port 8081 or native RPC. The temporary HTTPS hostname is printed by Cloudflare. Generate the full private guest link and QR code:

```bash
.venv/bin/python scripts/guest_link.py --url https://YOUR-HOSTNAME.trycloudflare.com
```

To show this invite using the laptop dashboard's **Guest mode** button, run this on the guest host in another terminal:

```bash
.venv/bin/python scripts/guest_invite.py
```

This read-only helper listens on **127.0.0.1:8003** and requires the existing dashboard bearer token. It accepts only local dashboard origins, checks the existing pass against the localhost guest gateway, and generates a matching QR in memory. It does not create or renew passes, start tunnels, or restart inference. **Never tunnel port 8003.** Keep it running while using the dashboard's invite panel; it can be stopped independently of inference. Missing, expired, rejected, or exhausted passes are shown without a shareable QR. Gateway readiness does not prove that the external tunnel is reachable.

Share `.state/guest-url.txt` or `.state/guest-qr.png` only with intended guests. The URL fragment contains the limited guest pass; it is distinct from the private control token. The page stores it for that browser tab and removes it from the address bar. A bare tunnel URL can display the page but cannot submit jobs or retrieve results without the pass. Stopping the guest gateway revokes its pass; stopping the tunnel removes external reachability. Neither requires stopping the model session.

The phone polls for partial output because [Cloudflare Quick Tunnels do not support SSE](https://developers.cloudflare.com/tunnel/get-started/quick-tunnels/). These temporary tunnels have no uptime guarantee. The underlying guest gateway consumes the existing native stream and marks interrupted output incomplete.

## Sources

- [Pinned llama.cpp runtime](https://github.com/ggml-org/llama.cpp/tree/5676dfbe01e7ebe0387913680eee0ed39bf4a363)
- [IBM Granite 4.2 8B GGUF](https://huggingface.co/ibm-granite/granite-4.2-8b-GGUF)
- [IBM Granite 4.2 30B GGUF](https://huggingface.co/ibm-granite/granite-4.2-30b-GGUF)


### Chat history on each device

The laptop dashboard stores its conversations in that device's browser storage. Guest chats stay in the guest's browser tab. There is no shared chat list: neither page imports the coordinator's latest answer, and opening the same guest invite on another device does not load the first device's conversations. Existing auto-imported coordinator answers are excluded from the new dashboard history; locally submitted messages and drafts are retained. The legacy browser-storage entry is left intact as a backup.

Within the same browser, dashboard tabs merge messages by ID and preserve drafts. A live stream remains attached to its originating tab; reloading it may leave a clearly labeled partial response. Keep the submitting tab open until completion. New chat reuses an unused empty conversation. Recent complete turns from the selected chat are sent as bounded context, with the built-in sample sent independently for reproducible checks.

This is local conversation history, not an isolation boundary for the trusted demo operators: prompts still run through the session coordinator, and existing host-side demo records and native logs remain. Refresh the page after building updated assets; a frontend build does not require restarting the model or peer agent.
