"""Recipes: the analysis steps of one batch, saved and applied to the next.

A recipe records, without any data:

* the integration settings (smoothing, baseline, detection threshold) used for each kind of signal,
* the compounds found in the reference samples as retention-time windows with their names, and
* the calibration curves.

Applying it to newly loaded samples integrates each matching signal with those settings, keeps the peaks that fall in
a recipe window (named after the compound), drops the other detected peaks, groups the peaks across samples and
reports which compounds were found or missing in each sample. Manual and deconvolved peaks are never touched.

Signals are matched by the same identity calibrations use (detector category, axes, wavelength, channel), never by
sample or file name.
"""
from __future__ import annotations

import json
import math
import statistics
from collections import Counter
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

RECIPE_FORMAT = 'geckoplotter-recipe'
SCHEMA_VERSION = 1
MAX_RECIPE_BYTES = 10_000_000
MAX_WINDOWS = 500

_SETTING_FIELDS = ('smooth_window', 'smooth_poly_order', 'baseline_method', 'baseline_iterations',
                   'baseline_poly_order', 'peak_threshold', 'slope_threshold', 'extension_factor',
                   'min_peak_width', 'min_peak_distance')
_BASELINE_MODES = ('linear', 'zero')
_SKIPPED_SOURCES = ('deconvolved',)
LOWER_THRESHOLDS = (0.2, 0.1, 0.05, 0.02)      # fraction of the tallest peak; tried in order when a compound is not found


class RecipeError(ValueError):
    """The recipe is not valid or cannot be applied."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def _number(value, default=None):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) else default


def _signal_key(entry) -> str:
    from services.calibration_workflow import _signal_identity
    return _signal_identity(entry)[0]


def _most_common(values):
    values = [v for v in values if v]
    return Counter(values).most_common(1)[0][0] if values else ''


def build_recipe(store, *, name: str = '', rt_tolerance: float = 0.3, baseline_mode: str = 'linear',
                 include_calibrations: bool = True) -> Dict[str, Any]:
    """Capture the integration settings, named compound windows and calibrations of the current workspace."""
    if baseline_mode not in _BASELINE_MODES:
        baseline_mode = 'linear'
    rt_tolerance = min(max(_number(rt_tolerance, 0.3), 0.02), 5.0)
    signals: Dict[str, Dict[str, Any]] = {}
    skipped = 0
    for file_id, peaks in store.peak_service.get_all_peaks().items():
        entry = store.get_data_by_id(file_id)
        if not entry or not peaks:
            continue
        key = _signal_key(entry)
        info = signals.setdefault(key, {'settings': [], 'groups': {}})
        info['settings'].append(store.integration_service.get_settings(file_id))
        for peak in peaks:
            if peak.source in _SKIPPED_SOURCES:
                skipped += 1
                continue
            apex = _number(getattr(peak, 'rt', None))
            if apex is None:
                continue
            info['groups'].setdefault(peak.group_id or f'single:{file_id}:{peak.peak_id}', []).append(peak)

    recipe_signals: List[Dict[str, Any]] = []
    for key, info in signals.items():
        settings = {}
        for field in _SETTING_FIELDS:
            settings[field] = Counter(getattr(s, field) for s in info['settings']).most_common(1)[0][0]
        windows = []
        for members in info['groups'].values():
            rts = [float(p.rt) for p in members]
            windows.append({
                'rt': round(statistics.median(rts), 4),
                'rt_min': round(min(rts), 4), 'rt_max': round(max(rts), 4),
                'name': _most_common(p.name for p in members),
                'label': _most_common(p.label for p in members),
                'samples': len(members),
            })
        windows.sort(key=lambda w: w['rt'])
        recipe_signals.append({'signal_key': key, 'settings': settings, 'windows': windows[:MAX_WINDOWS]})
    if not recipe_signals:
        raise RecipeError('Integrate at least one sample first: a recipe records the peaks you integrated.')

    recipe: Dict[str, Any] = {
        'format': RECIPE_FORMAT, 'schema_version': SCHEMA_VERSION, 'name': str(name or '').strip(),
        'created_at': _now(), 'rt_tolerance': rt_tolerance, 'baseline_mode': baseline_mode,
        'signals': recipe_signals,
        'notes': ([f'{skipped} deconvolved peak(s) were not recorded: shoulder splits are not part of recipes yet.']
                  if skipped else []),
    }
    if include_calibrations:
        service = store.calibration_service
        if service.get_all_models():
            recipe['calibrations'] = service.export_calibrations()
    return recipe


def dumps(recipe: Dict[str, Any]) -> str:
    return json.dumps(recipe, indent=2, ensure_ascii=False)


def loads(text: str) -> Dict[str, Any]:
    """Parse and validate a recipe file. Raises ``RecipeError``."""
    if len(text) > MAX_RECIPE_BYTES:
        raise RecipeError('This recipe file is too large.')
    try:
        data = json.loads(text)
    except ValueError as exc:
        raise RecipeError('This is not a GeckoPlotter recipe file.') from exc
    if not isinstance(data, dict) or data.get('format') != RECIPE_FORMAT:
        raise RecipeError('This is not a GeckoPlotter recipe file.')
    if not isinstance(data.get('schema_version'), int) or data['schema_version'] > SCHEMA_VERSION:
        raise RecipeError('This recipe was made by a newer GeckoPlotter and cannot be read.')
    signals = data.get('signals')
    if not isinstance(signals, list) or not signals:
        raise RecipeError('This recipe contains no signals.')
    clean_signals = []
    for item in signals:
        if not isinstance(item, dict) or not isinstance(item.get('signal_key'), str):
            raise RecipeError('This recipe has an unreadable signal.')
        settings = {f: item.get('settings', {}).get(f) for f in _SETTING_FIELDS
                    if isinstance(item.get('settings'), dict) and item['settings'].get(f) is not None}
        windows = []
        for window in (item.get('windows') or [])[:MAX_WINDOWS]:
            rt = _number(window.get('rt')) if isinstance(window, dict) else None
            if rt is None:
                raise RecipeError('This recipe has a compound window without a retention time.')
            windows.append({'rt': rt, 'name': str(window.get('name') or ''), 'label': str(window.get('label') or '')})
        clean_signals.append({'signal_key': item['signal_key'], 'settings': settings, 'windows': windows})
    data = dict(data, signals=clean_signals)
    data['rt_tolerance'] = min(max(_number(data.get('rt_tolerance'), 0.3), 0.02), 5.0)
    data['baseline_mode'] = data.get('baseline_mode') if data.get('baseline_mode') in _BASELINE_MODES else 'linear'
    return data


def _import_new_calibrations(store, payload) -> int:
    """Add the recipe's calibration curves that the workspace does not already have."""
    if not payload:
        return 0
    service = store.calibration_service

    def fingerprint(model):
        coefficients = tuple(round(c, 9) for c in (model.coefficients or ()))
        return (model.analyte_name, model.signal_key, round(_number(model.match_position, 0.0), 4), coefficients)

    existing = {fingerprint(m) for m in service.get_all_models().values()}
    wanted = []
    for item in (payload.get('models') or []):
        probe = type('Probe', (), {})()
        probe.analyte_name = item.get('analyte_name', '')
        probe.signal_key = item.get('signal_key', '')
        probe.match_position = item.get('match_position')
        probe.coefficients = item.get('coefficients')
        if fingerprint(probe) not in existing:
            wanted.append(item)
    if not wanted:
        return 0
    return len(service.import_calibrations(dict(payload, models=wanted)))


def apply_recipe(store, recipe: Dict[str, Any], *, keep_unmatched: bool = False,
                 rt_tolerance: Optional[float] = None) -> Dict[str, Any]:
    """Integrate every loaded signal the recipe covers and name its compounds. Returns a report."""
    recipe = loads(dumps(recipe))        # validates and cleans a recipe built here or read from a file
    tolerance = rt_tolerance if rt_tolerance is not None else recipe['rt_tolerance']
    by_key = {item['signal_key']: item for item in recipe['signals']}
    report: Dict[str, Any] = {'samples': [], 'unmatched_signals': 0, 'calibrations_added': 0}
    from callbacks.baseline_callbacks import get_xy_arrays
    for file_id, entry in list(store.loaded_data.items()):
        key = _signal_key(entry)
        item = by_key.get(key)
        if item is None:
            continue
        time_arr, signal_arr = get_xy_arrays(store, file_id)
        if time_arr is None or len(time_arr) < 3:
            report['unmatched_signals'] += 1
            continue
        settings = {k: v for k, v in item['settings'].items()}
        store.integration_service.update_settings(file_id, **settings)
        processed = store.integration_service.process_signal(file_id, time_arr, signal_arr)
        s = store.integration_service.get_settings(file_id)
        windows = item['windows']

        def detect_at(threshold):
            """Detect with this threshold and pair peaks with windows: closest first, one peak per window."""
            store.peak_service.clear_detected_peaks(file_id)
            found_peaks = store.peak_service.detect_peaks(
                file_id=file_id, signal=processed.corrected, time_axis=processed.time, threshold=threshold,
                slope_threshold=s.slope_threshold, extension_factor=s.extension_factor,
                display_signal=processed.raw, integration_baseline=recipe['baseline_mode'])
            found_peaks = [p for p in found_peaks if p.source == 'detected']   # manual/deconvolved peaks stay as they are
            candidates = sorted((abs(p.rt - w['rt']), pi, wi) for pi, p in enumerate(found_peaks)
                                for wi, w in enumerate(windows) if abs(p.rt - w['rt']) <= tolerance)
            taken_peaks, taken_windows, matched = set(), set(), []
            for _distance, pi, wi in candidates:
                if pi not in taken_peaks and wi not in taken_windows:
                    taken_peaks.add(pi), taken_windows.add(wi), matched.append((pi, wi))
            return found_peaks, matched

        # The recorded threshold is relative to the tallest peak, so a small compound can fall below it in a sample
        # dominated by another one. Lower it step by step until every compound is found, and say so in the report.
        threshold = s.peak_threshold
        detected, matched = detect_at(threshold)
        for lower in LOWER_THRESHOLDS:
            if len(matched) == len(windows) or lower >= threshold:
                continue
            retry, retry_matched = detect_at(lower)
            if len(retry_matched) > len(matched):
                detected, matched, threshold = retry, retry_matched, lower
            if len(matched) == len(windows):
                break
        if threshold != s.peak_threshold:
            detected, matched = detect_at(threshold)           # leave the peaks of the threshold actually used
        used_peaks = {pi for pi, _ in matched}
        used_windows = {wi for _, wi in matched}
        found = []
        for pi, wi in matched:
            window, peak = windows[wi], detected[pi]
            if window['name']:
                peak.name = window['name']
            peak.label = window['label'] or peak.label
            found.append(window['label'] or window['name'] or f"{window['rt']:g} min")
        if not keep_unmatched:
            for pi, peak in enumerate(detected):
                if pi not in used_peaks:
                    store.peak_service.remove_peak(file_id, peak.peak_id)
        missing = [(w['label'] or w['name'] or f"{w['rt']:g} min") for wi, w in enumerate(windows)
                   if wi not in used_windows]
        metadata = entry.get('metadata') or {}
        report['samples'].append({
            'file_id': file_id, 'found': found, 'missing': missing,
            'threshold': threshold, 'threshold_lowered': threshold != s.peak_threshold,
            'sample': metadata.get('parent_bundle_name') or metadata.get('sample_name')
                      or (entry.get('record') or {}).get('name') or file_id})

    store.peak_service.group_peaks_across_samples(file_overlay_map=store.build_file_overlay_map())
    if recipe.get('calibrations'):
        report['calibrations_added'] = _import_new_calibrations(store, recipe['calibrations'])
    from services.calibration_workflow import apply_calibrations
    apply_calibrations(store)
    if not report['samples']:
        raise RecipeError('No loaded signal matches this recipe (it matches by detector, axes and wavelength, '
                          'not by file name).')
    return report


def summarize(report: Dict[str, Any]) -> str:
    """One status line for the interface."""
    samples = report['samples']
    complete = sum(1 for s in samples if not s['missing'])
    text = f"Recipe applied to {len(samples)} signal(s); every compound found in {complete}."
    incomplete = [f"{s['sample']}: no {', '.join(s['missing'])}" for s in samples if s['missing']][:3]
    lowered = sum(1 for s in samples if s.get('threshold_lowered'))
    if lowered:
        text += f" The detection threshold had to be lowered in {lowered} to find every compound."
    if incomplete:
        text += ' Missing: ' + '; '.join(incomplete) + ('…' if len(samples) - complete > 3 else '.')
    if report.get('calibrations_added'):
        text += f" {report['calibrations_added']} calibration(s) added."
    return text
