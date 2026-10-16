@echo off
rem Installs the patched game APK on the phone over USB.
rem Uninstall any other FNAF AR / ARchive build from the phone first (different signature).
set ADB=%~dp0..\tools\platform-tools\adb.exe
"%ADB%" devices
"%ADB%" install -r "%~dp0..\patcher\build\FNaF.AR.8.0.0.offline-aligned-debugSigned.apk"
pause
