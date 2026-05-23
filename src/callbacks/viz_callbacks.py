# =============================================================================
# File: callbacks/viz_callbacks.py
# =============================================================================
"""
Visualization callbacks for GeckoPlotter V2.
"""

import logging
import sys
from typing import Dict, Any, Optional
import dash
from dash import Input, Output, State, html, dash_table
import numpy as np
import pandas as pd
from services.plot_manager import PlotManager
from services.storage_manager import DataManager
from components.data_table_editor import create_data_table_editor
from components.publication_plot import create_publication_plot

log = logging.getLogger('geckoplotter.viz')
if not log.handlers:
    _h = logging.StreamHandler(sys.stderr)
    _h.setFormatter(logging.Formatter('%(message)s'))
    log.addHandler(_h)
    log.setLevel(logging.DEBUG)


def prepare_table_data(file_data, file_id=None, visible_wells=None):
    """
    Prepare data for the table editor, following table_playground.py logic:
    - For generic CSV: add _row_id column
    - For UV-Vis: extract only the plotted well data (Wavelength + selected well)
    - For chromatograms: use time + intensity
    """
    if file_data is None or file_data.get('data') is None:
        return None
    
    data = file_data['data']
    file_type = file_data.get('metadata', {}).get('file_type') or file_data.get('type')
    
    log.debug(f"🔍 prepare_table_data: file_type={file_type}, visible_wells={visible_wells}, file_id={file_id}")
    
    # For UV-Vis data: extract only the well data (no metadata)
    if file_type == 'uvvis_csv':
        # If it's a well selection (file_id contains |)
        if file_id and '|' in file_id:
            _, well_name = file_id.split('|', 1)
            if 'Wavelength' in data.columns and well_name in data.columns:
                # Extract just Wavelength and the selected well
                table_data = data[['Wavelength', well_name]].copy()
                table_data = table_data.dropna()
                log.debug(f"✅ Extracted UV-Vis well data: Wavelength + {well_name} ({len(table_data)} rows)")
            else:
                table_data = data.copy()
                log.debug(f"⚠️ Could not extract well {well_name}, using full data")
        # If multiple wells are visible, show all visible wells
        elif visible_wells and len(visible_wells) > 0:
            cols = ['Wavelength'] + [w for w in visible_wells if w in data.columns]
            table_data = data[cols].copy()
            table_data = table_data.dropna()
            log.debug(f"✅ Extracted UV-Vis data for {len(visible_wells)} wells: {visible_wells} ({len(table_data)} rows)")
        else:
            # Show all well data (Wavelength + all wells)
            # The UV-Vis reader already filtered out metadata - data only contains Wavelength + wells
            table_data = data.copy()
            log.debug(f"✅ Using full UV-Vis well data: Wavelength + {len(data.columns)-1} wells ({len(table_data)} rows)")
    # For generic CSV: just use the data as-is
    elif file_type == 'generic_csv':
        table_data = data.copy()
        log.debug(f"✅ Using generic CSV data: {len(table_data)} rows × {len(table_data.columns)} columns")
        log.debug(f"   Columns: {list(table_data.columns)[:10]}")  # Show first 10 columns
        log.debug(f"   First row: {table_data.iloc[0].to_dict() if len(table_data) > 0 else 'empty'}")
    # For chromatograms: use time + intensity
    else:
        table_data = data.copy()
        log.debug(f"✅ Using chromatogram data: {len(table_data)} rows")
    
    # Add _row_id if not present (like table_playground.py does)
    if '_row_id' not in table_data.columns:
        table_data.insert(0, '_row_id', range(len(table_data)))
        log.debug(f"✅ Added _row_id column")
    
    return table_data


def _rgba(hex_color, alpha):
    """Convert #RRGGBB to rgba(...) while accepting existing rgba values."""
    if isinstance(hex_color, str) and hex_color.startswith('#') and len(hex_color) == 7:
        r = int(hex_color[1:3], 16)
        g = int(hex_color[3:5], 16)
        b = int(hex_color[5:7], 16)
        return f'rgba({r}, {g}, {b}, {alpha})'
    return hex_color


def _add_deselect_catcher(fig, dm, active_file_id):
    """Add a near-transparent plot-area trace that clicks to deselect."""
    import plotly.graph_objects as go

    file_data = dm.get_data_by_id(active_file_id)
    if file_data is None:
        bundle = dm.get_bundle_by_id(active_file_id)
        if bundle and bundle.main_file:
            file_data = dm.get_data_by_id(bundle.main_file.get('id'))
    if not file_data or file_data.get('data') is None:
        return

    df = file_data['data']
    time_col = signal_col = None
    for col in df.columns:
        cl = col.lower()
        if 'time' in cl:
            time_col = col
        elif any(k in cl for k in ('value', 'intensity', 'mau', 'absorbance', 'signal')):
            signal_col = col
    if time_col is None or signal_col is None:
        return

    try:
        x_vals = df[time_col].to_numpy(dtype=float)
        y_vals = df[signal_col].to_numpy(dtype=float)
    except Exception:
        return

    finite_x = x_vals[np.isfinite(x_vals)]
    finite_y = y_vals[np.isfinite(y_vals)]
    if finite_x.size < 2 or finite_y.size < 2:
        return

    x0, x1 = float(np.nanmin(finite_x)), float(np.nanmax(finite_x))
    y0, y1 = float(np.nanmin(finite_y)), float(np.nanmax(finite_y))
    y_pad = max((y1 - y0) * 0.08, 1e-9)
    y0 -= y_pad
    y1 += y_pad

    fig.add_trace(go.Scatter(
        x=[x0, x1, x1, x0, x0],
        y=[y0, y0, y1, y1, y0],
        fill='toself',
        fillcolor='rgba(255,255,255,0.001)',
        mode='lines',
        line=dict(width=0, color='rgba(255,255,255,0)'),
        customdata=[['__deselect__', 'catcher']] * 5,
        hoverinfo='skip',
        showlegend=False,
        meta='peak_overlay',
    ))


def _overlay_peaks_on_figure(dm, active_file_id, figure, selected_peak_id=None):
    """Overlay manual/imported/detected peak markers on the raw figure."""
    import plotly.graph_objects as go
    fig = go.Figure(figure) if isinstance(figure, dict) else figure
    fig.layout.shapes = ()
    fig.update_layout(uirevision='main-plot')

    all_peaks = dm.peak_service.get_peaks(active_file_id)
    if not all_peaks:
        return fig

    def _marker_y(rt: float, fallback: float) -> float:
        file_data = dm.get_data_by_id(active_file_id)
        if file_data is None:
            bundle = dm.get_bundle_by_id(active_file_id)
            if bundle and bundle.main_file:
                file_data = dm.get_data_by_id(bundle.main_file.get('id'))
        if not file_data or file_data.get('data') is None:
            return fallback

        df = file_data['data']
        time_col = signal_col = None
        for col in df.columns:
            cl = col.lower()
            if 'time' in cl:
                time_col = col
            elif any(k in cl for k in ('value', 'intensity', 'mau', 'absorbance', 'signal')):
                signal_col = col
        if time_col is None or signal_col is None:
            return fallback

        try:
            x = df[time_col].to_numpy(dtype=float)
            y = df[signal_col].to_numpy(dtype=float)
            return float(np.interp(rt, x, y))
        except Exception:
            return fallback

    FILL_COLORS = [
        'rgba(180, 120, 220, 0.30)',
        'rgba(100, 180, 120, 0.30)',
        'rgba(80, 160, 220, 0.30)',
        'rgba(220, 160, 80, 0.30)',
        'rgba(220, 100, 120, 0.30)',
        'rgba(120, 200, 200, 0.30)',
    ]

    for i, peak in enumerate(all_peaks):
        is_selected = peak.peak_id == selected_peak_id
        fill_color = _rgba(peak.color, 0.58 if is_selected else 0.30) if peak.color else FILL_COLORS[i % len(FILL_COLORS)]
        line_color = peak.color if is_selected else 'rgba(0,0,0,0)'

        has_custom_label = bool(peak.label) if hasattr(peak, 'label') else False

        if peak.poly_x and peak.poly_y:
            poly_x = list(peak.poly_x)
            poly_y = list(peak.poly_y)
            fig.add_trace(go.Scatter(
                x=poly_x, y=poly_y,
                fill='toself', fillcolor=fill_color,
                mode='lines',
                line=dict(color=line_color, width=2 if is_selected else 0),
                customdata=[peak.peak_id] * len(poly_x),
                hoverinfo='skip',
                showlegend=False, meta='peak_overlay',
            ))
            if has_custom_label:
                fig.add_trace(go.Scatter(
                    x=[peak.rt], y=[peak.height],
                    mode='text',
                    text=[peak.label],
                    textposition='top center',
                    textfont=dict(size=9, color='#333'),
                    hoverinfo='skip',
                    showlegend=False, meta='peak_overlay',
                ))
            if is_selected and peak.p_line and len(peak.p_line) == 2:
                p0, p1 = peak.p_line
                line_color = peak.color or '#E69F00'
                fig.add_shape(
                    type='line',
                    x0=p0[0], y0=p0[1],
                    x1=p1[0], y1=p1[1],
                    name=f'baseline:{peak.peak_id}',
                    line=dict(color=line_color, width=2, dash='dot'),
                    editable=True,
                )
                fig.add_trace(go.Scatter(
                    x=[p0[0], p1[0]],
                    y=[p0[1], p1[1]],
                    mode='markers',
                    marker=dict(
                        size=9,
                        color='#ffffff',
                        line=dict(color=line_color, width=2),
                        symbol='circle',
                    ),
                    customdata=[[peak.peak_id, 'p-point'], [peak.peak_id, 'p-point']],
                    hoverinfo='skip',
                    showlegend=False,
                    meta='peak_overlay',
                ))
        elif has_custom_label:
            marker_y = _marker_y(peak.rt, peak.height)
            fig.add_trace(go.Scatter(
                x=[peak.rt], y=[marker_y],
                mode='text',
                text=[peak.label],
                textposition='top center',
                textfont=dict(size=9, color='#333'),
                hovertemplate=f'{peak.name}<br>RT: {peak.rt:.3f}<br>Area: {peak.area:.1f}<extra></extra>',
                showlegend=False, meta='peak_overlay',
            ))

    return fig


def _get_source_category(metadata, fdata):
    """Return the instrument/source category for a file."""
    ft = metadata.get('file_type') or fdata.get('record', {}).get('type', '')
    if ft in ('chromatogram', 'text'):
        return 'chromatogram'
    if ft == 'uvvis_csv':
        return 'uvvis'
    if ft in ('lcms_cdf', 'lcms_ms_positive', 'lcms_ms_negative'):
        return 'lcms_ms'
    if ft in ('lcms_vwd_cdf', 'lcms_uv_a', 'lcms_uv_b'):
        return 'lcms_uv'
    return 'generic'


def _get_x_axis_name(metadata, fdata):
    """Return the X-axis column name for a file."""
    if metadata.get('auto_x'):
        return metadata['auto_x']

    ft = metadata.get('file_type') or fdata.get('record', {}).get('type', '')
    if ft in ('chromatogram', 'text'):
        return 'Time (min)'
    if ft == 'uvvis_csv':
        return 'Wavelength'
    if ft in ('lcms_cdf', 'lcms_ms_positive', 'lcms_ms_negative'):
        return 'm/z'
    if ft in ('lcms_vwd_cdf', 'lcms_uv_a', 'lcms_uv_b'):
        return 'Time (min)'

    data = fdata.get('data')
    if data is not None and hasattr(data, 'columns') and len(data.columns) > 0:
        return data.columns[0]

    return 'unknown'


def _get_overlay_group(metadata, fdata):
    """Return composite key (source_category, x_axis) for overlay grouping.

    Files overlay when they share both the same source type AND the same
    X-axis name.  This prevents e.g. a chromatogram (Time vs mAU) from
    mixing with a generic CSV that also has a Time column.
    """
    return (_get_source_category(metadata, fdata),
            _get_x_axis_name(metadata, fdata))


def _get_active_file_group(dm, active_file_id):
    """Return the group key for the active file."""
    if not active_file_id:
        return None
    fdata = dm.get_data_by_id(active_file_id)
    if not fdata:
        # Check bundles
        bundle = dm.get_bundle_by_id(active_file_id)
        if bundle and bundle.main_file:
            fdata = dm.get_data_by_id(bundle.main_file.get('id'))
    if not fdata:
        return None
    metadata = fdata.get('metadata', {})
    return _get_overlay_group(metadata, fdata)


def _collect_visible_files(dm, active_file_id=None, loaded_files=None):
    """Return dict of {group_key: [(name, file_data), ...]} for visible files.

    Only returns files matching the active file's type so different data
    types don't get mixed. The eye icon controls visibility within the group.
    Files not present in *loaded_files* (if given) are skipped to prevent
    stale data from previous uploads leaking in.
    """
    vis_state = getattr(dm, 'visibility_state', {})

    # Determine which group to show based on active file
    target_group = _get_active_file_group(dm, active_file_id) if active_file_id else None

    # Build set of IDs that are actually loaded in the UI right now
    valid_ids: set | None = None
    if loaded_files:
        valid_ids = set()
        for rec in loaded_files:
            valid_ids.add(rec.get('id'))
        # Also add bundle IDs that map to valid main-file IDs
        for bundle in dm.bundle_manager.bundles.values():
            main = bundle.main_file
            if main and main.get('id') in valid_ids:
                valid_ids.add(bundle.bundle_id)

    # Build set of main-file IDs represented by a bundle (skip raw dupes)
    bundled_main_ids: set = set()
    bundle_ids: set = set()
    for bundle in dm.bundle_manager.bundles.values():
        main = bundle.main_file
        if main:
            bundled_main_ids.add(main.get('id'))
            bundle_ids.add(bundle.bundle_id)
    for bkey in dm.lcms_bundles:
        bundle_ids.add(bkey)

    from collections import defaultdict
    groups = defaultdict(list)

    # First pass: collect all candidate files and their groups
    candidates = []
    print(f"🔍 _collect_visible_files: active={active_file_id}, valid_ids={valid_ids}, bundled_main_ids={bundled_main_ids}, bundle_ids={bundle_ids}")
    for fid, fdata in dm.loaded_data.items():
        if valid_ids is not None and fid not in valid_ids:
            print(f"  ❌ {fid}: not in valid_ids")
            continue
        if fid in bundled_main_ids and fid not in bundle_ids:
            print(f"  ❌ {fid}: bundled main (raw dupe)")
            continue
        if fdata.get('type') == 'lcms_bundle':
            print(f"  ❌ {fid}: lcms_bundle type")
            continue
        metadata = fdata.get('metadata', {})
        group = _get_overlay_group(metadata, fdata)
        print(f"  ✅ {fid}: group={group}, name={fdata.get('record', {}).get('name', '?')}")
        candidates.append((fid, fdata, metadata, group))

    # If active file was deleted/invalid, fall back to the first candidate's group
    if not target_group and candidates:
        target_group = candidates[0][3]

    for fid, fdata, metadata, group in candidates:
        file_type = metadata.get('file_type') or fdata.get('record', {}).get('type', '')

        if target_group and group != target_group:
            continue

        if file_type == 'uvvis_csv':
            filled_wells = metadata.get('filled_wells', [])
            vis_wells = []
            for well in filled_wells:
                well_id = f"{fid}|{well}"
                if vis_state.get(well_id, True):
                    vis_wells.append(well)
            if vis_wells:
                sub_df = fdata['data'][['Wavelength'] + vis_wells].copy()
                sub_data = {**fdata, 'data': sub_df}
                name = fdata.get('record', {}).get('name', fid)
                groups[group].append((name, sub_data))
        else:
            if vis_state.get(fid, True):
                name = fdata.get('record', {}).get('name', fid)
                groups[group].append((name, fdata))

    return dict(groups)


def register_viz_callbacks(app: dash.Dash, data_manager: DataManager) -> None:
    """Register visualization-related callbacks."""

    plot_manager = PlotManager()

    # File types that have a dedicated raw-data plot and should NOT auto-switch
    KNOWN_RAW_TYPES = {
        'chromatogram', 'text', 'uvvis_csv',
        'lcms_cdf', 'lcms_ms_positive', 'lcms_ms_negative',
        'lcms_vwd_cdf', 'lcms_uv_a', 'lcms_uv_b', 'lcms_bundle',
    }

    @app.callback(
        [Output('main-plot', 'figure', allow_duplicate=True),
         Output('active-file', 'data', allow_duplicate=True),
         Output('metadata-container', 'children', allow_duplicate=True),
         Output('table-editor-container', 'children', allow_duplicate=True),
         Output('pub-data-store', 'data', allow_duplicate=True),
         Output('view-mode', 'data', allow_duplicate=True)],
        [Input({'type': 'file-tree-item', 'index': dash.dependencies.ALL}, 'n_clicks')],
        [State('loaded-files', 'data'),
         State('active-file', 'data'),
         State('view-mode', 'data'),
         State('active-tab', 'data')],
        prevent_initial_call=True
    )
    def handle_file_selection(n_clicks_list, loaded_files, active_file, view_mode, active_tab):
        """Handle file selection from the tree."""
        
        from components.axis_mapper import get_empty_selections
        
        # Check if any file was clicked
        ctx = dash.callback_context
        if not ctx.triggered:
            return dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update

        # Find which file was clicked
        triggered_id = ctx.triggered[0]['prop_id']
        if 'n_clicks' not in triggered_id:
            return dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update

        # Extract file ID from the triggered component
        import json
        try:
            # Parse the component ID from the prop_id
            # Use rsplit to handle IDs containing periods (e.g. "lys - 2.5 mM")
            component_str = triggered_id.rsplit('.', 1)[0]
            component_id = json.loads(component_str)
            file_id = component_id['index']
            
            # IMPORTANT: Check if this is a control button click
            # Control buttons have different component types
            if ('visibility-btn' in triggered_id or 
                'delete-btn' in triggered_id or 
                'expand-btn' in triggered_id or 
                'collapse-btn' in triggered_id):
                log.debug(f"🚫 Ignoring control button click: {triggered_id}")
                return dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update
            
            # Check if this click actually happened (n_clicks > 0)
            trigger_value = ctx.triggered[0]['value']
            if not trigger_value or trigger_value == 0:
                return dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update
                
        except Exception as e:
            log.debug(f"Error parsing callback trigger: {e}")
            return dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update

        print(f"📊 File clicked: {file_id} (tab={active_tab})")

        # Don't redraw if the same file is already active
        if file_id == active_file:
            return dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update

        # On shared tabs, only update active-file and metadata — don't touch
        # main-plot or pub-data-store (those hold shared analysis data).
        on_shared_tab = active_tab in ('peak-analysis', 'across-samples')

        # Find the file data - check if it's a bundle first
        file_data = data_manager.get_data_by_id(file_id)

        if file_data:
            print(f"✅ Found direct file data for: {file_id}")
        else:
            print(f"🔍 No direct data found for '{file_id}', checking if it's a bundle...")
            print(f"   loaded_data keys: {list(data_manager.loaded_data.keys())}")

            # Check if this is a bundle
            bundle = data_manager.get_bundle_by_id(file_id)
            if bundle and bundle.main_file:
                # Use the main file's data for the bundle
                main_file_id = bundle.main_file.get('id')
                file_data = data_manager.get_data_by_id(main_file_id)

                if file_data:
                    print(f"✅ Using main file data for bundle: {bundle.base_name}")
                else:
                    print(f"❌ No data found for main file: {main_file_id}")
            else:
                print(f"❌ No bundle found for ID: {file_id}")
                print(f"   bundle_manager bundles: {list(data_manager.bundle_manager.bundles.keys())}")

        # Check if this is a well selection (file_id contains |)
        if not file_data and '|' in file_id:
            parent_file_id, well_name = file_id.split('|', 1)
            file_data = data_manager.get_data_by_id(parent_file_id)
            
            if file_data:
                log.debug(f"✅ Using well {well_name} from file {parent_file_id}")
                # Modify the plot manager call to handle well selection
                figure = plot_manager.create_uvvis_plot(
                    file_data['data'], 
                    file_data['metadata'], 
                    selected_columns=[well_name]
                )
                data_table = create_data_table(file_data)
                # Load data into table editor for publication plotting - extract only the plotted well
                table_data = prepare_table_data(file_data, file_id=file_id, visible_wells=[well_name])
                table_editor = create_data_table_editor(table_data, table_id='pub-table')
                if on_shared_tab:
                    pub_data = dash.no_update
                else:
                    pub_data = table_data.to_json(orient='split') if table_data is not None else None
                if data_manager.get_publication_memory(file_id) is None:
                    data_manager.initialise_publication_memory(file_id, get_empty_selections())
                return dash.no_update if on_shared_tab else figure, file_id, data_table, table_editor, pub_data, dash.no_update

        if not file_data:
            log.debug(f"❌ File data not found for ID: {file_id}")
            error_fig = plot_manager.create_empty_plot("File data not found")
            error_table = build_message_state(
                title="File data not available",
                subtitle="Try re-uploading the file or check if it was removed from the explorer.",
                icon="⚠️",
                variant="error"
            )
            empty_table_editor = create_data_table_editor(None, table_id='pub-table')
            if data_manager.get_publication_memory(file_id) is None:
                data_manager.initialise_publication_memory(file_id, get_empty_selections())
            return dash.no_update if on_shared_tab else error_fig, file_id, error_table, empty_table_editor, dash.no_update if on_shared_tab else None, dash.no_update

        log.debug(f"✅ Found file data, creating plot...")

        # Determine bundle context (Chromeleon, LCMS, etc.)
        bundle = data_manager.get_bundle_by_id(file_id)
        if not bundle and '|' in file_id:
            # Child selection (e.g., CSV well or LCMS component)
            parent_id = file_id.split('|', 1)[0]
            bundle = data_manager.get_bundle_by_id(parent_id)

        if bundle:
            log.debug(f"📦 Creating bundle metadata table for: {bundle.base_name}")
            data_table = create_bundle_data_table(bundle, file_data, data_manager)
            log.debug(f"✅ Bundle metadata table created")
        else:
            log.debug(f"📄 Creating file metadata table")
            data_table = create_data_table(file_data)
            log.debug(f"✅ File metadata table created")

        # Create the plot
        metadata = file_data.get('metadata', {})
        file_type = metadata.get('file_type') or file_data.get('type')
        
        # Initialize visible_wells for UV-Vis data
        visible_wells = None

        if file_type == 'uvvis_csv':
            # For UV-Vis files, check visibility state
            filled_wells = file_data.get('metadata', {}).get('filled_wells', [])
            visible_wells = []
            
            # Check which wells are visible
            for well in filled_wells:
                well_id = f"{file_id}|{well}"
                is_visible = True
                if hasattr(data_manager, 'visibility_state'):
                    is_visible = data_manager.visibility_state.get(well_id, True)
                if is_visible:
                    visible_wells.append(well)
            
            if visible_wells:
                figure = plot_manager.create_uvvis_plot(
                    file_data['data'], 
                    file_data['metadata'], 
                    selected_columns=visible_wells
                )
                log.debug(f"🎨 Plotted UV-Vis with {len(visible_wells)} visible wells: {visible_wells}")
                log.debug(f"📊 Will extract table data for wells: {visible_wells}")
            else:
                # All wells hidden, show empty plot
                figure = plot_manager.create_empty_plot("All wells hidden")
                log.debug("🚫 All UV-Vis wells hidden, showing empty plot")
        elif file_type in {'lcms_cdf', 'lcms_bundle'} or (bundle and getattr(bundle, 'bundle_type', '') == 'lcms'):
            # LCMS bundle or component selection
            component_metadata = metadata
            component_data = file_data.get('data')

            # If user clicked bundle parent, default to positive TIC if available
            if file_type == 'lcms_bundle' or bundle:
                lcms_bundle = data_manager.lcms_bundles.get(bundle.base_name if bundle else file_id)
                preferred_component = None
                if lcms_bundle:
                    preferred_component = lcms_bundle.get('ms_positive') or lcms_bundle.get('ms_negative') or lcms_bundle.get('vwd_a') or lcms_bundle.get('vwd_b')
                if preferred_component:
                    component_data = preferred_component['data']
                    component_metadata = preferred_component['metadata']
                else:
                    log.debug("⚠️ No LCMS components found for bundle, showing placeholder")

            # Decide plot type based on metadata
            component_type = metadata.get('component_type') or file_type
            if component_type in {'ms_positive', 'ms_negative', 'lcms_ms_positive', 'lcms_ms_negative', 'lcms_cdf'}:
                figure = plot_manager.create_lcms_tic_plot(component_data, component_metadata)
            elif component_type in {'vwd_a', 'vwd_b', 'lcms_uv_a', 'lcms_uv_b', 'lcms_vwd_cdf'}:
                figure = plot_manager.create_lcms_uv_plot(component_data, component_metadata)
            else:
                figure = plot_manager.get_plot_for_file(file_data)
        else:
            figure = plot_manager.get_plot_for_file(file_data)

        log.debug(f"🎉 Plot created successfully!")

        # Create table editor for publication plotting - use smart data extraction
        table_data = prepare_table_data(file_data, file_id=file_id, visible_wells=visible_wells if file_type == 'uvvis_csv' else None)
        table_editor = create_data_table_editor(table_data, table_id='pub-table')
        # On shared tabs, don't overwrite pub-data-store with per-file data
        # — it holds the shared table data that the plot needs.
        if on_shared_tab:
            pub_data = dash.no_update
        else:
            pub_data = table_data.to_json(orient='split') if table_data is not None else None

        if data_manager.get_publication_memory(file_id) is None:
            sr = file_data.get('standardized')
            if sr is not None and sr.x_columns and sr.y_columns:
                auto_x = sr.x_columns[0]
                auto_y = sr.y_columns
            else:
                auto_x = file_data.get('metadata', {}).get('auto_x')
                auto_y = file_data.get('metadata', {}).get('auto_y', [])
            if auto_x and auto_y and table_data is not None and '_row_id' in table_data.columns:
                all_row_ids = table_data['_row_id'].tolist()
                sel = get_empty_selections()
                sel['x']['data']['column_id'] = auto_x
                sel['x']['data']['row_ids'] = all_row_ids
                if auto_y:
                    sel['y1']['series'][0]['column_id'] = auto_y[0]
                    sel['y1']['series'][0]['row_ids'] = all_row_ids
                for extra_y in auto_y[1:]:
                    sel['y1']['series'].append({'column_id': extra_y, 'row_ids': all_row_ids})
                data_manager.initialise_publication_memory(file_id, sel)
                log.debug(f"📊 Auto-populated selections: X={auto_x}, Y={auto_y}")
            else:
                data_manager.initialise_publication_memory(file_id, get_empty_selections())

        # Auto-switch to analysis mode for generic/unknown file types that
        # don't have a meaningful raw-data plot (e.g. plain CSVs, tables).
        # Exception: generic CSVs with auto-detected axes have a good raw plot.
        # On shared tabs, don't change view mode.
        if on_shared_tab:
            new_view_mode = dash.no_update
        elif file_type not in KNOWN_RAW_TYPES:
            sr = file_data.get('standardized')
            has_auto_axes = False
            if sr is not None:
                has_auto_axes = bool(sr.x_columns and sr.y_columns)
            else:
                has_auto_axes = bool(
                    metadata.get('auto_x') and metadata.get('auto_y')
                )
            if has_auto_axes:
                new_view_mode = 'raw'
                log.debug(f"📊 Showing raw plot for generic CSV with auto-detected axes")
            else:
                new_view_mode = 'analysis'
                log.debug(f"🔀 Auto-switching to analysis mode for file type: {file_type}")
        else:
            new_view_mode = dash.no_update

        return dash.no_update if on_shared_tab else figure, file_id, data_table, table_editor, pub_data, new_view_mode

    @app.callback(
        Output('main-plot', 'figure', allow_duplicate=True),
        [Input('view-mode', 'data'),
         Input('pub-plot-trigger', 'data')],
        [State('active-file', 'data'),
         State('loaded-files', 'data'),
         State('pub-plot-figure', 'data'),
         State('current-plot-settings', 'data'),
         State('selected-peak-idx', 'data')],
        prevent_initial_call=True
    )
    def handle_view_mode_change(view_mode, plot_trigger, active_file, loaded_files, pub_plot_figure, plot_settings, selected_peak_id):
        """Handle view mode toggle between Raw Data and Analysis Plot."""
        import plotly.graph_objects as go
        from services.plot_settings_service import PlotSettingsService, DEFAULT_PLOT_SETTINGS

        if not active_file:
            return dash.no_update

        ctx = dash.callback_context
        if not ctx.triggered:
            return dash.no_update

        trigger_id = ctx.triggered[0]['prop_id'].rsplit('.', 1)[0]

        # If publication plot was updated, only show it if user is in analysis mode.
        if trigger_id == 'pub-plot-trigger':
            if (view_mode or 'raw') == 'analysis' and pub_plot_figure:
                return pub_plot_figure
            else:
                return dash.no_update

        # Get the active file data
        file_data = data_manager.get_data_by_id(active_file)
        if not file_data:
            bundle = data_manager.get_bundle_by_id(active_file)
            if bundle and bundle.main_file:
                file_data = data_manager.get_data_by_id(bundle.main_file.get('id'))
        if not file_data:
            return dash.no_update

        if view_mode == 'analysis':
            if pub_plot_figure:
                return pub_plot_figure
            else:
                figure = plot_manager.create_empty_plot("Select data in Data Selector to create analysis plot")
        else:
            # Raw mode — multi-file plot respecting visibility
            s = {**DEFAULT_PLOT_SETTINGS, **(plot_settings or {})}
            layout_mode = s.get('layout_mode', 'overlay')

            visible_files = _collect_visible_files(data_manager, active_file, loaded_files)
            if not visible_files:
                return plot_manager.create_hidden_state_plot()

            figure = plot_manager.create_multi_file_plot(visible_files, layout_mode)

            # Overlay peaks (manual baseline + imported + detected)
            figure = _overlay_peaks_on_figure(data_manager, active_file, figure, selected_peak_id)

            # Apply current plot settings
            if plot_settings:
                try:
                    fig_obj = go.Figure(figure) if isinstance(figure, dict) else figure
                    ps = PlotSettingsService.from_dict(s)
                    PlotSettingsService.apply_to_figure(fig_obj, ps)
                    figure = fig_obj
                except Exception:
                    log.exception("Failed to apply plot settings to raw figure")

        return figure

    # ------------------------------------------------------------------
    # Re-render raw plot when settings change (while in raw mode)
    # ------------------------------------------------------------------
    _last_raw_settings = [None]

    @app.callback(
        Output('main-plot', 'figure', allow_duplicate=True),
        [Input('current-plot-settings', 'data'),
         Input('peak-change-trigger', 'data')],
        [State('view-mode', 'data'),
         State('active-file', 'data'),
         State('loaded-files', 'data'),
         State('selected-peak-idx', 'data')],
        prevent_initial_call=True,
    )
    def apply_settings_to_raw_plot(plot_settings, peak_change, view_mode, active_file, loaded_files, selected_peak_id):
        """Re-render raw plot when settings change, but only in raw mode.

        Skips redraw when triggered by peak-change-trigger (baseline callback
        already returned updated figure) or when settings haven't changed
        (e.g. tab switch that re-hydrates the same values).
        """
        import plotly.graph_objects as go
        from services.plot_settings_service import PlotSettingsService, DEFAULT_PLOT_SETTINGS

        if (view_mode or 'raw') != 'raw' or not active_file:
            return dash.no_update

        ctx = dash.callback_context
        trigger_id = ctx.triggered[0]['prop_id'].rsplit('.', 1)[0] if ctx.triggered else ''
        if trigger_id == 'peak-change-trigger':
            return dash.no_update

        s = {**DEFAULT_PLOT_SETTINGS, **(plot_settings or {})}

        if s == _last_raw_settings[0]:
            return dash.no_update
        _last_raw_settings[0] = s

        layout_mode = s.get('layout_mode', 'overlay')

        visible_files = _collect_visible_files(data_manager, active_file, loaded_files)
        if not visible_files:
            return plot_manager.create_hidden_state_plot()

        fig = plot_manager.create_multi_file_plot(visible_files, layout_mode)

        # Overlay peaks
        fig = _overlay_peaks_on_figure(data_manager, active_file, fig, selected_peak_id)

        try:
            fig_obj = go.Figure(fig) if isinstance(fig, dict) else fig
            ps = PlotSettingsService.from_dict(s)
            PlotSettingsService.apply_to_figure(fig_obj, ps)
            return fig_obj
        except Exception:
            log.exception("Failed to apply settings to raw plot")
            return fig

    # Selection highlighting is handled centrally in app.py.
    # Keeping a second DOM-mutation callback here causes stale/high-conflicting
    # selection state where multiple file items can remain highlighted.

    # DISABLED: Event propagation handling - trying CSS z-index approach instead
    # app.clientside_callback(
    #     """
    #     function() {
    #         return null;
    #     }
    #     """,
    #     Output('dummy-output', 'style'),
    #     Input('file-tree', 'children')
    # )


def create_bundle_data_table(bundle, file_data: Dict[str, Any], data_manager) -> html.Div:
    """Create a data table display for a bundle with rich metadata."""
    try:
        main_file = bundle.main_file
        aux_files = bundle.auxiliary_files
        metadata = file_data.get('metadata', {})
        
        # Bundle header
        bundle_header = html.Div([
            html.H5(f"📦 {bundle.base_name}", 
                   style={'margin': '0 0 5px 0', 'color': '#ff6b35', 'fontSize': '16px'}),
            html.P([
                html.Strong("Bundle Type: "), f"{bundle.bundle_type.capitalize()}",
                html.Br(),
                html.Strong("Files: "), f"{1 + len(aux_files)} files in bundle",
            ], style={'margin': '0 0 15px 0', 'fontSize': '13px', 'color': '#666'})
        ])

        # File list section
        file_list_items = []
        file_list_items.append(html.Div([
            html.Span("📄 ", style={'marginRight': '5px'}),
            html.Strong(main_file.get('name', 'Unknown'), style={'color': '#333'})
        ], style={'padding': '4px 0', 'fontSize': '13px'}))
        
        for aux_file in aux_files:
            file_list_items.append(html.Div([
                html.Span("📄 ", style={'marginRight': '5px'}),
                html.Span(aux_file.get('name', 'Unknown'), style={'color': '#666'})
            ], style={'padding': '4px 0', 'fontSize': '13px'}))
        
        files_section = html.Div(file_list_items, style={'marginBottom': '20px', 'paddingLeft': '10px'})

        # Rich metadata section
        metadata_rows = []
        field_display_order = [
            ('file_path', 'File Path'), ('channel', 'Channel'), ('data_vault', 'Data Vault'),
            ('injection', 'Injection'), ('injection_number', 'Injection Number'), ('position', 'Position'),
            ('processing_method', 'Processing Method'), ('instrument_method', 'Instrument Method'),
            ('type', 'Type'), ('status', 'Status'), ('injection_date', 'Injection Date'),
            ('injection_time', 'Injection Time'), ('injection_volume_μl', 'Injection Volume μL'),
            ('dilution_factor', 'Dilution Factor'), ('weight', 'Weight'),
            ('time_min_min', 'Time Min (min)'), ('time_max_min', 'Time Max (min)'),
            ('data_points', 'Data Points'), ('detector', 'Detector'),
            ('exporting_data_system', 'Exporting Data System'), ('signal_quantity', 'Signal Quantity'),
            ('signal_unit', 'Signal Unit'), ('signal_min', 'Signal Min'), ('signal_max', 'Signal Max'),
            ('driver_name', 'Driver Name'), ('channel_type', 'Channel Type'),
            ('min_step_s', 'Min Step (s)'), ('max_step_s', 'Max Step (s)'), ('average_step_s', 'Average Step (s)'),
            ('signal_info', 'Signal Info'), ('wavelength_nm', 'Wavelength (nm)'),
            ('time_range', 'Time Range'), ('value_range', 'Value Range'),
        ]
        
        for field_key, field_label in field_display_order:
            if field_key in metadata:
                value = metadata[field_key]
                metadata_rows.append(html.Tr([
                    html.Td(field_label, style={'padding': '6px 10px', 'fontWeight': '500', 'color': '#555',
                        'fontSize': '13px', 'verticalAlign': 'top', 'width': '40%', 'borderBottom': '1px solid #f0f0f0'}),
                    html.Td(str(value), style={'padding': '6px 10px', 'color': '#333', 'fontSize': '13px',
                        'verticalAlign': 'top', 'borderBottom': '1px solid #f0f0f0', 'wordBreak': 'break-word'})
                ]))
        
        for key, value in metadata.items():
            if key not in [field[0] for field in field_display_order] and key != 'file_type':
                display_key = key.replace('_', ' ').title()
                metadata_rows.append(html.Tr([
                    html.Td(display_key, style={'padding': '6px 10px', 'fontWeight': '500', 'color': '#555',
                        'fontSize': '13px', 'verticalAlign': 'top', 'width': '40%', 'borderBottom': '1px solid #f0f0f0'}),
                    html.Td(str(value), style={'padding': '6px 10px', 'color': '#333', 'fontSize': '13px',
                        'verticalAlign': 'top', 'borderBottom': '1px solid #f0f0f0', 'wordBreak': 'break-word'})
                ]))
        
        metadata_section = html.Div([
            html.Table(metadata_rows, style={'width': '100%', 'borderCollapse': 'collapse',
                'backgroundColor': '#ffffff', 'border': '1px solid #e0e0e0', 'borderRadius': '4px'})
        ]) if metadata_rows else html.Div()

        return html.Div([bundle_header, files_section, metadata_section], style={'padding': '5px 0'})

    except Exception as e:
        import traceback
        traceback.print_exc()
        return build_message_state(title="Unable to display bundle details", subtitle=str(e), icon="⚠️", variant="error")


def create_data_table(file_data: Dict[str, Any]) -> html.Div:
    """Create a data table display for the selected file."""
    try:
        record = file_data.get('record', {})
        metadata = file_data.get('metadata', {})
        data = file_data.get('data')
        log.debug(f"🔍 METADATA DEBUG (single file): metadata keys: {list(metadata.keys())}")

        # File info section
        file_info = html.Div([
            html.H5(f"📄 {record.get('name', 'Unknown')}", style={'margin': '0 0 10px 0', 'color': '#333'}),
            html.P([
                html.Strong("Type: "), f"{record.get('type', 'unknown').capitalize()}",
                html.Br(),
                html.Strong("Size: "), f"{record.get('size_display', 'Unknown')}",
            ], style={'margin': '0 0 15px 0', 'fontSize': '14px', 'color': '#666'})
        ])

        # StandardizedResult identity section (pipeline info)
        sr_section = html.Div()
        sr = file_data.get('standardized')
        if sr is not None:
            identity = sr.identity
            sr_items = [
                html.P(f"Format: {identity.detected_format} (Stage {identity.detection_stage})",
                       style={'margin': '2px 0', 'fontSize': '13px'}),
                html.P(f"Columns: {', '.join(sr.x_columns)} (X) / {', '.join(sr.y_columns)} (Y)",
                       style={'margin': '2px 0', 'fontSize': '13px'}),
                html.P(f"Plot hint: {sr.plot_hint.value}",
                       style={'margin': '2px 0', 'fontSize': '13px'}),
            ]
            if sr.sample_name:
                sr_items.append(html.P(f"Sample: {sr.sample_name}",
                                        style={'margin': '2px 0', 'fontSize': '13px'}))
            for key, val in sr.metadata.items():
                if isinstance(val, dict):
                    for k2, v2 in val.items():
                        sr_items.append(html.P(f"{k2}: {v2}",
                                               style={'margin': '2px 0', 'fontSize': '13px'}))
                else:
                    sr_items.append(html.P(f"{key}: {val}",
                                           style={'margin': '2px 0', 'fontSize': '13px'}))
            sr_section = html.Div([
                html.H6("Pipeline Detection", style={'margin': '0 0 6px 0', 'color': '#333'}),
                html.Div(sr_items, style={'paddingLeft': '4px'})
            ], style={'marginBottom': '15px', 'padding': '8px', 'backgroundColor': '#f8f9fa',
                      'border': '1px solid #e0e0e0', 'borderRadius': '4px'})

        # Metadata section
        if metadata:
            metadata_items = []
            for key, value in metadata.items():
                if key != 'file_type':  # Skip redundant info
                    display_key = key.replace('_', ' ').title()
                    metadata_items.append(html.Tr([
                        html.Td(display_key, style={'fontWeight': 'bold', 'padding': '4px 8px'}),
                        html.Td(str(value), style={'padding': '4px 8px'})
                    ]))

            if metadata_items:
                metadata_section = html.Div([
                    html.H6("📊 Metadata", style={'margin': '0 0 8px 0', 'color': '#333'}),
                    html.Table(
                        metadata_items,
                        style={
                            'width': '100%',
                            'border': '1px solid #e0e0e0',
                            'borderRadius': '4px',
                            'fontSize': '13px'
                        }
                    )
                ], style={'marginBottom': '15px'})
            else:
                metadata_section = html.Div()
        else:
            metadata_section = html.Div()

        # Data info (no preview - that's in Data Overview tab)
        if data is not None and not data.empty:
            data_info = html.Div([
                html.P([
                    html.Strong("Data Shape: "),
                    f"{len(data)} rows × {len(data.columns)} columns"
                ], style={'margin': '0', 'fontSize': '14px', 'color': '#666'})
            ], style={'marginBottom': '10px'})
        else:
            data_info = html.Div()

        return html.Div([
            file_info,
            sr_section,
            metadata_section,
            data_info
        ], style={'width': '100%', 'boxSizing': 'border-box'})

    except Exception as e:
        return build_message_state(
            title="Error displaying file details",
            subtitle=str(e),
            icon="⚠️",
            variant="error"
        )


def build_message_state(title: str, subtitle: Optional[str] = None, icon: str = "🦎", variant: str = "default") -> html.Div:
    """Return a styled empty-state or message block."""

    classes = ['empty-state']
    if variant and variant != 'default':
        classes.append(f"empty-state--{variant}")

    children = [
        html.Span(icon, className='empty-state__icon'),
        html.H4(title, className='empty-state__title')
    ]

    if subtitle:
        children.append(html.P(subtitle, className='empty-state__subtitle'))

    return html.Div(children, className=" ".join(classes))
