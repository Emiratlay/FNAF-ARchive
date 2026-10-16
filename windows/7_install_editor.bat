@echo off
rem Installs the FNAF AR Editor app and updates the server code on the phone.
rem The save, assets and custom content on the phone are not touched.
set ADB=%~dp0..\tools\platform-tools\adb.exe
set SRC=%~dp0..\server
set DST=/sdcard/FNAFAR_server
"%ADB%" devices
"%ADB%" shell mkdir -p %DST%/custom
"%ADB%" push "%SRC%\server.py" "%SRC%\game.py" "%SRC%\start.sh" %DST%/
"%ADB%" push "%SRC%\templates" %DST%/
"%ADB%" install -r "%~dp0..\editor\build\FNAF.AR.Editor-aligned-debugSigned.apk"
echo.
echo Done. If the server is running in Termux, stop it with CTRL+c and start it again.
pause
