# Second setup

Prepare the user's **M3 Mac, peer B**, for the existing Open Swarm demo. The user's M4 Mac is peer A and will coordinate the first shared inference session. The brother's Windows laptop is peer C and will join later.

Current checkpoint: this M3 has built the pinned runtime and completed distributed inference with the M4. Preserve its existing `config/local.json`, shared token and hotspot addresses. The earlier private `second-setup.zip` has obsolete hotel-network addresses: do not re-extract its configuration. Source updates use Git; no new private configuration transfer is required for the caching update.

Read `AGENTS.md`, `PROJECT_CONTEXT.md` and `README.md` before acting. The user directly verified Python 3.12.16, CMake 4.5.0 and the configured Apple CommandLineTools path on this Mac. Inspect the existing project virtual environment and native build; let any active build finish rather than starting another. Do not repeat completed installations. Work on the published `main` revision for the two-Mac test. If updating an existing checkout, preserve local changes and use a fast-forward update only.

## Objective

Build the existing pinned native runtime and expose this M3's actual compute device so the M4 can discover it over the trusted LAN. Report reproducible evidence. The first milestone is **worker ready for discovery**. Successful distributed generation is a separate milestone requiring both laptops.

## Setup steps

- Check Git, Python, Node/npm, CMake, Apple compiler tools and the active LAN address.
- Follow the README to install missing development prerequisites, create the project virtual environment, install project dependencies, build the frontend and build the native runtime. Preserve unrelated system settings and installations.
- If Node installation delays setup, use the prebuilt `second-setup-ui.zip` supplied from the M4. Extract it from the repository root so it provides `frontend/dist/index.html` and assets. This skips Node/npm and the frontend build on the M3; Python and the native runtime are still needed. Inspect existing installations before retrying them.
- Keep llama.cpp pinned to `5676dfbe01e7ebe0387913680eee0ed39bf4a363`; use `scripts/build_runtime.py` and its existing flags.
- Use the supplied private `peer-b.json` as `config/local.json`. If it is missing, ask the user to transfer it from the M4. Do not create a new shared token or independently regenerate the roster. Preserve the 8,000,000,000-byte offer.
- Inspect configuration without printing the control token. Confirm peer ID `b` and that its bind address matches this laptop's active LAN address. Report an address mismatch for coordinated correction on both peers.
- Verify native devices with `.tools/llama.cpp/build/bin/llama-server --list-devices`. The M4 reports `MTL0`; confirm what the M3 actually reports. Adjust only the ignored local `worker_device` setting if needed, using the observed device name.
- Start `.venv/bin/python scripts/devices.py --worker` and leave it running for the M4's discovery test. Record its actual startup output, listening address and port. If the agent environment cannot access Metal, have the user run the same command from normal Terminal; do not claim the hardware lacks support based only on the agent environment.

The M4 is the first coordinator. Peer B does **not** need a model download or its own coordinator device list for this assignment. A full verified model file is required on the coordinator before generation.

## Caching update for the working M3

After the M4 has stopped the shared session, stop only this repository's `scripts/serve.py` with Ctrl+C. Inspect `git status --short`, preserve local changes, and update with `git pull --ff-only` when clean. Restart `.venv/bin/python scripts/serve.py` and enable **Share this laptop**. Do not run another temporary discovery worker, rebuild llama.cpp, reinstall packages, regenerate configurations or download weights. New app-managed workers now use `--cache` with `LLAMA_CACHE` pointing into ignored `.state/cache`; their startup log should report a local cache path ending in `/rpc`. The first cached load populates it and is not a warm-cache speed measurement. If Node/npm is already available, rebuild the frontend to obtain the saved-answer display; that UI update is optional for worker caching.

## Shared implementation constraints

Keep both laptops on matching application and runtime revisions. Preserve the existing architecture, runtime pin, operating system and firewall settings. If a source fix is needed, report the exact failure and propose the smallest patch so it can be reviewed and applied consistently on both laptops. Do not change versions or build flags as part of an automatic retry.

Do not commit or publish tokens, private configuration, weights, generated binaries or session logs. Do not push to `main` or merge changes. Do not run unrelated processes or kill processes by name.

Stop the temporary discovery worker with Ctrl+C before the app-managed inference session starts. The app will start its own worker on the same port. Do not leave two workers competing for that port.

## Report back

Return a short setup report for coordinating the two-laptop test:

1. Exact application Git commit and native llama.cpp commit.
2. Installed prerequisite versions and build results, including skipped steps that were already complete.
3. Exact native device discovery output.
4. Peer ID, LAN address, RPC port and whether the temporary worker is still running. Never include the token.
5. Any files changed, distinguishing ignored local configuration from source.
6. For a failure: the exact command, exit status and relevant error lines; label hypotheses separately from observations.

Only report checks that actually ran. A listening worker, an online dashboard or a successful build does not establish distributed inference, model quality or memory fit. Wait for the M4's discovery result before moving to the shared generation test.
