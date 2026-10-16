@echo off
rem Clears the game's data on the phone (cache, downloaded assets, login).
rem Use it if loading gets stuck after switching servers. The offline save is not touched.
set ADB=%~dp0..\tools\platform-tools\adb.exe
echo The game will be closed and its data on the phone cleared.
pause
"%ADB%" shell pm clear com.illumix.fnafar
pause
