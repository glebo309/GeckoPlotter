"""The whole project as one Excel workbook to keep working with.

Sheets, in this order:
  Overview          project, export time, version, whether an MCP agent worked on it, and the tabs inside
  <tab>             one sheet per plot tab, named like the tab: peak areas per compound and sample, then every peak
  <tab> data        that tab's traces: time and signal per sample and channel, to re-plot anywhere
  Calibration       standards, fits and R² (when calibrations exist)
  Samples           every sample with its channels, files and acquisition details
  History           the analysis history, with who made each change (the app or an MCP agent)

Used by Export > "Export results (Excel)" and by the agent (gecko_api.export_results).
"""
from __future__ import annotations

import io
import re
from collections import OrderedDict
from datetime import datetime
from typing import Dict, List, Optional

GREEN = '2C5240'
LIGHT = 'EEF4F0'
BAND = 'F7F9F8'
GREY = '6E7378'
LINE = 'D8DEDA'


# -- what goes in -----------------------------------------------------------------------------------------------------

def _tabs(store, tab_labels: Optional[Dict[str, str]] = None):
    """{tab label: [bundles]} as the plot tabs group the samples (a renamed tab keeps its new name)."""
    from callbacks.viz_callbacks import _get_overlay_group, _tab_id_from_group, _tab_label_from_group
    from services.natural_sort import natural_key
    tabs = OrderedDict()
    for bundle in store.iter_bundles():
        entry = store.get_data_by_id(bundle.bundle_id)
        if not entry:
            continue
        group = _get_overlay_group(entry.get('metadata', {}), entry, file_id=bundle.bundle_id, dm=store)
        label = (tab_labels or {}).get(_tab_id_from_group(group)) or _tab_label_from_group(group, store)
        tabs.setdefault(label, []).append(bundle)
    for label in tabs:
        tabs[label].sort(key=lambda b: natural_key(b.name))
    return tabs


def _peak_rows(store, bundles) -> List[dict]:
    rows = []
    for bundle in bundles:
        for component in bundle.component_list:
            peaks = sorted(store.peak_service.get_peaks(component.component_id) or [], key=lambda p: p.rt)
            total = sum(max(float(p.area or 0), 0) for p in peaks)
            for p in peaks:
                rows.append({
                    'Sample': bundle.name, 'Channel': bundle.component_display_name(component),
                    'Peak': p.label or p.name, 'RT (min)': float(p.rt), 'Start (min)': float(p.rt_start),
                    'End (min)': float(p.rt_end), 'Area': float(p.area), 'Height': float(p.height),
                    'Area %': 100 * float(p.area) / total if total > 0 else None,
                    'Width (min)': float(p.width) if p.width else None,
                    'Concentration': p.concentration, 'Integration': p.source})
    return rows


def peak_rows(store) -> List[dict]:
    """Every peak of the project (all tabs)."""
    return [row for bundles in _tabs(store).values() for row in _peak_rows(store, bundles)]


def _areas(rows, samples, value='Area'):
    """Compound (peak name, channel) x sample: the same peak in every sample on one row."""
    compounds = []
    for r in rows:
        key = (r['Peak'], r['Channel'])
        if key not in compounds:
            compounds.append(key)
    compounds.sort(key=lambda k: (k[1], min(r['RT (min)'] for r in rows if (r['Peak'], r['Channel']) == k)))
    table = []
    for name, channel in compounds:
        line = {'Compound': name, 'Channel': channel,
                'RT (min)': sum(r['RT (min)'] for r in rows if (r['Peak'], r['Channel']) == (name, channel)) /
                max(1, sum(1 for r in rows if (r['Peak'], r['Channel']) == (name, channel)))}
        for sample in samples:
            hits = [r[value] for r in rows if r['Sample'] == sample and (r['Peak'], r['Channel']) == (name, channel)
                    and r[value] is not None]
            line[sample] = sum(hits) if hits else None
        table.append(line)
    return table, ['Compound', 'Channel', 'RT (min)'] + list(samples)


# -- how it looks -----------------------------------------------------------------------------------------------------

FORMATS = {'RT (min)': '0.000', 'Start (min)': '0.000', 'End (min)': '0.000', 'Width (min)': '0.000',
           'Area %': '0.00', 'Height': '#,##0.00', 'Concentration': '0.000', 'R²': '0.00000'}


def _title(sheet, text, subtitle=None):
    from openpyxl.styles import Font
    sheet.cell(row=1, column=1, value=text).font = Font(size=15, bold=True, color=GREEN)
    if subtitle:
        sheet.cell(row=2, column=1, value=subtitle).font = Font(size=10, italic=True, color=GREY)
    sheet.sheet_view.showGridLines = False
    return 4


def _section(sheet, row, text):
    from openpyxl.styles import Font
    sheet.cell(row=row, column=1, value=text).font = Font(size=11, bold=True, color=GREEN)
    return row + 1


def _table(sheet, row, header, rows, number_format='#,##0.00'):
    """A table at ``row``: green header, thin lines, banded rows, numbers formatted. Returns the next free row."""
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    thin = Side(style='thin', color=LINE)
    for col, name in enumerate(header, start=1):
        cell = sheet.cell(row=row, column=col, value=name)
        cell.font = Font(bold=True, color='FFFFFF')
        cell.fill = PatternFill('solid', fgColor=GREEN)
        cell.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
        cell.border = Border(bottom=thin)
    for i, line in enumerate(rows, start=1):
        for col, name in enumerate(header, start=1):
            value = line.get(name)
            cell = sheet.cell(row=row + i, column=col, value=value)
            cell.border = Border(bottom=thin)
            if i % 2 == 0:
                cell.fill = PatternFill('solid', fgColor=BAND)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                cell.number_format = FORMATS.get(name, number_format)
    if not rows:
        sheet.cell(row=row + 1, column=1, value='None').font = Font(italic=True, color=GREY)
        return row + 3
    return row + len(rows) + 2


def _widths(sheet, minimum=10, maximum=46):
    from openpyxl.utils import get_column_letter
    widths = {}
    for row in sheet.iter_rows(min_row=4):
        for cell in row:
            if cell.value is not None:
                text = f'{cell.value:,.2f}' if isinstance(cell.value, float) else str(cell.value)
                widths[cell.column] = max(widths.get(cell.column, 0), len(text) + 2)
    for column, width in widths.items():
        sheet.column_dimensions[get_column_letter(column)].width = max(minimum, min(width, maximum))


def _sheet_name(label, used, suffix=''):
    """Excel sheet names: at most 31 characters, none of []:*?/\\, and unique."""
    base = re.sub(r'[\[\]:*?/\\]', '-', str(label)).strip() or 'Tab'
    name = (base[:31 - len(suffix)] + suffix)
    n = 2
    while name.lower() in used:
        tail = f' ({n})' + suffix
        name = base[:31 - len(tail)] + tail
        n += 1
    used.add(name.lower())
    return name


# -- the workbook -----------------------------------------------------------------------------------------------------

def _traces(store, sheet, bundles):
    """Time and signal columns for every channel of the tab's samples (each with its own time axis)."""
    from openpyxl.styles import Alignment, Font, PatternFill
    from callbacks.baseline_callbacks import get_xy_arrays
    col = 1
    for bundle in bundles:
        for component in bundle.component_list:
            x, y = get_xy_arrays(store, component.component_id)
            if x is None or y is None:
                continue
            label = f'{bundle.name} · {bundle.component_display_name(component)}'
            head = sheet.cell(row=4, column=col, value=label)
            head.font = Font(bold=True, color=GREEN)
            head.alignment = Alignment(wrap_text=True)
            sheet.merge_cells(start_row=4, start_column=col, end_row=4, end_column=col + 1)
            for offset, name in enumerate(('Time (min)', 'Signal')):
                cell = sheet.cell(row=5, column=col + offset, value=name)
                cell.font = Font(bold=True, color='FFFFFF')
                cell.fill = PatternFill('solid', fgColor=GREEN)
            for i, (xv, yv) in enumerate(zip(x, y), start=6):
                sheet.cell(row=i, column=col, value=float(xv)).number_format = '0.0000'
                sheet.cell(row=i, column=col + 1, value=float(yv)).number_format = '0.000'
            from openpyxl.utils import get_column_letter
            sheet.column_dimensions[get_column_letter(col)].width = 11
            sheet.column_dimensions[get_column_letter(col + 1)].width = 13
            col += 3
    sheet.freeze_panes = sheet.cell(row=6, column=1)


def build_results_workbook(store, project_name: str = '', tab_labels: Optional[Dict[str, str]] = None,
                           include_traces: bool = True) -> bytes:
    """The workbook as .xlsx bytes. ``tab_labels``: {plot tab id: name} for tabs the user renamed."""
    from openpyxl import Workbook
    from openpyxl.styles import Font
    from services import about
    from services.research_package import agent_note

    tabs = _tabs(store, tab_labels)
    project = project_name or (getattr(store, 'session_meta', {}) or {}).get('project_name') or 'Untitled project'
    book = Workbook()
    overview = book.active
    overview.title = 'Overview'
    row = _title(overview, project, 'GeckoPlotter results')
    facts = [('Exported', datetime.now().strftime('%d %b %Y, %H:%M')),
             ('GeckoPlotter version', about.VERSION.get('sha', '')[:7] or 'unknown'),
             ('Samples', sum(len(b) for b in tabs.values())),
             ('Peaks', sum(len(_peak_rows(store, b)) for b in tabs.values())),
             ('Agent', agent_note(store))]
    from openpyxl.styles import Alignment
    for key, value in facts:
        overview.cell(row=row, column=1, value=key).font = Font(bold=True, color=GREY)
        overview.cell(row=row, column=2, value=value).alignment = Alignment(horizontal='left')
        row += 1
    row = _section(overview, row + 1, 'Tabs')
    contents = []
    used = {'overview', 'calibration', 'samples', 'history'}
    sheets = []
    for label, bundles in tabs.items():
        name = _sheet_name(label, used)
        data_name = _sheet_name(label, used, ' data') if include_traces else None
        rows = _peak_rows(store, bundles)
        contents.append({'Sheet': name, 'Samples': len(bundles), 'Peaks': len(rows),
                         'Traces': data_name or '-'})
        sheets.append((name, data_name, label, bundles, rows))
    _table(overview, row, ['Sheet', 'Samples', 'Peaks', 'Traces'], contents, number_format='0')
    overview.column_dimensions['A'].width = 26
    for column in 'BCD':
        overview.column_dimensions[column].width = 14
    overview.column_dimensions['D'].width = 26

    from openpyxl.utils import get_column_letter
    for name, data_name, label, bundles, rows in sheets:
        sheet = book.create_sheet(name)
        samples = [b.name for b in bundles]
        r = _title(sheet, label, f'{len(samples)} sample(s): ' + ', '.join(samples[:12]) +
                   (' …' if len(samples) > 12 else ''))
        r = _section(sheet, r, 'Peak areas · compound × sample (the same peak in every sample on one row)')
        table, header = _areas(rows, samples)
        r = _table(sheet, r, header, table)
        if any(row_['Concentration'] is not None for row_ in rows):
            r = _section(sheet, r, 'Concentrations · from the calibrations')
            conc, conc_header = _areas(rows, samples, 'Concentration')
            r = _table(sheet, r, conc_header, conc, number_format='0.000')
        r = _section(sheet, r, 'Peaks · one row per peak')
        _table(sheet, r, ['Sample', 'Channel', 'Peak', 'RT (min)', 'Start (min)', 'End (min)', 'Area', 'Height',
                          'Area %', 'Width (min)', 'Concentration', 'Integration'], rows)
        _widths(sheet)
        sheet.column_dimensions['A'].width = max(sheet.column_dimensions['A'].width or 0, 22)
        if data_name:
            data = book.create_sheet(data_name)
            _title(data, f'{label} · traces', 'Time and signal per sample and channel, as loaded (no smoothing).')
            _traces(store, data, bundles)

    calibrations = []
    for model in store.calibration_service.get_all_models().values():
        coefficients = list(model.coefficients or [])
        for point in model.standards:
            calibrations.append({'Analyte': model.analyte_name, 'Fit': model.fit_type,
                                 'Through zero': 'yes' if model.force_zero else 'no',
                                 'Coefficients': ', '.join(f'{c:.6g}' for c in coefficients),
                                 'R²': model.r_squared, 'Standard': point.sample_name,
                                 'Concentration': point.concentration, 'Units': model.units,
                                 'Response': point.area, 'Used': 'yes' if point.included else 'no'})
    if calibrations:
        sheet = book.create_sheet('Calibration')
        r = _title(sheet, 'Calibration', 'Standards and fitted curves')
        _table(sheet, r, ['Analyte', 'Fit', 'Through zero', 'Coefficients', 'R²', 'Standard', 'Concentration',
                          'Units', 'Response', 'Used'], calibrations)
        _widths(sheet)

    samples = []
    for label, bundles in tabs.items():
        for bundle in bundles:
            meta = (bundle.primary.metadata if bundle.primary else {}) or {}
            samples.append({'Tab': label, 'Sample': bundle.name,
                            'Channels': ', '.join(bundle.component_display_name(c) for c in bundle.component_list),
                            'Files': ', '.join(dict.fromkeys(c.original_filename for c in bundle.component_list)),
                            'Acquired': str(meta.get('acquired_at') or meta.get('acquisition_date') or
                                            meta.get('acquired') or '') or None,
                            'Sample type': meta.get('sample_type') or None})
    sheet = book.create_sheet('Samples')
    r = _title(sheet, 'Samples', 'Every sample, its channels and source files')
    _table(sheet, r, ['Tab', 'Sample', 'Channels', 'Files', 'Acquired', 'Sample type'], samples)
    _widths(sheet, maximum=70)

    history = []
    for entry in getattr(store, 'analysis_history', None) or []:
        agent = entry.get('agent') or {}
        history.append({'Time (UTC)': str(entry.get('at', '')).replace('T', ' ')[:19],
                        'Change': '; '.join(entry.get('trigger') or []) or ', '.join(sorted(entry.get('changes', {}))),
                        'By': ('MCP agent · ' + ' '.join(str(x) for x in (agent.get('client'), agent.get('model')) if x))
                        if agent else 'GeckoPlotter app'})
    if history:
        sheet = book.create_sheet('History')
        r = _title(sheet, 'Analysis history', 'Changes to data, peaks, calibrations and processing settings')
        _table(sheet, r, ['Time (UTC)', 'Change', 'By'], history)
        _widths(sheet, maximum=90)

    buffer = io.BytesIO()
    book.save(buffer)
    return buffer.getvalue()
