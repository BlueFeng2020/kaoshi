@echo off
setlocal
cd /d "%~dp0"
set "PYTHONUTF8=1"
set "MODE=%~1"
if "%MODE%"=="" set "MODE=onefile"
if not "%MODE%"=="onefile" if not "%MODE%"=="onedir" goto usage
if exist ".venv\Scripts\python.exe" goto install
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
".venv\Scripts\python.exe" -m pip install -r requirements-build.txt
if errorlevel 1 goto fail
goto build
:offline
".venv\Scripts\python.exe" -m pip install --no-index --find-links wheelhouse -r requirements-build.txt
if errorlevel 1 goto fail
:build
".venv\Scripts\python.exe" build.py --mode %MODE%
if errorlevel 1 goto fail
echo Build completed. The final delivery folder has been opened.
echo Use the EXE inside the opened delivery folder, not build\artifacts.
echo The EXE passed --prepare; browser acceptance is still required.
pause
exit /b 0
:usage
echo Usage: build.bat [onefile or onedir]
exit /b 2
:nopython
echo Install Python 3.12 64-bit and enable Add Python to PATH, then retry.
:fail
echo Build failed. Read the error above. No successful build is claimed.
pause
exit /b 1
