@echo off
setlocal enabledelayedexpansion

set "ROOT=%~dp0"
set "VENV_DIR=%ROOT%venv"
set "BACKEND_DIR=%ROOT%backend"
set "FRONTEND_DIR=%ROOT%frontend"
set "REQUIREMENTS=%BACKEND_DIR%\requirements.txt"

:: 1. Create / activate Python virtual environment
if not exist "%VENV_DIR%\Scripts\python.exe" (
    echo Creating Python virtual environment...
    python -m venv "%VENV_DIR%"
    if errorlevel 1 (
        echo Failed to create virtual environment. Is Python installed?
        pause
        exit /b 1
    )
)

:: 2. Install / upgrade dependencies
echo Installing / upgrading Python dependencies...
"%VENV_DIR%\Scripts\python.exe" -m pip install --upgrade pip -q
"%VENV_DIR%\Scripts\pip.exe" install -r "%REQUIREMENTS%" -q
if errorlevel 1 (
    echo Failed to install dependencies.
    pause
    exit /b 1
)

:: 3. Verify free port
set "PORT=8100"
:checkport
netstat -an 2>nul | findstr ":%PORT% " >nul
if !errorlevel! equ 0 (
    echo Port !PORT! is in use, trying next...
    set /a PORT+=1
    goto checkport 
)

:: 4. Start the backend server
echo Starting server on http://localhost:!PORT!...
start "Backend" /B "%VENV_DIR%\Scripts\python.exe" -m uvicorn main:app --host 0.0.0.0 --port !PORT! --reload --app-dir "%BACKEND_DIR%"

:: 5. Wait briefly then open browser
timeout /t 3 /nobreak >nul
start "" "http://localhost:!PORT!"

echo.
echo Server running at http://localhost:!PORT!
echo Press any key to stop the server.
pause

:: 6. Stop uvicorn on keypress
taskkill /f /im uvicorn.exe 2>nul