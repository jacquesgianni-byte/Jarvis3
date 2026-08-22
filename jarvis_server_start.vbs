Set objShell = CreateObject("WScript.Shell")
objShell.CurrentDirectory = "C:\Users\ljmas\Desktop\jarvis3"
objShell.Run """C:\Users\ljmas\AppData\Local\Python\bin\python.exe"" -m apps.server.server_main >> data\logs\server.log 2>&1", 0, False
