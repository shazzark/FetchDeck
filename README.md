# FetchDeck

FetchDeck is a Windows-first desktop download manager built with Python, PySide6, and aria2. The foundation is complete; download workflow and later features are tracked in [the implementation plan](docs/implementation-plan.md).

## Development setup (Windows PowerShell)

1. Install 64-bit Python 3.13.x from [python.org](https://www.python.org/downloads/windows/) and select **Add python.exe to PATH**. Python 3.13.3 was detected on the development machine at `C:\Users\chido\.pyenv\pyenv-win\versions\3.13.3\python.exe`; it is the currently selected target. The machine's `py` launcher does not register that pyenv installation, so the venv was created with the full interpreter path. Python 3.11 and 3.12 are declared compatible but have not been verified yet.
2. Install aria2 and ensure `aria2c.exe` is on `PATH`. The development machine currently has no detected aria2c. FetchDeck does not bundle it.
3. From the repository root:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e .
python -m fetchdeck
```

If PowerShell blocks activation, use `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` for that terminal, then activate again. Alternatively invoke `.\.venv\Scripts\python.exe -m pip install -e .` and `.\.venv\Scripts\python.exe -m fetchdeck` without activation.

## Checks

Run `python -m compileall src` for a Python syntax check. Phase-specific integration and UI verification commands will be added alongside their implementations. `python -m fetchdeck` opens the PySide6 window.

The dashboard is optional during core development. Node setup is deferred until Phase 5.
