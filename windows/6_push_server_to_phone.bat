@echo off
rem Copies the server to the phone's internal storage (/sdcard/FNAFAR_server) for Termux.
rem Code, templates and assets are always updated. The save and custom content are only
rem copied if the phone does not have them yet, so your phone progress is never overwritten.
set ADB=%~dp0..\tools\platform-tools\adb.exe
set SRC=%~dp0..\server
set DST=/sdcard/FNAFAR_server
"%ADB%" devices
"%ADB%" shell mkdir -p %DST%/save %DST%/custom
echo Copying files (about 1.1 GB, this can take a few minutes)...
"%ADB%" push "%SRC%\server.py" "%SRC%\game.py" "%SRC%\start.sh" %DST%/
"%ADB%" push "%SRC%\templates" %DST%/
"%ADB%" push "%SRC%\cdn" %DST%/
if exist "%SRC%\save\state.json" (
    "%ADB%" shell ls %DST%/save/state.json >nul 2>&1
    if errorlevel 1 (
        echo Copying your PC save to the phone...
        "%ADB%" push "%SRC%\save\state.json" %DST%/save/
    ) else (
        echo The phone already has a save, it was not overwritten.
    )
)
if exist "%SRC%\custom\custom.json" (
    "%ADB%" shell ls %DST%/custom/custom.json >nul 2>&1
    if errorlevel 1 "%ADB%" push "%SRC%\custom\custom.json" %DST%/custom/
)
echo.
echo Done. Continue with the Termux steps in the README.
pause
