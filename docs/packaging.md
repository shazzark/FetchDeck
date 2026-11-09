# Windows package

FetchDeck can be built as a one-folder Windows application. Python and Node are build tools; neither is needed to launch the package. aria2 remains a separate installation and must be available as `aria2c.exe` on `PATH` or in a supported WinGet location.

## Build

From a Windows PowerShell terminal at the repository root:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-build.txt
npm ci
npm run build --workspace @fetchdeck/dashboard
.\scripts\build_windows.ps1
```

The result is `dist\FetchDeck\FetchDeck.exe` plus the portable archive `dist\FetchDeck-windows-x64.zip`. The production dashboard is placed under `dist\FetchDeck\_internal\dashboard`; the app serves it locally when the user opens Dashboard. The public website is not part of this package. `dist` is ignored by Git and remains a local build artifact.

## Runtime and user data

Install aria2 with WinGet (`winget install --id aria2.aria2 --exact`) or another trusted package source, then restart FetchDeck. The application stores settings, activity, notifications, session state, and torrent metadata under `%LOCALAPPDATA%\FetchDeck`; downloads remain in the folder selected by the user. Installing a newer package over an existing installation leaves this app-owned data in place.

## License and release status

The package contains PySide6/Qt and PyInstaller notices in `THIRD-PARTY-NOTICES.md` and `licenses`. aria2 is not bundled because it is GPL-2.0 and would add redistribution obligations. Qt for Python is available under LGPLv3/GPLv3 community terms or commercial terms. Before public ZIP distribution, review the applicable Qt terms, the shared-library replacement requirements for a PyInstaller bundle, and third-party notices for all dashboard npm assets. The repository's `docs/THIRD-PARTY-NOTICES.md` identifies the current review items.

## Verified Windows package checks

The source-code milestone has verified package launch with Python and Node absent from `PATH`, a controlled local HTTP download with matching SHA-256, dashboard page and stats API serving from loopback, and aria2 child cleanup on graceful app close. See `docs/tasks.md` for the recorded results.
