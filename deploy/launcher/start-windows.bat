@echo off
setlocal
title GeckoPlotter
rem One double-click: installs a private Python (uv) on the first run, fetches the newest GeckoPlotter from GitHub,
rem starts it on this computer and opens it in the browser. Nothing is installed system-wide.
set "RAW=https://raw.githubusercontent.com/glebo309/GeckoPlotter/main/deploy/launcher/"
set "HOME_DIR=%LOCALAPPDATA%\GeckoPlotter"
set "PATH=%USERPROFILE%\.local\bin;%USERPROFILE%\.cargo\bin;%PATH%"
if not exist "%HOME_DIR%" mkdir "%HOME_DIR%"
rem Keep a copy of this script next to the app: the Start menu and Desktop shortcuts run that one.
if /i not "%~dp0"=="%HOME_DIR%\" copy /y "%~f0" "%HOME_DIR%\start-windows.bat" >nul

where uv >nul 2>&1
if errorlevel 1 (
  echo Setting up GeckoPlotter for the first time. This needs the internet and takes a minute...
  powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://astral.sh/uv/install.ps1 | iex"
)
set "PATH=%USERPROFILE%\.local\bin;%USERPROFILE%\.cargo\bin;%PATH%"

rem Newest launcher (if GitHub cannot be reached, the copy already on this computer is used)
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ProgressPreference='SilentlyContinue'; [Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12; foreach($f in 'launcher.py','splash.html'){ try{ Invoke-WebRequest -UseBasicParsing -Uri ('%RAW%'+$f) -OutFile ('%HOME_DIR%\'+$f+'.new'); Move-Item -Force ('%HOME_DIR%\'+$f+'.new') ('%HOME_DIR%\'+$f) }catch{} }" >nul 2>&1

where uv >nul 2>&1
if errorlevel 1 goto failed
if not exist "%HOME_DIR%\launcher.py" goto failed
uv run --python 3.12 --no-project "%HOME_DIR%\launcher.py"
echo.
pause
exit /b 0

:failed
echo.
echo GeckoPlotter could not be set up. Check the internet connection and start this file again.
pause
exit /b 1
