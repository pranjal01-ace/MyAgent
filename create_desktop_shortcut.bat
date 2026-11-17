@echo off
title Create Desktop Shortcut for Ace AI Companion
cd /d "%~dp0"

echo Creating Desktop shortcut for Portgas D. Ace AI Companion...

set "SCRIPT_PATH=%~dp0run_companion.bat"
set "STOP_SCRIPT_PATH=%~dp0stop_services.bat"
set "VBS_SCRIPT=%TEMP%\create_ace_shortcut.vbs"

echo Set oWS = WScript.CreateObject("WScript.Shell") > "%VBS_SCRIPT%"
echo strDesktop = oWS.SpecialFolders("Desktop") >> "%VBS_SCRIPT%"
echo Set oLink = oWS.CreateShortcut(strDesktop ^& "\Ace AI Companion.lnk") >> "%VBS_SCRIPT%"
echo oLink.TargetPath = "%SCRIPT_PATH%" >> "%VBS_SCRIPT%"
echo oLink.WorkingDirectory = "%~dp0" >> "%VBS_SCRIPT%"
echo oLink.Description = "Launch Portgas D. Ace AI Desktop Companion" >> "%VBS_SCRIPT%"
echo oLink.WindowStyle = 1 >> "%VBS_SCRIPT%"
echo oLink.Save >> "%VBS_SCRIPT%"

echo Set oStopLink = oWS.CreateShortcut(strDesktop ^& "\Stop Ace AI.lnk") >> "%VBS_SCRIPT%"
echo oStopLink.TargetPath = "%STOP_SCRIPT_PATH%" >> "%VBS_SCRIPT%"
echo oStopLink.WorkingDirectory = "%~dp0" >> "%VBS_SCRIPT%"
echo oStopLink.Description = "Stop all running Ace AI and Ollama services" >> "%VBS_SCRIPT%"
echo oStopLink.WindowStyle = 1 >> "%VBS_SCRIPT%"
echo oStopLink.Save >> "%VBS_SCRIPT%"

cscript /nologo "%VBS_SCRIPT%"
del "%VBS_SCRIPT%" >nul 2>nul

echo.
echo [SUCCESS] Desktop shortcuts created:
echo  1. "%USERPROFILE%\Desktop\Ace AI Companion.lnk"
echo  2. "%USERPROFILE%\Desktop\Stop Ace AI.lnk"
echo.
echo You can now double-click:
echo  - "Ace AI Companion" to start
echo  - "Stop Ace AI" to stop all services!
echo.
