@echo off
rem Offline mode: the PC is the game server. Keep the phone plugged in over USB.
set ADB=%~dp0..\tools\platform-tools\adb.exe
"%ADB%" reverse tcp:9000 tcp:9000
cd /d "%~dp0..\server"
python server.py offline
pause
