# FetchDeck

FetchDeck is a Windows-first desktop download manager built with Python, PySide6, and aria2. Phases 0 through 5 are complete, including user-confirmed Windows notifications, a local statistics dashboard, and a separate public website. See [the implementation plan](docs/implementation-plan.md).

## Development setup (Windows PowerShell)

1. Install 64-bit Python 3.13.x from [python.org](https://www.python.org/downloads/windows/) and select **Add python.exe to PATH**. Python 3.13.3 was detected on the development machine at `C:\Users\chido\.pyenv\pyenv-win\versions\3.13.3\python.exe`; it is the currently selected target. The machine's `py` launcher does not register that pyenv installation, so the venv was created with the full interpreter path. Python 3.11 and 3.12 are declared compatible but have not been verified yet.
2. Install aria2 and ensure `aria2c.exe` is on `PATH`. On Windows with WinGet, use `winget install --id aria2.aria2 --exact`. aria2 1.37.0 is installed for development. FetchDeck does not bundle it and can find a WinGet per-user install.
3. From the repository root:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e .
python -m fetchdeck
```

On this machine, `py -3.13` does not see the pyenv interpreter. Create the environment with the detected interpreter instead: `& 'C:\Users\chido\.pyenv\pyenv-win\versions\3.13.3\python.exe' -m venv .venv`.

If PowerShell blocks activation, use `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` for that terminal, then activate again. Alternatively invoke `.\.venv\Scripts\python.exe -m pip install -e .` and `.\.venv\Scripts\python.exe -m fetchdeck` without activation.

## Checks

Run `python -m compileall src tests` for a Python syntax check and `python -m unittest discover -s tests -v` for the current test suite. The controlled-server aria2 integration test is skipped when aria2c is missing; a skip does not pass the Phase 1 real-engine gate. `python -m fetchdeck` opens the PySide6 window.

The Downloads screen supports HTTP, HTTPS, FTP, magnets, and `.torrent` files, pause/resume, queue controls, session recovery, status filtering, search, multi-select, restart collision choices, and confirmed Recycle Bin moves. Deliberately paused tasks stay paused after restart. Tracker lists sync at runtime and are not bundled. Settings persist locally; concurrency and per-task connections apply after restart, while speed limits and User-Agent apply immediately. The in-app completion/failure feed is implemented. The user confirmed Windows completion and failure notifications and the active-download quit warning; the Phase 2 server log verified resume from a nonzero byte range. Phase 5 builds the local dashboard and a separate public site; neither is deployed by this workflow.

## Dashboard and public site

Node.js 22 and npm are build tools for two separate Next.js 16 static exports. The desktop app remains usable without Node or the dashboard. To build either site, run these commands from the repository root:

```powershell
npm ci
npm run lint
npm run typecheck
npm run build --workspace @fetchdeck/dashboard
npm run build --workspace @fetchdeck/website
```

The dashboard export is written to `apps/dashboard/out`; the desktop **Dashboard** button serves that folder with a read-only API on `127.0.0.1` while the local page is open. The public website export is written separately to `apps/website/out`. It has no configured canonical domain yet. When a public domain is selected, set `$env:NEXT_PUBLIC_SITE_URL='https://your-domain.example'` before building to add canonical and absolute Open Graph/Twitter preview URLs. The branded preview image is `apps/website/public/og-image.png`. The Windows installer action remains disabled until a verified package has a public URL.

Windows package build instructions are in [docs/packaging.md](docs/packaging.md). The user guide is [docs/using-fetchdeck.md](docs/using-fetchdeck.md); license review items are in [docs/THIRD-PARTY-NOTICES.md](docs/THIRD-PARTY-NOTICES.md).
