@echo off
title Audio Slicer ^& Batch Renamer
cd /d "%~dp0"

echo ===================================================
echo Starting Audio Slicer ^& Batch Renamer Web App...
echo ===================================================

if not exist "venv\Scripts\python.exe" (
    echo Error: Virtual environment not found. Please ensure venv exists.
    pause
    exit /b 1
)

"venv\Scripts\python.exe" server.py

pause
