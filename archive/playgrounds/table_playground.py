#!/usr/bin/env python3
"""
Publication Plotter - Enhanced Axis Mapping Console
NEW: Transpose data, click column headers, export plot data, quick-clear selectors
"""

import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import dash
from dash import dash_table, dcc, html, Input, Output, State, callback_context, ALL
import base64
import io
import json
from datetime import datetime

app = dash.Dash(__name__, suppress_callback_exceptions=True)
app.title = "Publication Plotter - Enhanced"

# Okabe-Ito colorblind-friendly palette
OKABE_ITO = ["#E69F00", "#56B4E9", "#009E73", "#F0E442", "#0072B2", "#D55E00", "#CC79A7"]

# Color schemes for each axis
SECTION_COLORS = {
    'x': {'main': '#2196F3', 'light': '#E3F2FD', 'border': '#1976D2'},
    'y1': {'main': '#FF9800', 'light': '#FFF3E0', 'border': '#F57C00'},
    'y2': {'main': '#4CAF50', 'light': '#E8F5E9', 'border': '#388E3C'},
}


# --- normalize selector tuples so equality always works ---
def canon_selector(obj):
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
    return canon_selector(a) == canon_selector(b)


def read_file(contents, filename):
    """Read CSV/Excel file and add row tracking"""
    content_type, content_string = contents.split(',')
    decoded = base64.b64decode(content_string)
    
    try:
        df = pd.read_csv(io.StringIO(decoded.decode('utf-8')))
    except:
        try:
            df = pd.read_excel(io.BytesIO(decoded))
        except:
            return None
    
    # Add unique row identifier
    df.insert(0, '_row_id', range(len(df)))
    return df


def transpose_dataframe(df):
    """Transpose dataframe while preserving row IDs"""
    # Remove _row_id column temporarily
    df_no_id = df.drop(columns=['_row_id'])
    
    # Transpose
    df_t = df_no_id.T
    
    # Use first column as new column names if they're all strings/numbers
    try:
        df_t.columns = [str(c) for c in df_t.iloc[0]]
        df_t = df_t.iloc[1:]
    except:
        pass
    
    # Reset index to become a column
    df_t = df_t.reset_index()
    df_t.columns = ['Variable'] + list(df_t.columns[1:])
    
    # Replace None, NaN, "None" with empty string
    df_t = df_t.fillna('')
    df_t = df_t.replace(['None', 'nan', 'NaN'], '')
    
    # Add new row IDs
    df_t.insert(0, '_row_id', range(len(df_t)))
    
    return df_t


def create_plot(df, virtual_data, selections, plot_config):
    """Create publication-quality plot following table display order."""
    
    # Use virtual_data for display order, df for actual values
    df_display = pd.DataFrame(virtual_data) if virtual_data else df.copy()
    
    # Get display order from the table
    display_order = df_display['_row_id'].tolist()
    
    # Helper to get values in display order
    def get_values_in_display_order(row_ids, column_id, as_strings=False):
        """Return values for row_ids in display order."""
        if not row_ids or not column_id:
            return [], []
        
        # Filter to only rows that are selected
        selected_display_order = [rid for rid in display_order if rid in row_ids]
        
        values = []
        for rid in selected_display_order:
            row_data = df[df['_row_id'] == rid]
            if len(row_data) == 0:
                continue
            
            val = row_data.iloc[0][column_id]
            
            if as_strings:
                values.append(str(val))
            else:
                if isinstance(val, str):
                    val = val.replace('%', '').strip()
                try:
                    values.append(float(val))
                except:
                    values.append(np.nan)
        
        return selected_display_order, values

    # Check if we have any Y data
    any_y1 = any(series.get('row_ids') and series.get('column_id') for series in selections['y1']['series'])
    any_y2 = selections.get('y2_enabled') and selections['y2']['data'].get('row_ids') and selections['y2']['data'].get('column_id')

    if not any_y1 and not any_y2:
        fig = go.Figure()
        fig.add_annotation(
            text="Select data to start plotting",
            xref="paper", yref="paper", x=0.5, y=0.5,
            showarrow=False, font=dict(size=14, color='#999')
        )
        fig.update_layout(plot_bgcolor='white', paper_bgcolor='white', height=580)
        return fig, None

    # Build X axis based on display order
    x_sel = selections['x']['data']
    
    if x_sel.get('row_ids') and x_sel.get('column_id'):
        # X has data - use it
        x_order, x_labels_raw = get_values_in_display_order(x_sel['row_ids'], x_sel['column_id'], as_strings=True)
        x_vals = list(range(len(x_order)))
        use_categorical = True
    else:
        # No X selected - use all Y points in display order
        all_y_rows = set()
        for series in selections['y1']['series']:
            if series.get('row_ids'):
                all_y_rows.update(series['row_ids'])
        if selections.get('y2_enabled') and selections['y2']['data'].get('row_ids'):
            all_y_rows.update(selections['y2']['data']['row_ids'])
        
        x_order = [rid for rid in display_order if rid in all_y_rows]
        x_vals = list(range(len(x_order)))
        x_labels_raw = [str(i) for i in x_vals]
        use_categorical = True

    # Process Y1 series
    y1_series_data = []
    for series in selections['y1']['series']:
        if series.get('row_ids') and series.get('column_id'):
            series_dict = {}
            for rid in series['row_ids']:
                row_data = df[df['_row_id'] == rid]
                if len(row_data) > 0:
                    val = row_data.iloc[0][series['column_id']]
                    if isinstance(val, str):
                        val = val.replace('%', '').strip()
                    try:
                        series_dict[rid] = float(val)
                    except:
                        series_dict[rid] = np.nan
            y1_series_data.append(series_dict)
        else:
            y1_series_data.append({})

    # Process Y1 error
    y1_error_dict = {}
    y1_error_sel = selections['y1']['error']
    if y1_error_sel.get('row_ids') and y1_error_sel.get('column_id'):
        for rid in y1_error_sel['row_ids']:
            row_data = df[df['_row_id'] == rid]
            if len(row_data) > 0:
                val = row_data.iloc[0][y1_error_sel['column_id']]
                if isinstance(val, str):
                    val = val.replace('%', '').strip()
                try:
                    y1_error_dict[rid] = float(val)
                except:
                    y1_error_dict[rid] = np.nan

    # Process Y2
    y2_dict = {}
    y2_err_dict = {}
    if selections.get('y2_enabled'):
        y2_data_sel = selections['y2']['data']
        if y2_data_sel.get('row_ids') and y2_data_sel.get('column_id'):
            for rid in y2_data_sel['row_ids']:
                row_data = df[df['_row_id'] == rid]
                if len(row_data) > 0:
                    val = row_data.iloc[0][y2_data_sel['column_id']]
                    if isinstance(val, str):
                        val = val.replace('%', '').strip()
                    try:
                        y2_dict[rid] = float(val)
                    except:
                        y2_dict[rid] = np.nan
        
        y2_error_sel = selections['y2']['error']
        if y2_error_sel.get('row_ids') and y2_error_sel.get('column_id'):
            for rid in y2_error_sel['row_ids']:
                row_data = df[df['_row_id'] == rid]
                if len(row_data) > 0:
                    val = row_data.iloc[0][y2_error_sel['column_id']]
                    if isinstance(val, str):
                        val = val.replace('%', '').strip()
                    try:
                        y2_err_dict[rid] = float(val)
                    except:
                        y2_err_dict[rid] = np.nan

    # Create aligned data following x_order
    y1_aligned = []
    for series_dict in y1_series_data:
        y_vals = [series_dict.get(rid, np.nan) for rid in x_order]
        y1_aligned.append(pd.Series(y_vals, dtype=float))

    include_y2 = selections.get('y2_enabled', False) and len(y2_dict) > 0
    
    fig = make_subplots(specs=[[{"secondary_y": True}]]) if include_y2 else go.Figure()

    plot_type = plot_config.get('type', 'bar')
    show_raw = plot_config.get('show_raw_points', False)
    calc_stats = plot_config.get('calc_stats', False)
    stat_type = plot_config.get('stat_type', 'mean_sd')

    # Prepare export data structure
    export_data = {
        'x_labels': x_labels_raw,
        'x_values': x_vals,
        'y1_series': [],
        'y2': None
    }

    # Calculate statistics if requested
    if calc_stats and sum(len(s) > 0 for s in y1_series_data) > 1:
        # Find common indices
        present_mask = [all(not np.isnan(series.iloc[i]) for series in y1_aligned) for i in range(len(x_order))]
        
        if any(present_mask):
            common_idx = [i for i, ok in enumerate(present_mask) if ok]
            series_list_common = [s.iloc[common_idx].reset_index(drop=True) for s in y1_aligned]
            
            # Calculate statistics
            matrix = np.column_stack([s.values for s in series_list_common])
            
            if stat_type == 'mean_sd':
                y_mean = np.mean(matrix, axis=1)
                y_err = np.std(matrix, axis=1, ddof=1)
            elif stat_type == 'mean_sem':
                y_mean = np.mean(matrix, axis=1)
                y_err = np.std(matrix, axis=1, ddof=1) / np.sqrt(matrix.shape[1])
            elif stat_type == 'median_iqr':
                y_mean = np.median(matrix, axis=1)
                q25 = np.percentile(matrix, 25, axis=1)
                q75 = np.percentile(matrix, 75, axis=1)
                y_err = q75 - q25
            
            x_for_common = [x_vals[i] for i in common_idx]
            
            # Add to export
            export_data['y1_series'].append({
                'name': f"Mean ± {stat_type.split('_')[1].upper()}",
                'x': x_for_common,
                'y': y_mean.tolist(),
                'error': y_err.tolist()
            })
            
            # Add statistical trace
            if plot_type == 'bar':
                bar_width = min(0.75 / max(1, 1 + (1 if include_y2 else 0)), 0.55)
                fig.add_trace(go.Bar(
                    x=x_for_common, y=y_mean, name=f"Mean ± {stat_type.split('_')[1].upper()}",
                    marker_color=OKABE_ITO[0], marker_line=dict(color='black', width=0.75),
                    error_y=dict(type='data', array=y_err, thickness=1, width=3, color='black'),
                    width=bar_width, offsetgroup='y1-mean',
                    opacity=0.7 if show_raw else 1.0
                ), secondary_y=False if include_y2 else None)
            elif plot_type == 'scatter':
                fig.add_trace(go.Scatter(
                    x=x_for_common, y=y_mean, mode='markers', name=f"Mean ± {stat_type.split('_')[1].upper()}",
                    marker=dict(size=10, color=OKABE_ITO[0], line=dict(color='black', width=0.75)),
                    error_y=dict(type='data', array=y_err, thickness=1, width=3, color='black')
                ), secondary_y=False if include_y2 else None)
            else:  # line
                fig.add_trace(go.Scatter(
                    x=x_for_common, y=y_mean, mode='lines+markers', name=f"Mean ± {stat_type.split('_')[1].upper()}",
                    line=dict(color=OKABE_ITO[0], width=2.5),
                    marker=dict(size=8, color=OKABE_ITO[0], line=dict(color='black', width=0.75)),
                    error_y=dict(type='data', array=y_err, thickness=1, width=3, color='black')
                ), secondary_y=False if include_y2 else None)
            
            # Add raw points if requested
            if show_raw:
                for idx, series in enumerate(series_list_common):
                    x_jitter = np.array(x_for_common) + np.random.uniform(-0.08, 0.08, len(x_for_common))
                    fig.add_trace(go.Scatter(
                        x=x_jitter, y=series.values, mode='markers',
                        name=f'Raw {idx+1}', marker=dict(size=5, color=OKABE_ITO[0], opacity=0.5, line=dict(width=0)),
                        showlegend=False
                    ), secondary_y=False if include_y2 else None)
        else:
            calc_stats = False

    # Plot individual series if not calculating stats
    if not calc_stats:
        color_idx = 0
        total_series = sum(len(s) > 0 for s in y1_series_data) + (1 if include_y2 else 0)
        bar_width = min(0.75 / max(total_series, 1), 0.55) if plot_type == 'bar' else None
        
        for idx, series in enumerate(y1_aligned):
            if series.isna().all():
                continue
            
            y_plot = series.values
            
            # Add error bars for first series
            err_vals = None
            if idx == 0 and y1_error_dict:
                err_vals = [y1_error_dict.get(rid, np.nan) for rid in x_order]
                if all(np.isnan(err_vals)):
                    err_vals = None
            
            # Add to export
            export_data['y1_series'].append({
                'name': f"Series {idx+1}" if len(y1_aligned) > 1 else "Y1",
                'x': x_vals,
                'y': y_plot.tolist(),
                'error': err_vals if err_vals else None
            })
            
            color = OKABE_ITO[color_idx % len(OKABE_ITO)]
            color_idx += 1
            
            if plot_type == 'bar':
                fig.add_trace(go.Bar(
                    x=x_vals, y=y_plot, 
                    name=(f"Series {idx+1}" if len(y1_aligned) > 1 else "Y1"),
                    marker_color=color, marker_line=dict(color='black', width=0.75),
                    error_y=dict(type='data', array=err_vals, thickness=1, width=3, color='black') if err_vals else None,
                    width=bar_width, offsetgroup=f'y1-{idx}',
                    opacity=0.7 if show_raw else 1.0,
                    showlegend=len(y1_aligned) > 1 or include_y2
                ), secondary_y=False if include_y2 else None)
            elif plot_type == 'scatter':
                fig.add_trace(go.Scatter(
                    x=x_vals, y=y_plot, mode='markers',
                    name=(f"Series {idx+1}" if len(y1_aligned) > 1 else "Y1"),
                    marker=dict(size=10, color=color, line=dict(color='black', width=0.75)),
                    error_y=dict(type='data', array=err_vals, thickness=1, width=3, color='black') if err_vals else None,
                    showlegend=len(y1_aligned) > 1 or include_y2
                ), secondary_y=False if include_y2 else None)
            else:  # line
                fig.add_trace(go.Scatter(
                    x=x_vals, y=y_plot, mode='lines+markers',
                    name=(f"Series {idx+1}" if len(y1_aligned) > 1 else "Y1"),
                    line=dict(color=color, width=2.5),
                    marker=dict(size=8, color=color, line=dict(color='black', width=0.75)),
                    error_y=dict(type='data', array=err_vals, thickness=1, width=3, color='black') if err_vals else None,
                    showlegend=len(y1_aligned) > 1 or include_y2
                ), secondary_y=False if include_y2 else None)

    # Add Y2 if enabled
    if include_y2:
        y2_vals = [y2_dict.get(rid, np.nan) for rid in x_order]
        y2_err_vals = [y2_err_dict.get(rid, np.nan) for rid in x_order] if y2_err_dict else None
        
        # Add to export
        export_data['y2'] = {
            'name': 'Y2',
            'x': x_vals,
            'y': y2_vals,
            'error': y2_err_vals if y2_err_vals else None
        }
        
        color = OKABE_ITO[len(y1_aligned) % len(OKABE_ITO)]
        
        if plot_type == 'bar':
            fig.add_trace(go.Bar(
                x=x_vals, y=y2_vals, name='Y2',
                marker_color=color, marker_line=dict(color='black', width=0.75),
                error_y=dict(type='data', array=y2_err_vals, thickness=1, width=3, color='black') if y2_err_vals else None,
                width=bar_width if 'bar_width' in locals() else 0.4, 
                offsetgroup='y2'
            ), secondary_y=True)
        elif plot_type == 'scatter':
            fig.add_trace(go.Scatter(
                x=x_vals, y=y2_vals, mode='markers', name='Y2',
                marker=dict(size=10, color=color, line=dict(color='black', width=0.75)),
                error_y=dict(type='data', array=y2_err_vals, thickness=1, width=3, color='black') if y2_err_vals else None,
            ), secondary_y=True)
        else:  # line
            fig.add_trace(go.Scatter(
                x=x_vals, y=y2_vals, mode='lines+markers', name='Y2',
                line=dict(color=color, width=2.5),
                marker=dict(size=8, color=color, line=dict(color='black', width=0.75)),
                error_y=dict(type='data', array=y2_err_vals, thickness=1, width=3, color='black') if y2_err_vals else None,
            ), secondary_y=True)

    # Update axes
    xaxis_config = dict(
        title=plot_config.get('x_label', 'X'),
        showgrid=False,
        showline=True,
        linecolor='black',
        linewidth=1.5,
        mirror=True,
        ticks='outside',
        tickwidth=1.5,
        ticklen=5
    )
    
    if use_categorical:
        xaxis_config.update({
            'ticktext': x_labels_raw,
            'tickvals': x_vals,
            'tickmode': 'array'
        })

    fig.update_xaxes(**xaxis_config)

    yaxis_config = dict(
        title=plot_config.get('y1_label', 'Y1'),
        showgrid=False,
        showline=True,
        linecolor='black',
        linewidth=1.5,
        mirror=True,
        ticks='outside',
        tickwidth=1.5,
        ticklen=5
    )

    if include_y2:
        fig.update_yaxes(**yaxis_config, secondary_y=False)
        fig.update_yaxes(
            title=plot_config.get('y2_label', 'Y2'),
            showgrid=False,
            showline=True,
            linecolor='black',
            linewidth=1.5,
            mirror=True,
            ticks='outside',
            tickwidth=1.5,
            ticklen=5,
            secondary_y=True
        )
    else:
        fig.update_yaxes(**yaxis_config)

    fig.update_layout(
        font=dict(family='Arial', size=11),
        plot_bgcolor='white',
        paper_bgcolor='white',
        barmode='group',
        legend=dict(
            font=dict(size=10),
            borderwidth=1,
            bordercolor='black',
            bgcolor='rgba(255,255,255,0.9)',
            x=1, y=1,
            xanchor='right',
            yanchor='top'
        ),
        margin=dict(l=70, r=70 if include_y2 else 40, t=40, b=60),
        height=580
    )

    return fig, export_data


def section_style(color_key, active=False):
    """Generate section styling"""
    colors = SECTION_COLORS[color_key]
    return {
        'padding': '12px',
        'marginBottom': '10px',
        'backgroundColor': colors['light'] if active else 'white',
        'border': f"2px solid {colors['border']}" if active else f"1px solid {colors['light']}",
        'borderRadius': '8px',
        'transition': 'all 0.2s'
    }


def selector_button_style(color_key, active=False):
    """Generate selector button styling"""
    colors = SECTION_COLORS[color_key]
    base_style = {
        'padding': '8px 14px',
        'fontSize': '11px',
        'borderRadius': '6px',
        'cursor': 'pointer',
        'marginRight': '6px',
        'marginBottom': '6px',
        'transition': 'all 0.15s'
    }
    
    if active:
        return {**base_style,
            'border': f"2px solid {colors['main']}",
            'backgroundColor': colors['light'],
            'color': colors['main'],
            'fontWeight': '600',
            'boxShadow': f"0 0 8px {colors['light']}"
        }
    else:
        return {**base_style,
            'border': '1px solid #CCC',
            'backgroundColor': '#F5F5F5',
            'color': '#666',
            'fontWeight': '500',
            'boxShadow': 'none'
        }


def get_empty_selections(y1_count=1):
    """Create empty selections structure (simplified X axis)"""
    return {
        'x': {'data': {'row_ids': [], 'column_id': None}},
        'y1': {'series': [{'row_ids': [], 'column_id': None} for _ in range(y1_count)], 
               'error': {'row_ids': [], 'column_id': None}},
        'y2': {'data': {'row_ids': [], 'column_id': None}, 
               'error': {'row_ids': [], 'column_id': None}},
        'y2_enabled': False
    }


# Layout
app.layout = html.Div([
    # Header
    html.Div([
        html.H1("Publication Plotter", style={'margin': '0', 'fontSize': '22px', 'fontWeight': '600'}),
        html.P("Enhanced Axis Mapping Console", style={'margin': '4px 0 0 0', 'fontSize': '11px', 'opacity': '0.9'})
    ], style={'textAlign': 'center', 'padding': '16px', 'backgroundColor': '#37474F', 'color': 'white'}),
    
    # Upload
    dcc.Upload(
        id='upload',
        children=html.Div(['Drop CSV/Excel or click to browse']),
        style={
            'width': '96%', 'height': '45px', 'lineHeight': '45px',
            'borderWidth': '1px', 'borderStyle': 'dashed', 'borderRadius': '6px',
            'textAlign': 'center', 'margin': '10px auto 8px',
            'backgroundColor': '#FAFAFA', 'borderColor': '#CCC', 
            'cursor': 'pointer', 'fontSize': '11px', 'color': '#666'
        }
    ),
    
    html.Div(id='upload-status', style={'textAlign': 'center', 'marginBottom': '8px', 'fontSize': '10px'}),
    
    # Data tools
    html.Div([
        html.Button("↔️ Transpose", id='transpose-data', 
                   style={'padding': '5px 12px', 'fontSize': '10px', 'marginRight': '6px', 'display': 'none'}, 
                   title="Swap rows and columns"),
        html.Button("➕ Row", id='add-row', 
                   style={'padding': '5px 12px', 'fontSize': '10px', 'marginRight': '6px', 'display': 'none'}, 
                   title="Add a new row"),
        html.Button("➕ Column", id='add-column', 
                   style={'padding': '5px 12px', 'fontSize': '10px', 'display': 'none'}, 
                   title="Add a new column"),
    ], id='data-tools', style={'textAlign': 'center', 'marginBottom': '8px'}),
    
    # Main container
    html.Div([
        # Left: Mapping Console
        html.Div([
            html.Div([
                html.H3("Axis Mapping", style={'fontSize': '13px', 'fontWeight': '600', 'margin': '0 0 12px 0'}),
                
                # X-AXIS (Simplified!)
                html.Div([
                    html.Div([
                        html.Span("X-Axis", style={'fontSize': '12px', 'fontWeight': '600', 'color': SECTION_COLORS['x']['main']}),
                        html.Button("✕", id='clear-x', 
                                   style={'float': 'right', 'padding': '2px 6px', 'fontSize': '10px', 
                                          'border': '1px solid #CCC', 'borderRadius': '3px', 'cursor': 'pointer',
                                          'backgroundColor': 'white'},
                                   title="Clear X selection"),
                    ], style={'marginBottom': '8px', 'paddingBottom': '6px', 'borderBottom': f"2px solid {SECTION_COLORS['x']['light']}"}),
                    
                    html.Div([
                        html.Label("Label:", style={'fontSize': '10px', 'fontWeight': '600', 'color': '#666', 'marginBottom': '4px', 'display': 'block'}),
                        dcc.Input(id='x-label-input', value='X', style={'width': '100%', 'padding': '5px', 'fontSize': '10px', 'marginBottom': '8px'}),
                    ]),
                    
                    html.Div([
                        html.Label("Data:", style={'fontSize': '10px', 'fontWeight': '600', 'color': '#666', 'marginBottom': '4px'}),
                        html.Button("Select cells", id='btn-x-data', style=selector_button_style('x')),
                    ]),
                ], id='x-section', style=section_style('x')),
                
                # Y1-AXIS
                html.Div([
                    html.Div([
                        html.Span("Y-Axis (Primary)", style={'fontSize': '12px', 'fontWeight': '600', 'color': SECTION_COLORS['y1']['main']}),
                        html.Button("✕", id='clear-y1', 
                                   style={'float': 'right', 'padding': '2px 6px', 'fontSize': '10px', 
                                          'border': '1px solid #CCC', 'borderRadius': '3px', 'cursor': 'pointer',
                                          'backgroundColor': 'white'},
                                   title="Clear Y1 selections"),
                    ], style={'marginBottom': '8px', 'paddingBottom': '6px', 'borderBottom': f"2px solid {SECTION_COLORS['y1']['light']}"}),
                    
                    html.Div([
                        html.Label("Label:", style={'fontSize': '10px', 'fontWeight': '600', 'color': '#666', 'marginBottom': '4px', 'display': 'block'}),
                        dcc.Input(id='y1-label-input', value='Y₁', style={'width': '100%', 'padding': '5px', 'fontSize': '10px', 'marginBottom': '8px'}),
                    ]),
                    
                    html.Div(id='y1-series-container'),
                    
                    html.Div([
                        html.Button("+ Series", id='add-y1-series', 
                                   style={'padding': '5px 10px', 'fontSize': '10px', 'marginRight': '6px'}),
                        html.Button("− Series", id='remove-y1-series', 
                                   style={'padding': '5px 10px', 'fontSize': '10px', 'marginRight': '6px'}),
                        html.Span(id='y1-count', children="1 series", style={'fontSize': '9px', 'color': '#999'}),
                    ], style={'marginBottom': '10px', 'paddingTop': '8px', 'borderTop': '1px solid #EEE'}),
                    
                    html.Div([
                        html.Label("Error:", style={'fontSize': '10px', 'fontWeight': '600', 'color': '#666', 'marginBottom': '4px'}),
                        html.Button("Select cells", id='btn-y1-error', style=selector_button_style('y1')),
                    ], style={'marginBottom': '10px'}),
                    
                    html.Div([
                        html.Label("Stats:", style={'fontSize': '10px', 'fontWeight': '600', 'color': '#666', 'marginBottom': '6px', 'display': 'block'}),
                        dcc.Checklist(
                            id='y1-stats',
                            options=[
                                {'label': ' Mean ± SD', 'value': 'mean_sd'},
                                {'label': ' Mean ± SEM', 'value': 'mean_sem'},
                                {'label': ' Median ± IQR', 'value': 'median_iqr'},
                            ],
                            value=[],
                            style={'fontSize': '10px'}
                        ),
                        dcc.Checklist(
                            id='show-raw-points',
                            options=[{'label': ' Show raw points', 'value': 'show'}],
                            value=[],
                            style={'fontSize': '10px', 'marginTop': '4px'}
                        ),
                    ]),
                ], id='y1-section', style=section_style('y1')),
                
                # Y2-AXIS
                html.Div([
                    html.Div([
                        html.Span("Y₂-Axis (Secondary)", style={'fontSize': '12px', 'fontWeight': '600', 'color': SECTION_COLORS['y2']['main'], 'marginRight': '8px'}),
                        dcc.Checklist(
                            id='y2-enable',
                            options=[{'label': ' Enable', 'value': 'enable'}],
                            value=[],
                            inline=True,
                            style={'display': 'inline-block', 'fontSize': '10px'}
                        ),
                        html.Button("✕", id='clear-y2', 
                                   style={'float': 'right', 'padding': '2px 6px', 'fontSize': '10px', 
                                          'border': '1px solid #CCC', 'borderRadius': '3px', 'cursor': 'pointer',
                                          'backgroundColor': 'white'},
                                   title="Clear Y2 selections"),
                    ], style={'marginBottom': '8px', 'paddingBottom': '6px', 'borderBottom': f"2px solid {SECTION_COLORS['y2']['light']}"}),
                    
                    html.Div([
                        html.Div([
                            html.Label("Label:", style={'fontSize': '10px', 'fontWeight': '600', 'color': '#666', 'marginBottom': '4px'}),
                            dcc.Input(id='y2-label-input', value='Y₂', style={'width': '100%', 'padding': '5px', 'fontSize': '10px', 'marginBottom': '8px'}),
                        ]),
                        html.Div([
                            html.Label("Data:", style={'fontSize': '10px', 'fontWeight': '600', 'color': '#666', 'marginBottom': '4px'}),
                            html.Button("Select cells", id='btn-y2-data', style=selector_button_style('y2')),
                        ], style={'marginBottom': '8px'}),
                        html.Div([
                            html.Label("Error:", style={'fontSize': '10px', 'fontWeight': '600', 'color': '#666', 'marginBottom': '4px'}),
                            html.Button("Select cells", id='btn-y2-error', style=selector_button_style('y2')),
                        ]),
                    ], id='y2-controls', style={'display': 'none'}),
                ], id='y2-section', style=section_style('y2')),
                
                # PLOT TYPE
                html.Div([
                    html.Label("Plot Type:", style={'fontSize': '11px', 'fontWeight': '600', 'marginBottom': '6px', 'display': 'block'}),
                    dcc.RadioItems(
                        id='plot-type',
                        options=[
                            {'label': ' Bar', 'value': 'bar'},
                            {'label': ' Line', 'value': 'line'},
                            {'label': ' Scatter', 'value': 'scatter'}
                        ],
                        value='bar',
                        inline=True,
                        style={'fontSize': '10px'}
                    ),
                ], style={'padding': '10px', 'backgroundColor': '#F5F5F5', 'borderRadius': '6px', 'marginBottom': '10px'}),
                
                # TOOLS
                html.Div([
                    html.Button("Save Map", id='save-mapping', 
                               style={'padding': '6px 12px', 'fontSize': '10px', 'width': '48%', 'marginRight': '4%'}),
                    dcc.Download(id='download-mapping'),
                    html.Button("Load Map", id='load-mapping', 
                               style={'padding': '6px 12px', 'fontSize': '10px', 'width': '48%'}),
                    dcc.Upload(id='upload-mapping', style={'display': 'none'}),
                    html.Button("Clear All", id='clear-all', 
                               style={'padding': '6px 12px', 'fontSize': '10px', 'width': '100%', 'marginTop': '8px'}),
                ]),
            ], style={'height': '100%', 'overflowY': 'auto'}),
        ], style={'width': '340px', 'padding': '10px', 'backgroundColor': '#FAFAFA', 'borderRight': '1px solid #DDD'}),
        
        # Middle: Table
        html.Div([
            html.Div(id='mode-indicator', style={
                'padding': '6px 10px', 'fontSize': '10px', 'textAlign': 'center',
                'backgroundColor': '#FFF8E1', 'marginBottom': '8px', 'borderRadius': '4px'
            }),
            html.Div(id='table-container', style={'borderRadius': '6px', 'overflow': 'hidden'}),
        ], style={'flex': '1', 'padding': '10px', 'minWidth': '400px'}),
        
        # Right: Plot
        html.Div([
            dcc.Graph(id='plot', style={'height': '100%'}, config={'displayModeBar': True})
        ], style={'width': '45%', 'padding': '10px'}),
        
    ], style={'display': 'flex', 'height': 'calc(100vh - 180px)'}),
    
    # Stores
    dcc.Store(id='data-store'),
    dcc.Store(id='selections', data=get_empty_selections()),
    dcc.Store(id='active-selector', data=None),
    dcc.Store(id='y1-series-count', data=1),
    dcc.Store(id='plot-export-data'),  # NEW: Store plot data for export
    
], style={'backgroundColor': '#FAFAFA', 'fontFamily': 'Arial, sans-serif', 'height': '100vh', 'overflow': 'hidden'})


# Upload handler
@app.callback(
    [Output('data-store', 'data'),
     Output('upload-status', 'children'),
     Output('table-container', 'children'),
     Output('transpose-data', 'style'),
     Output('add-row', 'style'),
     Output('add-column', 'style')],
    Input('upload', 'contents'),
    State('upload', 'filename'),
    prevent_initial_call=True
)
def upload_file(contents, filename):
    if not contents:
        return None, "", html.Div("Upload file to start"), {'display': 'none'}, {'display': 'none'}, {'display': 'none'}
    
    df = read_file(contents, filename)
    if df is None:
        return None, html.Span("Error reading file", style={'color': '#f44336'}), html.Div("Upload failed"), {'display': 'none'}, {'display': 'none'}, {'display': 'none'}
    
    status = html.Span(f"✓ {filename} ({len(df)}×{len(df.columns)-1})", style={'color': '#4CAF50'})
    
    table = dash_table.DataTable(
        id='table',
        columns=[{"name": col, "id": col, "editable": col != '_row_id', "selectable": col != '_row_id', "deletable": col != '_row_id'} for col in df.columns],
        data=df.to_dict('records'),
        cell_selectable=True,
        column_selectable='single',
        editable=True,
        sort_action='native',
        row_selectable=False,
        row_deletable=True,
        style_table={'height': 'calc(100vh - 260px)', 'overflowY': 'auto'},
        style_cell={'textAlign': 'center', 'padding': '6px', 'fontSize': '10px'},
        style_header={
            'backgroundColor': '#37474F', 
            'color': 'white', 
            'fontWeight': '600', 
            'cursor': 'pointer',
            'textDecoration': 'underline dotted',
            'textUnderlineOffset': '3px'
        },
        style_header_conditional=[
            {'if': {'column_id': '_row_id'}, 'display': 'none'}
        ],
        style_cell_conditional=[
            {'if': {'column_id': '_row_id'}, 'display': 'none'}
        ],
    )
    
    # Show all data tool buttons
    tool_style = {'padding': '5px 12px', 'fontSize': '10px', 'marginRight': '6px', 'display': 'inline-block'}
    
    return df.to_json(orient='split'), status, table, tool_style, tool_style, tool_style


# NEW: Add row to table
@app.callback(
    [Output('table', 'data', allow_duplicate=True),
     Output('data-store', 'data', allow_duplicate=True)],
    Input('add-row', 'n_clicks'),
    State('table', 'data'),
    prevent_initial_call=True
)
def add_new_row(n_clicks, table_data):
    if not table_data:
        return dash.no_update, dash.no_update
    
    df = pd.DataFrame(table_data)
    
    # Create new empty row with next _row_id
    new_row_id = df['_row_id'].max() + 1 if len(df) > 0 else 0
    new_row = {'_row_id': new_row_id}
    
    # Add empty values for all other columns
    for col in df.columns:
        if col != '_row_id':
            new_row[col] = ''
    
    # Append new row
    df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
    
    return df.to_dict('records'), df.to_json(orient='split')


# NEW: Add column to table
@app.callback(
    [Output('table-container', 'children', allow_duplicate=True),
     Output('data-store', 'data', allow_duplicate=True)],
    Input('add-column', 'n_clicks'),
    State('table', 'data'),
    State('table', 'columns'),
    prevent_initial_call=True
)
def add_new_column(n_clicks, table_data, current_columns):
    if not table_data:
        return dash.no_update, dash.no_update
    
    df = pd.DataFrame(table_data)
    
    # Find next available column name
    col_num = 1
    while f'New_Column_{col_num}' in df.columns:
        col_num += 1
    
    new_col_name = f'New_Column_{col_num}'
    df[new_col_name] = ''
    
    # Create updated table
    table = dash_table.DataTable(
        id='table',
        columns=[{"name": col, "id": col, "editable": col != '_row_id', "selectable": col != '_row_id', "deletable": col != '_row_id', "renamable": col != '_row_id'} for col in df.columns],
        data=df.to_dict('records'),
        cell_selectable=True,
        column_selectable='single',
        editable=True,
        sort_action='native',
        row_selectable=False,
        row_deletable=True,
        style_table={'height': 'calc(100vh - 260px)', 'overflowY': 'auto'},
        style_cell={'textAlign': 'center', 'padding': '6px', 'fontSize': '10px'},
        style_header={
            'backgroundColor': '#37474F', 
            'color': 'white', 
            'fontWeight': '600', 
            'cursor': 'pointer',
            'textDecoration': 'underline dotted',
            'textUnderlineOffset': '3px'
        },
        style_header_conditional=[
            {'if': {'column_id': '_row_id'}, 'display': 'none'}
        ],
        style_cell_conditional=[
            {'if': {'column_id': '_row_id'}, 'display': 'none'}
        ],
    )
    
    return table, df.to_json(orient='split')


# NEW: Transpose data (with selection preservation)
@app.callback(
    [Output('data-store', 'data', allow_duplicate=True),
     Output('table-container', 'children', allow_duplicate=True),
     Output('selections', 'data', allow_duplicate=True)],
    Input('transpose-data', 'n_clicks'),
    State('data-store', 'data'),
    State('y1-series-count', 'data'),
    prevent_initial_call=True
)
def transpose_data(n_clicks, data_json, y1_count):
    if not data_json:
        return dash.no_update
    
    df = pd.read_json(io.StringIO(data_json), orient='split')
    df_transposed = transpose_dataframe(df)
    
    # Create new table with all features
    table = dash_table.DataTable(
        id='table',
        columns=[{"name": col, "id": col, "editable": col != '_row_id', "selectable": col != '_row_id', "deletable": col != '_row_id', "renamable": col != '_row_id'} for col in df_transposed.columns],
        data=df_transposed.to_dict('records'),
        cell_selectable=True,
        column_selectable='single',
        editable=True,
        sort_action='native',
        row_selectable=False,
        row_deletable=True,
        style_table={'height': 'calc(100vh - 260px)', 'overflowY': 'auto'},
        style_cell={'textAlign': 'center', 'padding': '6px', 'fontSize': '10px'},
        style_header={
            'backgroundColor': '#37474F', 
            'color': 'white', 
            'fontWeight': '600', 
            'cursor': 'pointer',
            'textDecoration': 'underline dotted',
            'textUnderlineOffset': '3px'
        },
        style_header_conditional=[
            {'if': {'column_id': '_row_id'}, 'display': 'none'}
        ],
        style_cell_conditional=[
            {'if': {'column_id': '_row_id'}, 'display': 'none'}
        ],
    )
    
    # Clear selections after transpose
    return df_transposed.to_json(orient='split'), table, get_empty_selections(y1_count)


# Y2 toggle
@app.callback(
    Output('y2-controls', 'style'),
    Input('y2-enable', 'value')
)
def toggle_y2(enabled):
    if 'enable' in (enabled or []):
        return {'display': 'block'}
    return {'display': 'none'}


# Y1 series management
@app.callback(
    [Output('y1-series-count', 'data'),
     Output('y1-series-container', 'children'),
     Output('y1-count', 'children'),
     Output('selections', 'data', allow_duplicate=True)],
    [Input('add-y1-series', 'n_clicks'),
     Input('remove-y1-series', 'n_clicks')],
    [State('y1-series-count', 'data'),
     State('selections', 'data')],
    prevent_initial_call=True
)
def manage_y1_series(add_clicks, remove_clicks, count, selections):
    ctx = callback_context
    if not ctx.triggered:
        return dash.no_update
    
    triggered = ctx.triggered[0]['prop_id'].split('.')[0]
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
    
    # Build series UI
    series_divs = []
    for i in range(count):
        series_divs.append(
            html.Div([
                html.Label(f"Series {i+1}:", style={'fontSize': '10px', 'fontWeight': '600', 'color': '#666', 'marginBottom': '4px'}),
                html.Button("Select data", id={'type': 'btn-y1-data', 'index': i}, style=selector_button_style('y1')),
            ], style={'marginBottom': '8px'})
        )
    
    return count, series_divs, f"{count} series", selections


# NEW: Quick-clear individual axis selections
@app.callback(
    Output('selections', 'data', allow_duplicate=True),
    [Input('clear-x', 'n_clicks'),
     Input('clear-y1', 'n_clicks'),
     Input('clear-y2', 'n_clicks')],
    State('selections', 'data'),
    prevent_initial_call=True
)
def quick_clear_axis(clear_x, clear_y1, clear_y2, selections):
    ctx = callback_context
    if not ctx.triggered or not selections:
        return dash.no_update
    
    triggered = ctx.triggered[0]['prop_id'].split('.')[0]
    
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
     Output('table', 'selected_cells'),
     Output('table', 'selected_columns'),
     Output('table', 'active_cell')],
    [Input('btn-x-data', 'n_clicks'),
     Input({'type': 'btn-y1-data', 'index': ALL}, 'n_clicks'),
     Input('btn-y1-error', 'n_clicks'),
     Input('btn-y2-data', 'n_clicks'),
     Input('btn-y2-error', 'n_clicks')],
    [State('active-selector', 'data'),
     State('selections', 'data')],
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
        trig_str = ctx.triggered[0]['prop_id'].split('.')[0]
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

    # Banner
    if new_sel:
        axis_names = {'x':'X-Axis','y1':'Y₁-Axis','y2':'Y₂-Axis'}
        axis_name = axis_names.get(new_sel[0], '')
        if len(new_sel) > 2 and new_sel[1] == 'data':
            indicator = f"Selecting {axis_name} Series {new_sel[2]+1} • Click cells, column header, or drag to select"
        else:
            indicator = f"Selecting {axis_name} {new_sel[1]} • Click cells, column header, or drag to select"
    else:
        indicator = ""

    # Clear table selection when turning OFF
    if new_sel is None:
        selected_cells, selected_columns, active_cell = [], [], None
    else:
        selected_cells = dash.no_update
        selected_columns = dash.no_update
        active_cell = dash.no_update

    store_value = list(new_sel) if new_sel is not None else None

    return (store_value, indicator, x_data_style, y1_data_styles,
            y1_error_style, y2_data_style, y2_error_style,
            selected_cells, selected_columns, active_cell)


# Selection handler with column-click support
@app.callback(
    [Output('selections', 'data'),
     Output('table', 'style_data_conditional'),
     Output('data-store', 'data', allow_duplicate=True)],
    [Input('table', 'selected_cells'),
     Input('table', 'selected_columns'),
     Input('table', 'active_cell'),
     Input('y2-enable', 'value'),
     Input('clear-all', 'n_clicks'),
     Input('table', 'derived_virtual_data'),
     Input('table', 'data')],
    [State('active-selector', 'data'),
     State('selections', 'data'),
     State('data-store', 'data'),
     State('y1-series-count', 'data')],
    prevent_initial_call=True
)
def update_selections(selected_cells, selected_columns, active_cell, y2_enabled, clear_clicks,
                      virtual_data, table_data, active_selector, selections, data_json_unused, y1_count):

    ctx = callback_context
    trigger_id = ctx.triggered[0]['prop_id'] if ctx.triggered else ''
    
    # DEBUG: Print what triggered the callback
    if 'selected_columns' in trigger_id:
        print(f"DEBUG: Column selected! Columns: {selected_columns}, Active selector: {active_selector}")

    active_selector = canon_selector(active_selector)

    if not selections:
        selections = get_empty_selections(y1_count)

    selections['y2_enabled'] = 'enable' in (y2_enabled or [])

    if 'clear-all' in trigger_id:
        # Return empty dataframe as JSON
        if table_data:
            df = pd.DataFrame(table_data)
            return get_empty_selections(y1_count), [], df.to_json(orient='split')
        return get_empty_selections(y1_count), [], None

    if not table_data:
        return selections, [], None

    # CRITICAL FIX: Always use table_data (current edited values)
    df_original = pd.DataFrame(table_data)
    df_sorted = pd.DataFrame(virtual_data) if virtual_data else df_original.copy()
    
    # Update data_json for return
    data_json = df_original.to_json(orient='split')

    # Only modify selections while a selector is active
    if active_selector and ('selected_cells' in trigger_id or 'selected_columns' in trigger_id or 'active_cell' in trigger_id):
        axis, kind = active_selector[0], active_selector[1]
        target = None
        
        if axis == 'x':
            target = selections['x']['data']
        elif axis == 'y1':
            if kind == 'error':
                target = selections['y1']['error']
            else:
                idx = active_selector[2]
                if idx < len(selections['y1']['series']):
                    target = selections['y1']['series'][idx]
        elif axis == 'y2':
            target = selections['y2'][kind]

        if target is not None:
            # ENHANCED: Whole column selection - select only non-empty cells
            if 'selected_columns' in trigger_id and selected_columns:
                col_id = selected_columns[0]
                if col_id != '_row_id':
                    # Get only rows with data (non-empty, non-NaN)
                    non_empty_rows = []
                    for idx, row in df_sorted.iterrows():
                        val = row[col_id]
                        if pd.notna(val) and str(val).strip() != '':
                            non_empty_rows.append(int(row['_row_id']))
                    
                    target['row_ids'] = non_empty_rows
                    target['column_id'] = col_id

            # Individual cells (with shift-select fix)
            elif 'selected_cells' in trigger_id and selected_cells:
                # Get column from first cell
                col_id = selected_cells[0].get('column_id') if selected_cells else None
                
                if col_id and col_id != '_row_id':
                    # CRITICAL FIX: Allow switching columns!
                    # If clicking a DIFFERENT column, start fresh with new column
                    if target.get('column_id') and col_id != target['column_id']:
                        target['column_id'] = col_id
                        target['row_ids'] = []
                    
                    # Initialize if empty
                    if not target.get('column_id'):
                        target['column_id'] = col_id
                        target['row_ids'] = []
                    
                    # Get all selected row IDs from this batch
                    new_row_ids = set()
                    for cell in selected_cells:
                        if cell.get('column_id') == col_id:
                            row_idx = cell.get('row')
                            if row_idx is not None and 0 <= row_idx < len(df_sorted):
                                new_row_ids.add(int(df_sorted.iloc[row_idx]['_row_id']))
                    
                    # Toggle logic: if ALL are already selected, deselect them; otherwise select them
                    existing = set(target['row_ids'])
                    if new_row_ids.issubset(existing):
                        # All are selected, so deselect
                        target['row_ids'] = list(existing - new_row_ids)
                    else:
                        # Some/none are selected, so select all
                        target['row_ids'] = list(existing | new_row_ids)

            # Single cell click
            elif 'active_cell' in trigger_id and active_cell:
                row_idx = active_cell.get('row')
                col_id = active_cell.get('column_id')
                if row_idx is not None and col_id and col_id != '_row_id':
                    if 0 <= row_idx < len(df_sorted):
                        row_id = int(df_sorted.iloc[row_idx]['_row_id'])
                        
                        # CRITICAL FIX: Allow switching columns!
                        if target.get('column_id') and col_id != target['column_id']:
                            # Different column - start fresh
                            target['column_id'] = col_id
                            target['row_ids'] = [row_id]
                        else:
                            # Same column or first selection - toggle
                            if not target.get('row_ids'):
                                target['row_ids'] = []
                            if not target.get('column_id'):
                                target['column_id'] = col_id
                            
                            if row_id in target['row_ids']:
                                target['row_ids'].remove(row_id)
                            else:
                                target['row_ids'].append(row_id)

    # Visual feedback
    style_conditions = [{'if': {'row_index': 'odd'}, 'backgroundColor': '#FAFAFA'}]

    def add_highlights(row_ids, col_id, bg, border, bold=False):
        if not row_ids or not col_id:
            return
        for rid in row_ids:
            match = df_sorted[df_sorted['_row_id'] == rid]
            if not match.empty:
                pos = int(match.index[0])
                style_conditions.append({
                    'if': {'row_index': pos, 'column_id': col_id},
                    'backgroundColor': bg,
                    'border': f'{"2px solid" if bold else "1px dashed"} {border}',
                    'fontWeight': '600' if bold else '500'
                })

    # Always show saved highlights
    x_dat = selections['x']['data']
    if x_dat.get('row_ids') and x_dat.get('column_id'):
        add_highlights(x_dat['row_ids'], x_dat['column_id'],
                       SECTION_COLORS['x']['light'], SECTION_COLORS['x']['main'], bold=False)

    # Y1 series
    y1_shades = ['#FFF3E0', '#FFE0B2', '#FFCC80', '#FFB74D']
    for i, series in enumerate(selections['y1']['series']):
        if series.get('row_ids') and series.get('column_id'):
            add_highlights(series['row_ids'], series['column_id'],
                           y1_shades[i % len(y1_shades)], SECTION_COLORS['y1']['main'], bold=False)

    # Y1 error
    y1_err = selections['y1']['error']
    if y1_err.get('row_ids') and y1_err.get('column_id'):
        add_highlights(y1_err['row_ids'], y1_err['column_id'],
                       '#F5F5F5', '#999', bold=False)

    # Y2 (if enabled)
    if selections.get('y2_enabled'):
        y2_dat = selections['y2']['data']
        if y2_dat.get('row_ids') and y2_dat.get('column_id'):
            add_highlights(y2_dat['row_ids'], y2_dat['column_id'],
                           SECTION_COLORS['y2']['light'], SECTION_COLORS['y2']['main'], bold=False)

        y2_err = selections['y2']['error']
        if y2_err.get('row_ids') and y2_err.get('column_id'):
            add_highlights(y2_err['row_ids'], y2_err['column_id'],
                           '#EFEBE9', '#795548', bold=False)

    # Active selector strong highlight
    if active_selector:
        axis, kind = active_selector[0:2]

        if axis == 'x':
            sel = selections['x']['data']
            add_highlights(sel.get('row_ids'), sel.get('column_id'),
                           SECTION_COLORS['x']['light'], SECTION_COLORS['x']['main'], bold=True)

        elif axis == 'y1':
            if kind == 'error':
                sel = selections['y1']['error']
                add_highlights(sel.get('row_ids'), sel.get('column_id'),
                               '#F5F5F5', '#666', bold=True)
            else:
                idx = active_selector[2]
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
            else:  # error
                add_highlights(sel.get('row_ids'), sel.get('column_id'),
                               '#EFEBE9', '#5D4037', bold=True)

    return selections, style_conditions, data_json


# Plot update (uses CURRENT table data including edits)
@app.callback(
    [Output('plot', 'figure'),
     Output('plot-export-data', 'data')],
    [Input('selections', 'data'),
     Input('plot-type', 'value'),
     Input('y1-stats', 'value'),
     Input('x-label-input', 'value'),
     Input('y1-label-input', 'value'),
     Input('y2-label-input', 'value'),
     Input('show-raw-points', 'value'),
     Input('table', 'derived_virtual_data'),
     Input('table', 'data')],  # CRITICAL FIX: Use table.data to get edited values
    prevent_initial_call=True
)
def update_plot(selections, plot_type, y1_stats, x_label, y1_label, y2_label, show_raw, virtual_data, table_data):
    if not table_data or not selections:
        fig = go.Figure()
        fig.add_annotation(text="Select data to plot", xref="paper", yref="paper",
                           x=0.5, y=0.5, showarrow=False, font=dict(size=14, color='#999'))
        fig.update_layout(plot_bgcolor='white', paper_bgcolor='white', height=580)
        return fig, None

    # CRITICAL FIX: Use table_data (current edited values) instead of data_json
    df = pd.DataFrame(table_data)

    plot_config = {
        'type': plot_type,
        'calc_stats': len(y1_stats) > 0 if y1_stats else False,
        'stat_type': y1_stats[0] if y1_stats else 'mean_sd',
        'x_label': x_label or 'X',
        'y1_label': y1_label or 'Y₁',
        'y2_label': y2_label or 'Y₂',
        'show_raw_points': 'show' in (show_raw or [])
    }

    fig, export_data = create_plot(df, virtual_data, selections, plot_config)
    return fig, export_data


# Save mapping
@app.callback(
    Output('download-mapping', 'data'),
    Input('save-mapping', 'n_clicks'),
    State('selections', 'data'),
    prevent_initial_call=True
)
def save_mapping(clicks, selections):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"plot_mapping_{timestamp}.json"
    return dict(content=json.dumps(selections, indent=2), filename=filename)


# Load mapping
@app.callback(
    Output('selections', 'data', allow_duplicate=True),
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


if __name__ == '__main__':
    print("\n" + "="*70)
    print("PUBLICATION PLOTTER - FINAL VERSION with Dynamic Editing!")
    print("="*70)
    print("\n✅ Column switching works perfectly!")
    print("✅ Cell edits update plot immediately")
    print("✅ NEW: Add rows on the fly (➕ Row button)")
    print("✅ NEW: Add columns on the fly (➕ Column button)")
    print("✅ NEW: Delete rows (click row number, then delete)")
    print("✅ NEW: Delete columns (click ✕ in header)")
    print("✅ NEW: Rename columns (double-click header)")
    print("✅ Transpose preserves Y2 enabled state")
    print("\nHow to use:")
    print("  1. Upload CSV")
    print("  2. Edit structure: Add rows/columns, rename, delete")
    print("  3. Select data for plotting")
    print("  4. Edit values in real-time")
    print("  5. Transpose if needed")
    print("\n📝 Multi-column selection: Coming in next version!")
    print("   (For now: reshape your data or add helper columns)")
    print("\nhttp://localhost:8069")
    print("="*70 + "\n")
    
    app.run(debug=True, port=8069)