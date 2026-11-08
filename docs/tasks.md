# Phase task ledger

Status meanings: **NOT STARTED** means no implementation work is underway; **IN PROGRESS** means work is active; **BLOCKED** means a required gate cannot pass yet; **COMPLETE** means acceptance criteria and required gate are verified. A checked item has observed evidence, not just an implementation claim.

## Phase 0 — Foundation and reference behavior — COMPLETE

- [x] Inspect git, branch, workspace, and repository instructions.
- [x] Audit Motrix GPUI README claims against source code and identify explicit placeholders and Windows-specific code paths.
- [x] Record runtime detection: Python 3.13.3 at `C:\Users\chido\.pyenv\pyenv-win\versions\3.13.3\python.exe`; `py -0p` finds no registered Pythons; aria2c is not installed/on PATH; Node exists but is deferred.
- [x] Add six-phase roadmap and Windows venv/setup/check commands.
- [x] Create `.venv` with Python 3.13.3 and install FetchDeck 0.1.0 with PySide6 6.9.2.
- [x] Launch `python -m fetchdeck` under `QT_QPA_PLATFORM=offscreen`; Qt entered its event loop and remained active until interrupted. This is process-level startup evidence; no manual visual inspection was performed.
- [x] Run `.\.venv\Scripts\python.exe -m compileall src` successfully.
- [x] Record aria2c missing setup and exact next prerequisite for Phase 1.

**Observed verification:** Before changes, `git status --porcelain=v1` was empty; branch was `main`, no commits existed, and `origin` was `https://github.com/shazzark/FetchDeck.git`. Direct interpreter reports Python 3.13.3. The `py` launcher reports no registered installations; the venv used the full interpreter path. `.venv\Scripts\python.exe -m pip install -e .` succeeded with PySide6 6.9.2. `QT_QPA_PLATFORM=offscreen .venv\Scripts\python.exe -m fetchdeck` entered the event loop and was stopped with Ctrl+C. `.venv\Scripts\python.exe -m compileall src` passed. `where.exe aria2c` found no executable. Node is installed but no Node setup was performed. Motrix GPUI source audited at `a26c3a9116375b45d941af9b0b2da91ebfcfc985`; implementation paths, placeholders, and Windows-specific code are summarized in `docs/implementation-plan.md`. The upstream code audit is not a real-engine or Windows verification run.

## Phase 1 — Direct downloads end to end — BLOCKED

- [ ] Private aria2 child, authenticated loopback RPC, timeouts, session exclusivity, clean shutdown.
- [ ] Responsive desktop downloads queue with direct links and task controls.
- [ ] Visible engine startup/runtime errors and collision behavior.
- [ ] Real aria2 controlled-server gate including SHA-256 comparison.

**Verification:** Not run. **Blocker / exact next action:** Install aria2 on Windows and ensure `aria2c.exe` is on `PATH` (`winget install aria2` is the setup hint shown by the audited reference). Then run `aria2c --version` and record its version. Until then the real-engine gate cannot run.

## Phase 2 — Session recovery and download controls — NOT STARTED

- [ ] Persist and restore unfinished/paused work.
- [ ] Bulk/list controls, restart overwrite handling, and Recycle Bin removal.
- [ ] FTP and collision-safe resume behavior.
- [ ] Interrupted-transfer offset/hash and forced-exit gate.

**Verification:** Not run. **Blockers:** Phase 1.

## Phase 3 — Torrents and tracker management — NOT STARTED

- [ ] Magnet and `.torrent` workflows.
- [ ] Licensed tracker list and resilient sync/apply behavior.
- [ ] DHT/PEX/seeding defaults and scope documented.
- [ ] Real lawful torrent/magnet, hash, seeding, pause, and sync success/failure gate.

**Verification:** Not run. **Blockers:** Phase 2 and licensing review.

## Phase 4 — Settings, notifications, and desktop polish — NOT STARTED

- [ ] Persistent settings and engine/UI effects.
- [ ] Completion/failure feed and native Windows notifications.
- [ ] Keyboard shortcuts, clear states, and quit warning.
- [ ] Reopen, real notification, and active-work quit gate.

**Verification:** Not run. **Blockers:** Phase 3.

## Phase 5 — Local Next.js and TypeScript dashboard — NOT STARTED

- [ ] Optional static dashboard, safe versioned read-only API, and same-origin server.
- [ ] Live and historical stats with restart-safe accounting.
- [ ] Lint, type, build, real download, persistence, empty, and disconnected checks.

**Verification:** Not run. Node setup intentionally deferred. **Blockers:** Phase 4.

## Phase 6 — Windows packaging and release readiness — NOT STARTED

- [ ] Verify redistribution terms and choose aria2 packaging strategy.
- [ ] Reproducible Windows package with dashboard assets and notices.
- [ ] Clean Windows full workflow, upgrade preservation, and process cleanup.
- [ ] User/troubleshooting docs and local release artifacts.

**Verification:** Not run. **Blockers:** Phases 0–5 and clean Windows environment.
