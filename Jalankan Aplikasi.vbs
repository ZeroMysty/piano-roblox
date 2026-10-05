Set WshShell = CreateObject("WScript.Shell")
WshShell.CurrentDirectory = CreateObject("Scripting.FileSystemObject").GetAbsolutePathName(".")
WshShell.Run "pythonw app.py", 0, False
