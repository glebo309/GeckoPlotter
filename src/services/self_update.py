"""Update from the About window: save the work, stop this GeckoPlotter and let the launcher start it again, which fetches
the newest version first (as every start does) and opens the browser on it.

Only an install made by the launcher can update itself this way; a git checkout is updated with git.
"""
from __future__ import annotations

import os
import subprocess
import sys
import threading
from pathlib import Path


def launcher_path() -> Path:
    from services.about import ROOT
    return ROOT.parent / 'launcher.py'


def can_update() -> bool:
    from services.about import VERSION
    return VERSION.get('source') == 'launcher' and launcher_path().is_file()


def restart_to_update(store=None) -> None:
    """Autosave, start the launcher once this app has stopped (``--wait-for-exit``), then stop."""
    if store is not None:
        try:
            from services import session_service
            if any(True for _ in store.iter_bundles()):
                session_service.save_autosave(store)
        except Exception:                               # noqa: BLE001  never block the update on the autosave
            pass
    command = [sys.executable, str(launcher_path()), '--background', '--wait-for-exit']
    options = {'cwd': str(launcher_path().parent), 'stdin': subprocess.DEVNULL, 'stdout': subprocess.DEVNULL,
               'stderr': subprocess.DEVNULL}
    if sys.platform.startswith('win'):
        options['creationflags'] = 0x00000008 | 0x00000200      # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    else:
        options['start_new_session'] = True
    subprocess.Popen(command, **options)
    threading.Timer(1.0, os._exit, args=(0,)).start()        # after the browser got the answer
