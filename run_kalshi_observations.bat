@echo off
setlocal enabledelayedexpansion

REM ============================================================
REM run_kalshi_observations.bat
REM   Task Scheduler wrapper for the Kalshi order-book depth +
REM   market-state observation collector (M1.T2).
REM
REM   DELIVERED BUT NOT YET SCHEDULED. Creating this file schedules
REM   nothing; a Task Scheduler entry must be registered separately
REM   (see scheduler notes) and only on the Architect's instruction.
REM
REM   Responsibilities (mirrors run_cli_collection.bat):
REM     * run the collector as a module from the repo root
REM     * append all output to a dated automation log
REM     * retry ONCE after a short delay if the collector fails
REM     * exit NON-ZERO if both attempts fail (never silently succeed)
REM
REM   The collector appends one row per successful observation and is
REM   safe to run at any cadence: every poll is a legitimate new
REM   observation (depth changes over time), so re-runs never clash.
REM
REM   Nothing here overwrites data: the collector only ever appends,
REM   and this wrapper only ever appends to the log (>>).
REM ============================================================

REM --- Fixed locations (edit REPO if you move the project) ----
set "REPO=C:\Projects\weather-pipeline"
set "DB=%REPO%\data\pipeline.db"
set "LOGDIR=%REPO%\logs"
set "PYTHON=%REPO%\venv\Scripts\python.exe"

REM --- Ensure the log directory exists ------------------------
if not exist "%LOGDIR%" mkdir "%LOGDIR%"

REM --- Build a dated log file name: kalshi_obs_YYYY-MM-DD.log --
set "STAMP="
for /f "skip=1 tokens=1" %%s in ('wmic os get localdatetime 2^>nul') do if not defined STAMP set "STAMP=%%s"
if defined STAMP (
    set "TODAY=!STAMP:~0,4!-!STAMP:~4,2!-!STAMP:~6,2!"
) else (
    set "TODAY=%DATE%"
)
set "LOGFILE=%LOGDIR%\kalshi_obs_!TODAY!.log"

REM --- Human-readable run timestamp for the log ---------------
set "NOW=%DATE% %TIME%"

echo. >> "%LOGFILE%"
echo ============================================================ >> "%LOGFILE%"
echo [!NOW!] Kalshi observation sweep starting (attempt 1) >> "%LOGFILE%"

REM --- Move to the repo root so relative imports resolve ------
cd /d "%REPO%"
if errorlevel 1 (
    echo [!NOW!] FATAL: cannot cd to %REPO% >> "%LOGFILE%"
    exit /b 20
)

REM --- Attempt 1 ---------------------------------------------
"%PYTHON%" -m collectors.kalshi_observation_collector "%DB%" >> "%LOGFILE%" 2>&1
set "RC=!errorlevel!"

if "!RC!"=="0" (
    echo [%DATE% %TIME%] SUCCESS on attempt 1 ^(exit 0^) >> "%LOGFILE%"
    exit /b 0
)

REM --- Attempt 1 failed: log, wait, retry once ---------------
echo [%DATE% %TIME%] FAILURE on attempt 1 ^(exit !RC!^) -- retrying in 60s >> "%LOGFILE%"

timeout /t 60 /nobreak >nul 2>&1

echo [%DATE% %TIME%] Kalshi observation sweep starting (attempt 2) >> "%LOGFILE%"
"%PYTHON%" -m collectors.kalshi_observation_collector "%DB%" >> "%LOGFILE%" 2>&1
set "RC=!errorlevel!"

if "!RC!"=="0" (
    echo [%DATE% %TIME%] SUCCESS on attempt 2 ^(exit 0^) >> "%LOGFILE%"
    exit /b 0
)

echo [%DATE% %TIME%] FAILURE on attempt 2 ^(exit !RC!^) -- giving up >> "%LOGFILE%"
exit /b !RC!