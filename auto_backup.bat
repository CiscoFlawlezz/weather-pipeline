@echo off
REM --- weather-pipeline auto-backup: commit + push to GitHub ---
cd /d C:\Projects\weather-pipeline

REM Stage all tracked changes (new/modified/deleted). .gitignore is respected.
git add -A

REM Only commit if there is something to commit; otherwise skip cleanly.
git diff --cached --quiet
if %errorlevel%==0 (
    echo No changes to back up.
    exit /b 0
)

REM Timestamped commit message.
for /f "tokens=1-4 delims=/ " %%a in ("%date%") do set d=%%a-%%b-%%c
git commit -m "Auto-backup: %date% %time%"

REM Push to GitHub.
git push origin main
