@echo off
REM ---------------------------------------------------------------------------
REM  Microgrid AI platform - start the server
REM  Trains the models on first run if the artifacts are missing OR cannot be
REM  used by the installed scikit-learn (model files are not portable across
REM  major scikit-learn releases), opens the firewall for the hotspot, then
REM  serves the API + dashboard on port 5000.
REM ---------------------------------------------------------------------------
setlocal
cd /d "%~dp0"

set "PY=python"
set "PORT=5000"

%PY% --version >nul 2>&1
if errorlevel 1 (
    echo [error] Python was not found on PATH. Run install.bat first.
    pause
    exit /b 1
)

REM Readiness probe: the models must be loadable AND produce sane
REM probabilities, not merely exist on disk.
%PY% -c "from backend.services.inference import SERVICE; import sys; sys.exit(0 if SERVICE.is_ready() else 1)" >nul 2>&1
if errorlevel 1 (
    echo [setup] Model artifacts are missing or incompatible with this Python - generating data and training ...
    %PY% -m ml.generate_dataset --rows 12000 --seed 42
    if errorlevel 1 goto :fail
    %PY% -m ml.train
    if errorlevel 1 goto :fail
    %PY% -m ml.evaluate
    if errorlevel 1 goto :fail
)

echo.
echo [net] Allowing inbound TCP %PORT% through Windows Firewall ...
netsh advfirewall firewall add rule name="Microgrid AI backend (%PORT%)" dir=in action=allow protocol=TCP localport=%PORT% >nul 2>&1
if errorlevel 1 (
    echo [note] Could not add the firewall rule ^(needs Administrator^).
    echo        If the ESP8266 cannot reach the server, run this once as Admin:
    echo          netsh advfirewall firewall add rule name="Microgrid AI backend" dir=in action=allow protocol=TCP localport=%PORT%
)

echo.
echo [net] Laptop addresses on this machine:
%PY% scripts\diagnose_network.py --port %PORT%
echo.
echo [net] Put the matching http://^<address^>:%PORT% value into
echo        firmware\microgrid_node\credentials.h as BACKEND_URL.
echo.

echo Starting the server - press Ctrl+C to stop.
echo.
%PY% -m backend.app --host 0.0.0.0 --port %PORT%
goto :eof

:fail
echo [error] Startup failed. Read the message above.
pause
exit /b 1
