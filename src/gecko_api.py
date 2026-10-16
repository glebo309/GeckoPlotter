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


def _names(bundles, limit: int = 6) -> str:
    names = [b.name for b in bundles]
    return ', '.join(names[:limit]) + (f' and {len(names) - limit} more' if len(names) > limit else '')


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


def _baseline_noise(x, y, rt_start: float, rt_end: float) -> float:
    """Robust noise of this channel, including slow baseline fluctuations in smoothed detector traces.
    Use first differences and the flanks (two window widths on either side, excluding the peak). Start the trend
    at the flank halves' medians, then refit without outliers so neighbouring narrow peaks do not set the slope."""
    keep = np.isfinite(x) & np.isfinite(y)
    x, y = x[keep], y[keep]
    order = np.argsort(x)
    x, y = x[order], y[order]

    def mad(values):
        return float(np.median(np.abs(values - np.median(values))) / 0.67448975) if len(values) else 0.0

    noise = mad(np.diff(y)) / np.sqrt(2)
    width = rt_end - rt_start
    flank = ((x >= rt_start - 2 * width) & (x < rt_start)) | ((x > rt_end) & (x <= rt_end + 2 * width))
    bx, by = x[flank], y[flank]
    if len(bx) >= 6:
        half = len(bx) // 2
        x1, x2 = np.median(bx[:half]), np.median(bx[half:])
        y1, y2 = np.median(by[:half]), np.median(by[half:])
        if x2 > x1:
            residual = by - (y1 + (bx - x1) * (y2 - y1) / (x2 - x1))
            background = np.abs(residual - np.median(residual)) <= 3 * mad(residual)
            if np.count_nonzero(background) >= 6 and np.ptp(bx[background]) > 0:
                residual = by - np.polyval(np.polyfit(bx[background], by[background], 1), bx)
            noise = max(noise, mad(residual))
    return float(noise)


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
        self.agent = None           # {'client', 'version', 'model'} of the MCP agent at work (gecko_mcp sets it)

    def _record(self, action: str) -> None:
        """Note a change in the analysis history (what the FAIR package and its report list), with the agent."""
        from services.research_package import record_analysis_state
        record_analysis_state(self.store, triggers=[action], agent=self.agent)

    # -- opening and saving ---------------------------------------------------------------------------------------

    def open(self, path: str, everything: bool = False) -> dict:
        """Open a file, a run folder, a folder of run folders (one sample per run, named by the folder) or a project
        (.gecko / FAIR package .zip, which replaces the workspace). From Agilent export folders only the full-scan
        spectra and the UV channels are read, unless ``everything``. Projects inside a data folder are listed
        separately under ``projects``; open the project file itself to restore it."""
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
        projects = []

        def data_files(folder):
            files = _files_in(folder)
            projects.extend(str(f) for f in files if f.suffix.lower() in ('.gecko', '.zip'))
            return [f for f in files if f.suffix.lower() not in ('.gecko', '.zip')]

        if path.is_file():
            runs = [(None, [path])]
        else:
            subfolders = {p: files for p in sorted(path.iterdir()) if p.is_dir() and (files := data_files(p))}
            loose = data_files(path)
            if subfolders:
                runs = list(zip(_run_names(list(subfolders)), subfolders.values()))
                if loose:
                    runs.append((None, loose))
            else:
                runs = [(None, loose)] if loose else []
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
        self._record(f'Opened {path.name}: {len(added)} sample(s)')
        report = {'added': added, 'not_readable': failed, 'samples': len(self.samples()), 'projects': sorted(projects)}
        if projects:
            report['note'] = 'Project files were left out of the data import; open_data(<project path>) opens one instead.'
        return report

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
        self._refresh_concentrations()
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
            'kind': ('eic' if meta.get('eic_extracted') else 'ms+' if role == 'ms_positive' else 'ms-' if role == 'ms_negative'
                     else 'uv' if meta.get('is_uv_data') or role.startswith('vwd') else role),
            'wavelength_nm': meta.get('wavelength_nm'),
            'points': int(len(x)) if x is not None else 0,
            'rt_range': [round(float(np.nanmin(x)), 3), round(float(np.nanmax(x)), 3)] if x is not None and len(x) else None,
            'mass_spectra': LCMSService._get_spectral_arrays(entry) is not None,
            'pda': isinstance(meta.get('pda'), dict),
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
        wanted = re.fullmatch(r'(?:uv\s*|pda\s*)?(\d+(?:\.\d+)?)\s*(?:nm)?', key)
        if not hits and wanted:                   # '200 nm' is the 201 nm channel the detector's pixel grid gives
            from services.channel_visibility import channel_identity
            near = []
            for n, c in named:
                identity = channel_identity(c)
                if identity and identity[0].startswith('uv:'):
                    gap = abs(float(identity[0][3:]) - float(wanted.group(1)))
                    if gap <= 2:
                        near.append((gap, n, c))
            if near:
                return min(near, key=lambda item: item[0])[2]
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
        self._record(f'Detected peaks (sensitivity {sensitivity:g}) on {channel or "the shown channel"} in '
                     f'{_names(self._samples(samples))}')
        return rows

    def integrate(self, rt_start: float, rt_end: float, samples=None, channel=None, name: Optional[str] = None,
                  snap_to_valleys: bool = True) -> List[dict]:
        """Integrate a peak with a straight baseline drawn on the curve, as in the plot. Each end walks down the slope
        to the nearest valley (at most 0.5 min), so a window that starts on the peak's flank still takes the whole
        peak; ``snap_to_valleys=False`` keeps the given times. Heights below three times the channel's robust
        baseline noise are refused. Returns the new peaks or a per-sample error."""
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
            if result['height'] < 3 * _baseline_noise(x, y, *times):
                out.append({'sample': bundle.name, 'channel': bundle.component_display_name(component),
                            'error': f'No peak above the noise between {rt_start:g} and {rt_end:g} min'})
                continue
            self.store.peak_service.save_undo()
            peak = self.store.peak_service.add_baseline_peak(
                component.component_id, area=result['area'], height=result['height'], apex_x=result['apex_x'],
                poly_x=result['poly_x'], poly_y=result['poly_y'], p_line=ends, q1=q1, q2=q2)
            self.store.peak_service.group_peaks_across_samples(file_overlay_map=self.store.build_file_overlay_map())
            if name:                                    # a custom name, kept by the group numbering
                self.store.peak_service.rename_peak(component.component_id, peak.peak_id, name)
            out += [r for r in self._peak_rows(bundle, component) if r['peak_id'] == peak.peak_id]
        self._record(f'Integrated {rt_start:g}-{rt_end:g} min' + (f' as {name}' if name else '') +
                     f' on {channel or "the shown channel"} in {_names(self._samples(samples))}')
        return out

    def deconvolve(self, rt_start: float, rt_end: float, samples=None, channel=None,
                   n_peaks: Optional[int] = None, names=None, centers=None, prominence: float = .05,
                   center_tolerance: Optional[float] = None) -> List[dict]:
        """Resolve a shoulder or overlapping peaks with the GUI's composite EMG model in the exact window.
        Fits a linear baseline with the components; components may not tail more than the main peak.
        Auto-detects centers unless supplied (RTs in minutes); n_peaks overrides the detected count and seeds weak
        shoulders from curvature. Optional center_tolerance bounds fitted apexes around explicit markers.
        names labels components in apex RT order. Replaces peaks whose stored RT lies in the window; the whole
        call is one undo step. Returns components (apex_rt is the fitted maximum, rt the GUI's stored EMG center),
        R², residual RMSE, reduced chi-square, FWHM and warnings for poor, collapsed or non-peak-shaped fits.
        Area % is relative to the fitted window. Check with figure(); a high R² alone does not establish identity."""
        from services.deconvolution_service import DeconvolutionService, _emg_mode_offset
        if not np.isfinite([rt_start, rt_end]).all() or rt_end <= rt_start:
            raise GeckoError('rt_end must be after rt_start; both must be finite.')
        if n_peaks is not None and (isinstance(n_peaks, bool) or not isinstance(n_peaks, int) or n_peaks < 1):
            raise GeckoError('n_peaks must be a positive integer.')
        if not np.isfinite(prominence) or not 0 < prominence <= 1:
            raise GeckoError('prominence must be between 0 (exclusive) and 1.')
        if centers is not None:
            centers = sorted(float(c) for c in centers)
            if (not centers or not np.isfinite(centers).all() or len(set(centers)) != len(centers)
                    or centers[0] < rt_start or centers[-1] > rt_end):
                raise GeckoError('centers must be distinct finite RTs inside the window.')
            if n_peaks is not None and len(centers) != n_peaks:
                raise GeckoError('centers must contain n_peaks RTs.')
        if center_tolerance is not None and (centers is None or not np.isfinite(center_tolerance)
                                             or center_tolerance <= 0):
            raise GeckoError('center_tolerance must be positive and requires explicit centers.')
        count = len(centers) if centers is not None else n_peaks
        if names is not None and (isinstance(names, str) or not names or any(not str(n).strip() for n in names)
                                  or (count is not None and len(names) != count)):
            raise GeckoError('names must contain one nonempty name per component in RT order.')
        bundles = self._samples(samples)
        targets = [(b, self._channel(b, channel)) for b in bundles]
        svc, ps = DeconvolutionService(), self.store.peak_service
        out, added = [], []
        for bundle, component in targets:
            fid = component.component_id
            row = {'sample': bundle.name, 'channel': bundle.component_display_name(component)}
            out.append(row)
            try:
                x, y = self._xy(fid)
                inside = (x >= rt_start) & (x <= rt_end)
                x, y = x[inside], y[inside]
                if len(x) < max(10, 4 * (count or 2) + 1) or not np.isfinite(y).all():
                    raise GeckoError('Region too narrow or contains nonfinite signal; widen the window.')
                baseline = np.interp(x, [x[0], x[-1]], [y[0], y[-1]])
                signal = y - baseline
                seeds = ([(c, float(np.interp(c, x, signal))) for c in centers] if centers is not None else
                         svc.seed_centers(x, signal, n_peaks, prominence) if n_peaks is not None else
                         svc.auto_detect_centers(x, signal, prominence=prominence))
                if not seeds or (count is None and len(seeds) < 2):
                    raise GeckoError('No second maximum or shoulder found. Widen the window or supply n_peaks/centers.')
                if names is not None and len(names) != len(seeds):
                    raise GeckoError(f'Detected {len(seeds)} components but received {len(names)} names.')
                main = int(np.argmax([h for _, h in seeds]))
                options = {'baseline': baseline, 'fit_baseline': True, 'tail_reference': main}
                if center_tolerance is not None:
                    options.update(apex_mode=True,
                                   center_bounds=[(c - center_tolerance, c + center_tolerance) for c in centers])
                elif len(seeds) > 1:
                    gaps = [min(abs(c - other) for other, _ in seeds if other != c) for c, _ in seeds]
                    reach = .25 if centers is None else .5
                    options.update(apex_mode=True, center_bounds=[(c - reach * gap, c + reach * gap)
                                                                 for (c, _), gap in zip(seeds, gaps)])
                result = svc.fit_peaks(x, y, seeds, **options)
                if result is None or not np.isfinite(result.r_squared):
                    raise GeckoError('Fit failed; try a wider window or explicit centers.')
                apex = lambda c: c.center + _emg_mode_offset(c.sigma, c.gamma)
                bounds = options.get('center_bounds') or [(x[0], x[-1])] * len(seeds)
                at_bound = any(min(abs(apex(c) - max(lo, x[0])), abs(apex(c) - min(hi, x[-1])))
                               < .01 * (hi - lo) for c, (lo, hi) in zip(result.components, bounds))
                widths = {id(c): svc._curve_apex_and_fwhm(x, c.curve)[1] for c in result.components}
                main_width = widths[id(result.components[main])]
                result.components.sort(key=apex)
                for i, comp in enumerate(result.components):
                    comp.index = i
                fitted = svc.result_to_peaks(result, fid, float(np.mean([c.center for c in result.components])))
            except Exception as exc:
                row['error'] = str(exc)
                continue
            if not added:
                ps.save_undo()
            for old in list(ps.get_peaks(fid) or []):
                if rt_start <= old.rt <= rt_end:
                    ps.remove_peak(fid, old.peak_id)
            stored = []
            for i, p in enumerate(fitted):
                peak = ps.add_baseline_peak(fid, area=p.area, height=p.height, apex_x=p.rt,
                    poly_x=p.poly_x, poly_y=p.poly_y, p_line=p.p_line, q1=p.q1, q2=p.q2,
                    source='deconvolved', deconv_group=p.deconv_group, fit_params=p.fit_params)
                if names is not None:
                    peak.name = peak.label = str(names[i])
                stored.append(peak)
            total = sum(p.area for p in stored)
            warnings = []
            if result.r_squared < .99:
                warnings.append('Poor fit (R² < 0.99); check figure() and adjust the window or centers.')
            if total <= 0 or any(p.area < .005 * total for p in stored):
                warnings.append('A component has collapsed below 0.5% of fitted area; check the component count.')
            widest = max(widths.values())
            for peak, comp in zip(stored, result.components):
                if widths[id(comp)] < widest / 3:
                    warnings.append(f'{peak.label or peak.name}: FWHM {widths[id(comp)]:.4g} min is below 1/3 of '
                                    f'the widest component ({widest:.4g} min); too narrow for a chromatographic '
                                    'peak. Check the component count.')
            if at_bound:
                warnings.append('A fitted apex is at its marker bound; the component area may depend on the constraint.')
            if any(widths[id(c)] > 2 * main_width or max(c.curve[0], c.curve[-1]) > .1 * c.curve.max()
                   for c in result.components):
                warnings.append('A component is not peak-shaped: broad relative to the main peak or truncated at an edge.')
            row.update(r_squared=result.r_squared, redchi=result.redchi,
                       residual_rmse=float(np.sqrt(np.mean(result.residuals ** 2))), warnings=warnings)
            added.append((row, bundle, component, stored, [(apex(c), widths[id(c)]) for c in result.components]))
        if added:
            ps.group_peaks_across_samples(file_overlay_map=self.store.build_file_overlay_map())
            for row, bundle, component, stored, apexes in added:
                rows = {r['peak_id']: r for r in self._peak_rows(bundle, component)}
                total = sum(p.area for p in stored)
                row['components'] = [dict(rows[p.peak_id], apex_rt=float(rt), fwhm=float(width),
                    area_percent=100 * p.area / total if total > 0 else None) for p, (rt, width) in zip(stored, apexes)]
            self._record(f'Deconvolved {rt_start:g}-{rt_end:g} min on {channel or "the shown channel"} in '
                         f'{_names(bundles)} (fitted linear baseline, tailing bounded to main peak; '
                         f'n_peaks={n_peaks}, centers={centers}, '
                         f'center_tolerance={center_tolerance}, prominence={prominence:g})')
        return out

    def peaks(self, samples=None) -> List[dict]:
        """The peak table of every channel that has peaks."""
        self._refresh_concentrations()
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
        self._record(f'Renamed peak {found.name} to {new_name}')
        return self.peaks()

    def remove_peak(self, sample, peak: str) -> List[dict]:
        """Delete a peak by name or id, as in the app; sample=None removes it from every sample that has it.
        The whole deletion is one undo step. Returns the remaining peak table."""
        targets = []
        for bundle in self._bundles() if sample is None else [self._sample(sample)]:
            try:
                component, found = self._find_peak(bundle, peak)
            except GeckoError:
                if sample is not None:
                    raise
                continue
            targets.append((component.component_id, found.peak_id))
        if not targets:
            raise GeckoError(f'No peak "{peak}" in the loaded samples.')
        self.store.peak_service.delete_peaks(targets, file_overlay_map=self.store.build_file_overlay_map())
        self._record(f'Removed peak {peak} from {sample if sample is not None else "every sample"}')
        return self.peaks()

    def _find_peak(self, bundle, peak):
        key = str(peak).strip().lower()
        for component in bundle.component_list:
            for p in self.store.peak_service.get_peaks(component.component_id) or []:
                if p.peak_id == peak or (p.name or '').lower() == key or (p.label or '').lower() == key:
                    return component, p
        raise GeckoError(f'{bundle.name} has no peak "{peak}".')

    # -- calibration ----------------------------------------------------------------------------------------------

    def _refresh_concentrations(self) -> None:
        from services.calibration_workflow import apply_calibrations
        apply_calibrations(self.store)

    def calibrate(self, peak: str, standards: dict, units: str = 'mM', fit: str = 'linear',
                  through_zero: bool = False, channel=None, rt_tolerance: float = 0.2,
                  name: Optional[str] = None) -> dict:
        """Fit a calibration of ``peak`` from standard samples ({sample: concentration}) as the app's calibration editor
        does, and quantify that peak in every other sample on the same channel within ± ``rt_tolerance``.
        Prefer the calibrated peak's name; only without that name, use the nearest RT (equal distances are ambiguous).
        Other peaks in standard samples are not unknowns. Recalibrating under the same name replaces the curve.
        Returns the fit, standards back-calculated (with a note when unavailable), concentrations and warnings."""
        from services.calibration_workflow import add_peak_rows, apply_calibrations, fit_calibration_form, \
            peak_candidates
        if fit not in ('linear', 'quadratic', 'power'):
            raise GeckoError('fit must be linear, quadratic or power.')
        warnings, ids, concentrations, group = [], [], {}, None
        for sample_name, concentration in (standards or {}).items():
            bundle = self._sample(sample_name)
            components = [self._channel(bundle, channel)] if channel is not None else bundle.component_list
            found = None
            for component in components:
                for p in self.store.peak_service.get_peaks(component.component_id) or []:
                    if peak in (p.name, p.label, p.peak_id) and (group is None or p.group_id == group or found is None):
                        found = (component, p)
                        if group is None or p.group_id == group:
                            break
                if found:
                    break
            if not found:
                warnings.append(f'{bundle.name} has no peak "{peak}": left out of the calibration.')
                continue
            group = group or found[1].group_id
            key = f'{self.store.peak_owner_id(found[0].component_id)}:{found[1].peak_id}'   # as the editor files it
            ids.append(key)
            concentrations[key] = float(concentration)
        if len(ids) < 2:
            raise GeckoError(f'Need at least two standards with the peak "{peak}"; found {len(ids)}.')
        try:
            rows = add_peak_rows([], ids, peak_candidates(self.store), 'area')
        except ValueError as exc:
            raise GeckoError(f'{exc} Give channel= to choose one.') from None
        for row in rows:
            row['concentration'] = concentrations[row['id']]
        label = (name or peak).strip()
        service = self.store.calibration_service
        existing = next((m.model_id for m in service.get_all_models().values() if m.analyte_name == label), None)
        position = sum(r['position'] for r in rows) / len(rows)
        for other in service.get_all_models().values():
            if other.model_id != existing and other.signal_key == rows[0]['signal_key'] and \
                    other.match_position is not None and abs(other.match_position - position) <= rt_tolerance + \
                    (other.match_tolerance or 0):
                raise GeckoError(f'The calibration "{other.analyte_name}" already covers this peak on this channel; '
                                 'remove it first (remove_calibration).')
        try:
            model = fit_calibration_form(service, existing, rows, range(len(rows)), name=label, units=units,
                                         fit_type=fit, force_zero=through_zero, response_type='area',
                                         position=position, tolerance=rt_tolerance, auto_apply=True)
        except ValueError as exc:
            raise GeckoError(str(exc)) from None
        results = apply_calibrations(self.store)
        coefficients = list(model.coefficients or [])
        names = {'linear': ('slope', 'intercept'), 'quadratic': ('a', 'b', 'c'), 'power': ('a', 'b')}[fit]
        if model.r_squared is not None and model.r_squared < 0.99:
            warnings.append(f'R² is {model.r_squared:.4f}: check the standards.')
        standard_rows = []
        for point in model.standards:
            back = None
            try:
                back = service.predict_concentration(model.model_id, point.area)
            except (ValueError, TypeError, ArithmeticError):
                pass
            error = 100 * (back - point.concentration) / point.concentration if back is not None and \
                point.concentration else None
            if error is not None and abs(error) > 15:
                warnings.append(f'{point.sample_name} back-calculates {error:+.0f} % off.')
            standard_rows.append({'sample': point.sample_name.split(' / ')[0], 'concentration': point.concentration,
                                  'area': point.area, 'back_calculated': back,
                                  'error_percent': round(error, 2) if error is not None else None,
                                  'used': point.included})
            if back is None:
                below_intercept = fit in ('linear', 'quadratic') and point.area < coefficients[-1]
                note = 'area below the intercept' if below_intercept else 'no nonnegative concentration could be calculated'
                standard_rows[-1]['note'] = note
                warnings.append(f'{point.sample_name}: {note}.')
        standard_ids = set(ids)
        candidates = {c['id']: c for c in peak_candidates(self.store)}
        quantified = []
        for key, result in results.items():
            if result.get('model_id') != model.model_id or key in standard_ids:
                continue
            c = candidates[key]
            quantified.append({'sample': c['sample'], 'peak': c['peak_name'], 'rt': c['position'],
                               'area': c['response'], 'concentration': result['concentration'],
                               'status': result['status']})
            if result['status'] != 'Calibrated':
                warnings.append(f"{c['sample']}: {result['status']}.")
        matched = {q['sample'] for q in quantified} | {r['sample_name'].split(' / ')[0] for r in rows}
        for c in candidates.values():
            if c['peak_name'] == label or c['peak_name'] == peak:
                same = True
            else:
                same = any(x.peak_id == c['peak_id'] and group and x.group_id == group
                           for x in self.store.peak_service.get_peaks(c['file_id']))
            if same and c['sample'] not in matched:
                warnings.append(f"{c['sample']}: its {c['peak_name']} at {c['position']:.2f} min is outside the "
                                f"window {position - rt_tolerance:.2f}-{position + rt_tolerance:.2f} min; "
                                'a larger rt_tolerance would include it.')
        concs = [r['concentration'] for r in rows]
        self._record(f'Calibrated {label}: {fit}{" through zero" if through_zero else ""}, {len(rows)} standards '
                     f'{min(concs):g}-{max(concs):g} {units}, R² {model.r_squared or 0:.4f}')
        return {'calibration': label, 'fit': fit, 'through_zero': through_zero, 'units': units,
                'coefficients': dict(zip(names, coefficients)), 'r_squared': model.r_squared,
                'rt_window': [round(position - rt_tolerance, 3), round(position + rt_tolerance, 3)],
                'standards': standard_rows, 'concentrations': quantified, 'warnings': warnings}

    def list_calibrations(self) -> List[dict]:
        out = []
        for model in self.store.calibration_service.get_all_models().values():
            used = [p.concentration for p in model.standards if p.included]
            out.append({'calibration': model.analyte_name, 'fit': model.fit_type, 'units': model.units,
                        'r_squared': model.r_squared, 'standards': len(used),
                        'range': [min(used), max(used)] if used else None,
                        'rt_window': [model.match_position - model.match_tolerance,
                                      model.match_position + model.match_tolerance]
                        if model.match_position is not None else None})
        return out

    def remove_calibration(self, name: str) -> List[dict]:
        service = self.store.calibration_service
        model = next((m for m in service.get_all_models().values() if name in (m.analyte_name, m.model_id)), None)
        if model is None:
            raise GeckoError(f'No calibration "{name}". Calibrations: ' +
                             ', '.join(m.analyte_name for m in service.get_all_models().values()))
        service.remove_model(model.model_id)
        self._refresh_concentrations()
        self._record(f'Removed calibration {model.analyte_name}')
        return self.list_calibrations()

    # -- PDA (3D UV) ----------------------------------------------------------------------------------------------

    def compare_wavelengths(self, peak: str, standards: dict, wavelengths=None, samples=None,
                           rt_tolerance: float = 0.2) -> dict:
        """Compare PDA calibration wavelengths using the highest standard's named peak window in every standard.
        Candidates default to UV maxima, the original channel and common wavelengths (up to eight). Reports area,
        linearity, saturation, S/N, estimated LOQ, baseline and spectral purity; rejects saturation, impurity and S/N < 10
        before ranking by back-calculation error then slope. Only the recommended channel is retained, in the
        standards and optional additional samples. Existing peaks are preserved; integrate the returned window
        with snap_to_valleys=False on the recommended channel before calibrating. LOQ has the standards' units.
        """
        from services.wavelength_comparison import compare_wavelengths
        return compare_wavelengths(self, peak, standards, wavelengths, samples, rt_tolerance)

    def _pda_source(self, bundle):
        from services.pda_service import resolve_pda_source
        for component in bundle.component_list:
            found = resolve_pda_source(self.store, component.component_id)
            if found:
                return found
        raise GeckoError(f'{bundle.name} has no PDA (3D UV) data: only its recorded channels can be used.')

    def add_uv_channel(self, wavelength_nm: float, samples=None) -> List[dict]:
        """Extract the absorbance at one wavelength from each sample's PDA data as a channel of its own (as the app's
        "Add N nm channel"), for compounds the recorded channels miss (no chromophore: 200-210 nm). It can then be
        integrated like any channel; an existing channel at that wavelength is reused."""
        from services.pda_service import add_pda_chromatogram, extract_pda_views
        out = []
        for bundle in self._samples(samples):
            try:
                source_id, payload = self._pda_source(bundle)
            except GeckoError as exc:
                out.append({'sample': bundle.name, 'error': str(exc)})
                continue
            view = extract_pda_views(payload, wavelength_nm)
            component_id = add_pda_chromatogram(self.store, source_id, wavelength_nm)
            component = next(c for c in bundle.component_list if c.component_id == component_id)
            out.append({'sample': bundle.name, 'channel': bundle.component_display_name(component),
                        'measured_nm': round(view['measured_wavelength_nm'], 2)})
        self._record(f'Added a {wavelength_nm:g} nm channel from the PDA data in {_names(self._samples(samples))}')
        return out

    def uv_spectrum(self, sample, rt: float, top: int = 5) -> dict:
        """The UV spectrum at one time from the sample's PDA data (the nearest recorded scan): its absorbance maxima
        and the absorbance every 10 nm."""
        from scipy.signal import find_peaks
        from services.pda_service import extract_pda_views
        bundle = self._sample(sample)
        _source, payload = self._pda_source(bundle)
        view = extract_pda_views(payload, None, float(rt))
        nm, mau = np.asarray(view['wavelengths'], dtype=float), np.asarray(view['spectrum'], dtype=float)
        order = np.argsort(nm)
        nm, mau = nm[order], mau[order]
        found, _ = find_peaks(mau, prominence=max(float(np.nanmax(np.abs(mau))) * 0.02, 1e-9))
        maxima = sorted(found, key=lambda i: -mau[i])[:max(1, int(top))]
        grid = np.arange(np.ceil(nm.min() / 10) * 10, nm.max() + 0.01, 10)
        return {'sample': bundle.name, 'time_min': round(view['time_min'], 4),
                'maxima': [{'nm': round(float(nm[i]), 1), 'mAU': round(float(mau[i]), 2)} for i in sorted(maxima)],
                'every_10_nm': {int(g): round(float(np.interp(g, nm, mau)), 2) for g in grid}}

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

    def add_eic_channel(self, mz: float, tolerance: float = 0.5, polarity: str = '+', samples=None) -> List[dict]:
        """Add the extracted-ion chromatogram of m/z ± tolerance as a channel of each run with full-scan spectra
        (polarity '+', '-' or 'both'), like the app's EIC "Add as channel": then it is integrated, matched across
        samples, calibrated and exported like any channel. Returns the channel names."""
        from services.eic_service import add_eic_chromatogram, ms_source
        out = []
        polarities = ['+', '-'] if str(polarity).lower() == 'both' else [polarity]
        for bundle in self._samples(samples):
            for pol in polarities:
                source = ms_source(self.store, bundle, pol)
                if source is None:
                    out.append({'sample': bundle.name, 'error': f'no {"negative" if pol.startswith("-") else "positive"}'
                                '-mode full-scan spectra'})
                    continue
                component_id = add_eic_chromatogram(self.store, source.component_id, mz, tolerance)
                component = next(c for c in bundle.component_list if c.component_id == component_id)
                out.append({'sample': bundle.name, 'channel': bundle.component_display_name(component)})
        self._record(f'Added EIC m/z {mz:g} ± {tolerance:g} ({polarity}) as a channel in '
                     f'{_names(self._samples(samples))}')
        return out

    def eic(self, mz: float, tolerance: float = 0.5, samples=None, polarity: str = '+',
            rt_start: Optional[float] = None, rt_end: Optional[float] = None) -> List[dict]:
        """Extracted-ion chromatogram of m/z ± tolerance in each run with spectra, added as a channel and integrated
        there: the tallest point (inside ``rt_start``-``rt_end`` if given), from where the trace falls to 5 % of
        that height on each side (or over the given window), straight baseline. The peak is in the app, editable;
        extracting again replaces the agent's earlier EIC peak at that place."""
        from callbacks.baseline_callbacks import _area_with_constraints
        from services.eic_service import add_eic_chromatogram, ms_source
        rows = []
        for bundle in self._samples(samples):
            source = ms_source(self.store, bundle, polarity)
            if source is None:
                rows.append({'sample': bundle.name, 'error': 'no full-scan mass spectra of this polarity '
                                                             '(only exported TIC traces or no MS)'})
                continue
            channel_id = add_eic_chromatogram(self.store, source.component_id, mz, tolerance)
            component = next(c for c in bundle.component_list if c.component_id == channel_id)
            t, inten = self._xy(channel_id)
            window = np.ones_like(t, dtype=bool)
            if rt_start is not None:
                window &= t >= rt_start
            if rt_end is not None:
                window &= t <= rt_end
            channel = bundle.component_display_name(component)
            if not window.any() or inten[window].max() <= 0:
                rows.append({'sample': bundle.name, 'channel': channel, 'apex_rt': None, 'height': 0.0, 'area': 0.0})
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
            result, q1, q2 = _area_with_constraints(t, inten, *ends)
            row = {'sample': bundle.name, 'channel': channel, 'mz': mz, 'tolerance': tolerance, 'polarity': polarity,
                   'apex_rt': round(float(t[apex]), 4), 'height': float(f'{inten[apex]:.6g}'),
                   'rt_start': round(lo, 4), 'rt_end': round(hi, 4), 'area': 0.0}
            if result:
                ps = self.store.peak_service
                for old in list(ps.get_peaks(channel_id) or []):
                    if old.source == 'agent-eic' and old.rt_start < hi and old.rt_end > lo:
                        ps.remove_peak(channel_id, old.peak_id)
                ps.save_undo()
                peak = ps.add_baseline_peak(channel_id, area=result['area'], height=result['height'],
                                            apex_x=result['apex_x'], poly_x=result['poly_x'], poly_y=result['poly_y'],
                                            p_line=ends, q1=q1, q2=q2, source='agent-eic')
                row.update(area=float(f'{result["area"]:.6g}'), peak_id=peak.peak_id)
            rows.append(row)
        self.store.peak_service.group_peaks_across_samples(file_overlay_map=self.store.build_file_overlay_map())
        self._record(f'Extracted and integrated EIC m/z {mz:g} ± {tolerance:g} ({polarity}) in '
                     f'{_names(self._samples(samples))}')
        return rows

    def mass_spectrum(self, sample, rt: Optional[float] = None, rt_start: Optional[float] = None,
                      rt_end: Optional[float] = None, peak: Optional[str] = None, polarity: Optional[str] = None,
                      top: int = 10) -> dict:
        """The mass spectrum at one time (the nearest scan), averaged over a window, or averaged over a peak's
        integration window as the app's Peak mass view does. Returns the ``top`` most intense m/z with intensities
        relative to the largest (%). Without ``polarity``: a peak integrated on −TIC or a negative EIC gives the
        negative spectrum, anything else the positive one."""
        from services.data_store import ComponentRole
        from services.lcms_service import LCMSService
        service = LCMSService()
        bundle = self._sample(sample)
        found = None
        if peak is not None:
            owner, found = self._find_peak(bundle, peak)
            if polarity is None:
                negative = owner.role == ComponentRole.MS_NEGATIVE or '(−)' in bundle.component_display_name(owner) \
                    or '(-)' in bundle.component_display_name(owner)
                polarity = '-' if negative else '+'
        polarity = polarity or '+'
        _component, entry = self._ms_entry(bundle, polarity)
        what = None
        if found is not None:
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

    def export_results(self, path: str) -> str:
        """The whole project as one Excel workbook: an overview, one sheet per plot tab (peak areas per compound and
        sample, every peak) with its traces, calibration, samples and history."""
        from services.results_workbook import build_results_workbook
        self._refresh_concentrations()
        path = Path(path).expanduser()
        if path.suffix.lower() != '.xlsx':
            path = path.with_suffix('.xlsx')
        path.write_bytes(build_results_workbook(self.store))
        return str(path)

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
