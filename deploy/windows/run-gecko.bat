@echo off
rem Keeps GeckoPlotter running on the lab PC: updates it, starts it, and starts it again 5 seconds after it stops
rem for any reason. Everything it prints goes to logs\gecko.log (slow callbacks are listed there as "slow callback").
rem Run it once by hand to check, then let Task Scheduler start it at boot (see README.md in this folder).
setlocal
cd /d "%~dp0..\.."
if not exist logs mkdir logs
set GECKO_HOST=0.0.0.0
set GECKO_PORT=8052
set GECKO_DEBUG=0

:loop
echo [%date% %time%] updating >> logs\gecko.log
git pull --ff-only >> logs\gecko.log 2>&1
python -m pip install --quiet -r requirements.txt >> logs\gecko.log 2>&1
echo [%date% %time%] starting >> logs\gecko.log
python app.py >> logs\gecko.log 2>&1
echo [%date% %time%] stopped, starting again in 5 seconds >> logs\gecko.log
timeout /t 5 /nobreak >nul
goto loop
