# Running GeckoPlotter on the always-on Windows PC

`run-gecko.bat` does the whole job in a loop: `git pull`, install any new requirement, start the app, and start it again
if it ever stops. Log: `logs\gecko.log` in the GeckoPlotter folder.

1. In the GeckoPlotter folder, check out the version to run once (`git checkout main`) and make sure `git pull` works
   without asking for a password.
2. Double-click `deploy\windows\run-gecko.bat` and open `http://localhost:8052`. If that works, close the window.
3. Task Scheduler, create a task (not a "basic" task):
   - General: *Run whether user is logged on or not*, *Run with highest privileges*
   - Triggers: *At startup*
   - Actions: *Start a program* `C:\path\to\GeckoPlotter\deploy\windows\run-gecko.bat`
     (*Start in*: `C:\path\to\GeckoPlotter\deploy\windows`)
   - Settings: *If the task fails, restart every 1 minute*, up to 999 times; untick *Stop the task if it runs longer than*.
4. To update the app, push to GitHub and restart the task (End, then Run): it pulls on every start.

Every browser has a workspace of its own, but all calculations run on this PC: a busy or slow computer makes everybody slow.
