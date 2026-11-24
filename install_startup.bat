@echo off
set SCRIPT_DIR=%~dp0
set VBS_PATH=%SCRIPT_DIR%run_yobot_silently.vbs
set STARTUP_DIR=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup
set SHORTCUT=%STARTUP_DIR%\YoBotAssistant.lnk

echo Creating Windows Startup Shortcut...
powershell -Command "$ws = New-Object -ComObject WScript.Shell; $s = $ws.CreateShortcut('%SHORTCUT%'); $s.TargetPath = 'wscript.exe'; $s.Arguments = '\"%VBS_PATH%\"'; $s.WorkingDirectory = '%SCRIPT_DIR%'; $s.Save()"
echo Done! YoBot will now start automatically whenever your computer boots up.
pause
