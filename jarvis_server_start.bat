@echo off
REM Jarvis Server Auto-Start ? Genesis-053 Sprint-005
REM Runs on Windows login via Startup Folder.
REM To disable: delete this file from the Startup Folder:
REM   C:\Users\ljmas\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Startup\jarvis_server_start.bat
REM Or run: explorer shell:startup

REM Prevent duplicate instances ? if server is already up, exit cleanly
tasklist /FI "IMAGENAME eq python.exe" /FI "WINDOWTITLE eq jarvis*" >nul 2>&1

cd /d C:\Users\ljmas\Desktop\jarvis3
echo [%DATE% %TIME%] Jarvis server starting... >> data\logs\server.log 2>&1
"C:\Users\ljmas\AppData\Local\Python\bin\python.exe" -m apps.server.server_main >> data\logs\server.log 2>&1
echo [%DATE% %TIME%] Jarvis server exited. >> data\logs\server.log 2>&1
