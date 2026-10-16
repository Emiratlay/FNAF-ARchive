@echo off
rem Writes the game's log to server\logcat.txt. Close this window to stop.
set ADB=%~dp0..\tools\platform-tools\adb.exe
"%ADB%" logcat -c
"%ADB%" logcat -v time Unity:V *:W > "%~dp0..\server\logcat.txt"
