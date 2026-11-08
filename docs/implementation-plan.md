# Implementation plan

This roadmap follows FetchDeck's six-phase delivery plan. FetchDeck is original code, UI, and branding, built around a Python/PySide6 desktop app, aria2 transfers, and an optional static Next.js dashboard. Browser extensions, plugins, and CLI integration are deferred.

### Historical source audit

During Phase 0, the public `missuo/motrix-gpui` source at commit `a26c3a9116375b45d941af9b0b2da91ebfcfc985` was inspected in a temporary read-only clone to inform the verification checklist. The notes below record that source audit; FetchDeck's own implementation and acceptance criteria are defined by the phase sections that follow.

- **Downloads / Phase 1–2:** `src/ui/add_task.rs` builds the URL and torrent forms; `src/aria2/client.rs` implements add, pause, resume, remove, and list RPC calls; `src/ui/downloads.rs` implements filters, search, bulk actions, confirmation, and trash handling. `src/state.rs` performs RPC and 1-second polling on background executors.
- **Engine / Phase 1:** `src/aria2/daemon.rs` finds or spawns aria2c, requests loopback-only RPC, and configures a session file. The client uses a 15-second HTTP timeout. Windows builds hide the child console and search `PATH`, `C:\Program Files\aria2\aria2c.exe`, and Chocolatey. Its implementation does not hold a cross-instance session lock and does not synchronously confirm engine readiness before the UI polls; FetchDeck will handle both per its requirements. The reference sets `--rpc-allow-origin-all=true` while binding RPC to loopback; FetchDeck will keep its local statistics origin policy restrictive.
- **Dashboard / Phase 5:** `src/ui/dashboard.rs` renders health, rates, task totals, and speed presets; `src/activity.rs` stores daily byte totals. These source paths substantiate the feature claims, but no upstream runtime or automated tests were run in this audit.
- **BitTorrent / trackers / Phase 3:** `src/ui/add_task.rs`, `src/aria2/client.rs`, and `src/aria2/daemon.rs` implement magnet/torrent submission, torrent options, DHT/PEX, seeding, and bundled tracker defaults. `src/ui/pages.rs` fetches best/all community tracker lists with a 20-second timeout, rejects an empty response, retains the current list on fetch failure, and applies the chosen list through a global aria2 option.
- **Settings / notifications / Phase 4:** `src/config.rs` persists settings and creates an RPC secret; `src/ui/settings.rs` wires options into aria2; `src/state.rs` detects task status transitions; `src/notifications.rs` has a Windows/non-macOS `notify-rust` path. The notification code path exists, but Windows delivery was not run or verified.
- **Explicit placeholders:** `src/ui/pages.rs` renders “Plugins are coming soon”; `src/ui/settings.rs` labels browser-extension and CLI integration as coming soon. These are not implemented features. Plugins and browser/CLI integration remain excluded from FetchDeck's roadmap.
- **Windows evidence and limitations:** The source has Windows-specific aria2 discovery and hidden-child-window behavior and a generic non-macOS notification branch. The README's title-bar and shortcut details are macOS-specific. No upstream Windows execution, packaging test, or UI inspection was performed. The source tree contains no standalone test files or `#[test]` declarations, so code presence is not proof the README workflow passes. FetchDeck's Windows gates remain independent.


## Phase 0 — Foundation and reference behavior

- **Goal:** Establish a reproducible local Python/PySide6 app foundation and record verified reference behavior and machine prerequisites.
- **Scope:** Inspect the repository and publicly documented download-manager behavior; separate README claims from implementation evidence; create this plan and task ledger; establish package metadata, a runnable desktop window, Windows setup instructions, and a test/check entrypoint. Record Python, PySide6, and aria2c detection.
- **Exclusions:** Download management, dashboard, Node setup, bundling third-party binaries, plugins, browser extensions, and CLI integration.
- **Dependencies:** Windows development machine; Python 3.11–3.13 candidate versions; PySide6 install; aria2c detection (installation is needed before Phase 1).
- **Acceptance criteria:** Documented install commands reproduce the environment; documented entrypoint launches the window; supported Python version is recorded from verification; aria2c version or missing setup is recorded; upstream feature claims and intentional differences are distinguished.
- **Verification:** Create a venv, install the project, run the documented app entrypoint and syntax check. Record exact output and whether the window was manually seen on Windows. Detect `aria2c --version` or explicitly document it missing.

## Phase 1 — Direct downloads end to end

- **Goal:** Reliably queue, monitor, and control HTTP/HTTPS downloads through a private aria2 child process.
- **Scope:** App-owned process and exclusive session lock; authenticated loopback JSON-RPC with random secret and bounded timeouts; safe shutdown; visible engine errors; background RPC/polling; URL and destination input; queue state, byte counts, progress, speed, and errors; per-task pause/resume/removal with confirmation and file preservation by default.
- **Exclusions:** FTP, torrents, session recovery guarantees, dashboard, settings expansion, notifications, packaging, browser integration, plugins, and CLI integration.
- **Dependencies:** Phase 0 complete; aria2c installed and version recorded; controlled local HTTP server.
- **Acceptance criteria:** UI remains responsive during slow or failed RPC; conflict/missing-engine/engine-exit errors are visible; direct HTTP and HTTPS queue controls work; credentials never enter source control, logs, frontend code, or API responses.
- **Verification:** Real-engine integration against a controlled server for success, queueing, pause/resume, removal, and failure; compare completed file SHA-256 with source. Label unit and engine integration evidence separately.

## Phase 2 — Session recovery and download controls

- **Goal:** Recover unfinished work and provide complete list and file-management controls.
- **Scope:** Persist/restore unfinished and deliberately paused tasks with aria2 control files and partial files; restart with overwrite handling; pause/resume all; filters, search, multiselect, context menus; confirmed move-to-Recycle-Bin; FTP and resume capability/error handling; collision protection.
- **Exclusions:** Torrent support, tracker management, dashboard, notifications, packaging, and integrations.
- **Dependencies:** Phase 1 complete; persistent app-owned storage; real HTTP/FTP server support for recovery tests.
- **Acceptance criteria:** Supported interrupted tasks resume from saved offsets; paused tasks stay paused; existing files are not silently overwritten; removal choices match their confirmation; forced-exit recovery limits are documented.
- **Verification:** Throttled real download, close/reopen, server offset logs, final hash, paused-state restore, removal, and forced-exit exercise. Keep unit and real-engine evidence distinct.

## Phase 3 — Torrents and tracker management

- **Goal:** Add BitTorrent and maintain usable tracker configuration.
- **Scope:** Magnet and `.torrent` tasks including metadata fetch, transfer, seeding, pause, and errors; runtime sync of upstream community best/all tracker lists with an app-owned last-good cache; DHT and peer exchange enabled; seeding capped at a 1.0 ratio or 1440 minutes, whichever comes first. Tracker changes use aria2 global options and affect new BitTorrent tasks, not existing ones.
- **Exclusions:** Browser integration, plugins, CLI integration, dashboard write actions, and unverified redistribution of third-party assets.
- **Dependencies:** Phase 2 complete; real aria2 BitTorrent support; controlled lawful torrent and known seeder. The upstream tracker-list repository identifies its data as GPL-2.0, so FetchDeck does not bundle the lists; users can sync them at runtime. Review release obligations before distributing cached data.
- **Acceptance criteria:** Magnet and torrent tasks function; tracker sync safely replaces data only after successful validation; failure preserves last good list; settings application scope is clear.
- **Verification:** Real lawful controlled torrent and magnet with matching SHA-256; seeding and pause behavior; successful and failed tracker sync with last-good cache retention. Mock-only provider tests do not pass the gate.

## Phase 4 — Settings, notifications, and desktop polish

- **Goal:** Make common behavior configurable, persistent, and understandable.
- **Scope:** Persist default folder, concurrency, connections, upload/download limits, User-Agent, theme, notification choices, resume-on-launch, and quit warning; completion/failure feed and Windows tray notifications; keyboard shortcuts; clear engine/settings states; restart-required notes.
- **Exclusions:** Dashboard redesign, packaging, plugins, browser and CLI integrations.
- **Dependencies:** Phase 3 complete; Windows notification support available on target OS.
- **Acceptance criteria:** Settings persist across app reopen and change engine/UI behavior as specified; polling does not duplicate events; quit flow explains active work; in-app and Windows notifications appear for completion and failure.
- **Verification:** Reopen and inspect settings and engine effects; verify real completion/failure notifications in the visible Windows desktop; exercise quit with a real active download. Automated UI checks do not replace visible Windows notification verification.

## Phase 5 — Local Next.js and TypeScript dashboard

- **Goal:** Provide a read-only local statistics dashboard while keeping downloads independent of it.
- **Scope:** Two independently buildable Next.js App Router projects in strict TypeScript: a static local dashboard and a static public website. Both use Tailwind CSS, shared FetchDeck colors/type/logo, and a consistent Lucide icon system. The dashboard shows engine health/version, active/queued counts, live upload/download rates, daily totals, and an activity heatmap; Python serves its export and a versioned read-only API on loopback and opens it from the desktop app. Local activity history persists across restarts without counting restored bytes twice. The public site includes a landing page, feature overview, real desktop and dashboard screenshots, Windows setup instructions, favicon/title/description/OG preview, and a disabled installer action until a verified public URL exists.
- **Exclusions:** Dashboard write controls; RPC credentials, file paths, and source URLs in API responses; Node runtime dependency for installed users; installer enablement without a verified public release URL; deployment before explicit user instruction; plugin/browser/CLI integrations.
- **Dependencies:** Phase 4 complete; Node build tooling; stable engine/stat persistence interfaces.
- **Acceptance criteria:** Both static exports build independently; local API exposes only safe stats and rejects untrusted Host/origin/methods without CORS; dashboard opens from FetchDeck and works while closed/unavailable without affecting downloads; restored bytes are not double-counted; public preview assets load locally, and public canonical/absolute social URLs remain unset until the domain is chosen.
- **Verification:** Lint, strict typecheck, and production build for each app; browser inspect desktop/mobile layout and icon labels; open production dashboard during a real aria2 transfer; verify live data, persisted totals across app restart, safe API output/Host rejection/GET-only behavior, empty/disconnected states, favicon, OG preview image, and all static assets. Public site is built for local verification only; do not deploy.

## Phase 6 - Windows packaging and release readiness

- **Goal:** Prepare a reproducible Windows package and user documentation.
- **Scope:** One-folder Windows application package and portable archive; include the built static dashboard export; third-party notices; external aria2 installation instructions; clean-machine launch and supported workflows; upgrade data preservation; child-process cleanup; supported-feature, limits, troubleshooting, and usage documentation; local artifacts.
- **Exclusions:** Publishing or pushing artifacts without explicit request, plugins, browser integration, and CLI integration.
- **Dependencies:** Phases 0-5 complete, including the Phase 5 dashboard export; Windows packaging toolchain and a clean Windows verification environment. aria2 remains separately installed unless redistribution obligations are resolved.
- **Acceptance criteria:** End users need neither Python nor Node; dashboard assets are included; aria2 prerequisites are explicit; package startup, workflows, data preservation, and child cleanup are verified; notices and docs match the package.
- **Verification:** Build on Windows, launch the package with host Python and Node unavailable, exercise supported downloads/recovery/dashboard with installed aria2, test upgrade against existing app data, and verify no child remains after exit. Record current-machine and clean-machine evidence separately.
