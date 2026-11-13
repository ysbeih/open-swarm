# Open Swarm — implementation context

Last updated: November 13, 2026. This record distinguishes completed physical tests from remaining validation.

**Latest checkpoint:** READY after restoring all three laptops to the hotspot and re-enabling Windows sharing. Session `0a67e4bc675344b18a2c886cbf355f22` runs Granite 4.2 8B Q4_K_M on M4, M3 and Windows. A fresh request through the public Cloudflare guest gateway completed in 23.284 seconds (first token 5.317 seconds, 120 prompt / 69 completion tokens), and the unchanged dashboard evaluator passed all three extraction checks. Native placement shows 14 assignments on M4, 14 on Windows and 13 on M3, including output. Graph-submission deltas were 140/70/70 respectively; these are not tokens or completed kernels. The live checker returned READY with no blockers. Exact input, output, usage, before/after snapshots, native log and checks are private under `.state/end-to-end/20261113T230404Z-930b19b1/`. The existing phone link and QR remain valid until 7:05 PM; this check consumed one guest request. Keep the three apps, warm session, guest gateway and tunnel running. No configuration file changed: the local config hash still matches the fingerprint recorded before this recovery.

**Session participant selection:** pulled main through `365a096`, then added a per-session two/three-peer selection to the dashboard and start API. Saved configuration retains the three-peer roster. Selected RPC indices and split ratios are derived without rewriting it; prepare, health, snapshots, checker and stop follow the immutable selected membership. The initiating laptop must participate. Subset sessions require updated selected workers; old workers produce a clear update-required error. Full-roster execution with the updated M4 and existing M3/Windows apps is physically verified above. The two-peer subset path passes API/lifecycle tests but has not yet been executed on physical peers; update/restart M3 before trying it. Validation: 92 Python tests, 18 UI tests, production build, and visual inspection of the participant controls. Do not interrupt the working three-laptop session just to update workers.

**Historical publication check before recovery:** the read-only checker returned BLOCKED: the coordinator was in `failed` state with its native runtime stopped after three consecutive missed health checks. M3 remained worker-ready; Windows was unreachable during the direct check. The browser showed the corresponding failure state at desktop and 390-pixel mobile widths. Publication validation passed 80 Python tests, 18 UI tests, the frontend production build and the guest JavaScript syntax check. No service restart, session reset or new inference request was performed during publication. Inspect live state before resuming the demo.

## Objective and current scope

Build a live demonstration of three laptops pooling computing resources to run **one IBM Granite model**, using llama.cpp RPC for model-parallel inference and React + FastAPI to show each laptop's contribution. User explicitly authorized implementation. Build the core demo first; add the separate watsonx.ai reference run later.

The first user is a developer who wants to test an exact open model artifact that exceeds the memory they can spare. A smaller model cannot validate that artifact. Cloud execution remains a valid alternative; no claim of superior cost, speed, privacy, energy use, or quality has been established. The long-term problem can assume broader scale; the three-machine demo proves a narrow instance.

Working sample: three short support-message extraction cases producing JSON, with deterministic checks. This is a functional test of the selected model, not evidence that 30B is necessary for classifying tickets. The product remains the shared compute network.

## User decisions

- Name: **Open Swarm**. GitHub repository: **ysbeih/open-swarm**, now public.
- Brother: **GarouHD**. GitHub invitation sent; last observed state is pending acceptance.
- Use the `ysbeih` account with repository-specific authentication; do not change the global GitHub identity.
- Development and integration run on the user's M4 Mac. Setup and validation on the user's other Mac (M3) follow `SECOND_SETUP.md`. Python, CMake, the pinned Metal build and native RPC discovery are verified. Preserve the working setup. The brother's computer is the Windows peer.
- No credits, earning/spending ledger, wallets, or payment.
- Build for one person; finished beats fancy; show the actual workflow live in person.
- No permanent central inference service/tracker. Same peer application on each laptop; a session has a temporary coordinator.
- Latest requested addition: a phone can submit jobs without joining the hotspot, through a separate temporary guest web gateway. Compute peers stay on the trusted private LAN. This does not add internet compute workers or expose native RPC.
- Manual membership, trusted LAN, one session and one active generation. No internet swarm, NAT traversal, live resharing, failover, marketplace, RAG, generated-code sandbox, or agent framework.
- Work in the existing Open Swarm project and preserve its implementation and local state.

## Hardware and model

| Peer | Owner and hardware | Offered RAM |
|---|---|---|
| A | User's Mac M4 Pro, 24 GB installed | 8,000,000,000 bytes |
| B | User's Mac M3 Pro, 18 GB installed, macOS 14.1 | 8,000,000,000 bytes |
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

Local checkout: the Open Swarm repository root containing this file.

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
- The user's normal Terminal confirmed `MTL0: Apple M4 Pro` with approximately 18,185 MiB free reported by the backend. The restricted development shell used during initial setup did not expose usable Metal. Launch the app from normal Terminal for the real Metal run. This available-memory report does not override the owner's 8GB contribution or establish model fit. Physical Metal generation is now verified on both Macs through RPC. An escalated project launcher also exposed Metal and LAN access during integration.
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
3. Native worker tensor caching is enabled and a repeat two-Mac load was faster in the observed test. Equal three-peer partitioning was subsequently verified separately below; do not conflate the two experiments. A better local network remains untested.
4. Source, recorder, frontend fix and neutral second-setup instructions are published in `b55d7ba`. Keep local configuration, token, evidence, binaries and model weights private. M3 needs a frontend rebuild if it has not yet done one; that UI update does not require another worker restart.
5. Windows was added after preserving the two-Mac configuration. Initial direct M4-to-Windows TCP and pinned llama.cpp discovery succeeded at 20:22 UTC, reporting 23,673 MiB total and 3,974 MiB free. That memory report is below the offered 8 GB and does not establish model fit. Private discovery evidence: `.state/windows-discovery/20261113T202241Z/`. Its initial RPC0 name changed to RPC1 when both remote peers were registered; the full device mapping and three-host execution are verified below. No 30B execution or reference equivalence is verified.
6. Later: separate watsonx.ai reference run using the provided IBM account, plus hackathon submission evidence.

## Three-laptop integration

All three peer apps now use the same ordered roster `a, b, c`, shared token and 8 GB offers. Actual native load logs map MTL0 to M4, RPC0 to M3 and RPC1 to Windows. The first three-host session `22a781ecf2f246b481583754beeff8c9` used device order `[MTL0, RPC1, RPC0]` and split `[8, 1, 1]`, preserving M3's cached final slice. A real sample request completed in 20.296 seconds with 6.185 seconds to first token, 120 prompt tokens and 69 completion tokens. The existing dashboard evaluator passed all three extraction checks. RPC graph-submission deltas were 140 at the coordinator and 70 at each worker; these are not token or completed-kernel counts. Observed peak process RSS was 4.862 GB on M4, 0.948 GB on M3 and 0.619 GB on Windows, with the usual unified/GPU-memory limitations. Exact input/output/usage, snapshots, native logs and checks are under `.state/test-runs/20261113T202801Z-7f466bc8/`.

The user requested roughly one-third of the work per laptop. Equal layer partitioning does not guarantee equal execution time or utilization across Metal and CPU backends. Session `8ace190e8ed04b629dd24626ff019ea0` successfully runs `[1, 1, 1]` in device order `[MTL0, RPC1, RPC0]`: 14 native assignments on M4, 14 on Windows and 13 on M3, including the output stage. Actual model buffers are 1,608.06 MiB on M4, 1,552.38 MiB on Windows and 1,715.83 MiB on M3, plus 220.50 MiB of coordinator CPU weights; runtime/cache/temporary allocations are additional. Request `a747747008d9492280056b5ada3f5cb0` passed all three sample checks in 16.233 seconds, with 3.9 seconds to first token, 120 prompt tokens and 69 completion tokens. Per-request graph-submission deltas were 140 at the coordinator and 70 at each worker. Observed peak process RSS was 2.256 GB on M4, 2.113 GB on M3 and 1.810 GB on Windows; this remains incomplete unified/GPU accounting, not proof of a hard budget fit. The recorder observed 870.728 seconds (~14.5 minutes) waiting for this first redistributed load. This is a measured run, not a general benchmark or verified cached-reload time. One temporary M3 status-connection failure during loading recovered without a restart.

The coordinator's configurable `model_load_timeout_seconds` retains a default of 600, accepts 60–1800, and is set locally to 1800 for the larger first transfer over the hotspot. The 17 backend tests and frontend production build pass. Equal-split input/output/usage, snapshots, native logs and `verified-summary.json` are under `.state/test-runs/20261113T203232Z-2dcf918b/`. Private two-peer backups and the working unequal three-peer fallback are under `.state/three-laptop/20261113T202502Z/`. Keep the existing coordinator, guest gateway, tunnel and remote apps running; the model is warm. Starting another M4 `scripts/serve.py` fails with address already in use because the current server owns port 8000; it does not require a reinstall or stopping the current server.

## Contribution status UI

The user requested a clear distinction between an active laptop and one actually holding model memory. The dashboard now separates `Online` (peer app reachable), `Sharing enabled` (owner opted in, awaiting a model), and `Memory in use` (running native process in the same confirmed loaded session). Loaded peers remain memory contributors between requests; their detail changes to `session generating` when the coordinator is busy. Loading, stopping, failed, offline and stale states have distinct labels and never inherit a positive loaded-memory badge from cached status. Process RSS remains separately labeled and is not presented as exact shared-model memory. The aggregate view counts online laptops separately from laptops holding model memory and labels offered RAM as a combined limit.

This is a frontend-only update in `frontend/src/main.jsx`, `style.css` and `peer-status.js`; it requires an asset rebuild/browser refresh, not a peer-server or native-runtime restart. Validation: frontend production build, 18 UI tests, 33 backend tests, browser inspection at regular/narrow layouts, live idle three-peer API classification, and classification of the recorded successful equal-split snapshot. The recorded loaded snapshot is not a fresh inference test. Evidence remains private under `.state/ui-contribution-status/`. Coordinator-only setup-warning cleanup remains deferred until after the demo.

## Larger-model preflight

The user asked to try a larger model, then asked us to check remote RAM directly. A temporary RPC discovery reservation read Windows available physical RAM as 6.20 GB; the M4 OS reported 9.29 GB available. The user subsequently relayed 6.93 GB available on the M3 after the requested local psutil command. This differs from its 12.88 GB Metal working-set budget, which is not a system-available-RAM reading. The current peer API does not expose that OS metric. An equal Q4 split would leave the M3 about 0.99 GB after estimated weights and KV, before other overhead; Windows remains the tighter constraint at about 0.23 GB. Temporary discovery workers were stopped cleanly, and the 8B configurations were preserved.

Official 30B Q4_K_M metadata was pinned at revision `27b350a791e81d9a4d1ddca1c49282e9ec533768`: 17,721,455,328 bytes, SHA-256 `f299dace85d77ee0e24ca0b6720bd211b1f4cd1f65b9c0a2111e79692e29c9be`. A 16 MiB range sample was fetched; no full larger-model download or execution has started. Parsing that GGUF header gives 64 decoder layers plus output. With the current equal split/device order, Windows would hold about 5.788 GB of weights and an estimated 0.185 GB FP16 KV cache at context 2048, leaving only about 0.230 GB of its observed available RAM for runtime, temporary buffers and OS variation. Fit is not established. The short download probe averaged 3.97 MB/s including connection setup; extrapolating that small sample gives about 75 minutes just to download, before the substantial first LAN distribution. This is not a sustained download benchmark. The official Q3_K_M artifact is 14.133 GB, but has not been selected or tested. Private metadata, memory readings and calculations are in `.state/larger-model-preflight/`.

Subsequent Q3 attempt: the user authorized finding and adding a Granite artifact exceeding a single 8 GB offer. The official 30B Q3_K_M artifact at the same revision is 14,133,162,720 bytes, SHA-256 `7aad53fe80a9751d543ee6799d205a0a4f5d07e8d7f186b8753bdad7a12dc312`. A bounded header read estimates weights of 4.725 GB on M4, 4.657 GB on Windows and 4.571 GB on M3, plus 0.177 GB coordinator CPU embeddings and additional attention/runtime buffers. Windows later reported 6,386 MiB (6.696 GB) available through its native CPU backend. Both remote workers accepted a temporary 30B manifest and native discovery succeeded; this did not load a model, and both reservations were stopped cleanly. Windows' fixed 8B model hash was cleared at the user's instruction, allowing the trusted coordinator's selected artifact, as already configured on M3.

The full Q3 download then lost its connection at about 3.06 GB. The user reported a much slower hotspot and explicitly chose to return to the smaller demo. The download and bounded parallel probe are stopped; do not resume them without renewed user direction. The partial download remains ignored. The 30B candidate was never activated or executed. Active config still selects the verified 8B Q4_K_M and equal split. Private candidate/rollback configs and evidence are under `.state/larger-model-preflight/`. `scripts/configure.py --quant Q3_K_M` and the dashboard candidate card support a later experiment without presenting it as verified.

## Demo checker review

Reviewed PR #1 at `adb3b07` and reproduced false READY for failed/missing remote workers and failed refreshes, stale coordinator readiness, and false BLOCKED on healthy worker-only laptops. The corrected branch is pushed as `c8924aa` on `check-demo`; the PR remains open. It validates every configured member, full session agreement, current native roles/running state, and native placement, while treating model files/device selection as coordinator-only requirements. Malformed responses return UNKNOWN, and both output formats redact credentials. 38 checker tests pass, including three-peer and worker-view regressions. All local Python tests total 72, UI tests 18, and the production build passes. Replaying the archived successful physical snapshot returns READY from all three perspectives; replay is not a new physical test. Live idle checks correctly report no active session. The user then requested the cached 8B demo. Its fresh run under `.state/test-runs/20261113T220053Z-ea78a1ee/` completed and passed the unchanged dashboard evaluator: 22.651 seconds, 7.47 seconds to first token, 120 prompt and 69 output tokens. The recorder observed 163.104 seconds waiting for readiness (not the full load duration). Graph-submission deltas were 140 on M4 and 70 on each worker; these are not tokens or completed kernels. Peak RSS was 2.251 GB on M4, 0.960 GB on M3 and 1.843 GB on Windows, with incomplete unified/GPU accounting. `verified-summary.json` and `dashboard-checks.json` preserve the evidence. The live corrected checker returns READY; the browser shows 3/3 memory contributors. Do not reload this working session.

## Guest gateway checkpoint

Implemented `backend/swarm/guest.py`, `scripts/guest.py`, a small responsive `guest/` frontend, and `scripts/guest_link.py` with optional QR dependencies in `requirements-guest.txt`. It is a separate localhost service on port 8002; do not mount or tunnel the control API. A randomly generated guest pass lasts up to two hours by default, allows 20 total jobs, and is separate from the peer bearer token. Inputs are capped at 2,000 characters and replies at 128 tokens; only one guest job runs at a time. The guest API exports a small allowlist of result/status fields and records full job input/output/usage privately under `.state/guest-jobs/`.

Seventeen tests pass, including guest authorization, expiry, absent control routes, body limits, busy/quota handling, output completion and local-record permissions. Frontend production build and guest JavaScript syntax checks pass. A real local guest-page request executed across both Macs and visibly completed in 11.77 seconds with 69 output tokens; native inference stayed loaded. The guest page was inspected at a phone-size viewport. This is not yet evidence of access from a physical phone's cellular network.

Cloudflare's official macOS ARM64 binary version 2026.11.0 was downloaded into ignored `.tools/cloudflared/` and verified against the release asset SHA-256. The user subsequently authorized Cloudflare for non-sensitive demo prompts and outputs; the tunnel launch was approved and succeeded. A temporary Quick Tunnel forwards only to the separate localhost guest gateway on port 8002. The full guest URL and QR are in ignored `.state/guest-url.txt` and `.state/guest-qr.png`; never commit their guest pass. Keep the gateway, tunnel and warm native session running while changing UI assets.

Public HTTPS checks verified the landing page returns 200, unauthenticated guest API access returns 401, and the privileged bootstrap route returns 404. A real browser request through the public tunnel completed across M4 Pro and M3 Pro: guest job `815b4e7d36e34e199ab57aa52eeb3bd7`, 9.581 seconds total, 0.566 seconds to first token, 120 prompt tokens and 69 completion tokens. Its output contains the three correct extraction records. Private input/output/usage is in `.state/guest-jobs/`; verification is in `.state/guest-verification/`. This verifies the public browser path, not a physical phone on cellular. Cloudflare relays web traffic; inference remains on the laptops. Guest pages use polling, not public SSE. The URL and pass are temporary, so inspect current local state before reusing them later.

The user subsequently reported that scanning the QR and using the phone page worked. This is user-reported physical-phone confirmation; the phone's network path was not independently inspected. After equal-split inference completed, public HTTPS guest status returned 200 and reported ready with all three laptops. An earlier readiness assertion coincided with another live request; the request completed normally and readiness returned without intervention.

## Hackathon and original research

Michigan DevFest + AI Hackathon, November13,2026. Rules explicitly accept IBM Granite and separately require using the provided IBM Cloud account. Business productivity and Michigan impact remain part of the pitch. Reference run deferred, not permanently removed from final eligibility work.

Rules: https://drive.google.com/file/d/1o1qw2w_xSat3OBMUhLRQATFC2GJYK-Ld/view

Official model files:
- https://huggingface.co/ibm-granite/granite-4.2-8b-GGUF/tree/main
- https://huggingface.co/ibm-granite/granite-4.2-30b-GGUF/tree/main

The parent workspace contains design history in `../outputs/final-product-and-architecture-decision-record.md` and `../work/`. Some persona/demo sections there predate the latest decisions above. Do not reintroduce old credits, LeetCode, or centralized PyTorch designs.

Guest renewal: the original two-hour pass expired. Only its verified `scripts/guest.py` process was stopped; the inference server, RPC workers, invite helper and Cloudflare tunnel stayed running. A new two-hour / 20-request pass was issued on the same localhost port 8002. The private `.state/guest-url.txt` and `.state/guest-qr.png` were regenerated. Both local and public status reported ready for Granite 8B across all three peers, and the dashboard Guest mode modal showed 20 requests and expiry 7:05 PM. Evidence: `.state/guest-verification/renewed-status.json`. Old invitations no longer authenticate.

Health-check recovery: the old monitor stopped the coordinator after any single failed HTTP snapshot. A transient control-path failure is consistent with the observed shutdown; the prior code did not record which peer failed. The new coordinator logs the peer on missed checks and stops after three consecutive misses for that peer. A successful check resets its count, and counts do not carry into a new session. A reachable worker reporting failed/stopped native execution, withdrawn sharing, or a changed manifest still stops the session immediately. Eight added lifecycle tests cover these cases and stale checks; the physical restarted request confirms distributed execution, not an injected network-failure experiment. Guest gateway, invite helper and public tunnel were not restarted.
