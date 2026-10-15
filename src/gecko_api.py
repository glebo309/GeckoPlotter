"""GeckoPlotter without a browser: open runs, integrate, extract ion chromatograms, read mass spectra, save a project.

The calls take and return plain values (names, numbers, lists of dicts), so an agent (gecko_mcp.py) or a script can use
them. Samples and channels are named as the app shows them. The work is done by the same services as the GUI, and the
result is saved as a ``.gecko`` project that opens in the app with every peak in place, ready to check and correct.

    ws = Workspace()
    ws.open('/data/HalB substrate scope')               # a folder of run folders: one sample per run
    ws.detect_peaks(channel='UV B')
    ws.eic(633.8, tolerance=0.5)
    ws.mass_spectrum('4', peak='Peak 3')
    ws.save('/data/HalB.gecko')
"""
from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Iterable, List, Optional, Sequence

import numpy as np

log = logging.getLogger(__name__)

# Agilent's own .ms files and ChemStation housekeeping: no reader, and the run's exports carry the same data.
SKIPPED_FILES = {'.ms', '.reg', '.mac', '.m', '.log', '.ini', '.ds_store'}


class GeckoError(ValueError):
    """A request that cannot be done as asked; the message says why and what would work."""


def _files_in(folder: Path) -> List[Path]:
    return sorted(p for p in folder.iterdir()
                  if p.is_file() and not p.name.startswith('.') and p.suffix.lower() not in SKIPPED_FILES)


def _run_names(folders: Sequence[Path]) -> List[str]:
    """Names of run folders without the part they all share (``2026-10-15 11-05-28+02-00-4`` -> ``4``)."""
    names = [f.name for f in folders]
    if len(names) < 2:
        return names
    prefix = os.path.commonprefix(names)
    cut = max(prefix.rfind(c) for c in ' -_+') + 1 if prefix else 0
    stripped = [n[cut:].strip(' -_') for n in names]
    return stripped if all(stripped) and len(set(stripped)) == len(stripped) else names


def _valleys(x, y, rt_start: float, rt_end: float, reach: float = 0.5):
    """``rt_start`` and ``rt_end`` moved outwards down the slope to the nearest minimum of the (lightly smoothed)
    signal, each by at most ``reach`` min: the valleys a chemist would draw the baseline between."""
    order = np.argsort(x)
    x, y = x[order], y[order]
    smooth = np.convolve(y, np.ones(3) / 3, mode='same')
    smooth[0], smooth[-1] = y[0], y[-1]

    def walk(t, step):
        i = int(np.clip(np.searchsorted(x, t), 0, len(x) - 1))
        while 0 <= i + step < len(x) and abs(x[i + step] - t) <= reach and smooth[i + step] <= smooth[i]:
            i += step
        return float(x[i])
    return walk(rt_start, -1), walk(rt_end, +1)


def _ions(mz, intensity, top: int, merge: float = 0.6) -> List[dict]:
    """The ``top`` most intense ions: apices of the spectrum, a weaker apex within ``merge`` m/z of a stronger one
    being the same ion (unit-resolution profile points, isotopes are kept: they are 1 m/z apart)."""
    from scipy.signal import find_peaks
    order = np.argsort(mz, kind='stable')
    x, y = mz[order], intensity[order]
    breaks = np.r_[0, np.flatnonzero(np.diff(x) > 0.15) + 1, x.size]
    apices = []
    for start, end in zip(breaks[:-1], breaks[1:]):
        found, _ = find_peaks(np.r_[-np.inf, y[start:end], -np.inf])
        apices.extend(found + start - 1)
    chosen = []
    for i in sorted(apices, key=lambda k: -y[k]):
        if y[i] < 0.01 * y.max():
            break
        if all(abs(x[i] - x[j]) >= merge for j in chosen):
            chosen.append(i)
            if len(chosen) >= max(1, int(top)):
                break
    return [{'mz': round(float(x[i]), 2), 'relative': round(float(100 * y[i] / y.max()), 1)} for i in chosen]


class Workspace:
    """One GeckoPlotter workspace (the same object the app holds per browser)."""

    def __init__(self, store=None):
        from services.data_store import DataStore
        self.store = store or DataStore()

    # -- opening and saving ---------------------------------------------------------------------------------------

    def open(self, path: str, everything: bool = False) -> dict:
        """Open a file, a run folder, a folder of run folders (one sample per run, named by the folder) or a project
        (.gecko / FAIR package .zip, which replaces the workspace). From Agilent export folders only the full-scan
        spectra and the UV channels are read, unless ``everything``."""
        from services.workspace_loader import load_files
        path = Path(path).expanduser()
        if not path.exists():
            raise GeckoError(f'Not found: {path}')
        if path.is_file() and path.suffix.lower() in ('.gecko', '.zip'):
            from services import session_service
            report = session_service.restore_session(self.store, str(path), search_dirs=[str(path.parent)])
            return {'opened': str(path), 'samples': [s['name'] for s in self.samples()],
                    'warnings': list(report.warnings) + list(report.errors),
                    'missing_files': list(report.missing_files)}
        if path.is_file():
            runs = [(None, [path])]
        else:
            subfolders = sorted(p for p in path.iterdir() if p.is_dir() and _files_in(p))
            if subfolders:
                runs = list(zip(_run_names(subfolders), [_files_in(f) for f in subfolders]))
                loose = _files_in(path)
                if loose:
                    runs.append((None, loose))
            else:
                runs = [(None, _files_in(path))]
        added, failed, bundles = [], [], []
        for name, files in runs:
            result = load_files(self.store, [(f.name, f.read_bytes()) for f in files], skip_duplicate_exports=not everything)
            failed += result.failed
            if name:
                self._name_run(result.bundles, name)
            added += [b.name for b in result.bundles]
            bundles += result.bundles
        if len(runs) > 1:
            label = re.sub(r'^[\d.\-]+[_ ]+', '', path.name) or path.name     # '2026-...-..._HalB scope' -> 'HalB scope'
            self._group_folder(bundles, label)
        return {'added': added, 'not_readable': failed, 'samples': len(self.samples())}

    def _group_folder(self, bundles, folder: str) -> None:
        """Runs opened together from one folder are one group in the file tree and one plot tab named after the
        folder (as if dragged into one group); only the first run is shown, the others are a click on their eye away."""
        from callbacks.viz_callbacks import _get_overlay_group
        from services.channel_visibility import set_sample_visibility
        runs = [b for b in bundles if b.bundle_type.value in ('lcms', 'chromatogram')]
        if len(runs) < 2:
            return
        # Shown first: a sample of its own folder, not one of several blanks/standards sharing a folder.
        shared = getattr(self, '_shared_folder_runs', set())
        runs.sort(key=lambda b: b.bundle_id in shared)
        entry = self.store.get_data_by_id(runs[0].bundle_id) or {}
        natural = _get_overlay_group(entry.get('metadata', {}), entry, file_id=runs[0].bundle_id, dm=self.store,
                                     ignore_override=True)
        key = ('folder', natural[1], folder)
        if not hasattr(self.store, 'group_overrides'):
            self.store.group_overrides = {}
        for i, bundle in enumerate(runs):
            self.store.group_overrides[bundle.bundle_id] = key
            if i:
                set_sample_visibility(self.store, bundle.bundle_id, False)

    def save(self, path: str, project_name: Optional[str] = None) -> str:
        """Save the workspace as a project (.gecko) that opens in GeckoPlotter with all peaks, names and calibrations."""
        from services import session_service
        path = Path(path).expanduser()
        if path.suffix.lower() != '.gecko':
            path = path.with_suffix('.gecko')
        saved = session_service.save_session(self.store, str(path), self._present_results(),
                                             project_name=project_name or path.stem)
        return str(saved)

    def _present_results(self) -> Optional[dict]:
        """Open the project on what was done: the runs holding peaks shown (the others of their folder hidden) and the
        first of them selected, so its peak table and Peak mass match the plot. Returns the app's client state."""
        from services.channel_visibility import set_sample_visibility, show_channel
        with_peaks = []
        for bundle in self._bundles():
            owners = [c.component_id for c in bundle.component_list
                      if self.store.peak_service.get_peaks(c.component_id)]
            if owners:
                with_peaks.append((bundle, owners))
        if not with_peaks:
            return None
        grouped = getattr(self.store, 'group_overrides', {}) or {}
        for bundle in self._bundles():
            if bundle.bundle_id in grouped:
                set_sample_visibility(self.store, bundle.bundle_id, False)
        for bundle, owners in with_peaks:
            set_sample_visibility(self.store, bundle.bundle_id, True)
            for owner in owners:                          # the channel the peaks are on is drawn
                show_channel(self.store, owner)
        return {'active-file': with_peaks[0][1][0]}

    # -- what is loaded -------------------------------------------------------------------------------------------

    def _name_run(self, bundles, name: str) -> None:
        """Name the samples of one run folder after it: the run itself ``4``, its exported traces ``4 · +EIC(...)``.
        A folder holding several runs (blanks, standards) numbers them by their time: ``S 14-45-04``."""
        main = [b for b in bundles if b.bundle_type.value in ('lcms', 'chromatogram')]
        if len(main) > 1:
            self._shared_folder_runs = getattr(self, '_shared_folder_runs', set()) | {b.bundle_id for b in main}
        for bundle in main:
            stamp = re.search(r'\d{2}-\d{2}-\d{2}(?=\+|$)', bundle.name) if len(main) > 1 else None
            self.store.rename_dataset(bundle.bundle_id, f'{name} {stamp.group(0)}' if stamp else name)
        for bundle in bundles:
            if bundle not in main:
                trace = re.search(r'\.dx_(?:MS\d )?(.+?)(?: ESI.*)?(?:\.csv)?$', bundle.name, re.I)
                self.store.rename_dataset(bundle.bundle_id, f'{name} · {trace.group(1) if trace else bundle.name}')

    def _bundles(self):
        return list(self.store._bundles.values())

    def _channel_info(self, bundle, component) -> dict:
        from services.lcms_service import LCMSService
        from callbacks.baseline_callbacks import get_xy_arrays
        entry = self.store.get_data_by_id(component.component_id) or {}
        x, _y = get_xy_arrays(self.store, component.component_id)
        meta = component.metadata or {}
        role = component.role.value
        return {
            'name': bundle.component_display_name(component),
            'kind': ('ms+' if role == 'ms_positive' else 'ms-' if role == 'ms_negative'
                     else 'uv' if meta.get('is_uv_data') or role.startswith('vwd') else role),
            'wavelength_nm': meta.get('wavelength_nm'),
            'points': int(len(x)) if x is not None else 0,
            'rt_range': [round(float(np.nanmin(x)), 3), round(float(np.nanmax(x)), 3)] if x is not None and len(x) else None,
            'mass_spectra': LCMSService._get_spectral_arrays(entry) is not None,
            'file': component.original_filename,
        }

    def samples(self) -> List[dict]:
        """Every loaded sample with its channels (name, kind, wavelength, points, time range, whether it holds mass
        spectra) and how many peaks it has."""
        out = []
        for bundle in self._bundles():
            channels = [self._channel_info(bundle, c) for c in bundle.component_list]
            peaks = sum(len(self.store.peak_service.get_peaks(c.component_id) or []) for c in bundle.component_list)
            out.append({'name': bundle.name, 'type': bundle.bundle_type.value, 'channels': channels, 'peaks': peaks})
        return out

    def _sample(self, name):
        bundles = self._bundles()
        if not bundles:
            raise GeckoError('Nothing is loaded. Open a file or folder first.')
        if name is None:
            if len(bundles) == 1:
                return bundles[0]
            raise GeckoError('Several samples are loaded; name one: ' + ', '.join(b.name for b in bundles))
        key = str(name).strip().lower()
        for hits in ([b for b in bundles if b.name == str(name).strip()], [b for b in bundles if b.name.lower() == key]):
            if len(hits) == 1:
                return hits[0]
        hits = [b for b in bundles if key in b.name.lower()]
        main = [b for b in hits if b.bundle_type.value in ('lcms', 'chromatogram')]
        if len(hits) == 1 or len(main) == 1:
            return (main or hits)[0]
        if hits:
            raise GeckoError(f'"{name}" matches several samples: ' + ', '.join(b.name for b in hits))
        raise GeckoError(f'No sample "{name}". Loaded: ' + ', '.join(b.name for b in bundles))

    def _samples(self, names) -> list:
        from services.data_store import BundleType
        if names is None:
            return [b for b in self._bundles() if b.bundle_type in (BundleType.LCMS, BundleType.CHROMATOGRAM)] \
                or self._bundles()
        if isinstance(names, str):
            names = [names]
        return [self._sample(n) for n in names]

    def _channel(self, bundle, channel):
        """The component of ``bundle`` called ``channel`` ('+TIC', 'UV 220', 'Ch B', ...); the shown one if None."""
        from services.channel_visibility import visible_component_id
        components = bundle.component_list
        if channel is None:
            shown = visible_component_id(self.store, bundle)
            return next((c for c in components if c.component_id == shown), bundle.primary or components[0])
        key = str(channel).strip().lower()
        named = [(bundle.component_display_name(c), c) for c in components]
        exact = [c for n, c in named if n.lower() == key]
        if exact:
            return exact[0]
        hits = [(n, c) for n, c in named if key in n.lower()]
        preferred = [(n, c) for n, c in hits if '(export)' not in n.lower()] or hits
        if len(preferred) == 1:
            return preferred[0][1]
        if not hits:
            raise GeckoError(f'{bundle.name} has no channel "{channel}". Channels: ' + ', '.join(n for n, _ in named))
        raise GeckoError(f'"{channel}" matches several channels of {bundle.name}: ' + ', '.join(n for n, _ in preferred))

    def _xy(self, component_id):
        from callbacks.baseline_callbacks import get_xy_arrays
        x, y = get_xy_arrays(self.store, component_id)
        if x is None or y is None or len(x) < 3:
            raise GeckoError('This channel has no plottable signal.')
        return np.asarray(x, dtype=float), np.asarray(y, dtype=float)

    # -- peaks ----------------------------------------------------------------------------------------------------

    def _peak_rows(self, bundle, component) -> List[dict]:
        peaks = sorted(self.store.peak_service.get_peaks(component.component_id) or [], key=lambda p: p.rt)
        total = sum(max(float(p.area or 0), 0) for p in peaks)
        return [{'sample': bundle.name, 'channel': bundle.component_display_name(component), 'name': p.name,
                 'label': p.label or None, 'rt': round(p.rt, 4), 'rt_start': round(p.rt_start, 4),
                 'rt_end': round(p.rt_end, 4), 'area': float(f'{p.area:.6g}'), 'height': float(f'{p.height:.6g}'),
                 'area_percent': round(100 * p.area / total, 2) if total > 0 else None,
                 'concentration': p.concentration, 'source': p.source, 'peak_id': p.peak_id} for p in peaks]

    def detect_peaks(self, samples=None, channel=None, sensitivity: float = 50) -> List[dict]:
        """Detect peaks as the Detect button does (sensitivity 0-100, minimum height 100-sensitivity % of the tallest).
        Replaces earlier detected peaks of that channel; manual ones stay. Returns the peak table."""
        from services.detection import detect
        rows = []
        for bundle in self._samples(samples):
            component = self._channel(bundle, channel)
            x, y = self._xy(component.component_id)
            detect(self.store, component.component_id, x, y, sensitivity)
            rows += self._peak_rows(bundle, component)
        return rows

    def integrate(self, rt_start: float, rt_end: float, samples=None, channel=None, name: Optional[str] = None,
                  snap_to_valleys: bool = True) -> List[dict]:
        """Integrate a peak with a straight baseline drawn on the curve, as in the plot. Each end walks down the slope
        to the nearest valley (at most 0.5 min), so a window that starts on the peak's flank still takes the whole
        peak; ``snap_to_valleys=False`` keeps the given times. Returns the new peaks."""
        from callbacks.baseline_callbacks import _area_with_constraints
        if rt_end <= rt_start:
            raise GeckoError('rt_end must be after rt_start.')
        out = []
        for bundle in self._samples(samples):
            component = self._channel(bundle, channel)
            x, y = self._xy(component.component_id)
            times = _valleys(x, y, rt_start, rt_end) if snap_to_valleys else (rt_start, rt_end)
            ends = [(float(t), float(np.interp(t, x, y))) for t in times]
            result, q1, q2 = _area_with_constraints(x, y, *ends)
            if not result:
                out.append({'sample': bundle.name, 'channel': bundle.component_display_name(component),
                            'error': 'Nothing above the baseline between these times.'})
                continue
            self.store.peak_service.save_undo()
            peak = self.store.peak_service.add_baseline_peak(
                component.component_id, area=result['area'], height=result['height'], apex_x=result['apex_x'],
                poly_x=result['poly_x'], poly_y=result['poly_y'], p_line=ends, q1=q1, q2=q2)
            self.store.peak_service.group_peaks_across_samples(file_overlay_map=self.store.build_file_overlay_map())
            if name:                                    # a custom name, kept by the group numbering
                self.store.peak_service.rename_peak(component.component_id, peak.peak_id, name)
            out += [r for r in self._peak_rows(bundle, component) if r['peak_id'] == peak.peak_id]
        return out

    def peaks(self, samples=None) -> List[dict]:
        """The peak table of every channel that has peaks."""
        rows = []
        for bundle in self._samples(samples):
            for component in bundle.component_list:
                rows += self._peak_rows(bundle, component)
        return rows

    def rename_peak(self, sample, peak: str, new_name: str) -> List[dict]:
        """Rename a peak (by name or id); the name spreads to the same peak in every sample, as in the app."""
        bundle = self._sample(sample)
        component, found = self._find_peak(bundle, peak)
        self.store.peak_service.rename_peak(component.component_id, found.peak_id, new_name)
        return self.peaks()

    def _find_peak(self, bundle, peak):
        key = str(peak).strip().lower()
        for component in bundle.component_list:
            for p in self.store.peak_service.get_peaks(component.component_id) or []:
                if p.peak_id == peak or (p.name or '').lower() == key or (p.label or '').lower() == key:
                    return component, p
        raise GeckoError(f'{bundle.name} has no peak "{peak}".')

    # -- mass spectra ---------------------------------------------------------------------------------------------

    def _ms_entry(self, bundle, polarity: str):
        from services.data_store import ComponentRole
        from services.lcms_service import LCMSService
        role = ComponentRole.MS_NEGATIVE if str(polarity).startswith(('-', 'n')) else ComponentRole.MS_POSITIVE
        for component in bundle.component_list:
            if component.role == role:
                entry = self.store.get_data_by_id(component.component_id)
                if entry and LCMSService._get_spectral_arrays(entry) is not None:
                    return component, entry
        raise GeckoError(f'{bundle.name} has no {"negative" if role == ComponentRole.MS_NEGATIVE else "positive"}-mode '
                         'mass spectra (only exported TIC traces or no MS at all).')

    def eic(self, mz: float, tolerance: float = 0.5, samples=None, polarity: str = '+',
            rt_start: Optional[float] = None, rt_end: Optional[float] = None) -> List[dict]:
        """Extracted-ion chromatogram of m/z ± tolerance in each sample with mass spectra.

        The peak is the tallest point (inside ``rt_start``-``rt_end`` if given); its area is integrated from where
        the trace falls to 5 % of that height on each side, or over the given window, with a straight baseline.
        The EIC also appears in the app's EIC view of that sample."""
        from services.lcms_service import LCMSService
        from callbacks.baseline_callbacks import _area_with_constraints
        service = LCMSService()
        rows = []
        for bundle in self._samples(samples):
            try:
                component, entry = self._ms_entry(bundle, polarity)
            except GeckoError as exc:
                rows.append({'sample': bundle.name, 'error': str(exc)})
                continue
            t, inten = service.extract_eic(entry, float(mz), float(tolerance))
            t, inten = np.asarray(t, dtype=float), np.asarray(inten, dtype=float)
            if hasattr(self.store, 'add_lcms_eic_overlay'):
                self.store.add_lcms_eic_overlay(component.component_id, {
                    'mz': float(mz), 'tolerance': float(tolerance), 'time': t, 'intensity': inten})
            window = np.ones_like(t, dtype=bool)
            if rt_start is not None:
                window &= t >= rt_start
            if rt_end is not None:
                window &= t <= rt_end
            if not window.any() or inten[window].max() <= 0:
                rows.append({'sample': bundle.name, 'mz': mz, 'apex_rt': None, 'height': 0.0, 'area': 0.0})
                continue
            apex = int(np.flatnonzero(window)[np.argmax(inten[window])])
            if rt_start is not None and rt_end is not None:
                lo, hi = float(rt_start), float(rt_end)
            else:
                floor = 0.05 * inten[apex]
                i = apex
                while i > 0 and inten[i - 1] > floor and inten[i - 1] <= inten[i] * 1.5:
                    i -= 1
                j = apex
                while j < len(t) - 1 and inten[j + 1] > floor and inten[j + 1] <= inten[j] * 1.5:
                    j += 1
                lo, hi = float(t[max(i - 1, 0)]), float(t[min(j + 1, len(t) - 1)])
            ends = [(lo, float(np.interp(lo, t, inten))), (hi, float(np.interp(hi, t, inten)))]
            result, _q1, _q2 = _area_with_constraints(t, inten, *ends)
            rows.append({'sample': bundle.name, 'mz': mz, 'tolerance': tolerance, 'polarity': polarity,
                         'apex_rt': round(float(t[apex]), 4), 'height': float(f'{inten[apex]:.6g}'),
                         'rt_start': round(lo, 4), 'rt_end': round(hi, 4),
                         'area': float(f'{result["area"]:.6g}') if result else 0.0})
        return rows

    def mass_spectrum(self, sample, rt: Optional[float] = None, rt_start: Optional[float] = None,
                      rt_end: Optional[float] = None, peak: Optional[str] = None, polarity: str = '+',
                      top: int = 10) -> dict:
        """The mass spectrum at one time (the nearest scan), averaged over a window, or averaged over a peak's
        integration window as the app's Peak mass view does. Returns the ``top`` most intense m/z with intensities
        relative to the largest (%)."""
        from services.lcms_service import LCMSService
        service = LCMSService()
        bundle = self._sample(sample)
        _component, entry = self._ms_entry(bundle, polarity)
        what = None
        if peak is not None:
            _c, found = self._find_peak(bundle, peak)
            rt_start, rt_end = found.rt_start, found.rt_end
            what = f'average over {found.name}, {rt_start:.2f}-{rt_end:.2f} min'
        if rt_start is not None and rt_end is not None:
            mz, inten = service.get_averaged_spectrum(entry, float(rt_start), float(rt_end))
            what = what or f'average {rt_start:.2f}-{rt_end:.2f} min'
        elif rt is not None:
            mz, inten = service.get_mass_spectrum_at_time(entry, float(rt))
            what = f'scan nearest {rt:.2f} min'
        else:
            raise GeckoError('Give rt, rt_start and rt_end, or peak.')
        mz, inten = np.asarray(mz, dtype=float), np.asarray(inten, dtype=float)
        if not mz.size or inten.max() <= 0:
            return {'sample': bundle.name, 'spectrum': what, 'peaks': []}
        return {'sample': bundle.name, 'spectrum': what, 'polarity': polarity, 'peaks': _ions(mz, inten, top)}

    # -- figures --------------------------------------------------------------------------------------------------

    def figure(self, path: str, samples=None, channel=None, rt_start: Optional[float] = None,
               rt_end: Optional[float] = None, eic_mz: Optional[float] = None, tolerance: float = 0.5,
               polarity: str = '+', width: int = 1100, height: int = 500) -> str:
        """Draw the samples' channel (or the EIC of ``eic_mz``) overlaid, integrated peaks shaded and named, to a PNG."""
        import plotly.graph_objects as go
        from services.lcms_service import LCMSService
        figure = go.Figure()
        colours = ['#0072B2', '#D55E00', '#009E73', '#CC79A7', '#E69F00', '#56B4E9', '#F0E442', '#000000']
        for k, bundle in enumerate(self._samples(samples)):
            colour = colours[k % len(colours)]
            if eic_mz is not None:
                try:
                    _component, entry = self._ms_entry(bundle, polarity)
                except GeckoError:
                    continue
                x, y = LCMSService().extract_eic(entry, float(eic_mz), float(tolerance))
                label, peaks = f'{bundle.name} · EIC {eic_mz:g}', []
            else:
                component = self._channel(bundle, channel)
                x, y = self._xy(component.component_id)
                label = f'{bundle.name} · {bundle.component_display_name(component)}'
                peaks = self.store.peak_service.get_peaks(component.component_id) or []
            x, y = np.asarray(x, dtype=float), np.asarray(y, dtype=float)
            figure.add_trace(go.Scatter(x=x, y=y, mode='lines', name=label, line=dict(color=colour, width=1.4)))
            for p in peaks:
                if p.poly_x and p.poly_y:
                    px, py = p.poly_x, p.poly_y
                else:
                    inside = (x >= p.rt_start) & (x <= p.rt_end)
                    px, py = list(x[inside]) + list(x[inside][::-1]), list(y[inside]) + [0.0] * int(inside.sum())
                figure.add_trace(go.Scatter(x=px, y=py, fill='toself', mode='none', fillcolor=colour, opacity=.25,
                                            showlegend=False, hoverinfo='skip'))
                figure.add_annotation(x=p.rt, y=float(np.interp(p.rt, x, y)), text=p.label or p.name,
                                      showarrow=False, yshift=10, font=dict(size=11))
        if not figure.data:
            raise GeckoError('Nothing to draw for these samples.')
        figure.update_layout(template='simple_white', width=width, height=height, margin=dict(l=70, r=20, t=30, b=50),
                             xaxis_title='Time (min)', yaxis_title='Ion count' if eic_mz is not None else None,
                             legend=dict(x=1, xanchor='right', y=1))
        if rt_start is not None or rt_end is not None:
            figure.update_xaxes(range=[rt_start if rt_start is not None else float(np.nanmin(x)),
                                       rt_end if rt_end is not None else float(np.nanmax(x))])
        path = str(Path(path).expanduser().with_suffix('.png'))
        figure.write_image(path, scale=2)
        return path
