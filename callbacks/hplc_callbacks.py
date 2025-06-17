# callbacks/hplc_callbacks.py - FIXED VERSION

from dash import Input, Output, State, html, dash_table, dcc
import pandas as pd
import plotly.graph_objects as go
import numpy as np


def register_peak_grouping_callback(app, data_manager):
    """Register callback for peak grouping functionality."""
    
    def convert_german_to_float(value):
        """Convert German decimal format (comma) to float."""
        if pd.isna(value):
            return 0.0
        try:
            str_val = str(value).replace(',', '.')
            return float(str_val)
        except (ValueError, TypeError):
            return 0.0
    
    def detect_columns(integration_table):
        """Detect column names in integration table."""
        columns = {}
        
        # Peak number/name column
        peak_cols = ['No.', 'No', 'Peak', 'Peak No.', 'Peak No', 'Peak Number', 'Peak Name']
        for col in peak_cols:
            if col in integration_table.columns:
                columns['peak'] = col
                break
        if 'peak' not in columns:
            columns['peak'] = integration_table.columns[0]
        
        # Retention time column
        rt_cols = ['Retention Time (min)', 'Retention Time', 'RT (min)', 'RT']
        for col in rt_cols:
            if col in integration_table.columns:
                columns['rt'] = col
                break
        
        # Area column
        area_cols = ['Area (mAU*min)', 'Area', 'Area (mAU·min)', 'Peak Area']
        for col in area_cols:
            if col in integration_table.columns:
                columns['area'] = col
                break
        
        # Height column
        height_cols = ['Height (mAU)', 'Height', 'Peak Height']
        for col in height_cols:
            if col in integration_table.columns:
                columns['height'] = col
                break
        
        # Relative area column
        rel_area_cols = ['Relative Area (%)', 'Relative Area', 'Rel Area (%)', 'Rel Area']
        for col in rel_area_cols:
            if col in integration_table.columns:
                columns['rel_area'] = col
                break
        
        # Relative height column
        rel_height_cols = ['Relative Height (%)', 'Relative Height', 'Rel Height (%)', 'Rel Height']
        for col in rel_height_cols:
            if col in integration_table.columns:
                columns['rel_height'] = col
                break
        
        return columns
    
    @app.callback(
        [Output('peak-grouping-results', 'children'),
         Output('comparison-table-container', 'children')],
        [Input('group-peaks-btn', 'n_clicks')],
        [State('rt-tolerance-slider', 'value')],
        prevent_initial_call=True
    )
    def group_peaks_across_samples(n_clicks, rt_tolerance):
        """Group peaks across all HPLC samples based on retention time."""
        
        if not n_clicks:
            return [], []
        
        # Get all HPLC files
        hplc_files = []
        for filename in data_manager.get_loaded_files():
            file_data = data_manager.get_file_data(filename)
            if file_data and file_data.get('type') in ['chromatogram', 'chromeleon_bundle']:
                hplc_files.append({
                    'filename': filename,
                    'data': file_data
                })
        
        if not hplc_files:
            return [html.P("No HPLC files available.")], []
        
        # Extract all peaks from all samples
        all_peaks = []
        for file_info in hplc_files:
            filename = file_info['filename']
            file_data = file_info['data']
            integration_table = file_data.get('integration_table')
            
            if integration_table is not None and len(integration_table) > 1:
                sample_name = filename.replace('_UV_VIS_1.txt', '').replace('temp_', '')
                
                # Detect column names for this table
                cols = detect_columns(integration_table)
                print(f"[DEBUG] Detected columns for {sample_name}: {cols}")
                
                # Filter out total rows
                peak_col = cols.get('peak')
                if peak_col:
                    peaks_only = integration_table[
                        ~integration_table[peak_col].astype(str).str.contains('Total', case=False, na=False)
                    ]
                else:
                    peaks_only = integration_table
                
                # Extract peak data
                for _, peak in peaks_only.iterrows():
                    peak_data = {
                        'sample': sample_name,
                        'filename': filename,
                        'peak_no': peak.get(cols.get('peak', ''), ''),
                        'rt': convert_german_to_float(peak.get(cols.get('rt', ''), 0)),
                        'area': convert_german_to_float(peak.get(cols.get('area', ''), 0)),
                        'height': convert_german_to_float(peak.get(cols.get('height', ''), 0)),
                        'rel_area': convert_german_to_float(peak.get(cols.get('rel_area', ''), 0)),
                        'rel_height': convert_german_to_float(peak.get(cols.get('rel_height', ''), 0))
                    }
                    all_peaks.append(peak_data)
                    print(f"[DEBUG] Added peak: {peak_data}")
        
        if not all_peaks:
            return [html.P("No peaks found in any samples.")], []
        
        # Group peaks by retention time
        peak_groups = group_peaks_by_retention_time(all_peaks, rt_tolerance)
        
        # Create grouping results display
        grouping_results = create_peak_grouping_display(peak_groups, rt_tolerance)
        
        # Create comparison table
        comparison_table = create_cross_sample_comparison_table(peak_groups, hplc_files)
        
        return grouping_results, comparison_table

def group_peaks_by_retention_time(peaks, tolerance):
    """Group peaks across samples based on retention time tolerance."""
    
    peaks_sorted = sorted(peaks, key=lambda x: x['rt'])
    groups = []
    
    for peak in peaks_sorted:
        # Find if this peak belongs to an existing group
        assigned = False
        for group in groups:
            group_rt_avg = sum(p['rt'] for p in group) / len(group)
            if abs(peak['rt'] - group_rt_avg) <= tolerance:
                group.append(peak)
                assigned = True
                break
        
        if not assigned:
            groups.append([peak])
    
    return groups

def create_peak_grouping_display(peak_groups, tolerance):
    """Create a display showing how peaks were grouped."""
    
    if not peak_groups:
        return [html.P("No peaks found to group.")]
    
    # Filter groups with multiple samples (comparative peaks)
    multi_sample_groups = [g for g in peak_groups if len(set(p['sample'] for p in g)) > 1]
    single_sample_peaks = [g for g in peak_groups if len(set(p['sample'] for p in g)) == 1]
    
    content = [
        html.H6(f"Peak Grouping Results (RT tolerance: ±{tolerance} min)", 
                style={'color': '#495057', 'marginBottom': '15px'}),
        
        html.Div([
            html.Div([
                html.H6("🎯 Comparative Peaks", style={'color': '#28a745', 'fontSize': '14px'}),
                html.P(f"{len(multi_sample_groups)} peak groups found in multiple samples")
            ], className="col-md-6"),
            
            html.Div([
                html.H6("🔸 Unique Peaks", style={'color': '#ffc107', 'fontSize': '14px'}),
                html.P(f"{len(single_sample_peaks)} peaks found in only one sample")
            ], className="col-md-6")
        ], className="row", style={'marginBottom': '15px'}),
    ]
    
    # Show details of comparative groups
    if multi_sample_groups:
        group_details = []
        for i, group in enumerate(multi_sample_groups):
            avg_rt = sum(p['rt'] for p in group) / len(group)
            samples = sorted(set(p['sample'] for p in group))
            
            group_details.append({
                'Group': f"Peak {i+1}",
                'Avg RT (min)': f"{avg_rt:.3f}",
                'Samples': len(samples),
                'Sample Names': ', '.join(samples[:3]) + ('...' if len(samples) > 3 else ''),
                'RT Range': f"{min(p['rt'] for p in group):.3f} - {max(p['rt'] for p in group):.3f}",
                'RSD %': f"{(np.std([p['rt'] for p in group]) / avg_rt * 100):.1f}"
            })
        
        df = pd.DataFrame(group_details)
        content.append(
            dash_table.DataTable(
                data=df.to_dict('records'),
                columns=[{"name": col, "id": col} for col in df.columns],
                style_table={'overflowX': 'auto', 'marginTop': '10px'},
                style_cell={'fontSize': '11px', 'padding': '6px', 'textAlign': 'left'},
                style_header={'backgroundColor': '#d4edda', 'fontWeight': 'bold', 'color': '#155724'},
                style_data_conditional=[
                    {
                        'if': {'row_index': 'odd'},
                        'backgroundColor': '#f8f9fa'
                    }
                ]
            )
        )
    
    return content

def create_cross_sample_comparison_table(peak_groups, hplc_files):
    """Create a comprehensive cross-sample comparison table."""
    
    if not peak_groups:
        return []
    
    # Get all sample names
    all_samples = sorted(set(info['filename'].replace('_UV_VIS_1.txt', '').replace('temp_', '') 
                            for info in hplc_files))
    
    # Filter to comparative groups only
    multi_sample_groups = [g for g in peak_groups if len(set(p['sample'] for p in g)) > 1]
    
    if not multi_sample_groups:
        return [html.P("No peaks found in multiple samples for comparison.")]
    
    content = [
        html.H6("📊 Cross-Sample Peak Comparison", 
                style={'color': '#495057', 'marginBottom': '15px', 'marginTop': '25px'}),
    ]
    
    # Create comparison data
    comparison_data = []
    
    for i, group in enumerate(multi_sample_groups):
        avg_rt = sum(p['rt'] for p in group) / len(group)
        
        # Create a row for each measurement type
        for measure in ['Area', 'Height', 'Rel_Area', 'Rel_Height']:
            row = {
                'Peak_Group': f"Peak {i+1}",
                'Avg_RT': f"{avg_rt:.3f}",
                'Measurement': measure.replace('_', ' '),
                'Unit': get_measurement_unit(measure)
            }
            
            # Add data for each sample
            for sample in all_samples:
                sample_peak = next((p for p in group if p['sample'] == sample), None)
                if sample_peak:
                    if measure == 'Area':
                        row[sample] = f"{sample_peak['area']:.2f}"
                    elif measure == 'Height':
                        row[sample] = f"{sample_peak['height']:.1f}"
                    elif measure == 'Rel_Area':
                        row[sample] = f"{sample_peak['rel_area']:.1f}%"
                    elif measure == 'Rel_Height':
                        row[sample] = f"{sample_peak['rel_height']:.1f}%"
                else:
                    row[sample] = "N.D."  # Not Detected
            
            comparison_data.append(row)
    
    if comparison_data:
        df = pd.DataFrame(comparison_data)
        
        # Create columns config
        columns = [
            {"name": "Peak Group", "id": "Peak_Group"},
            {"name": "Avg RT (min)", "id": "Avg_RT"},
            {"name": "Measurement", "id": "Measurement"},
            {"name": "Unit", "id": "Unit"}
        ]
        
        # Add sample columns
        for sample in all_samples:
            columns.append({"name": sample, "id": sample})
        
        # Conditional styling
        conditional_styles = [
            {
                'if': {'row_index': 'odd'},
                'backgroundColor': '#f8f9fa'
            }
        ]
        
        # Add N.D. highlighting for each sample column
        for sample in all_samples:
            conditional_styles.append({
                'if': {'filter_query': f'{{{sample}}} = N.D.'},
                'backgroundColor': '#fff3cd',
                'color': '#856404'
            })
        
        content.append(
            dash_table.DataTable(
                data=df.to_dict('records'),
                columns=columns,
                style_table={'overflowX': 'auto', 'marginTop': '10px'},
                style_cell={
                    'fontSize': '11px', 
                    'padding': '6px', 
                    'textAlign': 'left',
                    'fontFamily': 'monospace'
                },
                style_header={
                    'backgroundColor': '#e3f2fd', 
                    'fontWeight': 'bold', 
                    'color': '#1565c0'
                },
                style_data_conditional=conditional_styles,
                merge_duplicate_headers=True
            )
        )
        
        # Add download button
        content.append(
            html.Div([
                html.Button("📥 Download Comparison as CSV", 
                           id="download-comparison-btn", 
                           className="btn btn-outline-primary btn-sm",
                           style={'marginTop': '10px'})
            ])
        )
    
    return content

def get_measurement_unit(measure):
    """Get the unit for a measurement type."""
    units = {
        'Area': 'mAU·min',
        'Height': 'mAU', 
        'Rel_Area': '%',
        'Rel_Height': '%'
    }
    return units.get(measure, '')