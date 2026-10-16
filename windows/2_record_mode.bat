@echo off
rem Record mode (internet required): forwards the game's requests to the real ARchive
rem PlayFab server and saves them in server\captures. Only needed for development.
set ADB=%~dp0..\tools\platform-tools\adb.exe
"%ADB%" reverse tcp:9000 tcp:9000
cd /d "%~dp0..\server"
python server.py record
pause
