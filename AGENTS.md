# Open Swarm

Read `PROJECT_CONTEXT.md` before making project decisions. Continue the implementation already in this repository; do not restart the architecture review.

- Build real distributed inference on the two available Macs first, then add the third laptop. The watsonx.ai reference run is deferred by the user.
- One IBM Granite model must execute across physical peers. Separate replicas, hosted API answers, simulated telemetry, or fake ready states do not meet the objective.
- Stack: native pinned llama.cpp RPC, Python/FastAPI peer agent, React dashboard.
- Development setup: development and integration run on the user's M4 Mac; setup and validation on the user's M3 Mac follow `SECOND_SETUP.md`. The brother's computer is the Windows peer.
- Product: share spare compute when using the app. No credits, wallets, currency, permanent tracker, or generic chatbot pivot.
- Build for one person; finished beats fancy; the demo is in person.
- Show actual native layer placement and measured activity. Clearly label RSS limitations and graph submission counts. Never invent benchmarks or claim an untested memory fit.
- Keep credentials, model weights, generated runtime binaries, and local session data out of Git.
- Repository owner is `ysbeih`; repository is `https://github.com/ysbeih/open-swarm`; collaborator is `GarouHD`.
- Do not switch the user's global GitHub identity. Use project-specific configuration.
- Run meaningful lifecycle/API tests, the frontend production build, and actual native integration checks appropriate to each change. A mock transport test is not a physical cluster test.
