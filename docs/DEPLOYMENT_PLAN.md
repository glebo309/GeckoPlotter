# GeckoPlotter Deployment Plan: Auto-Pull + Auto-Restart

_Written 2026-06-01 for implementation on the HPLC Windows machine._

## Context

GeckoPlotter and other lab tools run on a Windows HPLC computer at `130.92.104.206`. Colleagues access them via browser at `http://130.92.104.206:<port>`. Currently, updating the tools requires manually copying files to the machine and restarting processes. The goal is to automate this so Glenn can push from his laptop (at lab or home via VPN) and the tools update within minutes.

### Current State

- **GeckoPlotter repo**: `glebo309/GeckoPlotter` on GitHub (private)
- **App entry point**: `python app.py` (Dash, runs on port 8052)
- **Python**: system Python 3 (NOT the .venv -- the stale .venv has old Dash 2.14 and crashes)
- **Other tools**: there are other Streamlit/Dash tools on this machine, each on its own port
- **Startup**: a batch file launched by Windows Task Scheduler starts all the tools on boot
- **LAN access**: `http://130.92.104.206:8052` for GeckoPlotter, other ports for other tools
- **Wiki links**: the lab wiki (Quartz-hosted ParadisiVault) links to these tools, opening in new tabs

### What We Decided

Phase 1 (now): Git-pull-on-cron + auto-restart wrapper on the HPLC machine. Zero cost, solves the immediate pain.

Phase 2 (later, optional): Move everything to a Hetzner VPS (4 EUR/month) to stop depending on the HPLC machine. Docker Compose setup. Not needed yet.

## Phase 1 Implementation

### Step 1: Auto-Pull Script

Create a batch script that checks for updates and pulls if available.

**File**: `C:\LabTools\scripts\auto-pull.bat` (or wherever the scripts live)

```bat
@echo off
cd /d C:\path\to\GeckoPlotter_V2
git fetch origin main --quiet
for /f %%i in ('git rev-parse HEAD') do set LOCAL=%%i
for /f %%i in ('git rev-parse origin/main') do set REMOTE=%%i
if not "%LOCAL%"=="%REMOTE%" (
    echo [%date% %time%] Pulling new changes... >> C:\LabTools\logs\auto-pull.log
    git pull origin main --quiet
    echo [%date% %time%] Pull complete, restarting app... >> C:\LabTools\logs\auto-pull.log
    taskkill /f /fi "WINDOWTITLE eq GeckoPlotter" >nul 2>&1
    start "GeckoPlotter" /min python app.py
    echo [%date% %time%] App restarted. >> C:\LabTools\logs\auto-pull.log
) else (
    echo [%date% %time%] No changes. >> C:\LabTools\logs\auto-pull.log
)
```

**Notes for the implementer:**
- Find the actual path to the GeckoPlotter checkout on this machine
- Find which Python executable is used (must NOT be the .venv one)
- The `taskkill` line needs to match however the app process is identified -- could be by window title, PID file, or process name. Investigate what's running.
- Create `C:\LabTools\logs\` if it doesn't exist

### Step 2: Scheduled Task (every 2 minutes)

Use Windows Task Scheduler to run `auto-pull.bat` every 2 minutes:

```
schtasks /create /tn "GeckoPlotter AutoPull" /tr "C:\LabTools\scripts\auto-pull.bat" /sc minute /mo 2 /ru SYSTEM
```

Or set it up via the Task Scheduler GUI if you prefer.

### Step 3: Auto-Restart Wrapper

The app should restart automatically if it crashes. Wrap `python app.py` in a loop:

**File**: `C:\LabTools\scripts\run-gecko.bat`

```bat
@echo off
:loop
echo [%date% %time%] Starting GeckoPlotter... >> C:\LabTools\logs\gecko.log
cd /d C:\path\to\GeckoPlotter_V2
python app.py >> C:\LabTools\logs\gecko.log 2>&1
echo [%date% %time%] App exited, restarting in 5 seconds... >> C:\LabTools\logs\gecko.log
timeout /t 5 /nobreak >nul
goto loop
```

Replace the existing startup batch file entry for GeckoPlotter with this wrapper.

### Step 4: Git Authentication

The machine needs to be able to `git pull` from the private GitHub repo without prompting for credentials.

Options (pick one):
1. **GitHub CLI**: `gh auth login` (simplest)
2. **Credential Manager**: `git config --global credential.helper manager` (Windows built-in, may already work)
3. **SSH key**: generate a key on this machine and add it to Glenn's GitHub account
4. **Personal Access Token**: store in Windows Credential Manager

Check if `git pull` already works without prompting. If yes, skip this step.

### Step 5: Verify

1. Make a trivial change on the laptop (e.g. bump a comment), push to GitHub
2. Wait 2 minutes
3. Check `C:\LabTools\logs\auto-pull.log` for "Pulling new changes"
4. Reload `http://130.92.104.206:8052` and verify the change is live
5. Kill the Python process manually and verify it auto-restarts within 5 seconds

## Paths and Details to Discover

The implementing session needs to find these on the Windows machine:

- [ ] Where is GeckoPlotter checked out? (`dir /s /b C:\*app.py` or ask Glenn)
- [ ] Which Python is used to run it? (`where python`, check version)
- [ ] Is there an existing startup batch file? What does it do? Where is it?
- [ ] Is git installed? (`git --version`)
- [ ] Does `git pull` work without prompting for credentials?
- [ ] What other tools run on this machine and on which ports?
- [ ] Is there an existing Task Scheduler task for the tools?

## Other Lab Tools

The same auto-pull + auto-restart pattern can be applied to any other tool on this machine. Each tool gets:
1. Its own `auto-pull-<toolname>.bat`
2. Its own `run-<toolname>.bat` wrapper
3. Its own scheduled task

If there are many tools, consolidate into a single `auto-pull-all.bat` that loops through each repo.

## Phase 2 (Future): Hetzner VPS

When/if Glenn decides to move off the HPLC machine:

- **Provider**: Hetzner Cloud CX22, 4GB RAM, 4 EUR/month
- **Stack**: Docker Compose + Caddy reverse proxy
- **Each tool**: Dockerfile + entry in docker-compose.yml
- **Auto-deploy**: GitHub webhook or cron `git pull` + `docker compose up -d --build`
- **Auth**: Caddy basic auth or Authelia in front of lab tools
- **Domain**: optional, can use IP or free Hetzner subdomain

The Docker setup would be written when this phase is needed. The git-pull approach from Phase 1 transfers directly -- just pull inside the container instead of on bare metal.

## Key Constraints

- **Do NOT use the .venv** in the GeckoPlotter_V2 folder. It has stale Dash 2.14 / React 16 which causes useId crashes and empty menus. Use system `python3` (Dash 3.0.4 / React 18).
- **Port 8052** is GeckoPlotter's port. Don't change it without updating the wiki links.
- **The machine is on UniBE network** at 130.92.104.206. Accessible from campus LAN and via VPN.
