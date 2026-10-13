"""Group defaults that the instrument files do not record (routine column, system dwell volume).

They come from ``lab_defaults.json`` next to this file, taken from the group's UHPLC SOP, and are only ever offered
as editable starting values: the column is installed by hand, so the files cannot confirm it.
"""
import json
from pathlib import Path

_PATH = Path(__file__).with_name('lab_defaults.json')


def lab_defaults() -> dict:
    try:
        data = json.loads(_PATH.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def default_column() -> str:
    return str(lab_defaults().get('column') or '')


def dwell_volume_ul():
    value = lab_defaults().get('dwell_volume_ul')
    return float(value) if isinstance(value, (int, float)) and value > 0 else None
