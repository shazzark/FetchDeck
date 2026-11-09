# Phase task ledger

Status meanings: **NOT STARTED** means no implementation work is underway; **IN PROGRESS** means work is active; **BLOCKED** means a required gate cannot pass yet; **COMPLETE** means acceptance criteria and required gate are verified. Check marks record implementation or checks with observed evidence; a source implementation alone does not pass a real-engine gate.

## Phase 0 - Foundation and reference behavior - COMPLETE

- [x] Inspect git, branch, workspace, and repository instructions.
- [x] Audit a publicly available download-manager README against its source code and identify explicit placeholders and Windows-specific code paths.
- [x] Record runtime detection: Python 3.13.3 at `C:\Users\chido\.pyenv\pyenv-win\versions\3.13.3\python.exe`; `py -0p` finds no registered Pythons; aria2c was initially not found; it was installed in Phase 1. Node exists but is deferred.
- [x] Add six-phase roadmap and Windows venv/setup/check commands.
- [x] Create `.venv` with Python 3.13.3 and install FetchDeck 0.1.0 with PySide6 6.9.2.
- [x] Launch `python -m fetchdeck` under `QT_QPA_PLATFORM=offscreen`; Qt entered its event loop and remained active until interrupted. This is process-level startup evidence; no manual visual inspection was performed.
- [x] Run `.\.venv\Scripts\python.exe -m compileall src` successfully.
- [x] Record aria2c missing setup and exact next prerequisite for Phase 1.

**Observed verification:** Before changes, `git status --porcelain=v1` was empty; branch was `main`, no commits existed, and `origin` was `https://github.com/shazzark/FetchDeck.git`. Direct interpreter reports Python 3.13.3. The `py` launcher reports no registered installations; the venv used the full interpreter path. `.venv\Scripts\python.exe -m pip install -e .` succeeded with PySide6 6.9.2. `QT_QPA_PLATFORM=offscreen .venv\Scripts\python.exe -m fetchdeck` entered the event loop and was stopped with Ctrl+C. `.venv\Scripts\python.exe -m compileall src` passed. `where.exe aria2c` found no executable. Node is installed but no Node setup was performed. The Phase 0 source audit is summarized in `docs/implementation-plan.md`; it is not a real-engine or Windows verification run.

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

**Phase 4 completion commit:** `248a66be1345ea78b275b173967509650682461c` (`docs(phase4): close manual Windows verification gate`).

## Phase 5 - Local dashboard and public website - COMPLETE

- [x] Build independently buildable strict-TypeScript Next.js App Router dashboard and public website as separate static exports.
- [x] Apply FetchDeck brand colors, logo, typography, Lucide icons, and Tailwind CSS to both apps; share the reusable wordmark component.
- [x] Serve the dashboard export and versioned, read-only stats API from one loopback Python origin; launch it from the desktop Dashboard button.
- [x] Derive live rates/counts from aria2 and persist daily activity with per-task byte checkpoints.
- [x] Build the public landing page, features, genuine desktop/dashboard screenshots, Windows setup, favicon/title/description, branded PNG Open Graph asset, and disabled unpublished-installer button.
- [x] Run lint, strict type checks, and independent production builds; inspect both production pages in desktop and mobile browser sizes; verify assets, API privacy/security, disconnected state, real transfer, and totals after restart.

**Observed verification:** Node 22.13.0 and npm 11.1.0. `npm install` added 404 packages; the lockfile is committed for reproducible `npm ci`. `npm run lint` passed for both workspaces; `npm run typecheck` passed in strict mode for both. `npm run build --workspace @fetchdeck/dashboard` and `npm run build --workspace @fetchdeck/website` each produced independent static exports. An elevated `npm audit` reported 10 moderate findings in the development dependency chain, including a `minimatch` glob-pattern denial-of-service advisory pulled in through ESLint. `npm audit fix` did not resolve it; `npm audit fix --force` proposed downgrading ESLint 10 to ESLint 9, so that breaking change was not applied. A later audit retry could not reach npm's advisory endpoint.

Python checks: `.venv\Scripts\python.exe -m compileall src tests` passed. The Windows suite ran 32 tests in 107.562 seconds, including the real aria2 HTTP, FTP, torrent, resume, and task-control cases; all passed and `.venv\Scripts\python.exe -m pip check` reported no broken requirements. The added desktop Dashboard-button smoke test separately passed: it started a temporary same-origin server and verified `QDesktopServices.openUrl` receives its loopback URL.

Real dashboard browser check: the production export was served with `DashboardServer` while aria2 1.37.0 downloaded the controlled 8 MiB byte-range test file. Playwright observed the live rate (about 256 KB/s), one active job, changing daily total, and successful JS/CSS/favicon/API requests with no console errors. Persisted activity held exactly 8,388,608 bytes after the engine/app-data restart and before a second download; after a second real 8 MiB transfer it was 16,777,216 bytes. This shows the prior transfer was retained once and only new bytes were added. The actual app screenshot shows the running aria2 task; the dashboard screenshot shows the live rate and transfer total. A separate production static-server view without the API displayed the designed disconnected message and zero-value state.

API contract/security tests passed: statistics expose only aggregate fields; URL, file path, and GID sentinels were absent. Wrong Host returned HTTP 400, foreign Origin returned HTTP 403, and POST returned HTTP 405. The same-origin API is read-only and sends no permissive CORS headers.

Public-site browser check: the production export rendered at desktop and 390-pixel mobile width; the mobile document width was 375 px with no horizontal page overflow. All 14 visible SVG icons rendered; the only button is a text-labeled, disabled installer action. The desktop and dashboard PNG screenshots loaded (both image elements and their static files returned HTTP 200). The FetchDeck SVG favicon returned HTTP 200 and the 1200x630 branded PNG Open Graph asset returned `image/png`/HTTP 200. No public domain has been chosen, so canonical and absolute social preview metadata remain unset; `NEXT_PUBLIC_SITE_URL` configures them at the domain-specific build. The installer button remains disabled because Phase 6 packaging is not yet verified and no public URL exists.

**Local commit:** pending final diff review.

**Dependencies:** Phase 4 complete. Phase 6 packaging must include `apps/dashboard/out`; the public website remains a separate export and has not been deployed.

## Phase 6 - Windows packaging and source-code milestone - COMPLETE

- [x] Add a pinned PyInstaller build requirement and repeatable PowerShell one-folder build script, including the Phase 5 dashboard export.
- [x] Include PySide6, Shiboken6, PyInstaller notices and document Qt, npm asset, and aria2 redistribution review items.
- [x] Add Windows package setup, user, feature, and troubleshooting documentation; create a local portable ZIP from the package.
- [x] On this Windows 11 machine, launch the package with Python and Node removed from PATH and aria2 supplied externally; verify the engine-ready screen.
- [x] Through the packaged UI, download a controlled local 1 MiB HTTP file and compare its SHA-256 with the source.
- [x] Open the packaged dashboard; verify the static page and aggregate stats API respond from the app's loopback server.
- [x] Close the packaged app and verify its aria2 child exits. Use isolated temporary app data so the existing desktop session remains untouched.
- [ ] Complete third-party license review for public ZIP distribution, including Qt shared-library requirements and dashboard npm asset notices.

**Observed verification:** `.\scripts\build_windows.ps1` built a Windows one-folder package with PyInstaller 6.22.3 using the installed Python 3.13.7 runtime. PyInstaller's default `_internal` resource directory was handled by resolving the dashboard from `sys._MEIPASS`; the first package smoke launch also exposed a standalone-relative-import issue, fixed with `scripts/launcher.py`. The package contains `FetchDeck.exe`, `THIRD-PARTY-NOTICES.md`, `licenses/`, and the Phase 5 dashboard under `_internal/dashboard`; the build script creates `dist\FetchDeck-windows-x64.zip`. Running the package with PATH limited to Windows system folders plus the external aria2 install showed `aria2 1.37.0 is running`. A controlled 1 MiB local HTTP download through the package UI completed with a matching SHA-256. The packaged Dashboard button served the production page and `/api/v1/stats` from loopback, with no source URL field in the response. A graceful window close exited the package and its aria2 child. Build outputs remain ignored under `dist/` and are local only.

**Milestone boundary / follow-up:** Phase 6 is complete for the source-code milestone based on the Windows package checks above. Before public ZIP distribution, review Qt shared-library requirements and collect the applicable dashboard npm asset notices. The public website remains undeployed and has no selected domain.

**Local package artifact:** `dist\FetchDeck\FetchDeck.exe` and `dist\FetchDeck-windows-x64.zip` (ignored by Git).
