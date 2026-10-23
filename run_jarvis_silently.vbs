Set WshShell = CreateObject("WScript.Shell")
WshShell.Run "venv\Scripts\pythonw.exe bot.py", 0, False
Set WshShell = Nothing
