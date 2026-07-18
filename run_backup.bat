@echo off
setlocal enabledelayedexpansion

REM ============================================================
REM run_backup.bat
REM   Task Scheduler wrapper for the pipeline.db backup.
REM
REM   Mirrors run_cli_collection.bat's conventions:
REM     * run from the repo root
REM     * append all output to a dated log
REM     * exit NON-ZERO on failure (never a false success)
REM
REM   NO RETRY, deliberately. Unlike collection (where a transient
REM   network blip is worth a second attempt), a backup failure
REM   means the drive is missing or the DB is corrupt. Retrying
REM   either one immediately just fails again and buries the signal.
REM   Tomorrow's run is the retry.
REM
REM   This wrapper never touches the live database.
REM ============================================================

set "REPO=C:\Projects\weather-pipeline"
set "LOGDIR=%REPO%\logs"
set "PYTHON=%REPO%\venv\Scripts\python.exe"

if not exist "%LOGDIR%" mkdir "%LOGDIR%"

REM --- Dated log name: backup_YYYY-MM-DD.log (WMIC = locale-independent)
set "STAMP="
for /f "skip=1 tokens=1" %%s in ('wmic os get localdatetime 2^>nul') do if not defined STAMP set "STAMP=%%s"
if defined STAMP (
    set "TODAY=!STAMP:~0,4!-!STAMP:~4,2!-!STAMP:~6,2!"
) else (
    set "TODAY=%DATE%"
)
set "LOGFILE=%LOGDIR%\backup_!TODAY!.log"

echo. >> "%LOGFILE%"
echo ============================================================ >> "%LOGFILE%"
echo [%DATE% %TIME%] Backup run starting >> "%LOGFILE%"

cd /d "%REPO%"
if errorlevel 1 (
    echo [%DATE% %TIME%] FATAL: cannot cd to %REPO% >> "%LOGFILE%"
    exit /b 20
)

"%PYTHON%" scripts\backup_db.py >> "%LOGFILE%" 2>&1
set "RC=!errorlevel!"

if "!RC!"=="0" (
    echo [%DATE% %TIME%] SUCCESS ^(exit 0^) >> "%LOGFILE%"
    exit /b 0
)

echo [%DATE% %TIME%] FAILURE ^(exit !RC!^) >> "%LOGFILE%"
exit /b !RC!
