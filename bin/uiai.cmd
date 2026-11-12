@echo off
rem uiai launcher for Windows (cmd / PowerShell). Requires only uv.
rem Messages here are ASCII: cmd.exe reads batch files in the OEM code page, not UTF-8.
setlocal
where uv >nul 2>nul
if errorlevel 1 (
  echo uiai: uv not found. Install: https://docs.astral.sh/uv/getting-started/installation/ 1>&2
  exit /b 2
)
uv run --quiet --script "%~dp0..\engine\main.py" %*
exit /b %ERRORLEVEL%
