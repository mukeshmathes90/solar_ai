@echo off
REM ---------------------------------------------------------------------------
REM  Microgrid AI platform - first-time setup
REM  Creates the virtual environment, installs dependencies, generates the
REM  dataset, trains the models and renders the analysis figures.
REM ---------------------------------------------------------------------------
setlocal
cd /d "%~dp0"

echo ============================================================
echo  Microgrid AI platform - installation
echo ============================================================
echo.

set "PY=python"
%PY% --version >nul 2>&1
if errorlevel 1 (
    echo [error] Python was not found on PATH.
    echo         Install Python 3.8+ and tick "Add Python to PATH", then re-run.
    goto :fail
)

for /f "tokens=2" %%v in ('%PY% --version 2^>^&1') do set "PYVER=%%v"
echo [ok] Found Python %PYVER%
echo.

echo [1/4] Upgrading pip ...
%PY% -m pip install --upgrade pip
if errorlevel 1 goto :fail
echo.

echo [2/4] Installing dependencies from requirements.txt ...
%PY% -m pip install -r requirements.txt
if errorlevel 1 goto :fail
echo.

echo [3/4] Generating the simulated dataset ...
%PY% -m ml.generate_dataset --rows 12000 --seed 42
if errorlevel 1 goto :fail
echo.

echo [4/4] Training the models and rendering the figures ...
%PY% -m ml.train
if errorlevel 1 goto :fail
%PY% -m ml.evaluate
if errorlevel 1 goto :fail
echo.

echo ============================================================
echo  Installation complete.
echo  Start the dashboard with:  run.bat
echo  Run the test suite with:   python -m pytest
echo ============================================================
pause
exit /b 0

:fail
echo.
echo ============================================================
echo  [error] Installation did not finish. Read the message above.
echo ============================================================
pause
exit /b 1
