# Phase task ledger

Status meanings: **NOT STARTED** means no implementation work is underway; **IN PROGRESS** means work is active; **BLOCKED** means a required gate cannot pass yet; **COMPLETE** means acceptance criteria and required gate are verified. Check marks record implementation or checks with observed evidence; a source implementation alone does not pass a real-engine gate.

## Phase 0 - Foundation and reference behavior - COMPLETE

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

## Phase 1 - Direct downloads end to end - COMPLETE

- [x] Implement an app-owned aria2 child with random RPC secret, loopback binding, request/startup timeouts, session lock, and graceful shutdown.
- [x] Implement background JSON-RPC polling and a downloads UI for HTTP/HTTPS links, save-folder selection, queue status/progress/speed/errors, pause/resume, and confirmed removal that preserves files by default.
- [x] Add focused unit/contract coverage for URL validation, JSON-RPC authentication/response validation, cross-process session locking, and task display data.
- [x] Add a real aria2 controlled-server integration test through `EngineWorker` for queueing, pause/resume, task removal, failure, and SHA-256 comparison.
- [x] Pass the real aria2 integration test and verify the finished file hashes on Windows.

**Observed verification:** Installed aria2 with `winget install --id aria2.aria2 --exact`; the executable reports version 1.37.0. `.venv\Scripts\python.exe -m compileall src tests` passed. `.venv\Scripts\python.exe -m unittest discover -s tests -v` ran 8 tests and all passed, including the real aria2 controlled-server test using the app's worker. It observed a waiting job, paused and resumed a live job, verified removal retained its completed file, recorded a controlled 404, and compared both 8 MiB files' SHA-256 values with the server payload. `.venv\Scripts\python.exe -m pip check` reported `No broken requirements found.` The PySide6 app started aria2 1.37.0 under the offscreen backend and shut down its child cleanly; `Get-Process aria2c` returned no process afterward. Real transfer verification used HTTP. HTTPS URL acceptance is covered by unit tests, but a real TLS transfer remains unverified: this aria2 Windows TLS build relies on the Windows trust store, and Windows canceled the test-only CA import (`certutil` exit `0x800704C7`). Certificate verification was not disabled. No manual visual inspection was performed.
## Phase 2 - Session recovery and download controls - COMPLETE

- [x] Persist unfinished work and deliberately paused tasks, including aria2 control files.
- [x] Add pause/resume all, status filters, search, multi-select, context menus, restart choices, and confirmed Recycle Bin removal.
- [x] Add FTP and handle supported REST resume or report when the server rejects it; protect existing restart destinations.
- [x] Pass graceful-restart offset/hash, paused-state, removal, and forced-exit recovery gate.

**Verified design evidence:** On Windows aria2 1.37.0, a real paused HTTP job written by `saveSession` produced a session entry containing `pause=true`, retained its `.aria2` control file, and kept its partial output in the configured download folder. This confirms deliberate pause persistence for aria2 input-file recovery. The [aria2 1.37.0 manual](https://aria2.github.io/manual/en/html/aria2c.html) documents that `--save-session` output can be used as `--input-file` on restart and that `--auto-save-interval` writes control files during a download.

**Observed verification:** `.venv\Scripts\python.exe -m compileall src tests` passed. With aria2 1.37.0 on Windows, `.venv\Scripts\python.exe -m unittest discover -s tests -v` ran 18 tests in 82.442 seconds; all passed. The real-engine cases verified HTTP graceful restart and paused-state restoration with a nonzero Range offset and SHA-256 match; forced aria2 termination after a control-file checkpoint, followed by offset-based recovery and matching SHA-256; FTP transfer and REST resume with a matching SHA-256; a no-REST FTP server reporting that it cannot resume; explicit restart keep-both and replace choices; and pause-all/resume-all over two queued HTTP tasks. The earlier Phase 1 real-engine case also verified queueing, per-task pause/resume, file-preserving removal, and a controlled 404. Two UI tests verified startup failure display, persistent multiselection across polling snapshots, and status filtering. Two unit tests cover unique restart destinations and the Windows Recycle Bin shell-operation flags/error path (shell API mocked; no real file was moved). `.venv\Scripts\python.exe -m pip check` reported no broken requirements. Actual PySide6 startup showed aria2 1.37.0 ready and graceful window close stopped its worker. The process query returned no aria2c process. After the final session destination fallback edit, compileall passed again; the 5 Phase 2 unit/UI tests and the real aria2 collision-restart integration test all passed. No manual visual inspection or real Recycle Bin movement was performed.



## Phase 3 - Torrents and tracker management - COMPLETE

- [x] Add magnet and `.torrent` workflows, metadata status, transfer, pause, and seeding display.
- [x] Sync best/all community lists in a worker; validate entries, write atomically, and retain the last usable list after fetch/validation failures.
- [x] Enable DHT/PEX and set seeding to a 1.0 ratio or 1440-minute cap; document that tracker changes apply to new BitTorrent tasks only.
- [x] Verify a controlled lawful torrent and magnet against a known local seeder, compare hashes, pause/resume seeding, and exercise tracker sync success/failure.

**Observed verification:** `.venv\Scripts\python.exe -m compileall src tests` passed. `.venv\Scripts\python.exe -m unittest discover -s tests -v` with `LOCALAPPDATA` set to the installed aria2 location required elevated filesystem access and ran 22 tests in 96.784 seconds; all passed without skips. The controlled local tracker test verified successful sync, deduplication/validation, failure on HTTP 503 and empty content, and retention of the last valid cache. The real aria2 1.37.0 torrent gate used generated lawful test data and a known local aria2 seeder: `.torrent` and magnet downloads completed with matching SHA-256, both entered seeding, the `.torrent` task paused and resumed, and aria2's global tracker option contained the controlled tracker. The full suite also reran Phase 1/2 HTTP, FTP, restart, forced-exit, UI, and unit checks. Runtime tracker lists are not bundled because the upstream repository identifies its lists as GPL-2.0; downstream redistribution obligations need review before shipping lists. aria2 docs specify that `--seed-time=0` disables seeding, so the configured finite cap is 1440 minutes.

**Local commit:** `7ecf19d3a904e5e95fe22d31a717c997bb49f2e3` (`feat(torrents): implement Phase 3 torrent and tracker workflows`).

## Phase 4 - Settings, notifications, and desktop polish - COMPLETE

- [x] Persist the requested settings, reopen the UI from the saved file, and verify engine/UI effects.
- [x] Add a deduplicated completion/failure feed and Windows tray notification delivery path.
- [x] Add keyboard shortcuts, theme, empty/loading/error states, and active-work quit warning.
- [x] Verify aria2 option changes and resume-on-launch behavior with the real engine; exercise the quit prompt response in a UI test.
- [x] User confirmed the W3C `dummy.pdf` HTTPS transfer completed and Windows displayed the "Download complete" banner.
- [x] User reported the test file paused at 44% (3.5 MB), reopened active at 51% (4.1 MB), and completed with a Windows notification; verify the resume offset from the server log.
- [x] User confirmed the active-download quit warning appeared and both Windows completion and failure notifications worked.

**Observed verification:** `.venv\Scripts\python.exe -m compileall src tests` passed. `$env:LOCALAPPDATA='C:\Users\chido\AppData\Local'; .venv\Scripts\python.exe -m unittest discover -s tests -v` ran 29 tests in 102.439 seconds; all passed without skips, including real aria2 1.37.0 checks for startup concurrency/connections, runtime upload/download limits and User-Agent, and `resume_on_launch=false` restoring a saved task paused without sending an HTTP request. UI tests verified preferences remain populated after reopening the window, task transition notifications are persisted and deduplicated, and a simulated No response keeps the active-work quit dialog open. `.venv\Scripts\python.exe -m pip check` reported no broken requirements. User-reported visible Windows check (2026-11-08): W3C `dummy.pdf` completed over HTTPS and the Windows "Download complete" banner appeared. Two Tele2 `10MB.zip` attempts failed with a connection error at 0 B; the user confirmed that the Windows failure notification worked. The user then reported the local 8 MiB test file paused at 44% (3.5 MB), reopened active at 51% (4.1 MB), and completed with a Windows completion notification. The server log confirms nonzero resume offsets: `Range=bytes=2736128-8388607` and `Range=bytes=3719168-8388607`; the latter is about 44.3% of 8 MiB and matches the reported pause point. The live manual recovery server reuses `ControlledHandler` from `tests/test_aria2_integration.py`; it serves 8 MiB at 64 KiB chunks with a 0.25-second delay and byte-range support. Range preflight received HTTP 206. Server PID 17196 listens on 127.0.0.1:8765; request log: `%TEMP%\fetchdeck-phase2-http-requests.log`.

**Phase 4 acceptance verified:** User confirmed the active-download quit warning appeared while the test download was active and both the Windows completion and failure notifications appeared. The local server log confirmed a nonzero resume offset matching the reported 44% pause. The two Tele2 failures are recorded as connection errors at 0 B, not successful download tests.

**Phase 4 implementation checkpoint:** `299e59788fb72b2ec06c597547911331aa4886c5` (`feat(settings): add Phase 4 preferences and notifications`).

**Phase 4 completion commit:** Pending.

## Phase 5 - Local Next.js and TypeScript dashboard - NOT STARTED

**Disposition:** Deferred to a future release by user request; Phase 6 does not depend on it.

- [ ] Static dashboard, safe versioned read-only API, same-origin server, and dashboard checks (future release).

**Verification:** Not started. Node setup deferred. Not a Phase 6 dependency.

## Phase 6 - Windows packaging and release readiness - IN PROGRESS

- [ ] Build a reproducible one-folder Windows package and portable archive; defer dashboard assets with Phase 5.
- [ ] Include applicable third-party notices and document aria2 as an external runtime dependency.
- [ ] Verify launch without host Python, real aria2 workflows, app-data upgrade preservation, and child-process cleanup.
- [ ] Update supported-feature, troubleshooting, and usage documentation; create local release artifacts.

**Preparation:** Phase 4 is complete. PyInstaller 6.22.3 is installed in `.venv`; Phase 6 build is underway. Packaging research found aria2 is GPL-2.0, PySide6/Qt use LGPL/GPL and include third-party notices, and PyInstaller has a bootloader exception. The package keeps aria2 external and must preserve applicable Qt notices and replaceable shared libraries. Phase 5 is deferred and is not a dependency. A separate clean Windows machine is not available in this workspace.
