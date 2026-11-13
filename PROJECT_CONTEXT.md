# Open Swarm — implementation context

Last updated: November 13, 2026. This is a working status record, not proof that the demo has run.

**Latest steering:** start with the two Macs. Their LAN addresses are configured in ignored `config/peer-a.json` and `config/peer-b.json`. The second Mac's owner can run Terminal commands; it has Git 2.48.1, Python 3.8.2 and Node 18.13.0, but no CMake. They were given Homebrew commands for CMake, Python 3.12 and Node 22; completion is pending. Use Granite 8B for integration: 30B Q4 weights exceed two 8GB offers. Add Windows and test 30B after the real two-Mac path works. Open Swarm exists as a Codex project and this chat was moved into it.

## Objective and current scope

Build a live demonstration of three laptops pooling computing resources to run **one IBM Granite model**, using Codex for development, llama.cpp RPC for model-parallel inference, and React + FastAPI to show each laptop's contribution. User explicitly authorized implementation. Build the core demo first; add the separate watsonx.ai reference run later.

The first user is a developer who wants to test an exact open model artifact that exceeds the memory they can spare. A smaller model cannot validate that artifact. Cloud execution remains a valid alternative; no claim of superior cost, speed, privacy, energy use, or quality has been established. The long-term problem can assume broader scale; the three-machine demo proves a narrow instance.

Working sample: three short support-message extraction cases producing JSON, with deterministic checks. This is a functional test of the selected model, not evidence that 30B is necessary for classifying tickets. The product remains the shared compute network.

## User decisions

- Name: **Open Swarm**. GitHub repository: **ysbeih/open-swarm**, now public.
- Brother: **GarouHD**. GitHub invitation sent; last observed state is pending acceptance.
- Use the `ysbeih` account, not the other accounts connected to Codex.
- Keep the coding setup in Codex. Bob/Gemini are optional development tools, not core inference dependencies.
- No credits, earning/spending ledger, wallets, or payment.
- Build for one person; finished beats fancy; show the actual workflow live in person.
- No permanent central inference service/tracker. Same peer application on each laptop; a session has a temporary coordinator.
- Manual membership, trusted LAN, one session and one active generation. No internet swarm, NAT traversal, live resharing, failover, marketplace, RAG, generated-code sandbox, or agent framework.
- User created the separate Open Swarm Codex project; the current chat is already in it.

## Hardware and model

| Peer | Hardware | Offered RAM |
|---|---|---|
| A | Mac M4 Pro, 24 GB installed | 8,000,000,000 bytes |
| B | Mac M3 Pro, 18 GB installed, macOS 14.1 | 8,000,000,000 bytes |
| C | Windows, Ryzen AI 9 365, 24 GB installed, Radeon 880M | 8,000,000,000 bytes |

The memory contribution is decimal 8 GB (~7.45 GiB), including runtime overhead, not the entire installed RAM. Shared GPU memory is not additional capacity. macOS Metal on A/B; native CPU on Windows C. No driver or OS upgrade on the critical path.

- Integration model: IBM Granite 4.2 8B Q4_K_M, official GGUF approximately 5.35 GB.
- Target: IBM Granite 4.2 30B Q4_K_M, approximately 17.7 GB.
- 30B is unverified within the three budgets. Whole-model file size alone does not establish fit. A sufficiently provisioned single machine could run it; do not claim otherwise.
- Candidate runtime pin: `5676dfbe01e7ebe0387913680eee0ed39bf4a363` from `ggml-org/llama.cpp`.
- Start with context 2048, one sequence, batch128/ubatch64, FP16 KV, flash attention off, greedy output, thinking off.
- Native worker binary: `ggml-rpc-server`. Coordinator: `llama-server` with explicit devices/split and RPC endpoints.
- Prospective coordinators need the entire GGUF on disk. Stock RPC does not download only each peer's layers.

## Architecture and truthfulness

All peers expose the same FastAPI application and local React dashboard. Each owner enables sharing. A coordinator reserves the two or three configured peers using an immutable session manifest, starts remote RPC workers, then loads the model. Requests from any peer are forwarded to that session's coordinator. Changing coordinator requires unloading/reloading; there is no hot migration.

The native data path is a star around the temporary coordinator. Model computation is distributed; workers do not directly pass activations to each other. Keep this distinction honest.

All telemetry must come from actual processes/logs. Process RSS is an incomplete measurement of total memory, particularly unified/GPU allocations. The stop guard is sampled and advisory, not a hard quota. Native RPC graph submissions are not completed kernels, tokens, or performance measurements.

Raw llama.cpp RPC is a fragile, insecure prototype. Use only trusted isolated LAN peers and synthetic demo inputs. A control API bearer token does not secure native RPC.

## Implementation status

Local path: `/Users/viviana/Documents/Codex/2026-11-12/files-pasted-by-the-user-multi/open-swarm`.

Implemented, with physical inference still pending:

- `backend/swarm/config.py`: typed local configuration and roster.
- `backend/swarm/runtime.py`: native process supervision, log parsing, RSS/CPU samples, native commands.
- `backend/swarm/peer.py`: owner consent, prepare/commit, session stop/reset, generation stream, peer status.
- `backend/swarm/app.py`: FastAPI routes, local token bootstrap, request forwarding, static UI serving.
- `frontend/src/main.jsx` and `style.css`: styled React dashboard, two/three-peer layouts and three-case JSON test. Production build passes; local browser layout inspected.
- `scripts/serve.py`: one app listening on localhost and the configured LAN address.
- Build, model-download, peer-configuration and device-discovery scripts; README with two-Mac setup steps.
- Lifecycle/API tests cover consent, races, reservation integrity, failures, stopping, authorization, streams and native evidence parsing. Two-peer and fresh-configuration checks added.

Environment:

- Python 3.9.6; project `.venv` has FastAPI 0.115.14, uvicorn0.34.3, httpx0.28.1, psutil7, pytest8.4.2 and pytest-asyncio0.25.3 installed.
- Node24.22.1 is on PATH. No global npm. Downloaded npm11.6.2 lives at `.tools/package/bin/npm-cli.js`; invoke it with `node`. Set npm cache to `.tools/npm-cache` inside the repository.
- CMake and AppleClang are available. No global `gh` installed.
- Pinned llama.cpp source downloaded in `.tools/llama.cpp`. Metal/RPC `llama-server` and `ggml-rpc-server` successfully compiled.
- Native binaries were rebuilt after the folder rename with corrected rpaths. `llama-server --version` works. A real loopback CPU RPC worker was discovered as RPC0; this is not a physical cluster test.
- The Codex shell's device discovery has not exposed usable local Metal. Verify from the user's Terminal before diagnosing hardware support. CPU worker execution works; no Metal or distributed generation has run yet.
- Python compileall hit the host's redirected cache permission. Use `PYTHONDONTWRITEBYTECODE=1` for normal tests or set `PYTHONPYCACHEPREFIX` inside `.state` for compileall; do not request access to unrelated global caches.
- Official 8B GGUF download is in progress; `.gguf.part` is incomplete and must not be used. No generation or hardware-fit measurement completed. Do not interrupt the downloader casually: the current script does not resume partial files.
- GitHub CLI is authenticated as ysbeih after user authorization. Config is isolated to ignored `.state/github-ysbeih`, with owner-only permissions. Do not switch global identity or reveal credentials. First source push is being prepared.

## Immediate remaining work

1. Push reviewed source so the second Mac can clone it and build the pinned native runtime.
2. Transfer its ignored peer configuration directly; check authenticated peer connectivity and native device discovery. Stop temporary discovery workers before app-managed startup.
3. Finish/hash the official 8B download. Run actual two-Mac inference, record layer placement, memory, latency and failure behavior. Loopback success is not physical distribution.
4. Resolve local Metal visibility from the user's Terminal; do not fabricate device names or claim a successful GPU run.
5. Restart the local app with its actual LAN configuration and exact discovered devices, then verify both dashboards.
6. Add the third laptop and test 30B only after 8B distributed execution works. Preserve the integration profile.
7. Later: separate watsonx.ai reference run using the provided IBM account, plus hackathon submission evidence.

## Hackathon and original research

Michigan DevFest + AI Hackathon, November13,2026. Rules explicitly accept IBM Granite and separately require using the provided IBM Cloud account. Business productivity and Michigan impact remain part of the pitch. Reference run deferred, not permanently removed from final eligibility work.

Rules: https://drive.google.com/file/d/1o1qw2w_xSat3OBMUhLRQATFC2GJYK-Ld/view

Official model files:
- https://huggingface.co/ibm-granite/granite-4.2-8b-GGUF/tree/main
- https://huggingface.co/ibm-granite/granite-4.2-30b-GGUF/tree/main

The parent workspace contains design history in `../outputs/final-product-and-architecture-decision-record.md` and `../work/`. Some persona/demo sections there predate the latest decisions above. Do not reintroduce old credits, LeetCode, or centralized PyTorch designs.
