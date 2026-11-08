# FetchDeck

FetchDeck is a Windows-first desktop download manager built with Python, PySide6, and aria2. Phases 0 through 3 are complete. Phase 4 settings and notification workflows are implemented; completion notification is confirmed; failure-notification and active-download quit verification remain. See [the implementation plan](docs/implementation-plan.md).

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

The Downloads screen supports HTTP, HTTPS, FTP, magnets, and `.torrent` files, pause/resume, queue controls, session recovery, status filtering, search, multi-select, restart collision choices, and confirmed Recycle Bin moves. Deliberately paused tasks stay paused after restart. Tracker lists sync at runtime and are not bundled. Settings persist locally; concurrency and per-task connections apply after restart, while speed limits and User-Agent apply immediately. The in-app completion/failure feed is implemented. A user-confirmed Windows "Download complete" banner was shown for a completed HTTPS transfer; the active-download quit and resume check is pending. The Next.js dashboard (Phase 5) is deferred to a future release.
