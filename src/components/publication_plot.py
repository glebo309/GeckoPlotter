"""
Publication Plot Component
Creates publication-quality plots based on axis selections
"""

import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# Okabe-Ito colorblind-friendly palette
OKABE_ITO = ["#E69F00", "#56B4E9", "#009E73", "#F0E442", "#0072B2", "#D55E00", "#CC79A7"]


def create_publication_plot(df, virtual_data, selections, plot_config):
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
        fig.update_layout(plot_bgcolor='white', paper_bgcolor='white', autosize=True)
        return fig, None

    # Build X axis based on display order
    x_sel = selections['x']['data']
    
    force_categorical = plot_config.get('categorical_x', True)

    if x_sel.get('row_ids') and x_sel.get('column_id'):
        # X has data - use it
        x_order, x_labels_raw = get_values_in_display_order(x_sel['row_ids'], x_sel['column_id'], as_strings=True)
        if not force_categorical:
            numeric_x = []
            for lbl in x_labels_raw:
                try:
                    numeric_x.append(float(lbl))
                except (ValueError, TypeError):
                    numeric_x = None
                    break
            if numeric_x is not None:
                x_vals = numeric_x
                use_categorical = False
            else:
                x_vals = list(range(len(x_order)))
                use_categorical = True
        else:
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
    y1_series_names = []
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
            y1_series_names.append(series.get('column_id', f'Series {len(y1_series_names)+1}'))
        else:
            y1_series_data.append({})
            y1_series_names.append(f'Series {len(y1_series_names)+1}')

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

    # Group-based aggregation: when Group column has values, aggregate rows by group
    has_groups = 'Group' in df.columns and df['Group'].astype(str).str.strip().ne('').any()

    if calc_stats and has_groups:
        y1_col = y1_series_names[0] if y1_series_names else None
        if y1_col and y1_col in df.columns:
            grouped = df[df['Group'].astype(str).str.strip().ne('')].copy()
            grouped['_y_val'] = pd.to_numeric(grouped[y1_col].astype(str).str.replace('%', ''), errors='coerce')
            agg = grouped.groupby('Group', sort=False)['_y_val']

            group_labels = []
            y_means = []
            y_errs = []
            y_raw_groups = []

            for gname, gvals in agg:
                vals = gvals.dropna().values
                if len(vals) == 0:
                    continue
                group_labels.append(str(gname))
                if stat_type == 'mean_sd':
                    y_means.append(np.mean(vals))
                    y_errs.append(np.std(vals, ddof=1) if len(vals) > 1 else 0)
                elif stat_type == 'mean_sem':
                    y_means.append(np.mean(vals))
                    sd = np.std(vals, ddof=1) if len(vals) > 1 else 0
                    y_errs.append(sd / np.sqrt(len(vals)))
                elif stat_type == 'median_iqr':
                    y_means.append(np.median(vals))
                    y_errs.append(np.percentile(vals, 75) - np.percentile(vals, 25) if len(vals) > 1 else 0)
                y_raw_groups.append(vals)

            if group_labels:
                if not force_categorical:
                    numeric_gx = []
                    for lbl in group_labels:
                        try:
                            numeric_gx.append(float(lbl))
                        except (ValueError, TypeError):
                            numeric_gx = None
                            break
                    if numeric_gx is not None:
                        g_x = numeric_gx
                    else:
                        g_x = list(range(len(group_labels)))
                else:
                    g_x = list(range(len(group_labels)))
                stat_label = stat_type.split('_')[1].upper()

                export_data['y1_series'].append({
                    'name': f"Mean ± {stat_label}",
                    'x': g_x,
                    'y': y_means,
                    'error': y_errs,
                })

                if plot_type == 'bar':
                    fig.add_trace(go.Bar(
                        x=g_x, y=y_means, name=f"Mean ± {stat_label}",
                        marker_color=OKABE_ITO[0], marker_line=dict(color='black', width=0.75),
                        error_y=dict(type='data', array=y_errs, thickness=1, width=3, color='black'),
                        opacity=0.7 if show_raw else 1.0,
                    ))
                elif plot_type == 'scatter':
                    fig.add_trace(go.Scatter(
                        x=g_x, y=y_means, mode='markers', name=f"Mean ± {stat_label}",
                        marker=dict(size=10, color=OKABE_ITO[0], line=dict(color='black', width=0.75)),
                        error_y=dict(type='data', array=y_errs, thickness=1, width=3, color='black'),
                    ))
                else:
                    fig.add_trace(go.Scatter(
                        x=g_x, y=y_means, mode='lines+markers', name=f"Mean ± {stat_label}",
                        line=dict(color=OKABE_ITO[0], width=2.5),
                        marker=dict(size=8, color=OKABE_ITO[0], line=dict(color='black', width=0.75)),
                        error_y=dict(type='data', array=y_errs, thickness=1, width=3, color='black'),
                    ))

                if show_raw:
                    for gi, vals in enumerate(y_raw_groups):
                        x_jitter = np.full(len(vals), g_x[gi]) + np.random.uniform(-0.08, 0.08, len(vals))
                        fig.add_trace(go.Scatter(
                            x=x_jitter, y=vals, mode='markers',
                            name=f'Raw', marker=dict(size=5, color=OKABE_ITO[0], opacity=0.5, line=dict(width=0)),
                            showlegend=(gi == 0),
                        ))

                x_labels_raw = group_labels
                x_vals = g_x
                use_categorical = force_categorical
                calc_stats = False
                y1_series_data = []
                y1_aligned = []

    # Calculate statistics if requested (multi-series, no Group column)
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
            
            series_name = y1_series_names[idx] if idx < len(y1_series_names) else f'Series {idx+1}'
            
            # Add to export
            export_data['y1_series'].append({
                'name': series_name,
                'x': x_vals,
                'y': y_plot.tolist(),
                'error': err_vals if err_vals else None
            })
            
            color = OKABE_ITO[color_idx % len(OKABE_ITO)]
            color_idx += 1
            
            if plot_type == 'bar':
                fig.add_trace(go.Bar(
                    x=x_vals, y=y_plot, 
                    name=series_name,
                    marker_color=color, marker_line=dict(color='black', width=0.75),
                    error_y=dict(type='data', array=err_vals, thickness=1, width=3, color='black') if err_vals else None,
                    width=bar_width, offsetgroup=f'y1-{idx}',
                    opacity=0.7 if show_raw else 1.0,
                    showlegend=True
                ), secondary_y=False if include_y2 else None)
            elif plot_type == 'scatter':
                fig.add_trace(go.Scatter(
                    x=x_vals, y=y_plot, mode='markers',
                    name=series_name,
                    marker=dict(size=10, color=color, line=dict(color='black', width=0.75)),
                    error_y=dict(type='data', array=err_vals, thickness=1, width=3, color='black') if err_vals else None,
                    showlegend=True
                ), secondary_y=False if include_y2 else None)
            else:  # line
                fig.add_trace(go.Scatter(
                    x=x_vals, y=y_plot, mode='lines+markers',
                    name=series_name,
                    line=dict(color=color, width=2.5),
                    marker=dict(size=8, color=color, line=dict(color='black', width=0.75)),
                    error_y=dict(type='data', array=err_vals, thickness=1, width=3, color='black') if err_vals else None,
                    showlegend=True
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
        autosize=True
    )

    return fig, export_data
