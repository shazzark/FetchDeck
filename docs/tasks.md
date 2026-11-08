# Phase task ledger

Status meanings: **NOT STARTED** means no implementation work is underway; **IN PROGRESS** means work is active; **BLOCKED** means a required gate cannot pass yet; **COMPLETE** means acceptance criteria and required gate are verified. Check marks record implementation or checks with observed evidence; a source implementation alone does not pass a real-engine gate.

## Phase 0 â€” Foundation and reference behavior â€” COMPLETE

- [x] Inspect git, branch, workspace, and repository instructions.
- [x] Audit Motrix GPUI README claims against source code and identify explicit placeholders and Windows-specific code paths.
- [x] Record runtime detection: Python 3.13.3 at `C:\Users\chido\.pyenv\pyenv-win\versions\3.13.3\python.exe`; `py -0p` finds no registered Pythons; aria2c was initially not found; it was installed in Phase 1. Node exists but is deferred.
- [x] Add six-phase roadmap and Windows venv/setup/check commands.
- [x] Create `.venv` with Python 3.13.3 and install FetchDeck 0.1.0 with PySide6 6.9.2.
- [x] Launch `python -m fetchdeck` under `QT_QPA_PLATFORM=offscreen`; Qt entered its event loop and remained active until interrupted. This is process-level startup evidence; no manual visual inspection was performed.
- [x] Run `.\.venv\Scripts\python.exe -m compileall src` successfully.
- [x] Record aria2c missing setup and exact next prerequisite for Phase 1.

**Observed verification:** Before changes, `git status --porcelain=v1` was empty; branch was `main`, no commits existed, and `origin` was `https://github.com/shazzark/FetchDeck.git`. Direct interpreter reports Python 3.13.3. The `py` launcher reports no registered installations; the venv used the full interpreter path. `.venv\Scripts\python.exe -m pip install -e .` succeeded with PySide6 6.9.2. `QT_QPA_PLATFORM=offscreen .venv\Scripts\python.exe -m fetchdeck` entered the event loop and was stopped with Ctrl+C. `.venv\Scripts\python.exe -m compileall src` passed. `where.exe aria2c` found no executable. Node is installed but no Node setup was performed. Motrix GPUI source audited at `a26c3a9116375b45d941af9b0b2da91ebfcfc985`; implementation paths, placeholders, and Windows-specific code are summarized in `docs/implementation-plan.md`. The upstream code audit is not a real-engine or Windows verification run.

**Local commit:** `7c1d7e1040dcb974a60a00af79a5c93155e32c14` (`feat(foundation): establish Phase 0 app scaffold`).

## Phase 1 — Direct downloads end to end — COMPLETE

- [x] Implement an app-owned aria2 child with random RPC secret, loopback binding, request/startup timeouts, session lock, and graceful shutdown.
- [x] Implement background JSON-RPC polling and a downloads UI for HTTP/HTTPS links, save-folder selection, queue status/progress/speed/errors, pause/resume, and confirmed removal that preserves files by default.
- [x] Add focused unit/contract coverage for URL validation, JSON-RPC authentication/response validation, cross-process session locking, and task display data.
- [x] Add a real aria2 controlled-server integration test through `EngineWorker` for queueing, pause/resume, task removal, failure, and SHA-256 comparison.
- [x] Pass the real aria2 integration test and verify the finished file hashes on Windows.

**Observed verification:** Installed aria2 with `winget install --id aria2.aria2 --exact`; the executable reports version 1.37.0. `.venv\Scripts\python.exe -m compileall src tests` passed. `.venv\Scripts\python.exe -m unittest discover -s tests -v` ran 8 tests and all passed, including the real aria2 controlled-server test using the app's worker. It observed a waiting job, paused and resumed a live job, verified removal retained its completed file, recorded a controlled 404, and compared both 8 MiB files' SHA-256 values with the server payload. `.venv\Scripts\python.exe -m pip check` reported `No broken requirements found.` The PySide6 app started aria2 1.37.0 under the offscreen backend and shut down its child cleanly; `Get-Process aria2c` returned no process afterward. Real transfer verification used HTTP. HTTPS URL acceptance is covered by unit tests, but a real TLS transfer remains unverified: this aria2 Windows TLS build relies on the Windows trust store, and Windows canceled the test-only CA import (`certutil` exit `0x800704C7`). Certificate verification was not disabled. No manual visual inspection was performed.
## Phase 2 â€” Session recovery and download controls â€” NOT STARTED

- [ ] Persist and restore unfinished/paused work.
- [ ] Bulk/list controls, restart overwrite handling, and Recycle Bin removal.
- [ ] FTP and collision-safe resume behavior.
- [ ] Interrupted-transfer offset/hash and forced-exit gate.

**Verification:** Not run. **Blockers:** Phase 1.

## Phase 3 â€” Torrents and tracker management â€” NOT STARTED

- [ ] Magnet and `.torrent` workflows.
- [ ] Licensed tracker list and resilient sync/apply behavior.
- [ ] DHT/PEX/seeding defaults and scope documented.
- [ ] Real lawful torrent/magnet, hash, seeding, pause, and sync success/failure gate.

**Verification:** Not run. **Blockers:** Phase 2 and licensing review.

## Phase 4 â€” Settings, notifications, and desktop polish â€” NOT STARTED

- [ ] Persistent settings and engine/UI effects.
- [ ] Completion/failure feed and native Windows notifications.
- [ ] Keyboard shortcuts, clear states, and quit warning.
- [ ] Reopen, real notification, and active-work quit gate.

**Verification:** Not run. **Blockers:** Phase 3.

## Phase 5 â€” Local Next.js and TypeScript dashboard â€” NOT STARTED

- [ ] Optional static dashboard, safe versioned read-only API, and same-origin server.
- [ ] Live and historical stats with restart-safe accounting.
- [ ] Lint, type, build, real download, persistence, empty, and disconnected checks.

**Verification:** Not run. Node setup intentionally deferred. **Blockers:** Phase 4.

## Phase 6 â€” Windows packaging and release readiness â€” NOT STARTED

- [ ] Verify redistribution terms and choose aria2 packaging strategy.
- [ ] Reproducible Windows package with dashboard assets and notices.
- [ ] Clean Windows full workflow, upgrade preservation, and process cleanup.
- [ ] User/troubleshooting docs and local release artifacts.

**Verification:** Not run. **Blockers:** Phases 0â€“5 and clean Windows environment.
