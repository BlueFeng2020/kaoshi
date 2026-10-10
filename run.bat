@echo off
setlocal
cd /d "%~dp0"
set "PYTHONUTF8=1"
if exist ".venv\Scripts\python.exe" goto checkdeps
py -3 --version >nul 2>&1
if errorlevel 1 goto plainpython
py -3 -m venv .venv
if errorlevel 1 goto fail
goto install
:plainpython
python --version >nul 2>&1
if errorlevel 1 goto nopython
python -m venv .venv
if errorlevel 1 goto fail
:install
if exist wheelhouse goto offline
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto fail
goto run
:checkdeps
".venv\Scripts\python.exe" -c "import flask, pandas, matplotlib" >nul 2>&1
if errorlevel 1 goto install
goto run
:offline
".venv\Scripts\python.exe" -m pip install --no-index --find-links wheelhouse -r requirements.txt
if errorlevel 1 goto fail
:run
".venv\Scripts\python.exe" app.py
if errorlevel 1 goto fail
exit /b 0
:nopython
echo Install Python 3.12 64-bit and enable Add Python to PATH, then retry.
:fail
echo Startup failed. Check the error above. If dependencies are missing, use README install commands.
pause
exit /b 1
