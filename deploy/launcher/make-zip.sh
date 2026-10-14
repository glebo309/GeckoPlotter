#!/bin/sh
# Builds GeckoPlotter-Launcher.zip, the one file colleagues download. Rebuild it only when the Start scripts change;
# launcher.py and splash.html are fetched from GitHub on every start, so editing those needs no new zip.
set -eu
cd "$(dirname "$0")"
rm -f GeckoPlotter-Launcher.zip
zip -q GeckoPlotter-Launcher.zip "Start GeckoPlotter.bat" "Start GeckoPlotter.command" start-geckoplotter.sh launcher.py splash.html README.txt
zip -q -j GeckoPlotter-Launcher.zip icon/icon.png icon/icon.ico icon/icon.icns
echo "built $(pwd)/GeckoPlotter-Launcher.zip"
