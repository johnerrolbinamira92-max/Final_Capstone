@echo off
setlocal
cd /d "%~dp0"

netstat -ano -p tcp | findstr /R /C:":8501 .*LISTENING" >nul
if not errorlevel 1 goto wait_for_port

set "FOUND_PYTHON="
call :tryPython "%~dp0.venv\Scripts\python.exe"
call :tryPython "%~dp0venv\Scripts\python.exe"
call :tryPython "%~dp0Final_Capstone\Scripts\python.exe"
call :tryPython "%USERPROFILE%\.virtualenvs\Final_Capstone\Scripts\python.exe"
call :tryPython "%USERPROFILE%\anaconda3\envs\Final_Capstone\python.exe"
call :tryPython "%USERPROFILE%\miniconda3\envs\Final_Capstone\python.exe"

if not defined FOUND_PYTHON (
  for /f "delims=" %%P in ('where python 2^>nul') do call :tryPython "%%P"
)
if not defined FOUND_PYTHON (
  for /f "delims=" %%P in ('py -c "import streamlit, sys; print(sys.executable)" 2^>nul') do call :tryPython "%%P"
)

if not defined FOUND_PYTHON (
  echo No Python interpreter with Streamlit installed was found.
  echo Checked the project, virtualenv, Conda, PATH, and py environments.
  pause
  exit /b 1
)

echo Starting the Holy Face Center Admin Portal...
start "HFRC_Streamlit_Server" /min "%FOUND_PYTHON%" -m streamlit run admin_portal/app.py --server.port 8501 --server.headless true > "%TEMP%\hfrc_admin_portal.log" 2>&1

:wait_for_port
echo Waiting for the Admin Portal to become available...
powershell -NoProfile -Command "$deadline = (Get-Date).AddSeconds(25); while ((Get-Date) -lt $deadline) { try { Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:8501' -TimeoutSec 1 -ErrorAction Stop | Out-Null; exit 0 } catch { Start-Sleep -Seconds 1 } }; exit 1"
if errorlevel 1 (
  echo The Admin Portal did not become available at http://127.0.0.1:8501.
  echo Streamlit startup output:
  if exist "%TEMP%\hfrc_admin_portal.log" (
    type "%TEMP%\hfrc_admin_portal.log"
  ) else (
    echo No startup log was created at "%TEMP%\hfrc_admin_portal.log".
  )
  pause
  exit /b 1
)

start "" msedge --app=http://127.0.0.1:8501
if not errorlevel 1 exit /b 0

start "" chrome --app=http://127.0.0.1:8501
if not errorlevel 1 exit /b 0

start "" http://127.0.0.1:8501
exit /b 0

:tryPython
if defined FOUND_PYTHON exit /b 0
if not exist "%~1" exit /b 0
"%~1" -c "import streamlit" >nul 2>&1
if not errorlevel 1 set "FOUND_PYTHON=%~1"
exit /b 0
