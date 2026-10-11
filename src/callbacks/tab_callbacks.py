# =============================================================================
# File: callbacks/tab_callbacks.py
# =============================================================================
"""
Tab callbacks for GeckoPlotter V2 - Handles tab content updates.
"""

import logging
import sys

import dash
from dash import html, callback, Input, Output, State, dcc
from typing import Dict, Any, List
import pandas as pd
import re
from components.data_table_editor import create_data_table_editor

log = logging.getLogger('geckoplotter.tabs')
if not log.handlers:
    _h = logging.StreamHandler(sys.stderr)
    _h.setFormatter(logging.Formatter('%(message)s'))
    log.addHandler(_h)
    log.setLevel(logging.DEBUG)


def register_tab_callbacks(app: dash.Dash, data_manager) -> None:
    """Register all tab-related callbacks."""

    def peak_sources(active_file_id):
        """LC-MS results cover the bundle while storage remains per channel."""
        bundle = data_manager.get_bundle(active_file_id)
        if bundle is None and hasattr(data_manager, 'get_bundle_for_component'):
            bundle = data_manager.get_bundle_for_component(active_file_id)
        if bundle is None or getattr(bundle.bundle_type, 'value', bundle.bundle_type) != 'lcms':
            return [(active_file_id, None)]
        from collections import Counter
        signals = [(component.component_id, bundle.component_display_name(component))
                   for component in bundle.component_list if component.dataframe is not None]
        counts = Counter(label for _, label in signals)
        seen = Counter()
        result = []
        for fid, label in signals:
            seen[label] += 1
            result.append((fid, f'{label} ({seen[label]})' if counts[label] > 1 else label))
        return result
    
    @app.callback(
        [Output('peak-table', 'data', allow_duplicate=True),
         Output('peak-table', 'columns', allow_duplicate=True),
         Output('peak-table', 'style_table', allow_duplicate=True),
         Output('peak-table-store', 'data', allow_duplicate=True)],
        [Input('active-file', 'data'),
         Input('peak-change-trigger', 'data'),
         Input('peak-name-persist-trigger', 'data'),
         Input('cross-sample-name-trigger', 'data'),
         Input('active-tab', 'data'),
         Input('cal-revision', 'data')],
        [State('loaded-files', 'data')],
        prevent_initial_call=True
    )
    def update_peak_analysis_tab(active_file_id, peak_change, _name_trigger, _xname_trigger, active_tab, cal_revision=0, loaded_files=None):
        """Update peak-table data in-place (preserves selections)."""

        HIDE = {'display': 'none'}
        SHOW = {'overflowX': 'auto', 'overflowY': 'auto', 'maxHeight': '500px'}

        if not active_file_id:
            return [], [], HIDE, None

        bundle = data_manager.get_bundle(active_file_id)

        try:
            if bundle and bundle.has_integration_data():
                peaks_exist = data_manager.peak_service.get_peaks(active_file_id)
                if not peaks_exist:
                    text = bundle.get_integration_text()
                    if text:
                        integration_results = parse_integration_results(text)
                        if integration_results:
                            time_arr, signal_arr = data_manager.get_xy_arrays(active_file_id)
                            if time_arr is not None:
                                data_manager.peak_service.import_instrument_peaks(
                                    file_id=active_file_id,
                                    parsed_results=integration_results,
                                    sample_name=bundle.name,
                                    time_axis=time_arr,
                                    signal=signal_arr,
                                )
                                data_manager.peak_service.group_peaks_across_samples(
                                    file_overlay_map=data_manager.build_file_overlay_map())

            from services.calibration_workflow import apply_calibrations
            calibration_results = apply_calibrations(data_manager)
            frames = []
            for fid, signal in peak_sources(active_file_id):
                frame = data_manager.peak_service.peaks_to_table(fid)
                if not frame.empty:
                    predictions = {peak.peak_id: calibration_results.get(f'{peak.file_id}:{peak.peak_id}', {})
                                   for peak in data_manager.peak_service.get_peaks(fid)}
                    for label, key in [('Concentration', 'concentration'), ('Concentration units', 'units'),
                                       ('Calibration', 'model'), ('Calibration status', 'status')]:
                        frame[label] = [predictions.get(pid, {}).get(key) for pid in frame['peak_id']]
                    if signal is not None:
                        frame.insert(1, 'Signal', signal)
                    frames.append(frame)
            df = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
            if df.empty:
                return [], [], HIDE, None

            if '_row_id' not in df.columns:
                df.insert(0, '_row_id', range(len(df)))
            hidden = {'_row_id', 'peak_id'}
            calculated = {'Signal', 'Concentration', 'Concentration units', 'Calibration', 'Calibration status'}
            columns = [
                {"name": col, "id": col,
                 "editable": col not in hidden and col not in calculated,
                 "selectable": col not in hidden,
                 "deletable": col not in hidden and col not in calculated,
                 "renamable": col not in hidden and col not in calculated}
                for col in df.columns if col not in hidden
            ]
            return df.to_dict('records'), columns, SHOW, df.to_json(orient='split')

        except Exception as e:
            log.exception(f"Error updating peak analysis tab: {e}")
            return [], [], HIDE, None

    @app.callback(Output('peak-analysis-empty', 'style'), Input('peak-table', 'data'))
    def show_peak_table_empty_state(rows):
        return {'display': 'none'} if rows else {'display': 'block'}

    @app.callback(
        [Output('selected-peak-idx', 'data', allow_duplicate=True),
         Output('active-file', 'data', allow_duplicate=True),
         Output('render-trigger', 'data', allow_duplicate=True)],
        Input('peak-table', 'active_cell'),
        [State('peak-table', 'derived_viewport_data'), State('peak-table', 'data'),
         State('active-file', 'data'), State('render-trigger', 'data'), State('view-mode', 'data')],
        prevent_initial_call=True,
    )
    def select_peak_table_row(cell, visible_rows, rows, active_file_id, render_counter, view_mode):
        if not cell or not active_file_id or (view_mode or 'raw') != 'raw':
            raise dash.exceptions.PreventUpdate
        displayed = visible_rows if visible_rows is not None else (rows or [])
        index = cell.get('row')
        if not isinstance(index, int) or not 0 <= index < len(displayed):
            raise dash.exceptions.PreventUpdate
        peak_id = displayed[index].get('peak_id')
        peak = next((peak for fid, _ in peak_sources(active_file_id)
                     for peak in data_manager.peak_service.get_peaks(fid) if peak.peak_id == peak_id), None)
        if peak is None:
            raise dash.exceptions.PreventUpdate
        owner = peak.file_id if peak.file_id != active_file_id else dash.no_update
        return peak.peak_id, owner, (render_counter or 0) + 1

    @app.callback(
        Output('peak-name-persist-trigger', 'data', allow_duplicate=True),
        Input('peak-table', 'data'),
        State('active-file', 'data'),
        prevent_initial_call=True
    )
    def persist_peak_names(table_data, active_file_id):
        """Write Peak Name edits from the peak-analysis table back to peak_service."""
        log.debug(f"[persist_peak_names] fired, active_file={active_file_id}, rows={len(table_data) if table_data else 0}")
        if not table_data or not active_file_id:
            return dash.no_update
        ps = data_manager.peak_service
        peaks = [peak for fid, _ in peak_sources(active_file_id) for peak in ps.get_peaks(fid)]
        if not peaks:
            log.debug("[persist_peak_names] no peaks in service")
            return dash.no_update
        changed = False
        for row in table_data:
            pid = row.get('peak_id')
            new_name = row.get('Peak Name', '')
            rt = row.get('RT (min)')
            log.debug(f"[persist_peak_names] row peak_id={pid!r}, RT={rt}, name={new_name!r}, keys={list(row.keys())}")
            if not new_name:
                continue
            matched = None
            if pid:
                matched = next((p for p in peaks if p.peak_id == pid), None)
            if matched is None and not pid and rt is not None:
                matched = next((p for p in peaks if abs(p.rt - float(rt)) < 0.01), None)
            if matched and matched.name != new_name:
                log.debug(f"[persist_peak_names] RENAME {matched.name!r} -> {new_name!r} (pid={matched.peak_id})")
                ps.rename_peak(matched.file_id, matched.peak_id, new_name)
                changed = True
        if changed:
            ps.group_peaks_across_samples(
                file_overlay_map=data_manager.build_file_overlay_map())
        log.debug(f"[persist_peak_names] changed={changed}")
        return {'ts': str(changed)} if changed else dash.no_update

    @app.callback(
        Output('cross-sample-name-trigger', 'data'),
        Input('cross-sample-table', 'data'),
        State('loaded-files', 'data'),
        prevent_initial_call=True
    )
    def persist_cross_sample_peak_names(table_data, loaded_files):
        """Write Peak Name edits from the cross-sample table back to peak_service.

        Snapshot service names BEFORE applying changes so that only the
        user-edited row triggers a rename.  rename_peak propagates via
        group_id, so the un-edited rows (which still show the old name
        in the table) won't overwrite the propagation.
        """
        log.debug(f"[persist_cross_sample] fired, rows={len(table_data) if table_data else 0}")
        if not table_data or not loaded_files:
            return dash.no_update
        ps = data_manager.peak_service

        snapshot = {}
        for row in table_data:
            sample = row.get('Sample', '')
            rt = row.get('RT (min)')
            if not sample or rt is None:
                continue
            bundle = next((b for b in data_manager.bundle_manager.bundles.values()
                           if b.base_name == sample), None)
            if not bundle:
                continue
            for p in ps.get_peaks(bundle.bundle_id):
                if abs(p.rt - float(rt)) < 0.01:
                    snapshot[(sample, rt)] = (p.name, bundle.bundle_id, p.peak_id)
                    break

        changed = False
        for row in table_data:
            sample = row.get('Sample', '')
            rt = row.get('RT (min)')
            new_name = row.get('Peak Name', '')
            if not sample or rt is None or not new_name:
                continue
            entry = snapshot.get((sample, rt))
            if not entry:
                continue
            old_name, bid, pid = entry
            if old_name != new_name:
                log.debug(f"[persist_cross_sample] RENAME {old_name!r} -> {new_name!r} (sample={sample})")
                ps.rename_peak(bid, pid, new_name)
                changed = True
        if changed:
            ps.group_peaks_across_samples(
                file_overlay_map=data_manager.build_file_overlay_map())
        log.debug(f"[persist_cross_sample] changed={changed}")
        return {'ts': str(changed)} if changed else dash.no_update

    def selected_comparison_ids(selected_ids, visible_selected_ids, selected_rows, visible_rows, rows):
        # Dash's selected_rows indexes the original data; row IDs survive sorting.
        chosen = visible_selected_ids if visible_selected_ids is not None else selected_ids
        if chosen is None:
            chosen = [(rows[index] or {}).get('id') for index in (selected_rows or [])
                      if isinstance(index, int) and 0 <= index < len(rows or [])]
        visible = {row.get('id') for row in (visible_rows if visible_rows is not None else rows or [])}
        return list(dict.fromkeys(key for key in chosen if key and key in visible))

    selection_inputs = [Input('cross-sample-table', 'selected_row_ids'),
                        Input('cross-sample-table', 'derived_virtual_selected_row_ids'),
                        Input('cross-sample-table', 'selected_rows'),
                        Input('cross-sample-table', 'derived_virtual_data'),
                        Input('cross-sample-table', 'data')]

    @app.callback(Output('cross-use-calibration-btn', 'disabled'), selection_inputs)
    def cross_calibration_disabled(selected_ids, visible_selected_ids, selected_rows, visible_rows, rows):
        return not selected_comparison_ids(selected_ids, visible_selected_ids, selected_rows, visible_rows, rows)

    @app.callback([Output('cal-import-peaks', 'data'),
                   Output('active-tab', 'data', allow_duplicate=True),
                   Output('cross-calibration-feedback', 'children')],
                  Input('cross-use-calibration-btn', 'n_clicks'),
                  [State(item.component_id, item.component_property) for item in selection_inputs],
                  prevent_initial_call=True)
    def use_cross_sample_peaks_for_calibration(clicks, selected_ids, visible_selected_ids,
                                               selected_rows, visible_rows, rows):
        if not clicks:
            return dash.no_update, dash.no_update, dash.no_update
        ids = selected_comparison_ids(selected_ids, visible_selected_ids, selected_rows, visible_rows, rows)
        if not ids:
            return dash.no_update, dash.no_update, 'Select peak rows to use as calibration standards.'
        from services.calibration_workflow import peak_candidates
        available = {peak['id'] for peak in peak_candidates(data_manager)}
        if any(key not in available for key in ids):
            return dash.no_update, dash.no_update, 'A selected peak is no longer available. Select the current peak rows.'
        import uuid
        return {'ids': ids, 'ts': str(uuid.uuid4())}, 'calibration', ''

    @app.callback(
        [Output('across-samples-container', 'children'),
         Output('cross-sample-table-store', 'data', allow_duplicate=True),
         Output('cross-sample-table', 'data', allow_duplicate=True),
         Output('cross-sample-table', 'columns', allow_duplicate=True),
         Output('cross-sample-table', 'style_table', allow_duplicate=True),
         Output('peak-group-selector', 'options', allow_duplicate=True),
         Output('peak-group-selector', 'value', allow_duplicate=True),
         Output('peak-group-selector-wrapper', 'style'),
         Output('retention-slider-wrapper', 'style')],
        [Input('loaded-files', 'data'),
         Input('peak-change-trigger', 'data')],
        prevent_initial_call=True
    )
    def update_across_samples_tab(loaded_files, peak_change):
        """Update the Across Samples tab with controls + selectable DataTable.

        NOTE: This does NOT depend on active-file — it's shared across all samples.
        It only rebuilds when files are added/removed (loaded-files changes).
        """
        HIDE = {'display': 'none'}
        SHOW_BLOCK = {'display': 'block', 'marginTop': '15px', 'padding': '10px',
                      'backgroundColor': '#f8f9fa', 'borderRadius': '4px'}
        empty_table = ([], [], HIDE)
        empty_controls = ([], None, HIDE, HIDE)

        if not loaded_files:
            return (html.P("Load multiple bundles to compare peaks across samples",
                         style={'color': '#666', 'textAlign': 'center', 'padding': '20px'}),
                    None, *empty_table, *empty_controls)

        bundles_with_peaks = _collect_bundles_with_peaks(data_manager, loaded_files)

        if len(bundles_with_peaks) < 2:
            return (html.P("Load at least 2 bundles with integration data to compare peaks",
                         style={'color': '#666', 'textAlign': 'center', 'padding': '20px'}),
                    None, *empty_table, *empty_controls)

        content, initial_json, group_options = create_across_samples_comparison_with_slider(bundles_with_peaks)

        table_data, table_cols, table_style = empty_table
        if initial_json:
            import io as _io
            df = pd.read_json(_io.StringIO(initial_json), orient='split')
            hidden = {'_row_id', 'id', 'file_id', 'peak_id'}
            table_cols = [
                {"name": col, "id": col,
                 "editable": col not in hidden,
                 "selectable": col not in hidden,
                 "deletable": False, "renamable": False}
                for col in df.columns if col not in hidden
            ]
            table_data = df.to_dict('records')
            table_style = {'overflowX': 'auto'}

        selector_style = {'display': 'block'} if group_options else HIDE
        slider_style = SHOW_BLOCK

        return (content, initial_json, table_data, table_cols, table_style,
                group_options, 0, selector_style, slider_style)

    # Handle peak group selection dropdown — updates cross-sample-table DATA
    # in-place (not replacing the component) so selections are preserved.
    @app.callback(
        [Output('cross-sample-table', 'data', allow_duplicate=True),
         Output('cross-sample-table', 'columns', allow_duplicate=True),
         Output('cross-sample-table-store', 'data', allow_duplicate=True)],
        [Input('peak-group-selector', 'value'),
         Input('retention-time-slider', 'value'),
         Input('peak-name-persist-trigger', 'data'),
         Input('cross-sample-name-trigger', 'data')],
        [State('loaded-files', 'data'),
         State('cross-sample-table', 'data')],
        prevent_initial_call=True
    )
    def update_selected_peak_group(selected_group_idx, time_window, _name_trigger, _xname_trigger, loaded_files, current_data):
        """Update cross-sample-table data when peak group selection or time window changes."""

        if selected_group_idx is None or not loaded_files:
            return dash.no_update, dash.no_update, dash.no_update

        if time_window is None:
            time_window = 0.2

        bundles_with_peaks = _collect_bundles_with_peaks(data_manager, loaded_files)

        if not bundles_with_peaks:
            return dash.no_update, dash.no_update, dash.no_update

        all_peaks = _collect_all_peaks(bundles_with_peaks)
        peak_groups = group_peaks_by_retention_time(all_peaks, time_window)
        comparison_groups = [g for g in peak_groups if len(g) > 1]

        if selected_group_idx < len(comparison_groups):
            selected_group = comparison_groups[selected_group_idx]
            df = cross_sample_group_to_dataframe(selected_group)
            if '_row_id' not in df.columns:
                df.insert(0, '_row_id', range(len(df)))

            if current_data:
                old_groups = {row.get('Sample', ''): row.get('Group', '')
                              for row in current_data if row.get('Group', '').strip()}
                if old_groups:
                    df['Group'] = df['Sample'].map(old_groups).fillna('')

            hidden = {'_row_id', 'id', 'file_id', 'peak_id'}
            columns = [
                {"name": col, "id": col,
                 "editable": True, "selectable": True,
                 "deletable": True, "renamable": True}
                for col in df.columns if col not in hidden
            ]
            return df.to_dict('records'), columns, df.to_json(orient='split')
        else:
            return dash.no_update, dash.no_update, dash.no_update

    @app.callback(
        [Output('cross-sample-table', 'data', allow_duplicate=True),
         Output('cross-sample-table-store', 'data', allow_duplicate=True)],
        Input('apply-group-btn', 'n_clicks'),
        [State('group-label-input', 'value'),
         State('cross-sample-table', 'selected_rows'),
         State('cross-sample-table', 'data')],
        prevent_initial_call=True
    )
    def apply_group_label(n_clicks, label, selected_rows, data):
        """Apply a group label to selected rows in the cross-sample table."""
        if not n_clicks or not label or not selected_rows or not data:
            raise PreventUpdate
        for idx in selected_rows:
            if 0 <= idx < len(data):
                data[idx]['Group'] = label.strip()
        df = pd.DataFrame(data)
        return data, df.to_json(orient='split')

    @app.callback(
        Output('cross-sample-table', 'data', allow_duplicate=True),
        Input('clear-groups-btn', 'n_clicks'),
        State('cross-sample-table', 'data'),
        prevent_initial_call=True
    )
    def clear_all_groups(n_clicks, data):
        """Clear all group labels from the cross-sample table."""
        if not n_clicks or not data:
            raise PreventUpdate
        for row in data:
            row['Group'] = ''
        return data

    GROUP_COLORS = [
        '#eaf2f7', '#faf5ed', '#edf5f0', '#f5f0f5',
        '#f0f5f0', '#f5f2ea', '#edf0f5', '#f5edea',
    ]

    @app.callback(
        [Output('peak-group-selector', 'options'),
         Output('peak-group-selector', 'value')],
        [Input('retention-time-slider', 'value')],
        [State('loaded-files', 'data')],
        prevent_initial_call=True
    )
    def update_group_options_on_slider(time_window, loaded_files):
        """Re-group peaks and update dropdown options when the slider changes."""
        if not loaded_files or time_window is None:
            return dash.no_update, dash.no_update

        bundles_with_peaks = _collect_bundles_with_peaks(data_manager, loaded_files)
        if len(bundles_with_peaks) < 2:
            return [], None

        all_peaks = _collect_all_peaks(bundles_with_peaks)
        peak_groups = group_peaks_by_retention_time(all_peaks, time_window)
        comparison_groups = [g for g in peak_groups if len(g) > 1]

        if not comparison_groups:
            return [], None

        group_options = []
        for i, group in enumerate(comparison_groups):
            avg_time = sum(p['retention_time'] for p in group) / len(group)
            samples = sorted(set(p['sample_name'] for p in group))
            samples_str = ', '.join(samples)
            group_options.append({
                'label': f"Group {i+1}: {avg_time:.2f} min - Found in {len(group)} samples ({samples_str})",
                'value': i
            })
        return group_options, 0

    @app.callback(
        Output('peak-group-selector', 'value', allow_duplicate=True),
        Input('selected-peak-idx', 'data'),
        [State('active-file', 'data'),
         State('loaded-files', 'data'),
         State('retention-time-slider', 'value')],
        prevent_initial_call=True
    )
    def sync_group_selector_to_selected_peak(selected_peak_id, active_file, loaded_files, time_window):
        """When a peak is clicked on the plot, jump the Across Samples dropdown to its group."""
        if not selected_peak_id or not active_file or not loaded_files:
            raise dash.exceptions.PreventUpdate

        peaks = data_manager.peak_service.get_peaks(active_file)
        selected = next((p for p in peaks if p.peak_id == selected_peak_id), None)
        if not selected:
            raise dash.exceptions.PreventUpdate

        bundle = data_manager.get_bundle_by_id(active_file)
        if not bundle:
            raise dash.exceptions.PreventUpdate
        sample_name = bundle.base_name

        if time_window is None:
            time_window = 0.2

        bundles_with_peaks = _collect_bundles_with_peaks(data_manager, loaded_files)
        if len(bundles_with_peaks) < 2:
            raise dash.exceptions.PreventUpdate

        all_peaks = _collect_all_peaks(bundles_with_peaks)
        peak_groups = group_peaks_by_retention_time(all_peaks, time_window)
        comparison_groups = [g for g in peak_groups if len(g) > 1]

        for idx, group in enumerate(comparison_groups):
            if any(p['sample_name'] == sample_name and abs(p['retention_time'] - selected.rt) < 0.001
                   for p in group):
                return idx

        raise dash.exceptions.PreventUpdate

    @app.callback(
        Output('peak-group-selector', 'value', allow_duplicate=True),
        Input('active-plot-tab', 'data'),
        State('custom-plot-figures', 'data'),
        prevent_initial_call=True
    )
    def sync_group_selector_to_plot_tab(active_tab_id, figures):
        """When switching to a custom plot tab from Across Samples, sync the dropdown."""
        if not active_tab_id or not figures:
            raise dash.exceptions.PreventUpdate
        entry = figures.get(active_tab_id)
        if not entry or entry.get('source_tab') != 'across-samples':
            raise dash.exceptions.PreventUpdate
        idx = entry.get('peak_group_idx')
        if idx is None:
            raise dash.exceptions.PreventUpdate
        return idx


def parse_integration_results(content: str) -> List[Dict[str, Any]]:
    """Parse integration results from text content using your proven method."""
    log.debug(f"Parsing Integration Results:")
    log.debug(f"   Content length: {len(content)}")
    
    try:
        import re
        import pandas as pd
        from io import StringIO
        
        section_title = "Integration Results"
        
        if section_title not in content:
            log.debug(f"   ❌ Section title '{section_title}' not found.")
            return []

        # Split the text at the section title
        section = content.split(section_title)[1]
        
        # IMPORTANT: Apply German number conversion to the entire section (your solution)
        original_section = section
        
        # Handle numbers like 1.234,56 -> 1234.56 (thousands separator + decimal)
        section = re.sub(r'\d{1,3}(?:\.\d{3})*,\d+', lambda m: m.group().replace('.', '').replace(',', '.'), section)
        
        # Handle simple numbers like 123,45 -> 123.45 (just decimal separator)
        section = re.sub(r'\b(\d+),(\d+)\b', r'\1.\2', section)
        
        # Handle numbers with leading/trailing whitespace in table cells
        section = re.sub(r'\t(\d+),(\d+)\t', r'\t\1.\2\t', section)
        section = re.sub(r'\t(\d+),(\d+)$', r'\t\1.\2', section, flags=re.MULTILINE)
        section = re.sub(r'^(\d+),(\d+)\t', r'\1.\2\t', section, flags=re.MULTILINE)
        
        log.debug(f"   ✅ Converted German number format")
        
        lines = section.strip().split('\n')
        
        # Find the header line (first non-empty line with actual column names)
        header_line = None
        header_idx = -1
        
        for i, line in enumerate(lines):
            line = line.strip()
            if not line:  # Skip empty lines
                continue
                
            # Check if this looks like a header line (contains column names)
            if any(keyword in line for keyword in ["No.", "Peak Name", "Retention Time", "Area", "Height"]):
                header_line = line
                header_idx = i
                log.debug(f"   Found header at line {i}: {line}")
                break
        
        if header_line is None:
            log.debug(f"   ❌ No header line found")
            return []
            
        # Find where the actual data starts (skip empty lines and units lines)
        data_lines = []
        
        for i in range(header_idx + 1, len(lines)):
            line = lines[i].strip()
            if not line:  # Skip empty lines
                continue
                
            # Skip units lines (typically contain only units like "min", "mAU", "%", etc.)
            line_parts = [part.strip() for part in line.split('\t')]
            is_units_line = all(
                part in ['', 'min', 'mAU', 'mAU*min', '%', 'n.a.'] 
                for part in line_parts if part
            )
            
            if is_units_line:
                log.debug(f"   Skipping units line: {line}")
                continue
            
            # Stop at Total line
            if 'Total:' in line:
                log.debug(f"   Found total line, stopping: {line}")
                break
            
            # This is a data line
            data_lines.append(line)
            log.debug(f"   Data line: {line}")
        
        if not data_lines:
            log.debug(f"   ❌ No data lines found")
            return []
        
        # Reconstruct the CSV content with proper header
        csv_lines = [header_line] + data_lines
        csv_content = '\n'.join(csv_lines)
        
        log.debug(f"   CSV content:\n{csv_content}")
        
        # Parse with pandas
        df = pd.read_csv(StringIO(csv_content), sep="\t")
        
        # Clean up column names (remove extra whitespace)
        df.columns = [col.strip() for col in df.columns]
        
        # Remove completely empty columns
        df = df.dropna(how="all", axis=1)
        
        # Remove completely empty rows
        df = df.dropna(how="all", axis=0)
        
        # Convert numeric columns properly
        for col in df.columns:
            if col in ['Retention Time', 'Area', 'Height', 'Relative Area', 'Relative Height']:
                df[col] = pd.to_numeric(df[col], errors='coerce')
        
        log.debug(f"   ✅ Parsed DataFrame:\n{df}")
        
        # Convert DataFrame to list of dictionaries
        results = []
        for _, row in df.iterrows():
            result = {
                'peak_number': int(row.iloc[0]) if pd.notna(row.iloc[0]) else 0,
                'peak_name': str(row.iloc[1]) if len(df.columns) > 1 and pd.notna(row.iloc[1]) else '',
                'retention_time': float(row['Retention Time']) if 'Retention Time' in df.columns and pd.notna(row['Retention Time']) else 0,
                'area': float(row['Area']) if 'Area' in df.columns and pd.notna(row['Area']) else 0,
                'height': float(row['Height']) if 'Height' in df.columns and pd.notna(row['Height']) else 0,
                'relative_area': float(row['Relative Area']) if 'Relative Area' in df.columns and pd.notna(row['Relative Area']) else 0,
                'relative_height': float(row['Relative Height']) if 'Relative Height' in df.columns and pd.notna(row['Relative Height']) else 0,
            }
            results.append(result)
            log.debug(f"   ✅ Parsed peak: {result}")
        
        log.debug(f"   Final results: {len(results)} peaks parsed")
        return results
        
    except Exception as e:
        log.exception(f"Error parsing integration results: {e}")
        return []


def group_peaks_by_retention_time(all_peaks, time_window=0.2):
    """Group peaks from different samples by retention time proximity.
    Peaks from the same sample are never placed in the same group."""
    sorted_peaks = sorted(all_peaks, key=lambda p: p['retention_time'])

    peak_groups = []
    for peak in sorted_peaks:
        placed = False
        for group in peak_groups:
            avg_rt = sum(p['retention_time'] for p in group) / len(group)
            samples_in_group = {p['sample_name'] for p in group}
            if abs(peak['retention_time'] - avg_rt) <= time_window and peak['sample_name'] not in samples_in_group:
                group.append(peak)
                placed = True
                break
        if not placed:
            peak_groups.append([peak])

    return peak_groups


def create_across_samples_comparison_with_slider(bundles_with_peaks: List[Dict[str, Any]]):
    """Create across samples peak comparison content and dropdown options.

    Returns (content, initial_json, group_options).
    The peak-group-selector and retention-time-slider live in the static
    layout; this function only returns data for them.
    """
    all_peaks = _collect_all_peaks(bundles_with_peaks)

    default_time_window = 0.2
    peak_groups = group_peaks_by_retention_time(all_peaks, default_time_window)
    comparison_groups = [group for group in peak_groups if len(group) > 1]

    group_options = []
    if comparison_groups:
        for i, group in enumerate(comparison_groups):
            avg_time = sum(p['retention_time'] for p in group) / len(group)
            samples = sorted(set(p['sample_name'] for p in group))
            samples_str = ', '.join(samples)
            group_options.append({
                'label': f"Group {i+1}: {avg_time:.2f} min - Found in {len(group)} samples ({samples_str})",
                'value': i
            })

    content = html.Div()
    if not comparison_groups:
        content = html.P("No peak groups found with the current time window. Try increasing the time window.",
                         style={'color': '#666', 'textAlign': 'center', 'padding': '20px'})

    initial_json = None
    if comparison_groups:
        default_df = cross_sample_group_to_dataframe(comparison_groups[0])
        if '_row_id' not in default_df.columns:
            default_df.insert(0, '_row_id', range(len(default_df)))
        initial_json = default_df.to_json(orient='split')

    return content, initial_json, group_options



def create_group_comparison_table(group):
    """Create a compact comparison table for a specific peak group."""
    
    # Calculate average retention time for the group
    avg_rt = sum(p['retention_time'] for p in group) / len(group)
    rt_std = (sum((p['retention_time'] - avg_rt) ** 2 for p in group) / len(group)) ** 0.5
    
    # Calculate total area across all samples for this peak group
    total_group_area = sum(p['area'] for p in group)
    
    # Compact header
    header = html.Div([
        html.H6(f"Peak Group Comparison - Average RT: {avg_rt:.3f} ± {rt_std:.3f} min", 
               style={'margin': '0 0 8px 0', 'color': '#333', 'fontSize': '14px'})
    ])
    
    # Create comparison table
    rows = []
    for peak in group:
        # Calculate this sample's contribution to the total peak group area
        cross_sample_relative = (peak['area'] / total_group_area * 100) if total_group_area > 0 else 0
        
        rows.append(html.Tr([
            html.Td(peak['sample_name'], style={'padding': '4px 6px', 'border': '1px solid #e0e0e0', 'fontWeight': 'bold', 'fontSize': '13px'}),
            html.Td(str(peak.get('peak_number', '')), style={'padding': '4px 6px', 'textAlign': 'center', 'border': '1px solid #e0e0e0', 'fontSize': '13px'}),
            html.Td(peak.get('peak_name', ''), style={'padding': '4px 6px', 'border': '1px solid #e0e0e0', 'fontSize': '13px'}),
            html.Td(f"{peak.get('retention_time', 0):.3f}", style={'padding': '4px 6px', 'textAlign': 'right', 'border': '1px solid #e0e0e0', 'fontSize': '13px'}),
            html.Td(f"{peak.get('area', 0):,.0f}", style={'padding': '4px 6px', 'textAlign': 'right', 'border': '1px solid #e0e0e0', 'fontSize': '13px'}),
            html.Td(f"{peak.get('height', 0):,.0f}", style={'padding': '4px 6px', 'textAlign': 'right', 'border': '1px solid #e0e0e0', 'fontSize': '13px'}),
            html.Td(f"{peak.get('relative_area', 0):.2f}", style={'padding': '4px 6px', 'textAlign': 'right', 'border': '1px solid #e0e0e0', 'fontSize': '13px'}),
            html.Td(f"{cross_sample_relative:.2f}", style={'padding': '4px 6px', 'textAlign': 'right', 'border': '1px solid #e0e0e0', 'fontSize': '13px', 'fontWeight': 'bold', 'backgroundColor': '#f5f5f5'}),
        ]))
    
    # Add total row
    total_row = html.Tr([
        html.Td("Total:", style={'padding': '4px 6px', 'fontWeight': 'bold', 'backgroundColor': '#f8f9fa', 'border': '1px solid #e0e0e0', 'fontSize': '13px'}),
        html.Td("", style={'padding': '4px 6px', 'backgroundColor': '#f8f9fa', 'border': '1px solid #e0e0e0'}),
        html.Td("", style={'padding': '4px 6px', 'backgroundColor': '#f8f9fa', 'border': '1px solid #e0e0e0'}),
        html.Td("", style={'padding': '4px 6px', 'backgroundColor': '#f8f9fa', 'border': '1px solid #e0e0e0'}),
        html.Td(f"{total_group_area:,.0f}", style={'padding': '4px 6px', 'textAlign': 'right', 'fontWeight': 'bold', 'backgroundColor': '#f8f9fa', 'border': '1px solid #e0e0e0', 'fontSize': '13px'}),
        html.Td("", style={'padding': '4px 6px', 'backgroundColor': '#f8f9fa', 'border': '1px solid #e0e0e0'}),
        html.Td("", style={'padding': '4px 6px', 'backgroundColor': '#f8f9fa', 'border': '1px solid #e0e0e0'}),
        html.Td("100.00", style={'padding': '4px 6px', 'textAlign': 'right', 'fontWeight': 'bold', 'backgroundColor': '#f8f9fa', 'border': '1px solid #e0e0e0', 'fontSize': '13px'}),
    ])
    
    table = html.Table([
        html.Tr([
            html.Th("Sample", style={'padding': '6px', 'fontWeight': 'bold', 'backgroundColor': '#f8f9fa', 'border': '1px solid #e0e0e0', 'fontSize': '13px'}),
            html.Th("Peak #", style={'padding': '6px', 'fontWeight': 'bold', 'backgroundColor': '#f8f9fa', 'border': '1px solid #e0e0e0', 'fontSize': '13px'}),
            html.Th("Peak Name", style={'padding': '6px', 'fontWeight': 'bold', 'backgroundColor': '#f8f9fa', 'border': '1px solid #e0e0e0', 'fontSize': '13px'}),
            html.Th("RT (min)", style={'padding': '6px', 'fontWeight': 'bold', 'backgroundColor': '#f8f9fa', 'border': '1px solid #e0e0e0', 'fontSize': '13px'}),
            html.Th("Area", style={'padding': '6px', 'fontWeight': 'bold', 'backgroundColor': '#f8f9fa', 'border': '1px solid #e0e0e0', 'fontSize': '13px'}),
            html.Th("Height", style={'padding': '6px', 'fontWeight': 'bold', 'backgroundColor': '#f8f9fa', 'border': '1px solid #e0e0e0', 'fontSize': '13px'}),
            html.Th("Within Sample (%)", style={'padding': '6px', 'fontWeight': 'bold', 'backgroundColor': '#f8f9fa', 'border': '1px solid #e0e0e0', 'fontSize': '13px'}),
            html.Th("Cross-Sample (%)", style={'padding': '6px', 'fontWeight': 'bold', 'backgroundColor': '#f5f5f5', 'border': '1px solid #e0e0e0', 'fontSize': '13px'}),
        ])
    ] + rows + [total_row], style={
        'width': '100%',
        'borderCollapse': 'collapse',
        'fontSize': '13px'
    })
    
    return html.Div([header, table])


def create_integration_results_table(results: List[Dict[str, Any]], sample_name: str) -> html.Div:
    """Create a compact table displaying integration results."""
    
    # Create table header
    header = html.Tr([
        html.Th("No.", style={'padding': '6px', 'fontWeight': 'bold', 'backgroundColor': '#f8f9fa', 'border': '1px solid #e0e0e0', 'fontSize': '13px'}),
        html.Th("Peak Name", style={'padding': '6px', 'fontWeight': 'bold', 'backgroundColor': '#f8f9fa', 'border': '1px solid #e0e0e0', 'fontSize': '13px'}),
        html.Th("RT (min)", style={'padding': '6px', 'fontWeight': 'bold', 'backgroundColor': '#f8f9fa', 'border': '1px solid #e0e0e0', 'fontSize': '13px'}),
        html.Th("Area", style={'padding': '6px', 'fontWeight': 'bold', 'backgroundColor': '#f8f9fa', 'border': '1px solid #e0e0e0', 'fontSize': '13px'}),
        html.Th("Height", style={'padding': '6px', 'fontWeight': 'bold', 'backgroundColor': '#f8f9fa', 'border': '1px solid #e0e0e0', 'fontSize': '13px'}),
        html.Th("Rel. Area (%)", style={'padding': '6px', 'fontWeight': 'bold', 'backgroundColor': '#f8f9fa', 'border': '1px solid #e0e0e0', 'fontSize': '13px'}),
        html.Th("Rel. Height (%)", style={'padding': '6px', 'fontWeight': 'bold', 'backgroundColor': '#f8f9fa', 'border': '1px solid #e0e0e0', 'fontSize': '13px'}),
    ])
    
    # Create table rows
    rows = []
    for result in results:
        row = html.Tr([
            html.Td(str(result.get('peak_number', '')), style={'padding': '4px 6px', 'textAlign': 'center', 'border': '1px solid #e0e0e0', 'fontSize': '13px'}),
            html.Td(result.get('peak_name', ''), style={'padding': '4px 6px', 'border': '1px solid #e0e0e0', 'fontSize': '13px'}),
            html.Td(f"{result.get('retention_time', 0):.3f}", style={'padding': '4px 6px', 'textAlign': 'right', 'border': '1px solid #e0e0e0', 'fontSize': '13px'}),
            html.Td(f"{result.get('area', 0):,.0f}", style={'padding': '4px 6px', 'textAlign': 'right', 'border': '1px solid #e0e0e0', 'fontSize': '13px'}),
            html.Td(f"{result.get('height', 0):,.0f}", style={'padding': '4px 6px', 'textAlign': 'right', 'border': '1px solid #e0e0e0', 'fontSize': '13px'}),
            html.Td(f"{result.get('relative_area', 0):.2f}", style={'padding': '4px 6px', 'textAlign': 'right', 'border': '1px solid #e0e0e0', 'fontSize': '13px'}),
            html.Td(f"{result.get('relative_height', 0):.2f}", style={'padding': '4px 6px', 'textAlign': 'right', 'border': '1px solid #e0e0e0', 'fontSize': '13px'}),
        ])
        rows.append(row)
    
    # Calculate totals
    total_area = sum(r.get('area', 0) for r in results)
    total_height = sum(r.get('height', 0) for r in results)
    
    # Add total row
    total_row = html.Tr([
        html.Td("Total:", style={'padding': '4px 6px', 'fontWeight': 'bold', 'backgroundColor': '#f8f9fa', 'border': '1px solid #e0e0e0', 'fontSize': '13px'}),
        html.Td("", style={'padding': '4px 6px', 'backgroundColor': '#f8f9fa', 'border': '1px solid #e0e0e0'}),
        html.Td("", style={'padding': '4px 6px', 'backgroundColor': '#f8f9fa', 'border': '1px solid #e0e0e0'}),
        html.Td(f"{total_area:,.0f}", style={'padding': '4px 6px', 'textAlign': 'right', 'fontWeight': 'bold', 'backgroundColor': '#f8f9fa', 'border': '1px solid #e0e0e0', 'fontSize': '13px'}),
        html.Td(f"{total_height:,.0f}", style={'padding': '4px 6px', 'textAlign': 'right', 'fontWeight': 'bold', 'backgroundColor': '#f8f9fa', 'border': '1px solid #e0e0e0', 'fontSize': '13px'}),
        html.Td("100.00", style={'padding': '4px 6px', 'textAlign': 'right', 'fontWeight': 'bold', 'backgroundColor': '#f8f9fa', 'border': '1px solid #e0e0e0', 'fontSize': '13px'}),
        html.Td("100.00", style={'padding': '4px 6px', 'textAlign': 'right', 'fontWeight': 'bold', 'backgroundColor': '#f8f9fa', 'border': '1px solid #e0e0e0', 'fontSize': '13px'}),
    ])
    
    return html.Div([
        html.Table([header] + rows + [total_row],
                  style={
                      'width': '100%',
                      'borderCollapse': 'collapse',
                      'fontSize': '13px',
                      'border': '1px solid #e0e0e0'
                  })
    ])


def peaks_to_dataframe(integration_results, sample_name=None):
    """Convert parsed integration results to a DataFrame for the pub-table."""
    rows = []
    for r in integration_results:
        row = {
            'Peak Name': r.get('peak_name', ''),
            'RT (min)': round(r.get('retention_time', 0), 3),
            'Area': round(r.get('area', 0), 1),
            'Height': round(r.get('height', 0), 1),
            'Rel. Area (%)': round(r.get('relative_area', 0), 2),
            'Rel. Height (%)': round(r.get('relative_height', 0), 2),
        }
        if sample_name:
            row = {'Sample': sample_name, **row}
        rows.append(row)
    return pd.DataFrame(rows)


def cross_sample_group_to_dataframe(group):
    """Convert a cross-sample peak group to a DataFrame for the pub-table."""
    total_area = sum(p.get('area', 0) for p in group)
    rows = []
    for p in group:
        cross_pct = (p['area'] / total_area * 100) if total_area > 0 else 0
        rows.append({
            'id': f"{p['file_id']}:{p['peak_id']}" if p.get('file_id') and p.get('peak_id') else None,
            'file_id': p.get('file_id'),
            'peak_id': p.get('peak_id'),
            'Sample': p.get('sample_name', ''),
            'Group': '',
            'Peak Name': p.get('peak_name', ''),
            'RT (min)': round(p.get('retention_time', 0), 3),
            'Area': round(p.get('area', 0), 1),
            'Height': round(p.get('height', 0), 1),
            'Within Sample (%)': round(p.get('relative_area', 0), 2),
            'Cross-Sample (%)': round(cross_pct, 2),
        })
    return pd.DataFrame(rows)


def _collect_bundles_with_peaks(data_manager, loaded_files):
    """Collect all bundles that have integration data.

    Also stores/updates peaks in PeakService so cross-sample grouping
    and persistence work through the service layer.
    """
    bundles_with_peaks = []
    for bundle_id in list(data_manager.loaded_data.keys()):
        bundle = data_manager.get_bundle(bundle_id)
        if not bundle:
            continue

        if bundle.has_integration_data():
            peaks_exist = data_manager.peak_service.get_peaks(bundle_id)
            if not peaks_exist:
                try:
                    text = bundle.get_integration_text()
                    if text:
                        results = parse_integration_results(text)
                        if results:
                            time_arr, signal_arr = data_manager.get_xy_arrays(bundle_id)
                            if time_arr is not None:
                                data_manager.peak_service.import_instrument_peaks(
                                    file_id=bundle_id,
                                    parsed_results=results,
                                    sample_name=bundle.name,
                                    time_axis=time_arr,
                                    signal=signal_arr,
                                )
                                data_manager.peak_service.group_peaks_across_samples(
                                    file_overlay_map=data_manager.build_file_overlay_map())
                except Exception:
                    continue

        service_peaks = data_manager.peak_service.get_peaks(bundle_id)
        if service_peaks:
            total_area = sum(max(float(p.area or 0.0), 0.0) for p in service_peaks)
            total_height = sum(max(float(p.height or 0.0), 0.0) for p in service_peaks)
            peak_dicts = []
            for i, p in enumerate(sorted(service_peaks, key=lambda pk: pk.rt), start=1):
                peak_dicts.append({
                    'file_id': p.file_id,
                    'peak_id': p.peak_id,
                    'peak_number': i,
                    'peak_name': p.name,
                    'retention_time': p.rt,
                    'area': p.area,
                    'height': p.height,
                    'relative_area': (p.area / total_area * 100.0) if total_area > 0 else 0.0,
                    'relative_height': (p.height / total_height * 100.0) if total_height > 0 else 0.0,
                    'source': p.source,
                })
            bundles_with_peaks.append({'bundle': bundle, 'peaks': peak_dicts})
    return bundles_with_peaks


def _collect_all_peaks(bundles_with_peaks):
    """Flatten all peaks from bundles into a single list with sample names."""
    all_peaks = []
    for bd in bundles_with_peaks:
        bundle = bd['bundle']
        for peak in bd['peaks']:
            all_peaks.append({
                'file_id': peak.get('file_id'),
                'peak_id': peak.get('peak_id'),
                'sample_name': bundle.name,
                'peak_number': peak.get('peak_number', 0),
                'peak_name': peak.get('peak_name', ''),
                'retention_time': peak.get('retention_time', 0),
                'area': peak.get('area', 0),
                'height': peak.get('height', 0),
                'relative_area': peak.get('relative_area', 0),
                'relative_height': peak.get('relative_height', 0),
            })
    return all_peaks
