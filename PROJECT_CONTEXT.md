# Open Swarm — implementation context

Last updated: November 13, 2026. This record distinguishes completed physical tests from remaining validation.

**Latest checkpoint:** one Granite 4.2 8B Q4_K_M model has executed across the M4 and M3 on a private phone hotspot. Native discovery, per-device assignments and a completed API request are verified. Both Macs remain on their 8 GB offers; RSS is not proof of a full memory-budget fit. Current split is intentionally uneven `[9, 1]` to reduce cold transfer, with 37 native assignments on MTL0 and 4 on RPC0 (including the output stage). Keep the warm session running. Do not restart installs or regenerate tokens. Add Windows and test 30B only after the two-Mac demo is stable. The watsonx.ai reference run remains deferred.

## Objective and current scope

Build a live demonstration of three laptops pooling computing resources to run **one IBM Granite model**, using Codex for development, llama.cpp RPC for model-parallel inference, and React + FastAPI to show each laptop's contribution. User explicitly authorized implementation. Build the core demo first; add the separate watsonx.ai reference run later.

The first user is a developer who wants to test an exact open model artifact that exceeds the memory they can spare. A smaller model cannot validate that artifact. Cloud execution remains a valid alternative; no claim of superior cost, speed, privacy, energy use, or quality has been established. The long-term problem can assume broader scale; the three-machine demo proves a narrow instance.

Working sample: three short support-message extraction cases producing JSON, with deterministic checks. This is a functional test of the selected model, not evidence that 30B is necessary for classifying tickets. The product remains the shared compute network.

## User decisions

- Name: **Open Swarm**. GitHub repository: **ysbeih/open-swarm**, now public.
- Brother: **GarouHD**. GitHub invitation sent; last observed state is pending acceptance.
- Use the `ysbeih` account, not the other accounts connected to Codex.
- Codex runs on the user's M4 Mac. IBM Bob handles setup and validation on the user's other Mac (M3), following `SECOND_SETUP.md`. Python, CMake, the pinned Metal build and native RPC discovery are verified. Preserve the working setup. The brother's computer is the Windows peer. These development tools are not core inference dependencies.
- No credits, earning/spending ledger, wallets, or payment.
- Build for one person; finished beats fancy; show the actual workflow live in person.
- No permanent central inference service/tracker. Same peer application on each laptop; a session has a temporary coordinator.
- Latest requested addition: a phone can submit jobs without joining the hotspot, through a separate temporary guest web gateway. Compute peers stay on the trusted private LAN. This does not add internet compute workers or expose native RPC.
- Manual membership, trusted LAN, one session and one active generation. No internet swarm, NAT traversal, live resharing, failover, marketplace, RAG, generated-code sandbox, or agent framework.
- User created the separate Open Swarm Codex project; the current chat is already in it.

## Hardware and model

| Peer | Owner and hardware | Offered RAM |
|---|---|---|
| A | User's Mac M4 Pro, 24 GB installed; Codex integration | 8,000,000,000 bytes |
| B | User's Mac M3 Pro, 18 GB installed, macOS 14.1; Bob setup assistance | 8,000,000,000 bytes |
| C | Brother's Windows laptop, Ryzen AI 9 365, 24 GB installed, Radeon 880M | 8,000,000,000 bytes |

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

Implemented, with a completed physical two-Mac inference request:

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
- The user's normal Terminal confirmed `MTL0: Apple M4 Pro` with approximately 18,185 MiB free reported by the backend. The Codex shell does not expose usable Metal. Launch the app from normal Terminal for the real Metal run. This available-memory report does not override the owner's 8GB contribution or establish model fit. Physical Metal generation is now verified on both Macs through RPC. An escalated project launcher also exposed Metal and LAN access during integration.
- Python compileall hit the host's redirected cache permission. Use `PYTHONDONTWRITEBYTECODE=1` for normal tests or set `PYTHONPYCACHEPREFIX` inside `.state` for compileall; do not request access to unrelated global caches.
- Official 8B GGUF download completed and passed the downloader's SHA-256/size checks: 5,347,917,952 bytes; SHA-256 `16a9369d0805f80b7377d25d87f937a90c05dc04ad79173a52001e42c9aab311`. Final `.gguf` and metadata are present. A physical two-Mac generation completed; full hardware-fit validation remains incomplete.
- M3 direct Terminal output confirms Python 3.12.16, CMake 4.5.0 and the configured Apple CommandLineTools path. The native Metal build and M4-to-M3 RPC discovery subsequently succeeded. To avoid installing Node on this worker, a verified ZIP of the already-built frontend is available locally at `.state/second-setup-ui.zip`; transfer it directly and extract from the M3 repo root. It contains only `frontend/dist/` assets, no tokens or model weights.
- Source is published at `ysbeih/open-swarm` (initial commit `5f17224`). GitHub CLI is authenticated as ysbeih after user authorization, with config isolated to ignored `.state/github-ysbeih` and owner-only permissions. Do not switch global identity or reveal credentials. Thirteen backend tests and the frontend production build pass. Physical 8B inference subsequently succeeded; see the checkpoint below.

## Physical checkpoint and immediate work

November 13, 2026: both Macs moved from hotel Wi-Fi to the same private phone hotspot. Cross-host discovery now reports local MTL0 (M4 Pro) and remote RPC0 (M3 Pro). Hotel client isolation was suspected after cross-host timeouts, but never independently established. Current LAN addresses are in ignored local configuration; both peers preserve the existing shared token. The old private setup ZIP contains the earlier network configuration: do not re-extract it over the working configuration.

The first equal-split load was intentionally stopped before generation because cold transfer was slow. The second session uses `[9, 1]`. Native model buffers were 4,192.20 MiB on MTL0 and 684.06 MiB on RPC0, plus 220.50 MiB on CPU. Native assignments 0–36 map to MTL0 and 37–40 to RPC0; these counts include the output stage. Both peers reported RPC graph submissions. These are not completed kernels or token counts.

First completed request: session `520567051a794740bd8d9a947e1df5fd`, request `bbe00242334842c592bd1d43ec92f355`. The three-message JSON extraction returned correct categories and order IDs, with case IDs encoded as strings. Usage was 120 prompt tokens and 69 completion tokens; server time 11.354 seconds, first token 2.725 seconds, after loading. Observed peak process RSS was about 5.39 GB on A and 0.91 GB on B. The recorder waited 333.928 seconds for readiness after it began observing; that is not the full cold-start duration. No general throughput or memory-fit claim follows from this single run.

Private evidence is under `.state/test-runs/20261113T185210Z-bf6b1746/`: exact input, raw stream, output, actual usage, timings, before/after peer snapshots, configuration provenance and native coordinator log. The first version of the recorder incorrectly required integer case IDs, unlike the existing dashboard. Its original FAIL verdict is preserved. Separate `dashboard-checks.json` evaluates the unchanged response with the pre-existing dashboard checker and passes all three cases. The recorder now logs completion only; the dashboard owns sample quality checks.

The dashboard previously showed only answers streamed by its own tab. It now restores the coordinator's latest completed answer from the existing peer API, explicitly labeled as a saved answer. Live output stays local to the submitting tab until completion; checks are only applied to a run of the exact built-in sample. This frontend change does not require a native restart. A fresh physical UI request completed and visibly passed all three checks: request `0ee3758848ea416aa24a3ba69cc3d042`, 120 prompt tokens, 69 completion tokens, 63.833 seconds total and 54.126 seconds to first token. Its input/output/usage and snapshots are saved under `.state/test-runs/20261113T190323Z-ui-c92b1c20/`. A separate user request occurred between its baseline snapshot and submission, so graph-count deltas cannot be attributed solely to this UI run. Thirteen API/lifecycle tests and the frontend production build passed after the UI change.

Performance finding: the native log for that UI request reports `prompt cache update took 51709.54 ms`, before prompt evaluation/generation. This observed cache-management delay explains most of the 63.833-second request time. The user authorized implementing both cache changes and restarting for validation: new coordinator launches use `--cache-ram 0` to disable saved-prompt caching (not the active attention KV cache); workers use `--cache` to save model tensors under `.state/cache/rpc`. Temporary discovery workers use that same private cache root. The changes pass the existing 13 tests and frontend build, and a separate native CPU worker confirmed cache initialization. The M3 pulled commit `b55d7ba` and restarted; no native rebuild, model download or configuration transfer was needed. The split remains `[9, 1]` to isolate the caching change. Physical validation is complete: the first cache-populating load took 241.804 seconds; the reload was observed ready at 39.670 seconds. The JSON request after switching to `hello` and back took 8.974 seconds (previously 63.833 seconds). All three sample checks passed; native logs report prompt caching disabled and no saved-prompt cache updates. These are observed runs on a shared hotspot, not controlled general benchmarks.

`scripts/record_test.py` records one request against an existing session without starting one. All test evidence remains ignored by Git. The server's existing completed-result files contain output and usage but no original prompt; the recorder captures the input as well. A full GGUF on a worker's disk does not avoid stock RPC tensor transfer. Native tensor caching is enabled for new workers only; old workers retain their original flags until restarted.

1. Both authorized cache changes are active and physically verified. Keep the current session warm. Evidence: `.state/cache-update/20261113T191530Z/verification-completed.json`; the final post-reload request and input/output/usage are under `.state/test-runs/20261113T192117Z-593eb2db/` (11.876 seconds, 120 input / 69 output tokens, three passing checks). The original private verifier stopped on an overly strict cache-log assertion after a successful reload: the last-30-line peer snapshot had dropped startup lines. Its original failure record is preserved, with separate completion evidence. Per-tensor cache-hit counts were not collected.
2. Verify physical stop/withdrawal behavior and complete OS/native memory checks before declaring a stable budget fit. Automated lifecycle tests are not substitutes.
3. Native worker tensor caching is now enabled and a repeat load was faster in the observed test. A better local network and a more even split remain separate, untested changes; do not conflate them with this result.
4. Source, recorder, frontend fix and neutral second-setup instructions are published in `b55d7ba`. Keep local configuration, token, evidence, binaries and model weights private. M3 needs a frontend rebuild if it has not yet done one; that UI update does not require another worker restart.
5. Add the third laptop and test 30B only after the working two-Mac profile is preserved. No 30B model execution or reference equivalence is verified.
6. Later: separate watsonx.ai reference run using the provided IBM account, plus hackathon submission evidence.

## Guest gateway checkpoint

Implemented `backend/swarm/guest.py`, `scripts/guest.py`, a small responsive `guest/` frontend, and `scripts/guest_link.py` with optional QR dependencies in `requirements-guest.txt`. It is a separate localhost service on port 8002; do not mount or tunnel the control API. A randomly generated guest pass lasts up to two hours by default, allows 20 total jobs, and is separate from the peer bearer token. Inputs are capped at 2,000 characters and replies at 128 tokens; only one guest job runs at a time. The guest API exports a small allowlist of result/status fields and records full job input/output/usage privately under `.state/guest-jobs/`.

Seventeen tests pass, including guest authorization, expiry, absent control routes, body limits, busy/quota handling, output completion and local-record permissions. Frontend production build and guest JavaScript syntax checks pass. A real local guest-page request executed across both Macs and visibly completed in 11.77 seconds with 69 output tokens; native inference stayed loaded. The guest page was inspected at a phone-size viewport. This is not yet evidence of access from a physical phone's cellular network.

Cloudflare's official macOS ARM64 binary version 2026.11.0 was downloaded into ignored `.tools/cloudflared/` and verified against the release asset SHA-256. Opening the public tunnel was rejected by automatic approval review because guest prompts/outputs would traverse Cloudflare and that specific destination had not been explicitly approved. User approval was requested with the bounded scope and non-sensitive demo-data restriction. Do not retry the tunnel until that approval arrives. No public tunnel is running at this checkpoint. The guest gateway itself is running locally; public URL/QR creation and external verification remain pending.

## Hackathon and original research

Michigan DevFest + AI Hackathon, November13,2026. Rules explicitly accept IBM Granite and separately require using the provided IBM Cloud account. Business productivity and Michigan impact remain part of the pitch. Reference run deferred, not permanently removed from final eligibility work.

Rules: https://drive.google.com/file/d/1o1qw2w_xSat3OBMUhLRQATFC2GJYK-Ld/view

Official model files:
- https://huggingface.co/ibm-granite/granite-4.2-8b-GGUF/tree/main
- https://huggingface.co/ibm-granite/granite-4.2-30b-GGUF/tree/main

The parent workspace contains design history in `../outputs/final-product-and-architecture-decision-record.md` and `../work/`. Some persona/demo sections there predate the latest decisions above. Do not reintroduce old credits, LeetCode, or centralized PyTorch designs.
