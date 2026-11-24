@echo off
echo Stopping YoBot background processes...
taskkill /F /IM python.exe 2>nul
taskkill /F /IM pythonw.exe 2>nul
echo YoBot processes terminated cleanly.
pause
