#!/usr/bin/env python3
"""Turn hook for live mode: an agent (Claude Code) runs this when the user sends a prompt (``start``) and when it has
answered (``end``), so GeckoPlotter's status bar shows the agent at work for the whole turn, not only during its calls.

It tells the GeckoPlotter used last (services/live_client) which processes it runs under; the app matches them with the
agent's GeckoPlotter MCP server, so a session without GeckoPlotter changes nothing. It prints nothing (Claude Code
adds a prompt hook's output to the conversation) and always exits 0 within a few seconds.
"""
import json
import os
import subprocess
import sys
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'src'))


def ancestors(limit: int = 8):
    """This process's parents, nearest first (the shell the hook runs in, the agent, its terminal...)."""
    found, pid = [], os.getppid()
    while pid > 1 and len(found) < limit:
        found.append(pid)
        try:
            out = subprocess.run(['ps', '-o', 'ppid=', '-p', str(pid)], capture_output=True, text=True, timeout=2)
            pid = int(out.stdout.strip() or 0)
        except (OSError, ValueError, subprocess.SubprocessError):
            break
    return found


def main(state: str) -> None:
    from services.live_agent import TURN
    from services.live_client import find
    info = find()
    if not info or state not in ('start', 'end'):
        return
    body = json.dumps({'state': state, 'ancestors': ancestors()}).encode()
    request = urllib.request.Request(f"http://127.0.0.1:{info['port']}{TURN}", data=body, method='POST',
                                     headers={'Content-Type': 'application/json', 'X-Gecko-Key': info['key']})
    with urllib.request.urlopen(request, timeout=3):
        pass


if __name__ == '__main__':
    try:
        sys.stdin.close()                                 # the hook's JSON input is not needed
        main(sys.argv[1] if len(sys.argv) > 1 else '')
    except Exception:                                     # noqa: BLE001  never disturb the agent
        pass
    sys.exit(0)
