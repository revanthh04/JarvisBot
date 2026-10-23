@echo off
echo Stopping Jarvis background processes...
taskkill /F /IM python.exe 2>nul
taskkill /F /IM pythonw.exe 2>nul
echo Jarvis processes terminated cleanly.
pause
