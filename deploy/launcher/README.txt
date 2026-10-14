GeckoPlotter launcher
=====================

Needs: the internet (first start only: about 600 MB), nothing else. No admin rights, nothing system-wide.

Windows : double-click "Start GeckoPlotter.bat".
          If Windows says "protected your PC": More info, then Run anyway (once).
Mac     : right-click "Start GeckoPlotter.command", choose Open, then Open again (once).
Linux   : run  bash start-geckoplotter.sh

After the first start there is a GeckoPlotter shortcut with the gecko icon (Start menu and Desktop on
Windows, Applications folder on Mac, the app menu on Linux): use that from then on.

Your browser opens by itself. First start takes a few minutes; later starts take seconds and update
GeckoPlotter from GitHub automatically. Keep the black window open while you work; close it to stop.

Everything runs on your own computer. Autosaves and projects are in Documents/GeckoPlotter.
Problems: send the file  launcher.log  from
  Windows  %LOCALAPPDATA%\GeckoPlotter
  Mac      ~/Library/Application Support/GeckoPlotter
  Linux    ~/.local/share/GeckoPlotter
