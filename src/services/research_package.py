"""Self-contained research exports with immutable imports and explicit provenance."""
from __future__ import annotations
import base64
import hashlib
import html
import io
import json
import logging
import platform
import re
import zipfile
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path

import numpy as np
import pandas as pd
from plotly.utils import PlotlyJSONEncoder

from services.plot_arrays import numeric_plot_array
from services.plot_smoothing import smoothing_fair_export_record

POLICY = 'https://zenodo.org/communities/nccr-catalysis/curation-policy'


def now():
    return datetime.now(timezone.utc).isoformat()


def dumps(value):
    # Plotly handles numpy/date values; JSON round-trip also removes references.
    return json.dumps(value, cls=PlotlyJSONEncoder, ensure_ascii=False, indent=2)


def safe_name(value):
    return re.sub(r'[^\w.-]+', '-', str(value)).strip('.-')[:90] or 'data'


def csv_bytes(frame):
    return frame.to_csv(index=False, lineterminator='\n').encode('utf-8')


def _history_metadata(metadata):
    result = {k:v for k,v in metadata.items() if k != 'mass_spectral_data'}
    pda = result.get('pda')
    if pda:
        keys = ('time_min', 'wavelength_nm', 'absorbance_mau')
        immutable = all(isinstance(pda.get(key), np.ndarray) and not pda[key].flags.writeable for key in keys)
        data_sha256 = pda.get('data_sha256') if immutable else None
        if not data_sha256:
            digest = hashlib.sha256()
            for key in keys:
                digest.update(np.asarray(pda[key], dtype='<f8').tobytes())
            data_sha256 = digest.hexdigest()
        result['pda'] = {k:v for k,v in pda.items() if k not in ('time_min','wavelength_nm','absorbance_mau')}
        result['pda'].update(shape=[len(pda['time_min']),len(pda['wavelength_nm'])], data_sha256=data_sha256)
    return result


def _dataframe_sha256(store, component):
    """SHA-256 of the component's CSV bytes, recomputed only when the table content changed.

    This runs after every callback, and serialising every table to CSV each time made each interaction slower
    the more data was loaded. A vectorised content fingerprint is ~1000x cheaper than writing the CSV.
    """
    frame = component.dataframe
    if frame is None:
        return None
    cache = store.__dict__.setdefault('_dataframe_digests', {})
    try:
        fingerprint = (id(frame), frame.shape, tuple(map(str, frame.columns)),
                       int(pd.util.hash_pandas_object(frame, index=True).sum()))
    except Exception:
        fingerprint = None
    cached = cache.get(component.component_id)
    if fingerprint is not None and cached and cached[0] == fingerprint:
        return cached[1]
    digest = hashlib.sha256(csv_bytes(frame)).hexdigest()
    if fingerprint is not None:
        cache[component.component_id] = (fingerprint, digest)
    return digest


def record_analysis_state(store, settings=None, triggers=None):
    """Record changed scientific state, not clicks or rendered UI noise."""
    if settings is not None:
        store.analysis_plot_settings = json.loads(dumps(settings))
    signals = {}
    for bundle in store.iter_bundles():
        for c in bundle.component_list:
            signals[c.component_id] = {'sample_name': bundle.name,
                'metadata': _history_metadata(c.metadata), 'column_roles': c.column_roles,
                'data_sha256': _dataframe_sha256(store, c)}
    state = json.loads(dumps({'signals': signals,
        'plot_settings': getattr(store, 'analysis_plot_settings', {}),
        'file_settings': store.file_ui_state,
        'peaks': store.peak_service.serialize(),
        'calibrations': store.calibration_service.serialize(),
        'integration_settings': store.integration_service.serialize()}))
    previous = getattr(store, '_analysis_previous', {})
    changes = {key: {'before': previous.get(key), 'after': value}
               for key, value in state.items() if previous.get(key) != value}
    if changes:
        revisions = {}
        previous_signals = previous.get('signals', {})
        for bundle in store.iter_bundles():
            for c in bundle.component_list:
                old = previous_signals.get(c.component_id, {})
                if old and old.get('data_sha256') != signals[c.component_id]['data_sha256'] and c.dataframe is not None:
                    revisions[c.component_id] = {'csv': c.dataframe.to_csv(index=False, lineterminator='\n')}
        if revisions:
            changes['edited_tables'] = revisions
        store.analysis_history.append({'at': now(), 'trigger': triggers or [], 'changes': changes})
        store._analysis_previous = state


SESSION_PATH = 'session/project.gecko'
SESSION_MAX_BYTES = 200_000_000


def _package_session(store, metadata, original_paths_by_sha):
    """The workspace as a reopenable ``.gecko`` for the package: ``(bytes | None, note)``.

    Originals are not embedded a second time: the session refers to the package's own
    ``raw_data/originals/...`` copies (same SHA-256), which ``restore_session`` reads out of the ZIP. A failure or an
    oversized result skips the file and says why; it never fails the export.
    """
    try:
        from services import session_service
        data = session_service.build_session(
            store, project_name=metadata.get('title') or None, embed_raw=False,
            source_paths=original_paths_by_sha)
    except Exception as exc:
        logging.getLogger(__name__).exception('Could not build the project file for the research package')
        return None, f'The reopenable project file could not be built ({exc}).'
    if len(data) > SESSION_MAX_BYTES:
        return None, (f'The reopenable project file would be {len(data) // 1_000_000} MB (edited tables), above the '
                      f'{SESSION_MAX_BYTES // 1_000_000} MB limit; it was left out.')
    return data, ''


def build_research_package(store, metadata, figure_request=None, formats=None, include_code=False):
    if not store.all_bundles():
        raise ValueError('Load data before exporting a FAIR-data package.')
    from services.calibration_workflow import apply_calibrations
    apply_calibrations(store)
    record_analysis_state(store, triggers=['research-package-export'])
    exported = now()
    metadata = {k: v for k, v in (metadata or {}).items() if v not in (None, '')}
    settings = getattr(store, 'analysis_plot_settings', {})
    files = {}
    descriptions = {}
    def add(path, content, kind, source=''):
        files[path] = content.encode('utf-8') if isinstance(content, str) else content
        descriptions[path] = {'kind': kind, 'source': source}
    signals = []
    original_paths = {}
    original_paths_by_sha = {}
    for bundle in store.iter_bundles():
        for c in bundle.component_list:
            key = safe_name(bundle.name)[:45] + '_' + safe_name(bundle.component_display_name(c))[:35] + '_' + safe_name(c.component_id)[:12]
            raw_path = f'raw_data/{key}.csv'
            processed_path = f'processed_data/{key}.csv'
            original_path = f'raw_data/originals/{key}/{safe_name(Path(c.original_filename).name)}'
            if c.raw_bytes:
                add(original_path, c.raw_bytes, 'original upload', c.component_id)
                original_paths[c.component_id] = original_path
                original_paths_by_sha.setdefault(hashlib.sha256(c.raw_bytes).hexdigest(), original_path)
            elif c.metadata.get('source_file_id') in original_paths:
                original_path = original_paths[c.metadata['source_file_id']]
            if c.imported_csv is not None:
                add(raw_path, c.imported_csv, 'unmodified parsed import', c.component_id)
            if c.dataframe is not None:
                current_csv = csv_bytes(c.dataframe)
                if current_csv == files.get(raw_path):
                    processed_path = raw_path
                else:
                    add(processed_path, current_csv, 'current data before display smoothing', raw_path)
            sr = c.standardized
            signal_meta = {**(sr.metadata if sr else {}), **c.metadata}
            signal_meta.setdefault('source_category', str(getattr(c.source_category, 'value', c.source_category)))
            if sr:
                signal_meta.setdefault('detected_format', sr.identity.detected_format)
            if c.dataframe is not None:
                ancillary = {}
                for column in c.dataframe.columns:
                    values = c.dataframe[column].dropna()
                    if len(values) and not pd.api.types.is_numeric_dtype(values):
                        ancillary[str(column)] = values.astype(str).drop_duplicates().head(50).tolist()
                if ancillary:
                    signal_meta.setdefault('source_text_fields', ancillary)
                    signal_meta['source_text_fields_note'] = 'First 50 distinct non-empty text values per source column; interpretation is not inferred. Complete values remain in CSV.'
            pda = signal_meta.pop('pda', None)
            if pda:
                matrix_path = f'raw_data/{key}_pda.csv'
                matrix = pd.DataFrame(pda['absorbance_mau'],
                                      columns=[format(float(w), '.12g') for w in pda['wavelength_nm']])
                matrix.insert(0, 'Time (min)', pda['time_min'])
                add(matrix_path, csv_bytes(matrix), 'PDA absorbance matrix (mAU); columns are wavelength in nm', original_path)
                signal_meta['pda'] = {k:v for k,v in pda.items() if k not in ('absorbance_mau', 'time_min', 'wavelength_nm')}
                signal_meta['pda'].update(matrix_csv=matrix_path, time_unit='min', wavelength_unit='nm', intensity_unit='mAU',
                                          shape=[len(pda['time_min']),len(pda['wavelength_nm'])])
            spectral = signal_meta.pop('mass_spectral_data', None)
            if spectral:
                masses = np.asarray(spectral.get('mass_values', []))
                intensities = np.asarray(spectral.get('intensity_values', []))
                indices = np.asarray(spectral.get('scan_index', []), dtype=int)
                points_path = f'raw_data/{key}_mass_points.csv'
                scans_path = f'raw_data/{key}_scan_index.csv'
                add(points_path, csv_bytes(pd.DataFrame({'mz': masses, 'intensity': intensities})), 'mass spectral points', original_path)
                scans = pd.DataFrame({'scan_index': indices})
                if 'point_count' in spectral: scans['point_count'] = spectral['point_count']
                if c.dataframe is not None and len(c.dataframe) == len(indices):
                    xcols = [col for col, role in c.column_roles.items() if str(getattr(role, 'value', role)) == 'x']
                    if xcols: scans[xcols[0]] = c.dataframe[xcols[0]].to_numpy()
                add(scans_path, csv_bytes(scans), 'zero-based offsets into mass point rows', points_path)
                signal_meta['mass_spectral_data'] = {'points_csv': points_path, 'scan_index_csv': scans_path}
            info = {'signal_id': c.component_id, 'peak_owner_id': store.peak_owner_id(c.component_id),
                'bundle_id': bundle.bundle_id, 'sample': bundle.name,
                'signal': bundle.component_display_name(c), 'original_filename': c.original_filename,
                'imported_at': c.imported_at, 'raw_csv': raw_path if raw_path in files else None,
                'processed_csv': processed_path if processed_path in files else None,
                'original_file': original_path if original_path in files else None,
                'column_roles': c.column_roles, 'metadata': signal_meta}
            signals.append(info)
    peaks = store.peak_service.serialize()
    add('analysis/peaks.json', dumps(peaks), 'full peak geometry and fit parameters')
    rows = [dict(p) for pks in peaks['peaks'].values() for p in pks]
    for row in rows:
        signal = next((s for s in signals if s['peak_owner_id'] == row['file_id']), {})
        row['sample'] = signal.get('sample', '')
        row['signal'] = signal.get('signal', '')
        row['position_axis'] = next((col for col, role in signal.get('column_roles', {}).items() if str(getattr(role,'value',role)) == 'x'), '')
        model = store.calibration_service.get_model(row.get('calibration_id'))
        row['concentration_units'] = model.units if model else ''
    if rows:
        excluded = {'poly_x', 'poly_y', 'p_line', 'q1', 'q2', 'fit_params'}
        add('analysis/peaks.csv', csv_bytes(pd.DataFrame([{k:v for k,v in p.items() if k not in excluded} for p in rows])), 'peak results', 'analysis/peaks.json')
    add('analysis/integration_settings.json', dumps(store.integration_service.serialize()), 'detection and integration settings')
    add('analysis/calibrations.json', dumps(store.calibration_service.serialize()), 'calibration models and points')
    add('analysis/history.json', dumps(store.analysis_history), 'timestamped before/after analysis history')
    add('analysis/plot_settings.json', dumps({'current': settings, 'files': store.file_ui_state}), 'visualization settings')
    software = {'GeckoPlotter': '2', 'Python': platform.python_version()}
    for library in ('numpy','pandas','scipy','plotly','kaleido','Pillow'):
        try: software[library] = version(library)
        except Exception: pass
    source = Path(__file__).resolve().parents[2]
    # Preserve the actual algorithms used, even for an uncommitted local build.
    for relative in ('services/plot_smoothing.py','services/integration_service.py','services/peak_service.py','services/deconvolution_service.py','services/calibration_service.py','services/calibration_workflow.py','services/figure_export.py','services/figure_sanitization.py','services/plot_arrays.py'):
        path = source/'src'/relative
        if include_code and path.exists(): add('analysis/software/'+relative, path.read_bytes(), 'analysis implementation')
    figure_sources = []
    figure_files = []
    if figure_request and figure_request.get('figure'):
        from services.figure_sanitization import clean_figure_for_output
        from services.figure_export import export_displayed_figure
        figure = clean_figure_for_output(figure_request['figure'])
        add('figures/figure.json', dumps(figure), 'editable Plotly figure')
        for i, trace in enumerate(figure.get('data', [])):
            meta = trace.get('meta') or {}
            if not isinstance(meta, dict) or not meta.get('file_id'): continue
            if 'x' not in trace or 'y' not in trace: continue
            x,y = numeric_plot_array(trace['x']), numeric_plot_array(trace['y'])
            if x.ndim != 1 or y.ndim != 1 or len(x)!=len(y): continue
            path = f'figures/source_data/trace-{i+1}.csv'
            add(path, csv_bytes(pd.DataFrame({'x': x,'y': y})), 'exact displayed trace', meta['file_id'])
            figure_sources.append({'file': path, 'signal_id': meta['file_id'], 'trace': trace.get('name'),
                'y_column': meta.get('y_column'), 'x_axis': trace.get('xaxis','x'), 'y_axis': trace.get('yaxis','y'),
                'smoothing': smoothing_fair_export_record(settings.get('smooth_window',0),len(y))})
        for fmt in formats if formats is not None else ['svg', 'pdf', 'png']:
            result = export_displayed_figure(figure, fmt, figure_request.get('width_mm',174),
                figure_request.get('height_mm',104), figure_request.get('dpi',300), figure_request.get('render_width',900), 'figure')
            path = 'figures/'+result['filename']
            add(path, base64.b64decode(result['content']) if result.get('base64') else result['content'], 'publication figure', 'figures/figure.json')
            figure_files.append(path)
    session_bytes, session_note = _package_session(store, metadata, original_paths_by_sha)
    if session_bytes is not None:
        add(SESSION_PATH, session_bytes, 'reopenable GeckoPlotter project (state only; originals are read from raw_data/originals/)',
            'raw_data/originals/')
    issues = []
    for key, label in [('title','Dataset title'),('description','Dataset description'),('creators','Authors'),
                       ('record_url','Dataset record DOI or URL'),('license','License')]:
        if not metadata.get(key): issues.append(label+' is missing.')
    if not metadata.get('orcid'): issues.append('Add an NCCR-affiliated author ORCID for NCCR community submission.')
    if session_note: issues.append(session_note)
    issues.append('Confirm applicable funding, sample/molecule identities and structure files before repository submission.')
    if any(not s['original_file'] for s in signals): issues.append('Some original upload bytes were unavailable; parsed CSV is included where available.')
    document = {'schema_version':'1.1', 'project_file': SESSION_PATH if session_bytes is not None else None,
        'project_file_note': session_note or None,
        'includes_analysis_code':include_code, 'exported_at':exported, 'dataset':metadata, 'software':software,
        'signals':signals, 'figure_sources':figure_sources, 'figure_files':figure_files,
        'processing':{'smoothing':smoothing_fair_export_record(settings.get('smooth_window',0)),
            'uv_ms_timing_correction':{'applied':False,'status':'Not implemented'},
            'history_started_at': store.analysis_history[0]['at'] if store.analysis_history else None,
            'scope':'History records application state changes since import in this workspace. Acquisition timestamps are preserved separately in signal metadata. Imported upstream processing is not inferred.'},
        'figure_export':{k:v for k,v in (figure_request or {}).items() if k in ('width_mm','height_mm','dpi','render_width')},
        'submission_review':issues, 'guidance':POLICY}
    add('metadata/dataset.json', dumps(document), 'linked dataset metadata')
    if include_code: add('analysis/requirements.txt', '\n'.join(k+'=='+v for k,v in software.items() if k not in ('GeckoPlotter','Python'))+'\n', 'analysis environment')
    if figure_files and include_code:
        add('analysis/reproduce_figure.py', '''from pathlib import Path
import base64
import json
import sys
root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root/'analysis/software'))
from services.figure_export import export_displayed_figure
metadata = json.loads((root/'metadata/dataset.json').read_text())
figure = json.loads((root/'figures/figure.json').read_text())
recipe = metadata['figure_export']
output = root/'reproduced_figures'
output.mkdir(exist_ok=True)
for path in metadata['figure_files']:
    fmt = Path(path).suffix.lstrip('.')
    result = export_displayed_figure(figure, fmt, recipe['width_mm'], recipe['height_mm'], recipe['dpi'], recipe['render_width'])
    content = base64.b64decode(result['content']) if result.get('base64') else result['content'].encode()
    (output/result['filename']).write_bytes(content)
''', 'recreate exported figures from saved figure and dimensions')
    flattened=[{k:(dumps(v) if isinstance(v,(dict,list)) else v) for k,v in s.items()} for s in signals]
    add('experiment_metadata.csv',csv_bytes(pd.DataFrame(flattened)), 'sample-to-file mapping')
    creators = [{'name': name.strip()} for name in metadata.get('creators','').split(';') if name.strip()]
    if creators:
        if metadata.get('orcid'): creators[0]['orcid']=metadata['orcid']
        if metadata.get('affiliation'): creators[0]['affiliation']=metadata['affiliation']
    zenodo={'title':metadata.get('title',''),'upload_type':'dataset','description':metadata.get('description',''),
        'creators':creators,'access_right':'open','license':metadata.get('license',''),
        'keywords':[k.strip() for k in metadata.get('keywords','').split(',') if k.strip()]}
    if metadata.get('article_doi'): zenodo['related_identifiers']=[{'identifier':metadata['article_doi'],'relation':'isSupplementTo','scheme':'doi'}]
    add('metadata/zenodo.json',dumps(zenodo),'repository metadata draft')
    title=metadata.get('title') or 'Research dataset'
    if session_bytes is not None:
        project_line = ('- session/project.gecko: the whole workspace (peaks, calibrations, names, figure settings) as a GeckoPlotter project. '
            'Open this ZIP in GeckoPlotter (Open, or drop it in) to keep editing; the instrument files are read from raw_data/originals/ '
            'inside the package, so nothing is stored twice. Not a data file: use the CSV files for other software.')
    else:
        project_line = '- session/: no reopenable project file in this package. ' + session_note
    readme=f'''# {title}

{metadata.get('description','Description not yet supplied.')}

Exported: {exported}
Authors: {metadata.get('creators','Not supplied')}
Affiliation: {metadata.get('affiliation','Not supplied')}
ORCID (first author): {metadata.get('orcid','Not supplied')}
Dataset record DOI or URL: {metadata.get('record_url','Not supplied; reserve a DOI and add it before deposition.')}
Related article DOI: {metadata.get('article_doi','Not supplied')}
License: {metadata.get('license','Not selected')}
Funding: {metadata.get('funding','Not supplied')}

## Contents and provenance

- raw_data/: untouched parsed CSV at import plus original uploaded files where available. This is the imported instrument export, not a claim that upstream processing never occurred.
- processed_data/: edited tables only, before display smoothing. Unchanged tables link to their raw CSV without a second copy.
- figures/: publication files, editable figure JSON, and exact displayed x/y source data. Axis labels and units are in figure.json; signal column names and instrument metadata are linked in metadata/dataset.json.
- analysis/: complete peak results, baselines, deconvolution parameters, calibration data, plot settings, timestamped before/after history. Analysis code and the figure recreation script are included only when selected.
{project_line}
- experiment_metadata.csv: links samples, signals, original filenames, raw and processed CSV, and imported metadata.
- dataset_manifest.csv: file descriptions, source links and SHA-256 checksums. The manifest excludes itself.
- report.html: readable analysis report; open locally or print to PDF.
- metadata/zenodo.json: repository metadata draft. No record is uploaded or published by this export.

Figure smoothing is Savitzky-Golay and does not overwrite raw points. Peak detection has its own processing pipeline and settings in analysis/integration_settings.json; changing smoothing can affect detected boundaries. Exact settings and effective per-trace windows are recorded. UV–MS timing correction is not applied. Acquisition dates are imported metadata; import, analysis event and export times are separate UTC timestamps.

## Methods and sample information

{metadata.get('methods','No additional methods supplied. See signal metadata in metadata/dataset.json and analysis history.')}

## Repository preparation

NCCR guidance: {POLICY}

'''+ '\n'.join('- '+i for i in issues)+'\n'
    add('README.md',readme,'package documentation')
    image_path=next((p for p in figure_files if p.endswith(('.svg','.png'))),None)
    preview=f'<img src="{image_path}" alt="Exported scientific figure">' if image_path else ''
    def describe(event):
        result = []
        labels = {'smooth_window':'Smoothing window (points)', 'legend_font_size':'Legend font size',
                  'legend_positions':'Legend placement', 'font_size':'Font size', 'legend_pos':'Legend position'}
        for group, change in event['changes'].items():
            before, after = change.get('before') or {}, change.get('after') or {}
            if group == 'plot_settings':
                if not before:
                    result.append('Initial figure settings recorded')
                    continue
                for key, value in after.items():
                    if key.startswith('_') or before.get(key) == value: continue
                    old = before.get(key, 'initial')
                    result.append(f"{labels.get(key, key.replace('_',' ').capitalize())}: {old} → {value}")
            elif group == 'peaks':
                old_n = sum(len(v) for v in before.get('peaks',{}).values())
                new_n = sum(len(v) for v in after.get('peaks',{}).values())
                result.append(f'Peak results updated ({old_n} → {new_n} peaks)')
            elif group == 'signals': result.append('Imported data or sample metadata updated')
            elif group == 'edited_tables': result.append('Data values edited; revised tables retained in history')
            elif group == 'integration_settings': result.append('Detection / integration parameters updated')
            elif group == 'calibrations': result.append('Calibration models updated')
        return '; '.join(result)
    event_rows=''.join('<tr><td>'+html.escape(e['at'].replace('T',' ')[:19])+'</td><td>'+html.escape(describe(e))+'</td></tr>' for e in store.analysis_history if describe(e))
    def shown(value):
        if value is None or (isinstance(value, float) and not np.isfinite(value)): return '—'
        return f'{value:.6g}' if isinstance(value, (float, np.floating)) else str(value)
    report_peaks = []
    for row in rows:
        report_peaks.append({'Sample': row.get('sample',''), 'Signal':row.get('signal',''), 'Peak':row['name'],
            'Position':shown(row['rt']), 'Axis':row.get('position_axis',''), 'Area':shown(row['area']),
            'Height':shown(row['height']), 'Concentration':shown(row.get('concentration'))+(' '+row['concentration_units'] if row.get('concentration_units') else ''),
            'Source':row.get('source','')})
    table=pd.DataFrame(report_peaks).to_html(index=False,escape=True,border=0) if rows else '<p>No integrated peaks.</p>'
    report='''<!doctype html><html lang="en"><meta charset="utf-8"><title>Analysis report</title><style>body{font:15px system-ui,sans-serif;color:#222;max-width:1100px;margin:36px auto;padding:0 20px}img{max-width:100%}table{border-collapse:collapse;width:100%;font-size:12px}td,th{padding:7px;border-bottom:1px solid #ddd;text-align:left;overflow-wrap:anywhere}pre{white-space:pre-wrap}h2{margin-top:30px}@media print{body{margin:0}h2{break-after:avoid}tr{break-inside:avoid}}</style>'''
    report+=f'<h1>{html.escape(title)}</h1><p>{html.escape(metadata.get("description",""))}</p><p>Exported {exported}</p>'+preview
    smooth = document['processing']['smoothing']
    smoothing_text = ('Savitzky–Golay; requested window '+str(smooth['parameters']['requested_window_points'])+' points; polynomial order '+str(smooth['parameters']['polynomial_order'])+'. Effective windows are recorded per figure trace.') if smooth['applied'] else 'Off'
    summary = [('Figure smoothing', smoothing_text), ('UV–MS timing correction','Not applied'),
        ('Figure size', shown(document['figure_export'].get('width_mm'))+' × '+shown(document['figure_export'].get('height_mm'))+' mm'),
        ('Raster resolution',str(document['figure_export'].get('dpi','—'))+' DPI'), ('Software',', '.join(k+' '+v for k,v in software.items()))]
    report+='<h2>Processing and output</h2><table>'+''.join('<tr><th>'+html.escape(k)+'</th><td>'+html.escape(v)+'</td></tr>' for k,v in summary)+'</table>'
    report+='<p>Figure smoothing preserves imported values. Detection parameters, baseline geometry, fitted components and calibrations are retained in the analysis files.</p>'
    report+='<h2>Samples</h2>'+pd.DataFrame([{'Sample':s['sample'],'Signal':s['signal'],'Source file':s['original_filename'],'Imported (UTC)':(s['imported_at'] or '').replace('T',' ')[:19]} for s in signals]).to_html(index=False,escape=True,border=0)
    report+='<h2>Peak results</h2>'+table+'<h2>Analysis history (UTC)</h2><table><tr><th>Time</th><th>Change</th></tr>'+event_rows+'</table><h2>Methods</h2><p>'+html.escape(metadata.get('methods','Not supplied'))+'</p><h2>Files and metadata</h2><p><a href="README.md">README</a> · <a href="metadata/dataset.json">Dataset metadata</a> · <a href="analysis/history.json">Full edit history</a> · <a href="experiment_metadata.csv">Sample mapping</a></p>'
    report+=('<p>Reopenable project: <code>'+SESSION_PATH+'</code> (open this ZIP in GeckoPlotter to keep editing the figure and analysis).</p>' if session_bytes is not None
             else '<p>Reopenable project: not included. '+html.escape(session_note)+'</p>')
    add('report.html',report,'readable analysis report')
    manifest=[{'path':path,**descriptions[path], 'bytes':len(content),'sha256':hashlib.sha256(content).hexdigest()} for path,content in files.items()]
    add('dataset_manifest.csv',csv_bytes(pd.DataFrame(manifest)),'manifest')
    output=io.BytesIO()
    with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as archive:
        for path,content in files.items(): archive.writestr(path,content)
    return output.getvalue()
