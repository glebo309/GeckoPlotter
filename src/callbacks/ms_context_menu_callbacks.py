"""Right-click context menu for MS Analysis graphs (spectrum + EIC).

'Open as new plot' extracts data from the figure and registers it as a new
Bundle in the data_manager, so it appears in the file explorer as a real
dataset that can be edited, overlaid, exported, etc.
"""

import logging
import sys
import traceback
import uuid

import dash
import numpy as np
import pandas as pd
from dash import Input, Output, State
from dash.exceptions import PreventUpdate

from ingestion.types import (
    ColumnRole,
    FileIdentity,
    PlotHint,
    SourceCategory,
    StandardizedResult,
)
from services.data_store import Bundle, BundleType, Component, ComponentRole

log = logging.getLogger('geckoplotter.ms_ctx')
if not log.handlers:
    _h = logging.StreamHandler(sys.stderr)
    _h.setFormatter(logging.Formatter('%(name)s: %(message)s'))
    log.addHandler(_h)
    log.setLevel(logging.DEBUG)

_ANCHOR_BASE = {
    'position': 'fixed', 'width': '1px', 'height': '1px',
    'zIndex': 4000, 'pointerEvents': 'none',
}


def _axis_label(layout, axis_key, fallback):
    """Extract axis label from Plotly layout, handling both string and dict title formats."""
    axis = layout.get(axis_key, {})
    if not isinstance(axis, dict):
        return fallback
    title = axis.get('title', '')
    if isinstance(title, dict):
        return title.get('text', '') or fallback
    if isinstance(title, str) and title:
        return title
    return fallback


def _extract_xy_from_figure(fig_dict, source):
    """Pull x/y arrays from a Plotly figure dict."""
    if not fig_dict or 'data' not in fig_dict:
        return None
    traces = fig_dict['data']
    if not traces:
        return None

    layout = fig_dict.get('layout', {})
    x_label = _axis_label(layout, 'xaxis', 'x')
    y_label = _axis_label(layout, 'yaxis', 'y')

    def _safe_float_array(vals):
        """Convert a list of values to float array, filtering out non-numeric entries."""
        clean = []
        for v in vals:
            if v is None or isinstance(v, dict):
                clean.append(np.nan)
            else:
                try:
                    clean.append(float(v))
                except (TypeError, ValueError):
                    clean.append(np.nan)
        return np.array(clean, dtype=float)

    if source == 'ms-spectrum-graph':
        for t in traces:
            mode = t.get('mode', '')
            if 'markers' in mode and t.get('x') and t.get('y'):
                x = _safe_float_array(t['x'])
                y = _safe_float_array(t['y'])
                mask = np.isfinite(x) & np.isfinite(y)
                if mask.any():
                    return x[mask], y[mask], x_label, y_label
        for t in traces:
            xs = t.get('x')
            ys = t.get('y')
            if xs and ys:
                x = _safe_float_array(xs)
                y = _safe_float_array(ys)
                mask = np.isfinite(x) & np.isfinite(y)
                if mask.any():
                    return x[mask], y[mask], x_label, y_label
    else:
        for t in traces:
            mode = t.get('mode', '')
            xs = t.get('x')
            ys = t.get('y')
            if xs and ys and 'markers' not in mode:
                x = _safe_float_array(xs)
                y = _safe_float_array(ys)
                mask = np.isfinite(x) & np.isfinite(y)
                if mask.any():
                    name = t.get('name', '')
                    return x[mask], y[mask], x_label, y_label, name
        for t in traces:
            xs = t.get('x')
            ys = t.get('y')
            if xs and ys:
                x = _safe_float_array(xs)
                y = _safe_float_array(ys)
                mask = np.isfinite(x) & np.isfinite(y)
                if mask.any():
                    name = t.get('name', '')
                    return x[mask], y[mask], x_label, y_label, name
    return None


def register_ms_context_menu_callbacks(app: dash.Dash, data_manager) -> None:

    @app.callback(
        [Output('ms-plot-context-menu', 'opened'),
         Output('ms-plot-context-menu-anchor', 'style')],
        Input('ms-plot-context-menu-store', 'data'),
        prevent_initial_call=True,
    )
    def open_ms_menu(store):
        if not store or not store.get('source'):
            raise PreventUpdate
        x = store.get('x', 0)
        y = store.get('y', 0)
        style = {**_ANCHOR_BASE, 'left': f'{x}px', 'top': f'{y}px'}
        return True, style

    @app.callback(
        Output('ms-plot-context-menu', 'opened', allow_duplicate=True),
        Input('ms-plot-context-menu-close-store', 'data'),
        prevent_initial_call=True,
    )
    def close_ms_menu(_):
        return False

    @app.callback(
        [Output('loaded-files', 'data', allow_duplicate=True),
         Output('file-tree', 'children', allow_duplicate=True),
         Output('active-file', 'data', allow_duplicate=True),
         Output('metadata-container', 'children', allow_duplicate=True),
         Output('table-editor-container', 'children', allow_duplicate=True),
         Output('pub-data-store', 'data', allow_duplicate=True),
         Output('render-trigger', 'data', allow_duplicate=True)],
        Input('ms-ctx-open-new-plot', 'n_clicks'),
        [State('ms-plot-context-menu-store', 'data'),
         State('ms-spectrum-graph', 'figure'),
         State('eic-graph', 'figure'),
         State('ms-scan-label', 'children'),
         State('render-trigger', 'data')],
        prevent_initial_call=True,
    )
    def open_as_new_plot(n_clicks, store, spectrum_fig, eic_fig, scan_label,
                         render_counter):
        if not n_clicks or not store:
            raise PreventUpdate

        source = store.get('source', '')
        fig = spectrum_fig if source == 'ms-spectrum-graph' else eic_fig

        try:
            result = _extract_xy_from_figure(fig, source)
            if result is None:
                log.warning("No data to extract from %s", source)
                raise PreventUpdate

            if source == 'ms-spectrum-graph':
                x_arr, y_arr, x_label, y_label = result
                trace_name = ''
            else:
                x_arr, y_arr, x_label, y_label, trace_name = result

            if source == 'ms-spectrum-graph':
                name = "MS Spectrum"
                if scan_label and scan_label != 'No scan selected':
                    name = f"MS {scan_label}"
                src_cat = SourceCategory.SPECTRUM
                plot_hint = PlotHint.LOLLIPOP
            else:
                name = f"EIC {trace_name}" if trace_name else "EIC"
                src_cat = SourceCategory.CHROMATOGRAM
                plot_hint = PlotHint.LINE

            x_col = x_label or 'x'
            y_col = y_label or 'y'
            df = pd.DataFrame({x_col: x_arr, y_col: y_arr})

            log.info("Extracted %d points from %s → '%s'", len(df), source, name)

            sr = StandardizedResult(
                data=df,
                column_roles={x_col: ColumnRole.X, y_col: ColumnRole.Y},
                identity=FileIdentity(f"{name}.csv", "csv", "ms_extract", 0),
                plot_hint=PlotHint.LINE,
                source_category=src_cat,
                sample_name=name,
                metadata={'auto_x': x_col, 'auto_y': [y_col]},
            )

            comp_id = str(uuid.uuid4())
            component = Component(
                component_id=comp_id,
                role=ComponentRole.PRIMARY,
                original_filename=f"{name}.csv",
                raw_bytes=df.to_csv(index=False).encode(),
                dataframe=df,
                column_roles=sr.column_roles,
                metadata=sr.metadata,
                source_category=sr.source_category,
                plot_hint=sr.plot_hint,
                standardized=sr,
            )

            bundle_id = str(uuid.uuid4())
            bundle = Bundle(
                bundle_id=bundle_id,
                name=name,
                bundle_type=BundleType.GENERIC,
                component_list=[component],
            )

            data_manager.add_bundle(bundle)
            log.info("Registered bundle '%s' (%s)", name, bundle_id)

            loaded_files = data_manager.get_loaded_files_list()

            file_data = data_manager.get_data_by_id(bundle_id)
            auto_table = dash.no_update
            table_editor = None
            pub_data = None
            if file_data:
                try:
                    from callbacks.viz_callbacks import create_data_table
                    auto_table = create_data_table(file_data)
                except Exception:
                    log.exception("Error building metadata table")

                try:
                    from callbacks.viz_callbacks import prepare_table_data
                    from components.data_table_editor import create_data_table_editor
                    table_data = prepare_table_data(file_data, file_id=bundle_id)
                    table_editor = create_data_table_editor(
                        table_data, table_id='pub-table')
                    pub_data = (table_data.to_json(orient='split')
                                if table_data is not None else None)
                except Exception:
                    log.exception("Error building table editor")

            from callbacks.upload_callbacks import render_file_tree_with_bundles_selected
            tree_items = render_file_tree_with_bundles_selected(
                loaded_files, data_manager, bundle_id)

            return (loaded_files, tree_items, bundle_id, auto_table,
                    table_editor, pub_data, (render_counter or 0) + 1)

        except PreventUpdate:
            raise
        except Exception:
            log.error("open_as_new_plot failed:\n%s", traceback.format_exc())
            raise PreventUpdate
