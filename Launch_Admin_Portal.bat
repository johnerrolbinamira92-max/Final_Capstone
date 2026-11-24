@echo off
setlocal
cd /d "%~dp0"

if exist ".venv\Scripts\activate.bat" (
  call ".venv\Scripts\activate.bat"
) else if exist "venv\Scripts\activate.bat" (
  call "venv\Scripts\activate.bat"
)

netstat -ano -p tcp | findstr /R /C:":8501 .*LISTENING" >nul
if errorlevel 1 (
  echo Starting the Holy Face Center Admin Portal...
  start "Holy Face Center Admin Portal" /min python -m streamlit run admin_portal/app.py --server.headless=true
)

echo Waiting for the Admin Portal to become available...
powershell -NoProfile -Command "$deadline = (Get-Date).AddSeconds(60); while ((Get-Date) -lt $deadline) { try { Invoke-WebRequest -UseBasicParsing -Uri 'http://localhost:8501' -TimeoutSec 2 -ErrorAction Stop | Out-Null; exit 0 } catch { Start-Sleep -Seconds 1 } }; exit 1"
if errorlevel 1 (
  echo The Admin Portal did not become available at http://localhost:8501.
  pause
  exit /b 1
)

start "" msedge --app=http://localhost:8501
if not errorlevel 1 exit /b 0

start "" chrome --app=http://localhost:8501
if not errorlevel 1 exit /b 0

start "" http://localhost:8501
