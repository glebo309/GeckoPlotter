# File: plot/hplc.py 



import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
import numpy as np
from datetime import datetime

def create_chromatogram_plot(file_data):
    """Create enhanced HPLC chromatogram plot with peak visualization"""
    
    data = file_data['data']
    metadata = file_data['metadata']
    file_type = file_data['type']
    
    if data is None or data.empty:
        return go.Figure().add_annotation(
            text="No chromatogram data available",
            xref="paper", yref="paper",
            x=0.5, y=0.5, xanchor='center', yanchor='middle',
            showarrow=False, font_size=16
        )
    
    # Check for expected columns (more robust matching)
    time_col = 'Time (min)'

    intensity_col = None
    candidate_names = [
        'Value (mAU)',
        'Intensity (mAU)',
        'Absorbance (mAU)',
        'Signal (mAU)',
        'Intensity',
        'Signal Intensity',
    ]

    # Case-insensitive matching for known column names
    lower_map = {c.lower(): c for c in data.columns}

    for cand in candidate_names:
        lc = cand.lower()
        if time_col in data.columns and lc in lower_map:
            intensity_col = lower_map[lc]
            break

    # Fallback: first numeric column that isn't the time column
    if not intensity_col:
        numeric_cols = [c for c in data.columns if c != time_col and np.issubdtype(data[c].dtype, np.number)]
        if numeric_cols:
            intensity_col = numeric_cols[0]

    if not intensity_col:
        available_cols = list(data.columns)
        return go.Figure().add_annotation(
            text=f"Invalid chromatogram data format<br>Available columns: {available_cols}",
            xref="paper", yref="paper",
            x=0.5, y=0.5, xanchor='center', yanchor='middle',
            showarrow=False, font_size=14
        )

    print(f"[DEBUG] 📊 Using columns: Time='{time_col}', Intensity='{intensity_col}'")

    fig = go.Figure()
    
    # Get metadata for styling
    wavelength = metadata.get('wavelength') or metadata.get('Wavelength (nm)')
    sample_name = metadata.get('Sample Name', metadata.get('file_name', 'Unknown'))
    method_name = metadata.get('Method', metadata.get('company_method_name', ''))
    operator = metadata.get('Operator', metadata.get('operator_name', ''))
    injection_date = metadata.get('Injection Date', metadata.get('injection_date_time_stamp', ''))
    injection_time = metadata.get('Injection Time', '')
    
    # Color based on wavelength (if available)
    if wavelength:
        wl_num = float(wavelength) if isinstance(wavelength, str) and wavelength.isdigit() else 280
        if wl_num <= 220:
            line_color = '#8E44AD'  # Purple for low UV
        elif wl_num <= 280:
            line_color = '#3498DB'  # Blue for standard UV
        else:
            line_color = '#E67E22'  # Orange for visible
    else:
        line_color = '#2E86AB'  # Default blue
    
    # Plot main chromatogram
    fig.add_trace(go.Scatter(
        x=data[time_col],
        y=data[intensity_col],
        mode='lines',
        name=f'λ={wavelength}nm' if wavelength else 'Chromatogram',
        line=dict(color=line_color, width=1.5),
        hovertemplate='<b>HPLC Chromatogram</b><br>' +
                    'RT: %{x:.2f} min<br>' +
                    'Absorbance: %{y:.1f} mAU<br>' +
                    '<extra></extra>'
    ))
    
    # Add peak visualization from integration table (imported peaks)
    filename = file_data.get('filename', metadata.get('file_name', 'Unknown'))
    fig = add_imported_peaks_to_plot(fig, file_data, data, time_col, intensity_col)
    
    # Add detected peaks from peak manager
    try:
        from utils.peak_integration import peak_manager
        fig = add_detected_peaks_to_plot(fig, filename, peak_manager)
    except ImportError:
        print("[DEBUG] Peak integration module not available")
    
    # Create informative title
    wl_part = f" (λ={wavelength} nm)" if wavelength else ""
    title = f"HPLC Chromatogram - {sample_name}{wl_part}"
    
    fig.update_layout(
        title=title,
        xaxis_title="Retention Time (min)",
        yaxis_title="Absorbance (mAU)",
        template='plotly_white',
        margin=dict(l=50, r=20, t=60, b=50),
        showlegend=True
    )
    
    # Calculate statistics
    max_absorbance = float(data[intensity_col].max())
    max_time = float(data.loc[data[intensity_col].idxmax(), time_col])
    data_points = len(data)
    rt_range = f"{data[time_col].min():.1f}-{data[time_col].max():.1f} min"
        
    # Format injection datetime
    injection_formatted = ""
    if injection_date and injection_time:
        injection_formatted = f"{injection_date} {injection_time}"
    elif injection_date:
        if len(injection_date) >= 12 and injection_date[:12].isdigit():
            try:
                dt = datetime.strptime(injection_date[:12], "%Y%m%d%H%M")
                injection_formatted = dt.strftime("%Y-%m-%d %H:%M")
            except:
                injection_formatted = injection_date
        else:
            injection_formatted = injection_date
    
    # Build comprehensive info annotation
    info_lines = [
        f"📊 Sample: {sample_name}",
        f"🌊 Wavelength: {wavelength} nm" if wavelength else "",
        f"🕒 RT Range: {rt_range}",
        f"📈 Max: {max_absorbance:.1f} mAU @ {max_time:.2f} min",
        f"📏 Data Points: {data_points}",
        f"👤 Operator: {operator}" if operator else "",
        f"⚙️ Method: {method_name}" if method_name else "",
        f"📅 Injection: {injection_formatted}" if injection_formatted else ""
    ]
    
    info_text = "<br>".join([line for line in info_lines if line])
    
    fig.add_annotation(
        text=info_text,
        x=0.01, y=0.99,
        xref='paper', yref='paper',
        xanchor='left', yanchor='top',
        showarrow=False,
        align='left',
        bgcolor='rgba(255,255,255,0.85)',
        bordercolor='rgba(0,0,0,0.1)',
        borderwidth=1,
        font=dict(size=9)
    )
    
    return fig

def add_imported_peaks_to_plot(fig: go.Figure, file_data: dict, chromatogram_data: pd.DataFrame, 
                              time_col: str, intensity_col: str) -> go.Figure:
    """Add imported peak markers from Chromeleon integration table"""
    
    integration_table = file_data.get('integration_table')
    if integration_table is None or integration_table.empty:
        return fig
    
    try:
        print(f"[DEBUG] 🎯 Adding {len(integration_table)} imported peaks to plot")
        
        # Add peak markers
        peak_times = []
        peak_heights = []
        peak_names = []
        peak_areas = []
        
        for _, peak_row in integration_table.iterrows():
            # Skip total rows
            peak_no = str(peak_row.get('No.', '')).strip().lower()
            if peak_no in ['total', 'n.a.', ''] or 'total' in peak_no:
                continue
            
            try:
                # Get retention time
                rt = float(str(peak_row.get('Retention Time', 0)).replace(',', '.'))
                if rt <= 0:
                    continue
                
                # Find corresponding height in chromatogram data
                closest_idx = np.abs(chromatogram_data[time_col] - rt).argmin()
                height = float(chromatogram_data.iloc[closest_idx][intensity_col])
                
                # Get peak properties
                area = float(str(peak_row.get('Area', 0)).replace(',', '.'))
                rel_area = float(str(peak_row.get('Relative Area', 0)).replace(',', '.'))
                
                peak_times.append(rt)
                peak_heights.append(height)
                peak_names.append(f"Peak {peak_no}")
                peak_areas.append(area)
                
            except (ValueError, TypeError) as e:
                print(f"[DEBUG] ⚠️ Skipping invalid peak: {e}")
                continue
        
        if peak_times:
            # Add peak markers
            fig.add_trace(go.Scatter(
                x=peak_times,
                y=peak_heights,
                mode='markers',
                marker=dict(
                    symbol='triangle-up',
                    size=12,
                    color='red',
                    line=dict(width=2, color='darkred')
                ),
                name='Imported Peaks',
                hovertemplate='<b>%{text}</b><br>' +
                            'RT: %{x:.3f} min<br>' +
                            'Height: %{y:.1f} mAU<br>' +
                            'Area: %{customdata:.2f} mAU·min<br>' +
                            '<extra></extra>',
                text=peak_names,
                customdata=peak_areas,
                showlegend=True
            ))
            
            print(f"[DEBUG] ✅ Added {len(peak_times)} imported peak markers")
        
        # Add peak integration regions
        fig = add_peak_integration_regions(fig, integration_table, chromatogram_data, time_col, intensity_col)
        
    except Exception as e:
        print(f"[DEBUG] ❌ Error adding imported peaks: {e}")
    
    return fig

def add_detected_peaks_to_plot(fig: go.Figure, filename: str, peak_manager) -> go.Figure:
    """Add detected peak markers *AND filled regions* from peak manager to the plot."""

    try:
        # --- Find the chromatogram trace for x/y data
        # Assume main trace is always first one (lines)
        if not fig.data or len(fig.data) == 0:
            return fig
        chromatogram_trace = None
        for trace in fig.data:
            if hasattr(trace, "mode") and "lines" in trace.mode:
                chromatogram_trace = trace
                break
        if chromatogram_trace is None:
            return fig

        x_data = np.array(chromatogram_trace.x)
        y_data = np.array(chromatogram_trace.y)

        # --- Get detected peaks
        peak_markers = peak_manager.get_peak_markers_for_plot(filename)
        if not peak_markers:
            return fig

        print(f"[DEBUG] 🔍 Adding {len(peak_markers)} detected peaks (filled+marker) to plot")

        # --- Overlay filled area and marker for each detected peak
        for marker in peak_markers:
            rt = marker['x']
            height = marker['y']
            area = marker['area']
            name = marker['name']

            # Estimate start/end based on width if provided, else ±0.05 min
            width = marker.get('width', 0.1)
            start_time = marker.get('start_time', rt - width/2)
            end_time = marker.get('end_time', rt + width/2)

            # Ensure indices make sense
            start_idx = np.abs(x_data - start_time).argmin()
            end_idx = np.abs(x_data - end_time).argmin()
            if start_idx >= end_idx:
                center_idx = np.abs(x_data - rt).argmin()
                start_idx = max(0, center_idx - 5)
                end_idx = min(len(x_data) - 1, center_idx + 5)
            px = x_data[start_idx:end_idx+1]
            py = y_data[start_idx:end_idx+1]
            baseline = min(py[0], py[-1], np.percentile(py, 10))

            # Add filled region for this detected peak
            fig.add_trace(go.Scatter(
                x=np.concatenate([[px[0]], px, [px[-1]]]),
                y=np.concatenate([[baseline], py, [baseline]]),
                fill='toself',
                fillcolor='rgba(255,170,0,0.30)',  # Orange transparent fill
                line=dict(color='rgba(200,120,0,0.8)', width=1),
                name=f'Detected Peak (RT: {rt:.2f})',
                hoverinfo="skip",
                showlegend=False,
                legendgroup='detected_peaks'
            ))

            # Add marker (diamond) at peak apex
            fig.add_trace(go.Scatter(
                x=[rt],
                y=[height],
                mode='markers',
                marker=dict(
                    symbol='diamond',
                    size=12,
                    color='orange',
                    line=dict(width=2, color='darkorange')
                ),
                name='Detected Peaks',
                hovertemplate='<b>%{text}</b><br>' +
                            'RT: %{x:.3f} min<br>' +
                            'Height: %{y:.1f} mAU<br>' +
                            'Area: %{customdata:.2f} mAU·min<br>' +
                            '<extra></extra>',
                text=[name],
                customdata=[area],
                showlegend=True
            ))

        print(f"[DEBUG] ✅ Added {len(peak_markers)} detected peak markers AND regions")

    except Exception as e:
        print(f"[DEBUG] ❌ Error adding detected peaks: {e}")

    return fig

def add_peak_integration_regions(fig: go.Figure, integration_table: pd.DataFrame, 
                                chromatogram_data: pd.DataFrame, time_col: str, 
                                intensity_col: str) -> go.Figure:
    """Add subtle peak integration region highlighting"""
    
    try:
        # Add subtle vertical lines and fill regions for each peak
        for _, peak_row in integration_table.iterrows():
            peak_no = str(peak_row.get('No.', '')).strip().lower()
            if peak_no in ['total', 'n.a.', ''] or 'total' in peak_no:
                continue
            
            try:
                rt = float(str(peak_row.get('Retention Time', 0)).replace(',', '.'))
                if rt <= 0:
                    continue
                
                # Estimate peak width (if not available, use default)
                width = 0.1  # Default width in minutes
                
                # Try to get actual width from peak table data
                if hasattr(peak_row, 'Width (50%)') and peak_row.get('Width (50%)'):
                    try:
                        width = float(str(peak_row.get('Width (50%)', 0.1)).replace(',', '.'))
                        width = width * 2  # Use 2x half-height width for visual region
                    except:
                        pass
                
                # Add vertical line at peak center
                fig.add_vline(
                    x=rt,
                    line_dash="dot",
                    line_color="rgba(255, 0, 0, 0.3)",
                    line_width=1,
                    annotation_text=f"Peak {peak_no}",
                    annotation_position="top"
                )
                
                # Add subtle fill region
                start_time = rt - width/2
                end_time = rt + width/2
                
                # Get y-values for the region
                mask = (chromatogram_data[time_col] >= start_time) & (chromatogram_data[time_col] <= end_time)
                region_data = chromatogram_data[mask]
                
                if not region_data.empty:
                    fig.add_trace(go.Scatter(
                        x=region_data[time_col],
                        y=region_data[intensity_col],
                        fill='tonexty',
                        fillcolor='rgba(255, 0, 0, 0.1)',
                        line=dict(color='rgba(255, 0, 0, 0)'),
                        showlegend=False,
                        hoverinfo='skip'
                    ))
                
            except Exception as e:
                print(f"[DEBUG] ⚠️ Error adding integration region: {e}")
                continue
    
    except Exception as e:
        print(f"[DEBUG] ❌ Error in peak integration regions: {e}")
    
    return fig

def create_chromeleon_bundle_plot(file_data):
    """Create plot for Chromeleon bundle with enhanced peak integration"""
    
    # Start with basic chromatogram with peaks
    fig = create_chromatogram_plot(file_data)
    
    # Get additional Chromeleon-specific data
    integration_table = file_data.get('integration_table')
    peak_table = file_data.get('peak_table') 
    sst_result = file_data.get('sst_result', {})
    
    # Add SST result to title if available
    if sst_result:
        total_result = sst_result.get('Total Result', '')
        if total_result:
            current_title = fig.layout.title.text
            result_color = "green" if total_result.lower() == "passed" else "red"
            fig.update_layout(
                title=f"{current_title} | SST: <span style='color:{result_color}'>{total_result}</span>"
            )
    
    return fig

def create_chromatogram_overlay_plot(file_data_list, title_prefix="Overlay"):
    """Create overlay plot for multiple chromatograms with peak visualization"""
    
    if not file_data_list:
        return go.Figure().add_annotation(
            text="No chromatogram data provided",
            xref="paper", yref="paper",
            x=0.5, y=0.5, xanchor='center', yanchor='middle',
            showarrow=False, font_size=16
        )
    
    fig = go.Figure()
    colors = px.colors.qualitative.Set1
    
    for i, file_data in enumerate(file_data_list):
        data = file_data['data']
        metadata = file_data['metadata']
        
        if data is None or data.empty:
            continue
            
        time_col = 'Time (min)'
        intensity_col = None

        for y_candidate in ['Value (mAU)', 'Intensity (mAU)', 'Absorbance (mAU)', 'Signal (mAU)']:
            if time_col in data.columns and y_candidate in data.columns:
                intensity_col = y_candidate
                break

        if not intensity_col:
            print(f"[DEBUG] Skipping overlay — no intensity column in file {metadata.get('file_name', i)}")
            continue

        # Get sample info for legend
        sample_name = metadata.get('Sample Name', metadata.get('file_name', f'Sample {i+1}'))
        wavelength = metadata.get('wavelength') or metadata.get('Wavelength (nm)')
        
        legend_name = f"{sample_name}"
        if wavelength:
            legend_name += f" (λ={wavelength}nm)"
        
        # Add main chromatogram trace
        fig.add_trace(go.Scatter(
            x=data[time_col],
            y=data[intensity_col],
            mode='lines',
            name=legend_name,
            line=dict(color=colors[i % len(colors)], width=1.5),
            hovertemplate=f'<b>{sample_name}</b><br>' +
                         'RT: %{x:.2f} min<br>' +
                         'Absorbance: %{y:.1f} mAU<br>' +
                         '<extra></extra>'
        ))
        
        # Add peaks for this chromatogram
        filename = file_data.get('filename', metadata.get('file_name', f'Sample_{i}'))
        fig = add_imported_peaks_to_plot(fig, file_data, data, time_col, intensity_col)
        
        try:
            from utils.peak_integration import peak_manager
            fig = add_detected_peaks_to_plot(fig, filename, peak_manager)
        except ImportError:
            pass
    
    fig.update_layout(
        title=f"{title_prefix} - HPLC Chromatograms with Peak Integration",
        xaxis_title="Retention Time (min)",
        yaxis_title="Absorbance (mAU)",
        template='plotly_white',
        height=500,
        margin=dict(l=60, r=60, t=80, b=60),
        showlegend=True,
        legend=dict(x=1.02, y=1, xanchor='left', yanchor='top')
    )
    
    return fig