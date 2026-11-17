@echo off
title Stop Ace AI Services
color 0E

echo ======================================================================
echo                 STOPPING ALL ACE AI SERVICES
echo ======================================================================
echo.

:: 1. Stop Ace AI Backend Server on Port 8000
echo [*] Checking for Ace AI server running on port 8000...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":8000" ^| findstr "LISTENING"') do (
    echo [*] Terminating Ace AI Backend process (PID: %%a)...
    taskkill /F /PID %%a >nul 2>nul
)

:: 2. Stop Python processes associated with Ace_Ai
echo [*] Cleaning up Ace AI companion processes...
powershell -Command "Get-Process python -ErrorAction SilentlyContinue | Where-Object { $_.Path -like '*Ace_Ai*' -or $_.CommandLine -like '*run.py*' } | Stop-Process -Force -ErrorAction SilentlyContinue" >nul 2>nul

:: 3. Stop Ollama LLM Service
echo [*] Checking for Ollama LLM service...
taskkill /F /IM ollama.exe >nul 2>nul
taskkill /F /IM "ollama app.exe" >nul 2>nul

echo.
echo ======================================================================
echo [SUCCESS] All Ace AI services and Ollama have been stopped!
echo Ports 8000 and 11434 are now free.
echo ======================================================================
echo.
pause
