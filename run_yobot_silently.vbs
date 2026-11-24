Set WshShell = CreateObject("WScript.Shell")
Set FSO = CreateObject("Scripting.FileSystemObject")
ScriptDir = FSO.GetParentFolderName(WScript.ScriptFullName)
WshShell.CurrentDirectory = ScriptDir
WshShell.Run Chr(34) & ScriptDir & "\venv\Scripts\pythonw.exe" & Chr(34) & " " & Chr(34) & ScriptDir & "\bot.py" & Chr(34), 0, False
Set WshShell = Nothing
Set FSO = Nothing
