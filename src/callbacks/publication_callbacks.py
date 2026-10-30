"""
Publication Plotter Callbacks
Handles all interactions for publication-quality plotting
"""

import json
import logging
import pandas as pd
import io
import sys
import time
from datetime import datetime
from dash import Input, Output, State, ALL, callback_context, dash
import base64
import copy

log = logging.getLogger('geckoplotter.pub')
if not log.handlers:
    _h = logging.StreamHandler(sys.stderr)
    _h.setFormatter(logging.Formatter('%(message)s'))
    log.addHandler(_h)
    log.setLevel(logging.DEBUG)

from components.axis_mapper import get_empty_selections, selector_button_style, SECTION_COLORS
from components.data_table_editor import transpose_dataframe, create_data_table_editor
from components.publication_plot import create_publication_plot
from services.plot_settings_service import PlotSettings, PlotSettingsService
from services import table_store


def canon_selector(obj):
    """Normalize selector tuples so equality always works"""
    if obj is None:
        return None
    if isinstance(obj, (list, tuple)):
        axis = str(obj[0]) if len(obj) > 0 else None
        kind = str(obj[1]) if len(obj) > 1 else None
        idx  = obj[2] if len(obj) > 2 else None
    elif isinstance(obj, dict):
        axis = str(obj.get('axis'))
        kind = str(obj.get('kind'))
        idx  = obj.get('idx')
    else:
        return None
    # force numeric idx to int when possible
    try:
        if idx is not None:
            idx = int(idx)
    except Exception:
        pass
    return (axis, kind) if idx is None else (axis, kind, idx)


def sel_eq(a, b):
    """Check if two selectors are equal"""
    return canon_selector(a) == canon_selector(b)


def build_y1_series_controls(count):
    """Build the Y1 series selector button UI."""
    from dash import html

    series_divs = []
    for i in range(count):
        series_divs.append(
            html.Div([
                html.Label(
                    f"Series {i+1}:",
                    style={'fontSize': '10px', 'fontWeight': '600', 'color': '#666', 'marginBottom': '4px'}
                ),
                html.Button("Select data", id={'type': 'btn-y1-data', 'index': i}, style=selector_button_style('y1')),
            ], style={'marginBottom': '8px'})
        )

    return series_divs


def _non_empty_ids(df, col):
    """Return _row_id values for non-empty cells in *col*."""
    ids = []
    for _, row in df.iterrows():
        val = row[col]
        if pd.notna(val) and str(val).strip() != '':
            ids.append(int(row['_row_id']))
    return ids


def _build_default_selections(df, x_col='Sample', y_col='Area'):
    """Build default axis selections for a DataFrame.

    Returns a selections dict with X mapped to *x_col* and Y1-Series-1
    mapped to *y_col*, using all non-empty rows.  Returns ``None`` if the
    required columns aren't present.
    """
    if df is None or x_col not in df.columns or y_col not in df.columns:
        return None
    if '_row_id' not in df.columns:
        df = df.copy()
        df.insert(0, '_row_id', range(len(df)))

    sel = get_empty_selections()
    sel['x']['data'] = {'row_ids': _non_empty_ids(df, x_col), 'column_id': x_col}
    sel['y1']['series'][0] = {'row_ids': _non_empty_ids(df, y_col), 'column_id': y_col}
    return sel


def _selection_matches_defaults(sel, x_col='Sample', y_col='Area'):
    """Return True when *sel* already maps X/Y1 to the expected defaults."""
    if not isinstance(sel, dict):
        return False

    current_x = sel.get('x', {}).get('data', {}).get('column_id')
    current_y = None
    series = sel.get('y1', {}).get('series', [])
    if series:
        current_y = series[0].get('column_id')

    return current_x == x_col and current_y == y_col


def _refresh_selection_row_ids(sel, df):
    """Re-compute row_ids for every mapped column in *sel* against new *df*.

    Keeps the column mappings but updates row_ids so they match the
    current data.  Returns a new selections dict.
    """
    import copy
    if df is None or sel is None:
        return sel
    if '_row_id' not in df.columns:
        df = df.copy()
        df.insert(0, '_row_id', range(len(df)))

    out = copy.deepcopy(sel)
    valid_cols = set(df.columns)

    def refresh(target):
        col = target.get('column_id')
        if col and col in valid_cols:
            target['row_ids'] = _non_empty_ids(df, col)
        elif col and col not in valid_cols:
            # Column gone — clear mapping
            target['row_ids'] = []
            target['column_id'] = None

    refresh(out.get('x', {}).get('data', {}))
    for series in out.get('y1', {}).get('series', []):
        refresh(series)
    refresh(out.get('y1', {}).get('error', {}))
    if out.get('y2_enabled'):
        refresh(out.get('y2', {}).get('data', {}))
        refresh(out.get('y2', {}).get('error', {}))

    return out


def _clean_selection_for_state(sel):
    """Return a copy of selections without volatile bookkeeping fields."""
    if not isinstance(sel, dict):
        return sel
    cleaned = copy.deepcopy(sel)
    cleaned.pop('last_updated', None)
    return cleaned


def register_publication_callbacks(app: dash.Dash, data_manager) -> None:
    """Register publication plotter callbacks."""
    
    # ── Selection routing ─────────────────────────────────────────────
    # Three stores:
    #   pub-selections          – the single source of truth for the active plot pipeline
    #   peak-shared-selections  – persists axis mappings for peak-analysis
    #   cross-shared-selections – persists axis mappings for across-samples
    #
    # On tab switch or file switch we copy the right source → pub-selections.

    @app.callback(
        [Output('pub-selections', 'data', allow_duplicate=True),
         Output('pub-data-store', 'data', allow_duplicate=True)],
        [Input('active-file', 'data'),
         Input('file-ui-state', 'data'),
         Input('active-tab', 'data')],
        [State('peak-shared-selections', 'data'),
         State('cross-shared-selections', 'data'),
         State('peak-table-store', 'data'),
         State('cross-sample-table-store', 'data'),
         State('pub-table-source', 'data')],
        prevent_initial_call=True
    )
    def load_selections_for_context(active_file, file_ui_state, active_tab,
                                     peak_shared_sel, cross_shared_sel, peak_json, cross_json, table_source=None):
        """Route the correct selections into pub-selections based on active tab.

        - data-overview / metadata: load per-file selections (and, on a tab switch, the file's table)
        - peak-analysis / across-samples: load tab-specific shared selections + matching data
        """
        ctx = callback_context
        trigger_id = ctx.triggered[0]['prop_id'] if ctx.triggered else ''

        # ── Shared tabs: peak-analysis, across-samples ──
        if active_tab in ('peak-analysis', 'across-samples'):
            # If the trigger is a tab switch, push shared selections + data
            if 'active-tab' in trigger_id:
                sel = dash.no_update
                data = dash.no_update
                shared_sel = peak_shared_sel if active_tab == 'peak-analysis' else cross_shared_sel
                tab_json = peak_json if active_tab == 'peak-analysis' else cross_json
                default_x = 'RT (min)' if active_tab == 'peak-analysis' else 'Sample'

                if tab_json:
                    try:
                        df = pd.read_json(io.StringIO(tab_json), orient='split')

                        if _selection_matches_defaults(shared_sel, x_col=default_x, y_col='Area'):
                            sel = _refresh_selection_row_ids(shared_sel, df)
                            log.debug(f"TAB SWITCH → shared selections (tab={active_tab}, X={default_x}, Y1=Area)")
                        else:
                            defaults = _build_default_selections(df, x_col=default_x, y_col='Area')
                            if defaults:
                                sel = defaults
                                log.debug(f"📋 TAB SWITCH → enforced defaults (X={default_x}, Y1=Area)")
                    except Exception:
                        pass
                elif shared_sel and isinstance(shared_sel, dict) and shared_sel.get('x', {}).get('data', {}).get('column_id'):
                    sel = shared_sel

                if tab_json:
                    data = tab_json
                return sel, data
            # File switch while on shared tab → don't touch anything
            return dash.no_update, dash.no_update

        # ── Per-file tabs: data-overview, metadata, calibration ──
        if not active_file:
            return get_empty_selections(), dash.no_update

        file_selections = None
        if isinstance(file_ui_state, dict) and file_ui_state.get('file_id') == active_file:
            file_selections = file_ui_state.get('pub_selections')

        if file_selections is None:
            file_state = data_manager.get_file_state(active_file)
            file_selections = file_state.get('pub_selections')
        if file_selections is None:
            file_selections = get_empty_selections()

        if isinstance(file_selections, dict):
            file_selections = _clean_selection_for_state(file_selections)
            file_selections['file_id'] = active_file

        x_col = file_selections.get('x', {}).get('data', {}).get('column_id')
        y1_series = [s.get('column_id') for s in file_selections.get('y1', {}).get('series', []) if s.get('column_id')]
        log.debug(f"📋 FILE LOAD → per-file selections ({active_file[:8]}): X={x_col}, Y1={y1_series}")

        # Back from a shared tab, pub-data-store still holds that tab's table.
        data = table_source if 'active-tab' in trigger_id and table_source else dash.no_update
        return file_selections, data
    
    # Update table highlighting when selections or active selector change.
    # IMPORTANT: This is the ONLY callback that writes to pub-table.style_data_conditional.
    # Keeping highlighting separate from update_selections breaks a circular dependency
    # where writing style_data_conditional causes selected_cells to reset, re-triggering
    # update_selections in a loop.
    @app.callback(
        Output('pub-table', 'style_data_conditional', allow_duplicate=True),
        [Input('pub-selections', 'data'),
         Input('active-selector', 'data'),
         Input('pub-table', 'data')],
        [State('pub-data-store', 'data'),
         State('active-file', 'data'),
         State('pub-table', 'style_data_conditional')],
        prevent_initial_call=True
    )
    def update_table_highlighting(selections, active_selector, page_rows, data_json, active_file, current=None):
        styles = _table_highlighting(selections, active_selector, page_rows, data_json, active_file)
        # An edited cell keeps its focus: rewriting the same rules would reset the table's selection.
        return dash.no_update if styles == current else styles

    def _table_highlighting(selections, active_selector, page_rows, data_json, active_file):
        """Update table cell highlighting based on current selections and active selector.

        Only rows on the shown page get a rule: a whole-column selection holds every row id of the table.
        """
        if not selections or not data_json:
            return [{'if': {'column_id': '_row_id'}, 'display': 'none'}]

        shown = {row.get('_row_id') for row in (page_rows or []) if isinstance(row, dict)}

        sel_file = selections.get('file_id', 'MISSING') if isinstance(selections, dict) else 'NOT_DICT'
        if active_file and isinstance(selections, dict) and sel_file != active_file:
            return [{'if': {'column_id': '_row_id'}, 'display': 'none'}]

        active_selector = canon_selector(active_selector)

        # Base styles
        style_conditions = [
            {'if': {'column_id': '_row_id'}, 'display': 'none'},
            {'if': {'row_index': 'odd'}, 'backgroundColor': '#FAFAFA'},
        ]

        y1_shades = ['#faf5ed', '#f5edd8', '#f0e4c5', '#e8d9b0']

        def add_highlights(row_ids, column_id, bg_color, border_color, bold=False):
            """Helper to add highlighting for selected cells."""
            if not row_ids or not column_id:
                return
            for rid in row_ids:
                if rid not in shown:
                    continue
                condition = {
                    'if': {'filter_query': f'{{_row_id}} = {rid}', 'column_id': column_id},
                    'backgroundColor': bg_color,
                    'border': f'{"2px solid" if bold else "1px dashed"} {border_color}',
                    'fontWeight': '600' if bold else '500',
                }
                style_conditions.append(condition)

        # X-axis highlighting
        x_sel = selections.get('x', {}).get('data', {})
        if x_sel.get('row_ids') and x_sel.get('column_id'):
            add_highlights(x_sel['row_ids'], x_sel['column_id'],
                          SECTION_COLORS['x']['light'], SECTION_COLORS['x']['main'])

        # Y1 series highlighting
        for idx, series in enumerate(selections.get('y1', {}).get('series', [])):
            if series.get('row_ids') and series.get('column_id'):
                shade = y1_shades[idx % len(y1_shades)]
                add_highlights(series['row_ids'], series['column_id'],
                              shade, SECTION_COLORS['y1']['main'])

        # Y1 error highlighting
        y1_error = selections.get('y1', {}).get('error', {})
        if y1_error.get('row_ids') and y1_error.get('column_id'):
            add_highlights(y1_error['row_ids'], y1_error['column_id'],
                          '#f5f5f5', '#999')

        # Y2 highlighting (if enabled)
        if selections.get('y2_enabled'):
            y2_data = selections.get('y2', {}).get('data', {})
            if y2_data.get('row_ids') and y2_data.get('column_id'):
                add_highlights(y2_data['row_ids'], y2_data['column_id'],
                              SECTION_COLORS['y2']['light'], SECTION_COLORS['y2']['main'])

            y2_error = selections.get('y2', {}).get('error', {})
            if y2_error.get('row_ids') and y2_error.get('column_id'):
                add_highlights(y2_error['row_ids'], y2_error['column_id'],
                              '#f0f0f0', '#666')

        # Active selector: show BOLD highlight for the currently active axis
        if active_selector:
            axis, kind = active_selector[0], active_selector[1]
            if axis == 'x':
                sel = selections['x']['data']
                add_highlights(sel.get('row_ids'), sel.get('column_id'),
                               SECTION_COLORS['x']['light'], SECTION_COLORS['x']['main'], bold=True)
            elif axis == 'y1':
                if kind == 'error':
                    sel = selections['y1']['error']
                    add_highlights(sel.get('row_ids'), sel.get('column_id'),
                                   '#f5f5f5', '#555', bold=True)
                else:
                    idx = active_selector[2] if len(active_selector) > 2 else 0
                    if idx < len(selections['y1']['series']):
                        series = selections['y1']['series'][idx]
                        shade = y1_shades[idx % len(y1_shades)]
                        add_highlights(series.get('row_ids'), series.get('column_id'),
                                       shade, SECTION_COLORS['y1']['main'], bold=True)
            elif axis == 'y2':
                sel = selections['y2'][kind]
                if kind == 'data':
                    add_highlights(sel.get('row_ids'), sel.get('column_id'),
                                   SECTION_COLORS['y2']['light'], SECTION_COLORS['y2']['main'], bold=True)
                else:
                    add_highlights(sel.get('row_ids'), sel.get('column_id'),
                                   '#f0f0f0', '#555', bold=True)

        return style_conditions
    
    # Highlighting for secondary tables (peak-table, cross-sample-table)
    # Reuses the same logic as update_table_highlighting but for each tab's table.
    @app.callback(
        Output('peak-table', 'style_data_conditional', allow_duplicate=True),
        [Input('pub-selections', 'data'),
         Input('active-selector', 'data')],
        [State('peak-table', 'data'),
         State('active-tab', 'data')],
        prevent_initial_call=True
    )
    def update_peak_table_highlighting(selections, active_selector, table_data, active_tab):
        if not selections or not table_data or active_tab != 'peak-analysis':
            return [{'if': {'column_id': '_row_id'}, 'display': 'none'}]
        return _build_highlight_styles(selections, active_selector)

    GROUP_COLORS = [
        '#eaf2f7', '#faf5ed', '#edf5f0', '#f5f0f5',
        '#f0f5f0', '#f5f2ea', '#edf0f5', '#f5edea',
    ]

    @app.callback(
        Output('cross-sample-table', 'style_data_conditional', allow_duplicate=True),
        [Input('pub-selections', 'data'),
         Input('active-selector', 'data'),
         Input('cross-sample-table', 'data')],
        State('active-tab', 'data'),
        prevent_initial_call=True
    )
    def update_cross_sample_table_highlighting(selections, active_selector, table_data, active_tab):
        base = [{'if': {'column_id': '_row_id'}, 'display': 'none'}]
        if not table_data:
            return base

        groups_seen = {}
        for row in table_data:
            g = (row.get('Group') or '').strip()
            if g and g not in groups_seen:
                groups_seen[g] = GROUP_COLORS[len(groups_seen) % len(GROUP_COLORS)]
        group_styles = []
        for i, row in enumerate(table_data):
            g = (row.get('Group') or '').strip()
            if g and g in groups_seen:
                group_styles.append({
                    'if': {'row_index': i},
                    'backgroundColor': groups_seen[g],
                })

        if not selections or active_tab != 'across-samples':
            return base + group_styles
        return _build_highlight_styles(selections, active_selector) + group_styles

    def _build_highlight_styles(selections, active_selector):
        """Build style_data_conditional for highlighting selected cells."""
        active_selector = canon_selector(active_selector)

        style_conditions = [
            {'if': {'column_id': '_row_id'}, 'display': 'none'},
            {'if': {'row_index': 'odd'}, 'backgroundColor': '#FAFAFA'},
        ]

        y1_shades = ['#faf5ed', '#f5edd8', '#f0e4c5', '#e8d9b0']

        def add_highlights(row_ids, column_id, bg_color, border_color, bold=False):
            if not row_ids or not column_id:
                return
            for rid in row_ids:
                style_conditions.append({
                    'if': {'filter_query': f'{{_row_id}} = {rid}', 'column_id': column_id},
                    'backgroundColor': bg_color,
                    'border': f'{"2px solid" if bold else "1px dashed"} {border_color}',
                    'fontWeight': '600' if bold else '500',
                })

        x_sel = selections.get('x', {}).get('data', {})
        if x_sel.get('row_ids') and x_sel.get('column_id'):
            add_highlights(x_sel['row_ids'], x_sel['column_id'],
                          SECTION_COLORS['x']['light'], SECTION_COLORS['x']['main'])

        for idx, series in enumerate(selections.get('y1', {}).get('series', [])):
            if series.get('row_ids') and series.get('column_id'):
                shade = y1_shades[idx % len(y1_shades)]
                add_highlights(series['row_ids'], series['column_id'],
                              shade, SECTION_COLORS['y1']['main'])

        y1_error = selections.get('y1', {}).get('error', {})
        if y1_error.get('row_ids') and y1_error.get('column_id'):
            add_highlights(y1_error['row_ids'], y1_error['column_id'], '#f5f5f5', '#999')

        if selections.get('y2_enabled'):
            y2_data = selections.get('y2', {}).get('data', {})
            if y2_data.get('row_ids') and y2_data.get('column_id'):
                add_highlights(y2_data['row_ids'], y2_data['column_id'],
                              SECTION_COLORS['y2']['light'], SECTION_COLORS['y2']['main'])
            y2_error = selections.get('y2', {}).get('error', {})
            if y2_error.get('row_ids') and y2_error.get('column_id'):
                add_highlights(y2_error['row_ids'], y2_error['column_id'], '#f0f0f0', '#666')

        if active_selector:
            axis, kind = active_selector[0], active_selector[1]
            if axis == 'x':
                sel = selections['x']['data']
                add_highlights(sel.get('row_ids'), sel.get('column_id'),
                               SECTION_COLORS['x']['light'], SECTION_COLORS['x']['main'], bold=True)
            elif axis == 'y1':
                if kind == 'error':
                    sel = selections['y1']['error']
                    add_highlights(sel.get('row_ids'), sel.get('column_id'), '#F5F5F5', '#666', bold=True)
                else:
                    idx = active_selector[2] if len(active_selector) > 2 else 0
                    if idx < len(selections['y1']['series']):
                        series = selections['y1']['series'][idx]
                        shade = y1_shades[idx % len(y1_shades)]
                        add_highlights(series.get('row_ids'), series.get('column_id'),
                                       shade, SECTION_COLORS['y1']['main'], bold=True)
            elif axis == 'y2':
                sel = selections['y2'][kind]
                if kind == 'data':
                    add_highlights(sel.get('row_ids'), sel.get('column_id'),
                                   SECTION_COLORS['y2']['light'], SECTION_COLORS['y2']['main'], bold=True)
                else:
                    add_highlights(sel.get('row_ids'), sel.get('column_id'), '#EFEBE9', '#5D4037', bold=True)

        return style_conditions

    # Y2 toggle visibility
    @app.callback(
        Output('y2-controls', 'style'),
        Input('y2-enable', 'checked')
    )
    def toggle_y2(enabled):
        if enabled:
            return {'display': 'block'}
        return {'display': 'none'}
    
    # Y1 series management
    @app.callback(
        [Output('y1-series-count', 'data'),
         Output('y1-series-container', 'children'),
         Output('y1-count', 'children'),
         Output('pub-selections', 'data', allow_duplicate=True)],
        [Input('add-y1-series', 'n_clicks'),
         Input('remove-y1-series', 'n_clicks')],
        [State('y1-series-count', 'data'),
         State('pub-selections', 'data')],
        prevent_initial_call=True
    )
    def manage_y1_series(add_clicks, remove_clicks, count, selections):
        ctx = callback_context
        if not ctx.triggered:
            return dash.no_update
        
        triggered = ctx.triggered[0]['prop_id'].rsplit('.', 1)[0]
        if triggered == 'add-y1-series':
            count = min(count + 1, 10)
        elif triggered == 'remove-y1-series':
            count = max(count - 1, 1)
        
        # Update selections
        if not selections:
            selections = get_empty_selections(count)
        
        while len(selections['y1']['series']) < count:
            selections['y1']['series'].append({'row_ids': [], 'column_id': None})
        while len(selections['y1']['series']) > count:
            selections['y1']['series'].pop()
        
        return count, build_y1_series_controls(count), f"{count} series", selections

    # Quick-clear individual axis selections
    @app.callback(
        Output('pub-selections', 'data', allow_duplicate=True),
        [Input('clear-x', 'n_clicks'),
         Input('clear-y1', 'n_clicks'),
         Input('clear-y2', 'n_clicks')],
        State('pub-selections', 'data'),
        prevent_initial_call=True
    )
    def quick_clear_axis(clear_x, clear_y1, clear_y2, selections):
        ctx = callback_context
        if not ctx.triggered or not selections:
            return dash.no_update
        
        triggered = ctx.triggered[0]['prop_id'].rsplit('.', 1)[0]
        
        if triggered == 'clear-x':
            selections['x']['data'] = {'row_ids': [], 'column_id': None}
        elif triggered == 'clear-y1':
            for series in selections['y1']['series']:
                series['row_ids'] = []
                series['column_id'] = None
            selections['y1']['error'] = {'row_ids': [], 'column_id': None}
        elif triggered == 'clear-y2':
            selections['y2']['data'] = {'row_ids': [], 'column_id': None}
            selections['y2']['error'] = {'row_ids': [], 'column_id': None}
        
        return selections
    
    # Selector button handler
    @app.callback(
        [Output('active-selector', 'data'),
         Output('mode-indicator', 'children'),
         Output('btn-x-data', 'style'),
         Output({'type': 'btn-y1-data', 'index': ALL}, 'style'),
         Output('btn-y1-error', 'style'),
         Output('btn-y2-data', 'style'),
         Output('btn-y2-error', 'style'),
         Output('pub-table', 'selected_cells', allow_duplicate=True),
         Output('pub-table', 'selected_columns', allow_duplicate=True),
         Output('pub-table', 'active_cell', allow_duplicate=True)],
        [Input('btn-x-data', 'n_clicks'),
         Input({'type': 'btn-y1-data', 'index': ALL}, 'n_clicks'),
         Input('btn-y1-error', 'n_clicks'),
         Input('btn-y2-data', 'n_clicks'),
         Input('btn-y2-error', 'n_clicks')],
        [State('active-selector', 'data'),
         State('pub-selections', 'data')],
        prevent_initial_call=True
    )
    def handle_selector_buttons(x_dat, y1_clicks, y1_err, y2_dat, y2_err,
                                active_selector_state, selections):
        ctx = callback_context
        if not ctx.triggered:
            return dash.no_update

        def has_mapping(sel_obj):
            return bool(sel_obj and sel_obj.get('column_id') and sel_obj.get('row_ids'))

        def mapped(style, color_key):
            colors = SECTION_COLORS[color_key]
            st = style.copy()
            st.update({
                'border': f"2px solid {colors['main']}",
                'color': colors['main'],
                'backgroundColor': '#F9FAFB',
                'fontWeight': '600'
            })
            return st

        def style_for(color_key, is_active, is_mapped):
            if is_active:
                return selector_button_style(color_key, True)
            base = selector_button_style(color_key, False)
            return mapped(base, color_key) if is_mapped else base

        # Get triggered ID
        trig = getattr(ctx, "triggered_id", None)
        if trig is None:
            trig_str = ctx.triggered[0]['prop_id'].rsplit('.', 1)[0]
            try:
                trig = json.loads(trig_str)
            except Exception:
                trig = trig_str

        current = canon_selector(active_selector_state)
        selections = selections or get_empty_selections()

        # Determine candidate selector
        if trig == 'btn-x-data':
            candidate = ('x', 'data')
        elif trig == 'btn-y1-error':
            candidate = ('y1', 'error')
        elif trig == 'btn-y2-data':
            candidate = ('y2', 'data')
        elif trig == 'btn-y2-error':
            candidate = ('y2', 'error')
        elif isinstance(trig, dict) and trig.get('type') == 'btn-y1-data':
            candidate = ('y1', 'data', trig.get('index'))
        else:
            candidate = None

        candidate = canon_selector(candidate)

        # Guard: if trigger wasn't a recognized button (e.g. pattern-matching
        # ALL fired because y1-series-container was rebuilt), don't touch state.
        if candidate is None and current is not None:
            return (dash.no_update,) * 10

        new_sel = None if sel_eq(candidate, current) else candidate  # Toggle

        # Compute button count
        btn_count = len(y1_clicks) if isinstance(y1_clicks, list) else 0

        # Styles
        x_data_style = style_for('x', sel_eq(new_sel, ('x','data')), has_mapping(selections['x']['data']))

        y1_data_styles = []
        for i in range(btn_count):
            is_active = sel_eq(new_sel, ('y1','data', i))
            is_mapped = i < len(selections['y1']['series']) and has_mapping(selections['y1']['series'][i])
            y1_data_styles.append(style_for('y1', is_active, is_mapped))

        y1_error_style = style_for('y1', sel_eq(new_sel, ('y1','error')), has_mapping(selections['y1']['error']))
        y2_data_style = style_for('y2', sel_eq(new_sel, ('y2','data')), has_mapping(selections['y2']['data']))
        y2_error_style = style_for('y2', sel_eq(new_sel, ('y2','error')), has_mapping(selections['y2']['error']))

        # Clear table selection when turning OFF
        if new_sel is None:
            selected_cells, selected_columns, active_cell = [], [], None
        else:
            selected_cells = dash.no_update
            selected_columns = dash.no_update
            active_cell = dash.no_update

        store_value = list(new_sel) if new_sel is not None else None

        # Mode indicator banner
        if new_sel:
            axis_names = {'x': 'X-Axis', 'y1': 'Y\u2081-Axis', 'y2': 'Y\u2082-Axis'}
            axis_name = axis_names.get(new_sel[0], '')
            if len(new_sel) > 2 and new_sel[1] == 'data':
                indicator = f"Selecting {axis_name} Series {new_sel[2]+1} \u2022 Click column header to select entire column, or click individual cells"
            else:
                indicator = f"Selecting {axis_name} {new_sel[1]} \u2022 Click column header to select entire column, or click individual cells"
        else:
            indicator = ""

        return (store_value, indicator, x_data_style, y1_data_styles,
                y1_error_style, y2_data_style, y2_error_style,
                selected_cells, selected_columns, active_cell)
    
    # Table row addition
    # Rows and columns are added to the full table on the server, never to the page the browser shows.
    @app.callback(
        [Output('pub-table-source', 'data', allow_duplicate=True),
         Output('pub-data-store', 'data', allow_duplicate=True),
         Output('pub-table', 'page_current', allow_duplicate=True)],
        Input('add-row', 'n_clicks'),
        [State('pub-table-source', 'data'),
         State('pub-table', 'page_size')],
        prevent_initial_call=True
    )
    def add_new_row(n_clicks, source, page_size):
        df = table_store.frame(source)
        if df is None or len(df.columns) == 0:
            return dash.no_update, dash.no_update, dash.no_update

        # Create new empty row with next _row_id
        new_row_id = int(df['_row_id'].max()) + 1 if len(df) > 0 else 0
        new_row = {'_row_id': new_row_id}

        # Add empty values for all other columns
        for col in df.columns:
            if col != '_row_id':
                new_row[col] = ''

        df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
        ref = table_store.remember(df)
        last_page = (len(df) - 1) // (page_size or table_store.PAGE_SIZE)
        return ref, ref, last_page

    # Table column addition
    @app.callback(
        [Output('table-editor-container', 'children', allow_duplicate=True),
         Output('pub-data-store', 'data', allow_duplicate=True)],
        Input('add-column', 'n_clicks'),
        State('pub-table-source', 'data'),
        prevent_initial_call=True
    )
    def add_new_column(n_clicks, source):
        df = table_store.frame(source)
        if df is None or len(df.columns) == 0:
            return dash.no_update, dash.no_update

        # Find next available column name
        col_num = 1
        while f'New_Column_{col_num}' in df.columns:
            col_num += 1

        new_col_name = f'New_Column_{col_num}'
        df[new_col_name] = ''

        ref = table_store.remember(df)
        table_editor = create_data_table_editor(df, table_id='pub-table', source=ref)

        return table_editor, ref

    # Transpose data
    @app.callback(
        [Output('pub-data-store', 'data', allow_duplicate=True),
         Output('table-editor-container', 'children', allow_duplicate=True),
         Output('pub-selections', 'data', allow_duplicate=True)],
        Input('transpose-data', 'n_clicks'),
        State('pub-data-store', 'data'),
        State('y1-series-count', 'data'),
        prevent_initial_call=True
    )
    def transpose_data(n_clicks, data_json, y1_count):
        df = table_store.frame(data_json)
        if df is None:
            return dash.no_update

        df_transposed = transpose_dataframe(df)
        ref = table_store.remember(df_transposed)

        # Create new table
        table_editor = create_data_table_editor(df_transposed, table_id='pub-table', source=ref)

        # Clear selections after transpose
        return ref, table_editor, get_empty_selections(y1_count)

    # The Data table holds one page. It is filled only while the Data tab is shown; paging and sorting ask the
    # server for the rows, and edits on the page (cells, deleted rows or columns) are applied to the full table.
    @app.callback(
        [Output('pub-table', 'data'),
         Output('pub-table', 'page_count'),
         Output('pub-table', 'page_current'),
         Output('pub-table-source', 'data', allow_duplicate=True),
         Output('pub-data-store', 'data', allow_duplicate=True)],
        [Input('pub-table-source', 'data'),
         Input('analysis-tabs', 'value'),
         Input('pub-table', 'page_current'),
         Input('pub-table', 'sort_by'),
         Input('pub-table', 'data_timestamp'),
         Input('pub-table', 'columns')],
        [State('pub-table', 'data'),
         State('pub-table', 'data_previous'),
         State('pub-table', 'page_size'),
         State('active-tab', 'data')],
        prevent_initial_call='initial_duplicate'
    )
    def serve_table_page(source, shown_tab, page_current, sort_by, edited_at, columns,
                         rows, previous, page_size, active_tab):
        no = dash.no_update
        triggers = {t['prop_id'] for t in callback_context.triggered} if callback_context.triggered else set()
        edited = None
        if source and 'pub-table.data_timestamp' in triggers:
            edited = table_store.apply_page_edits(source, rows, previous)
        if source and 'pub-table.columns' in triggers and columns is not None:
            edited = table_store.drop_columns(edited or source, [c.get('id') for c in columns]) or edited
        if edited:
            store = edited if active_tab not in ('peak-analysis', 'across-samples') else no
            if len(rows or []) >= len(previous or []):
                return no, no, no, edited, store            # the page already shows the edit
            page_rows, count, current = table_store.page(edited, page_current, page_size, sort_by)
            return page_rows, count, (current if current != page_current else no), edited, store
        if shown_tab != 'data-overview':
            return no, no, no, no, no
        if not source:
            return [], 1, (0 if page_current else no), no, no
        page_rows, count, current = table_store.page(source, page_current, page_size, sort_by)
        return page_rows, count, (current if current != page_current else no), no, no
    
    # Save mapping
    @app.callback(
        Output('download-mapping', 'data'),
        Input('save-mapping', 'n_clicks'),
        State('pub-selections', 'data'),
        prevent_initial_call=True
    )
    def save_mapping(clicks, selections):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"plot_mapping_{timestamp}.json"
        return dict(content=json.dumps(selections, indent=2), filename=filename)
    
    # Load mapping
    @app.callback(
        Output('pub-selections', 'data', allow_duplicate=True),
        Input('upload-mapping', 'contents'),
        State('upload-mapping', 'filename'),
        prevent_initial_call=True
    )
    def load_mapping(contents, filename):
        if not contents:
            return dash.no_update
        
        content_type, content_string = contents.split(',')
        decoded = base64.b64decode(content_string)
        
        try:
            selections = json.loads(decoded.decode('utf-8'))
            return selections
        except:
            return dash.no_update
    
    # Trigger file dialog for load button
    app.clientside_callback(
        """
        function(n_clicks) {
            if(n_clicks > 0) {
                document.querySelector('#upload-mapping input[type=file]').click();
            }
            return '';
        }
        """,
        Output('upload-mapping', 'children'),
        Input('load-mapping', 'n_clicks'),
        prevent_initial_call=True
    )
    
    # Main selection handler with column-click support.
    # NOTE: This callback does NOT write to pub-table.style_data_conditional.
    # Highlighting is handled entirely by update_table_highlighting above,
    # which fires when pub-selections changes. This avoids a circular loop.
    @app.callback(
        [Output('pub-selections', 'data', allow_duplicate=True),
         Output('pub-data-store', 'data', allow_duplicate=True)],
        [Input('pub-table', 'selected_cells'),
         Input('pub-table', 'selected_columns'),
         Input('pub-table', 'active_cell'),
         Input('y2-enable', 'checked'),
         Input('clear-all', 'n_clicks')],
        [State('pub-table', 'data'),
         State('pub-table', 'sort_by'),
         State('pub-table-source', 'data'),
         State('active-selector', 'data'),
         State('pub-selections', 'data'),
         State('y1-series-count', 'data'),
         State('active-file', 'data'),
         State('active-tab', 'data')],
        prevent_initial_call=True
    )
    def update_selections(selected_cells, selected_columns, active_cell, y2_enabled, clear_clicks,
                          page_rows, sort_by, source, active_selector, selections, y1_count, active_file, active_tab):
        ctx = callback_context
        trigger_id = ctx.triggered[0]['prop_id'] if ctx.triggered else ''

        active_selector = canon_selector(active_selector)

        # ── Guard: on shared tabs, pub-table is the per-file table and is
        # irrelevant — pub-data-store holds shared table data for the plot.
        # Bail out completely to prevent overwriting it.
        if active_tab in ('peak-analysis', 'across-samples'):
            return dash.no_update, dash.no_update

        # Edits reach pub-data-store through serve_table_page; this callback only maps cells to axes. Cell
        # positions are rows of the shown page (page_rows), whole columns come from the full table (source).
        is_selection_trigger = ('selected_cells' in trigger_id or 'selected_columns' in trigger_id or 'active_cell' in trigger_id)
        is_clear = 'clear-all' in trigger_id
        is_y2 = 'y2-enable' in trigger_id

        # ── Guard: bounce from table re-render.
        # After update_table_highlighting writes style_data_conditional the
        # DataTable clears selected_cells/active_cell.  That fires us again
        # with empty selection data.  Returning no_update breaks the loop.
        if is_selection_trigger and not is_clear and not is_y2:
            has_cells = selected_cells and len(selected_cells) > 0
            has_columns = selected_columns and len(selected_columns) > 0
            has_active = active_cell is not None
            if not has_cells and not has_columns and not has_active:
                return dash.no_update, dash.no_update

        if not selections:
            selections = get_empty_selections(y1_count)

        selections['y2_enabled'] = bool(y2_enabled)

        if is_clear:
            new_sel = get_empty_selections(y1_count)
            if active_file:
                new_sel['file_id'] = active_file
            return new_sel, source or None

        if not source:
            return selections, None

        data_json = source
        page = pd.DataFrame(page_rows or [])

        if isinstance(selections, dict) and active_file:
            selections.setdefault('file_id', active_file)

        # Only modify selections while a selector is active and user clicked cells
        if active_selector and is_selection_trigger:
            axis, kind = active_selector[0], active_selector[1]
            target = None

            if axis == 'x':
                target = selections['x']['data']
            elif axis == 'y1':
                if kind == 'error':
                    target = selections['y1']['error']
                else:
                    idx = active_selector[2] if len(active_selector) > 2 else 0
                    if idx < len(selections['y1']['series']):
                        target = selections['y1']['series'][idx]
            elif axis == 'y2':
                target = selections['y2'][kind]

            if target is not None:
                # Whole column selection - select only non-empty cells
                if 'selected_columns' in trigger_id and selected_columns:
                    col_id = selected_columns[0]
                    full = table_store.frame(source)
                    if col_id != '_row_id' and full is not None and col_id in full.columns:
                        full = table_store.sorted_frame(full, sort_by)
                        values = full[col_id]
                        filled = values.notna() & (values.astype(str).str.strip() != '')
                        target['row_ids'] = [int(rid) for rid in full.loc[filled, '_row_id']]
                        target['column_id'] = col_id

                # Individual cells (with shift-select support)
                elif 'selected_cells' in trigger_id and selected_cells:
                    col_id = selected_cells[0].get('column_id') if selected_cells else None
                    if col_id and col_id != '_row_id':
                        if target.get('column_id') and col_id != target['column_id']:
                            target['column_id'] = col_id
                            target['row_ids'] = []
                        if not target.get('column_id'):
                            target['column_id'] = col_id
                            target['row_ids'] = []

                        new_row_ids = set()
                        for cell in selected_cells:
                            if cell.get('column_id') == col_id:
                                row_idx = cell.get('row')
                                if row_idx is not None and 0 <= row_idx < len(page) and '_row_id' in page:
                                    new_row_ids.add(int(page.iloc[row_idx]['_row_id']))

                        existing = set(target['row_ids'])
                        if new_row_ids and new_row_ids.issubset(existing):
                            target['row_ids'] = list(existing - new_row_ids)
                        elif new_row_ids:
                            target['row_ids'] = list(existing | new_row_ids)

                # Single cell click
                elif 'active_cell' in trigger_id and active_cell:
                    row_idx = active_cell.get('row')
                    col_id = active_cell.get('column_id')
                    if row_idx is not None and col_id and col_id != '_row_id':
                        if 0 <= row_idx < len(page) and '_row_id' in page:
                            row_id = int(page.iloc[row_idx]['_row_id'])
                            if target.get('column_id') and col_id != target['column_id']:
                                target['column_id'] = col_id
                                target['row_ids'] = [row_id]
                            else:
                                if not target.get('row_ids'):
                                    target['row_ids'] = []
                                if not target.get('column_id'):
                                    target['column_id'] = col_id
                                if row_id in target['row_ids']:
                                    target['row_ids'].remove(row_id)
                                else:
                                    target['row_ids'].append(row_id)

        # Tag file_id so downstream callbacks stay synced
        if isinstance(selections, dict) and active_file:
            selections['file_id'] = active_file

        return selections, data_json
    
    # Save selections to memory whenever the selections store updates
    @app.callback(
        [Output('file-ui-state', 'data', allow_duplicate=True),
         Output('dummy-output', 'children', allow_duplicate=True)],
        Input('pub-selections', 'data'),
        [State('active-file', 'data'),
         State('file-ui-state', 'data'),
         State('active-tab', 'data')],
        prevent_initial_call=True
    )
    def save_selections_for_file(selections, active_file, file_ui_state, active_tab):
        """Persist current selections for the active file when user makes changes.

        Don't save when on peak-analysis or across-samples tabs — those
        selections are shared and live in tab-specific shared stores, not per-file.
        """
        if active_tab in ('peak-analysis', 'across-samples'):
            return dash.no_update, dash.no_update

        if not active_file or not selections:
            return dash.no_update, dash.no_update
        
        # Ensure selections are tagged to the active file
        sel_file = selections.get('file_id') if isinstance(selections, dict) else None
        if isinstance(selections, dict) and active_file and sel_file and sel_file != active_file:
            log.debug(f"⚠️ SAVE SKIP - selections belong to {str(sel_file)[:8]} but active file is {active_file[:8]}")
            return dash.no_update, dash.no_update

        if isinstance(selections, dict):
            selections = _clean_selection_for_state(selections)
            if active_file:
                selections['file_id'] = active_file

        current_state = None
        if isinstance(file_ui_state, dict) and file_ui_state.get('file_id') == active_file:
            current_state = dict(file_ui_state)
        else:
            current_state = data_manager.get_file_state(active_file)

        existing = _clean_selection_for_state(current_state.get('pub_selections'))
        selections = _clean_selection_for_state(selections)
        if existing == selections:
            log.debug(f"⏭️  Skipping save for {active_file[:8]}... (selections unchanged)")
            return dash.no_update, dash.no_update

        current_state['pub_selections'] = selections
        current_state['file_id'] = active_file
        saved_state = data_manager.save_file_state(active_file, current_state)

        x_col = selections.get('x', {}).get('data', {}).get('column_id')
        y1_series = [s.get('column_id') for s in selections.get('y1', {}).get('series', []) if s.get('column_id')]

        log.debug(f"💾 SAVE DEBUG - {active_file[:8]}...")
        log.debug(f"   Saved to memory: X={x_col}, Y1={y1_series}")
        log.debug(f"   Selection file_id: {selections.get('file_id', 'MISSING!')}")
        log.debug(f"   Selection keys: {list(selections.keys()) if isinstance(selections, dict) else 'NOT_DICT'}")
        log.debug(f"   Total files in memory: {len(data_manager.publication_memory)}")

        return saved_state, dash.no_update
    
    # Plot update — reads ONLY current-plot-settings (single source of truth)
    @app.callback(
        Output('pub-plot-figure', 'data'),
        Output('pub-plot-trigger', 'data'),
        Output('plot-export-data', 'data'),
        [Input('pub-selections', 'data'),
         Input('pub-data-store', 'data'),
         Input('current-plot-settings', 'data')],
        [State('active-file', 'data'),
         State('active-tab', 'data')],
        prevent_initial_call=True
    )
    def update_pub_plot(selections, data_json, settings,
                        active_file, active_tab):
        import plotly.graph_objects as go
        import pandas as pd
        import time
        from services.plot_settings_service import DEFAULT_PLOT_SETTINGS

        try:
            s = {**DEFAULT_PLOT_SETTINGS, **(settings or {})}

            if not data_json or selections is None:
                fig = go.Figure()
                fig.add_annotation(text="Select data to plot", xref="paper", yref="paper",
                                   x=0.5, y=0.5, showarrow=False, font=dict(size=14, color='#999'))
                fig.update_layout(plot_bgcolor='white', paper_bgcolor='white', autosize=True)
                return fig, time.time(), None

            df = table_store.frame(data_json)
            if df is None:
                fig = go.Figure()
                fig.add_annotation(text="Select data to plot", xref="paper", yref="paper",
                                   x=0.5, y=0.5, showarrow=False, font=dict(size=14, color='#999'))
                fig.update_layout(plot_bgcolor='white', paper_bgcolor='white', autosize=True)
                return fig, time.time(), None
            if '_row_id' not in df.columns:
                df.insert(0, '_row_id', range(len(df)))

            # Race guard: selections belong to a different file
            if active_tab not in ('peak-analysis', 'across-samples'):
                sel_file = selections.get('file_id') if isinstance(selections, dict) else None
                if sel_file is not None and active_file is not None and sel_file != active_file:
                    fig = go.Figure()
                    fig.add_annotation(text="Loading...", xref="paper", yref="paper",
                                       x=0.5, y=0.5, showarrow=False, font=dict(size=14, color='#999'))
                    fig.update_layout(plot_bgcolor='white', paper_bgcolor='white', autosize=True)
                    return fig, time.time(), None

            x_col = selections.get('x', {}).get('data', {}).get('column_id')
            y1_series = selections.get('y1', {}).get('series', [])
            y2_series = selections.get('y2', {}).get('series', [])

            if not x_col or len([sr for sr in y1_series if sr.get('column_id')]) == 0:
                fig = go.Figure()
                fig.add_annotation(text="Select X and at least one Y₁ series", xref="paper", yref="paper",
                                   x=0.5, y=0.5, showarrow=False, font=dict(size=14, color='#999'))
                fig.update_layout(plot_bgcolor='white', paper_bgcolor='white', autosize=True)
                return fig, time.time(), None

            # Column existence check (race during file switch)
            columns_to_check = [x_col] + [sr.get('column_id') for sr in y1_series if sr.get('column_id')]
            if selections.get('y2_enabled'):
                columns_to_check += [sr.get('column_id') for sr in y2_series if sr.get('column_id')]
            missing = [c for c in columns_to_check if c not in df.columns]
            if missing:
                fig = go.Figure()
                fig.add_annotation(text="Loading...", xref="paper", yref="paper",
                                   x=0.5, y=0.5, showarrow=False, font=dict(size=14, color='#999'))
                fig.update_layout(plot_bgcolor='white', paper_bgcolor='white', autosize=True)
                return fig, time.time(), None

            # Build plot from settings (all values come from current-plot-settings)
            plot_config = {
                'type': s['plot_type'],
                'calc_stats': len(s['y1_stats']) > 0,
                'stat_type': s['y1_stats'][0] if s['y1_stats'] else 'mean_sd',
                'x_label': s['x_label'],
                'y1_label': s['y1_label'],
                'y2_label': s['y2_label'],
                'show_raw_points': s['show_raw_points'],
                'categorical_x': s.get('categorical_x', True),
            }

            from services.area_display_units import area_label, publication_area_units
            displayed_area = area_label(df)
            plot_frame, plot_selections = publication_area_units(df, selections)
            if displayed_area != 'Area':
                for axis in ('y1', 'y2'):
                    if any(series.get('column_id') == 'Area' for series in selections.get(axis, {}).get('series', [])):
                        if plot_config.get(f'{axis}_label') in ('', 'Area', axis.upper(), None):
                            plot_config[f'{axis}_label'] = displayed_area
                            s[f'{axis}_label'] = displayed_area
            fig, export_data = create_publication_plot(plot_frame, None, plot_selections, plot_config)

            # Apply visual styling via PlotSettingsService
            # Store keys now match dataclass fields; only y_label needs mapping
            settings_for_style = dict(s, y_label=s.get('y1_label', 'Y1'))
            ps = PlotSettingsService.from_dict(settings_for_style)
            PlotSettingsService.apply_to_figure(fig, ps)

            return fig, time.time(), export_data

        except Exception as e:
            log.exception("Error creating publication plot")
            fig = go.Figure()
            fig.add_annotation(text=f"Error creating plot: {str(e)}", xref="paper", yref="paper",
                               x=0.5, y=0.5, showarrow=False, font=dict(size=12, color='#d32f2f'))
            fig.update_layout(plot_bgcolor='white', paper_bgcolor='white', autosize=True)
            return fig, time.time(), None

    # ── Secondary table selection handlers ──────────────────────────────
    # When the user selects data on peak-table or cross-sample-table,
    # mirror the data + selections into pub-data-store / pub-selections
    # so the existing analysis plot pipeline renders them.

    def _handle_secondary_table_selection(
        selected_cells, selected_columns, active_cell, table_data, virtual_data,
        active_selector, selections, y1_count, active_file, table_name,
        shared_sel=None, active_tab=None
    ):
        """Shared handler for peak-table and cross-sample-table selections.

        Returns (pub_selections, pub_data_store, shared_selections).
        """
        NO_UPDATE = (dash.no_update, dash.no_update, dash.no_update)
        ctx = callback_context
        # Check ALL triggers (not just the first) — when a DataTable is recreated,
        # data + selected_cells + active_cell may all fire simultaneously
        all_trigger_ids = [t['prop_id'] for t in ctx.triggered] if ctx.triggered else ['']
        trigger_str = ' '.join(all_trigger_ids)

        # Determine which tab this table belongs to
        table_tab = 'peak-analysis' if table_name == 'peak-table' else 'across-samples'
        # If this table's tab is NOT currently active, only update the table's
        # shared selections store
        # (don't push to pub-selections/pub-data-store or it will override the active tab's data)
        tab_is_active = (active_tab == table_tab)

        active_selector = canon_selector(active_selector)

        is_selection_trigger = ('selected_cells' in trigger_str or 'selected_columns' in trigger_str or 'active_cell' in trigger_str)
        is_data_trigger = any(('.data' in t and 'selected' not in t) for t in all_trigger_ids)

        # Pick default X column based on table type
        default_x = 'RT (min)' if table_name == 'peak-table' else 'Sample'

        # On data change: refresh selections to match new data.
        # Prioritise data trigger even if empty selection triggers fire simultaneously
        # (happens when DataTable is recreated and all props change at once).
        has_real_selection = (is_selection_trigger and (
            (selected_cells and len(selected_cells) > 0) or
            (selected_columns and len(selected_columns) > 0) or
            active_cell is not None))
        if is_data_trigger and not has_real_selection and table_data:
            df = pd.DataFrame(table_data)
            if '_row_id' not in df.columns:
                df.insert(0, '_row_id', range(len(df)))
            data_json = df.to_json(orient='split')

            if _selection_matches_defaults(shared_sel, x_col=default_x, y_col='Area'):
                # Keep column mappings, refresh row_ids for new data
                refreshed = _refresh_selection_row_ids(shared_sel, df)
                log.debug(f"📋 {table_name} data changed → refreshed row_ids (tab_active={tab_is_active})")
                if tab_is_active:
                    return refreshed, data_json, refreshed
                else:
                    # Only persist to the shared store, don't overwrite the active plot
                    return dash.no_update, dash.no_update, refreshed
            else:
                defaults = _build_default_selections(df, x_col=default_x, y_col='Area')
                if defaults:
                    log.debug(f"📋 {table_name} data loaded → enforced defaults (X={default_x}, Y1=Area, tab_active={tab_is_active})")
                    if tab_is_active:
                        return defaults, data_json, defaults
                    else:
                        return dash.no_update, dash.no_update, defaults
            return NO_UPDATE

        # Only act on actual cell/column clicks
        if not is_selection_trigger:
            return NO_UPDATE

        # Bounce guard for empty selections (table re-render)
        has_cells = selected_cells and len(selected_cells) > 0
        has_columns = selected_columns and len(selected_columns) > 0
        has_active = active_cell is not None
        if not has_cells and not has_columns and not has_active:
            return NO_UPDATE

        if not table_data:
            return NO_UPDATE

        if not selections:
            selections = get_empty_selections(y1_count)

        df_original = pd.DataFrame(table_data)
        df_sorted = pd.DataFrame(virtual_data) if virtual_data else df_original.copy()
        data_json = df_original.to_json(orient='split')

        # Ensure _row_id
        if '_row_id' not in df_original.columns:
            df_original.insert(0, '_row_id', range(len(df_original)))
        if '_row_id' not in df_sorted.columns:
            df_sorted.insert(0, '_row_id', range(len(df_sorted)))

        if active_file and isinstance(selections, dict):
            selections.setdefault('file_id', active_file)

        # Apply selection logic (same as pub-table handler)
        if active_selector and is_selection_trigger:
            axis, kind = active_selector[0], active_selector[1]
            target = None

            if axis == 'x':
                target = selections['x']['data']
            elif axis == 'y1':
                if kind == 'error':
                    target = selections['y1']['error']
                else:
                    idx = active_selector[2] if len(active_selector) > 2 else 0
                    if idx < len(selections['y1']['series']):
                        target = selections['y1']['series'][idx]
            elif axis == 'y2':
                target = selections['y2'][kind]

            if target is not None:
                if 'selected_columns' in trigger_str and selected_columns:
                    col_id = selected_columns[0]
                    if col_id != '_row_id':
                        non_empty_rows = []
                        for _, row in df_sorted.iterrows():
                            val = row[col_id]
                            if pd.notna(val) and str(val).strip() != '':
                                non_empty_rows.append(int(row['_row_id']))
                        target['row_ids'] = non_empty_rows
                        target['column_id'] = col_id

                elif 'selected_cells' in trigger_str and selected_cells:
                    col_id = selected_cells[0].get('column_id') if selected_cells else None
                    if col_id and col_id != '_row_id':
                        if target.get('column_id') and col_id != target['column_id']:
                            target['column_id'] = col_id
                            target['row_ids'] = []
                        if not target.get('column_id'):
                            target['column_id'] = col_id
                            target['row_ids'] = []

                        new_row_ids = set()
                        for cell in selected_cells:
                            if cell.get('column_id') == col_id:
                                row_idx = cell.get('row')
                                if row_idx is not None and 0 <= row_idx < len(df_sorted):
                                    new_row_ids.add(int(df_sorted.iloc[row_idx]['_row_id']))

                        existing = set(target['row_ids'])
                        if new_row_ids and new_row_ids.issubset(existing):
                            target['row_ids'] = list(existing - new_row_ids)
                        elif new_row_ids:
                            target['row_ids'] = list(existing | new_row_ids)

                elif 'active_cell' in trigger_str and active_cell:
                    row_idx = active_cell.get('row')
                    col_id = active_cell.get('column_id')
                    if row_idx is not None and col_id and col_id != '_row_id':
                        if 0 <= row_idx < len(df_sorted):
                            row_id = int(df_sorted.iloc[row_idx]['_row_id'])
                            if target.get('column_id') and col_id != target['column_id']:
                                target['column_id'] = col_id
                                target['row_ids'] = [row_id]
                            else:
                                if not target.get('row_ids'):
                                    target['row_ids'] = []
                                if not target.get('column_id'):
                                    target['column_id'] = col_id
                                if row_id in target['row_ids']:
                                    target['row_ids'].remove(row_id)
                                else:
                                    target['row_ids'].append(row_id)

        if isinstance(selections, dict) and active_file:
            selections['file_id'] = active_file

        # Return to both pub-selections (for plot) and the table's shared store
        return selections, data_json, selections

    @app.callback(
        [Output('pub-selections', 'data', allow_duplicate=True),
         Output('pub-data-store', 'data', allow_duplicate=True),
         Output('peak-shared-selections', 'data', allow_duplicate=True)],
        [Input('peak-table', 'selected_cells'),
         Input('peak-table', 'selected_columns'),
         Input('peak-table', 'active_cell'),
         Input('peak-table', 'data')],
        [State('peak-table', 'derived_virtual_data'),
         State('active-selector', 'data'),
         State('pub-selections', 'data'),
         State('y1-series-count', 'data'),
         State('active-file', 'data'),
         State('peak-shared-selections', 'data'),
         State('active-tab', 'data')],
        prevent_initial_call=True
    )
    def handle_peak_table_selection(selected_cells, selected_columns, active_cell, table_data,
                                     virtual_data, active_selector, selections, y1_count, active_file,
                                     shared_sel, active_tab):
        return _handle_secondary_table_selection(
            selected_cells, selected_columns, active_cell, table_data, virtual_data,
            active_selector, selections, y1_count, active_file, 'peak-table',
            shared_sel=shared_sel, active_tab=active_tab
        )

    @app.callback(
        [Output('pub-selections', 'data', allow_duplicate=True),
         Output('pub-data-store', 'data', allow_duplicate=True),
         Output('cross-shared-selections', 'data', allow_duplicate=True)],
        [Input('cross-sample-table', 'selected_cells'),
         Input('cross-sample-table', 'selected_columns'),
         Input('cross-sample-table', 'active_cell'),
         Input('cross-sample-table', 'data')],
        [State('cross-sample-table', 'derived_virtual_data'),
         State('active-selector', 'data'),
         State('pub-selections', 'data'),
         State('y1-series-count', 'data'),
         State('active-file', 'data'),
         State('cross-shared-selections', 'data'),
         State('active-tab', 'data')],
        prevent_initial_call=True
    )
    def handle_cross_sample_table_selection(selected_cells, selected_columns, active_cell, table_data,
                                             virtual_data, active_selector, selections, y1_count, active_file,
                                             shared_sel, active_tab):
        return _handle_secondary_table_selection(
            selected_cells, selected_columns, active_cell, table_data, virtual_data,
            active_selector, selections, y1_count, active_file, 'cross-sample-table',
            shared_sel=shared_sel, active_tab=active_tab
        )
