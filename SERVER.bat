@echo off
REM Web app launcher: the frp tunnel (when configured) and the FastAPI server.
REM Get the tunnel files from docs\runbooks\vps.md; without them the server
REM still runs on http://127.0.0.1:8000 for the PC itself.
cd /d "%~dp0"
if exist tools\frp\frpc.exe if exist tools\frp\frpc.toml start "frpc" tools\frp\frpc.exe -c tools\frp\frpc.toml
python server.py %*
pause
