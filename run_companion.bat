@echo off
setlocal enabledelayedexpansion
title Portgas D. Ace - AI Desktop Companion
color 0C

:: Navigate to project directory
cd /d "%~dp0"

echo ======================================================================
echo           PORTGAS D. ACE - AI DESKTOP COMPANION LAUNCHER
echo ======================================================================
echo.

:: 1. Prioritize project dedicated virtual environment (.venv)
set "PYTHON_EXE="
if exist "%~dp0.venv\Scripts\python.exe" (
    set "PYTHON_EXE=%~dp0.venv\Scripts\python.exe"
    echo [*] Using Project Virtual Environment: .venv
) else if exist "%~dp0venv\Scripts\python.exe" (
    set "PYTHON_EXE=%~dp0venv\Scripts\python.exe"
    echo [*] Using Project Virtual Environment: venv
) else (
    where python >nul 2>nul
    if !errorlevel! equ 0 (
        set "PYTHON_EXE=python"
        echo [*] Using System Python
    ) else if exist "D:\Anaconda\python.exe" (
        set "PYTHON_EXE=D:\Anaconda\python.exe"
        echo [*] Fallback Python: D:\Anaconda\python.exe
    ) else (
        echo [ERROR] Python environment was not found.
        echo Please ensure .venv exists or Python is installed.
        echo.
        pause
        exit /b 1
    )
)

echo [*] Python Path: !PYTHON_EXE!

:: 2. Check and Auto-start Ollama LLM Service
echo [*] Checking Ollama LLM Service...
curl -s http://localhost:11434/api/tags >nul 2>nul
if !errorlevel! neq 0 (
    echo [!] Ollama server is not running. Starting Ollama in background...
    if exist "%LOCALAPPDATA%\Programs\Ollama\ollama.exe" (
        start "" "%LOCALAPPDATA%\Programs\Ollama\ollama.exe" serve
    ) else (
        start "" ollama serve
    )
    timeout /t 3 /nobreak >nul
    curl -s http://localhost:11434/api/tags >nul 2>nul
    if !errorlevel! equ 0 (
        echo [OK] Ollama server started successfully on http://localhost:11434!
    ) else (
        echo [WARN] Ollama starting in background, proceeding...
    )
) else (
    echo [OK] Ollama is active on http://localhost:11434!
)

:: 3. Set Python Environment Variables
set "PYTHONPATH=%~dp0"

echo [*] Launching Ace AI Backend Server and Desktop Companion Overlay...
echo.

:: 4. Start Companion
"!PYTHON_EXE!" run.py

:: If it exits unexpectedly, pause so user can inspect error details
if !errorlevel! neq 0 (
    echo.
    echo ======================================================================
    echo [ERROR] Ace Companion exited with code !errorlevel!.
    echo Check logs above for details.
    echo ======================================================================
    pause
)
