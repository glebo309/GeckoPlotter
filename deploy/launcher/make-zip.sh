#!/bin/sh
# Builds GeckoPlotter-Launcher.zip, the one file colleagues download. Rebuild it only when the Start scripts change;
# launcher.py, splash.html and the icons are fetched from GitHub, so editing those needs no new zip.
set -eu
cd "$(dirname "$0")"
rm -f GeckoPlotter-Launcher.zip
zip -q GeckoPlotter-Launcher.zip start-windows.bat start-mac.command start-linux.sh README.txt
echo "built $(pwd)/GeckoPlotter-Launcher.zip"
