import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import io

st.set_page_config(page_title="SEC Data Visualizer", layout="wide")

st.title("Size Exclusion Chromatography Data Visualizer")
st.markdown("Upload your SEC export file to visualize and clean the data")

# File upload
uploaded_file = st.file_uploader("Choose your SEC data file", type=['txt', 'csv'])

# Add debug mode
debug_mode = st.checkbox("Show debug information", value=False)

if uploaded_file is not None:
    # Read the file with encoding detection
    raw_data = uploaded_file.read()
    
    # Try different encodings
    content = None
    encodings = ['utf-8', 'utf-16', 'utf-16-le', 'utf-16-be', 'latin-1', 'cp1252']
    successful_encoding = None
    
    for encoding in encodings:
        try:
            content = raw_data.decode(encoding)
            successful_encoding = encoding
            st.success(f"File successfully decoded using {encoding} encoding")
            break
        except UnicodeDecodeError:
            continue
    
    if content is None:
        st.error("Could not decode the file. Please check the file encoding.")
        st.stop()
    
    # Debug information
    if debug_mode:
        st.write("**Debug Information:**")
        st.write(f"- File size: {len(raw_data)} bytes")
        st.write(f"- First 20 bytes (hex): {' '.join(f'{b:02x}' for b in raw_data[:20])}")
        st.write(f"- Successfully decoded with: {successful_encoding}")
    
    # Debug information
    if debug_mode:
        st.write("**Debug Information:**")
        st.write(f"- File size: {len(raw_data)} bytes")
        st.write(f"- First 20 bytes (hex): {' '.join(f'{b:02x}' for b in raw_data[:20])}")
        st.write(f"- Successfully decoded with: {encoding}")
    
    lines = content.strip().split('\n')
    
    # Parse headers
    parameter_row = lines[1].split('\t')
    parameter_row = [p.strip() for p in parameter_row if p.strip()]
    unit_row = lines[2].split('\t')
    
    # Identify column structure
    columns = []
    for i in range(0, len(unit_row), 2):
        if i + 1 < len(unit_row):
            param_index = i // 2
            if param_index < len(parameter_row):
                columns.append({
                    'parameter': parameter_row[param_index],
                    'volume_index': i,
                    'value_index': i + 1,
                    'unit': unit_row[i + 1].strip()
                })
    
    # Parse data
    data = []
    for i in range(3, len(lines)):
        cells = lines[i].split('\t')
        row = {}
        
        for col in columns:
            if col['volume_index'] < len(cells) and col['value_index'] < len(cells):
                try:
                    volume = float(cells[col['volume_index']])
                except:
                    volume = 0
                
                value = cells[col['value_index']]
                try:
                    parsed_value = float(value)
                except:
                    parsed_value = value.replace('"', '')
                
                row[f"{col['parameter']}_volume"] = volume
                row[f"{col['parameter']}_value"] = parsed_value
        
        if row:  # Only add non-empty rows
            data.append(row)
    
    # Create clean dataframe
    clean_data = []
    for row in data:
        clean_row = {
            'Volume_ml': row.get('UV_volume', 0),
            'UV_mAU': row.get('UV_value', 0),
            'Conductivity_mS_cm': row.get('Cond_value', 0),
            'Conc_B_percent': row.get('Conc B_value', 0),
            'Injection': row.get('Injection_value', ''),
            'Run_Log': row.get('Run Log_value', ''),
            'Fraction': row.get('Fraction_value', ''),
            'UV_Baseline_mAU': row.get('UV_CUT_TEMP@100,BASEM_value', 0)
        }
        clean_data.append(clean_row)
    
    df = pd.DataFrame(clean_data)
    
    # Display data info
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total Data Points", f"{len(df):,}")
    with col2:
        st.metric("Volume Range (ml)", f"{df['Volume_ml'].min():.3f} to {df['Volume_ml'].max():.3f}")
    with col3:
        st.metric("UV Range (mAU)", f"{df['UV_mAU'].min():.1f} to {df['UV_mAU'].max():.1f}")
    with col4:
        st.metric("Run Time (ml)", f"{df['Volume_ml'].max() - df['Volume_ml'].min():.1f}")
    
    # Create tabs
    tab1, tab2, tab3, tab4, tab5 = st.tabs(["📊 Chromatogram", "📈 Multi-Parameter Plot", "🔍 Peak Analysis", "📋 Data Table", "💾 Export"])
    
    with tab1:
        st.subheader("UV Chromatogram")
        
        # Data decimation for large datasets
        if len(df) > 10000:
            decimate_factor = len(df) // 5000
            plot_df = df.iloc[::decimate_factor]
            st.info(f"Plotting every {decimate_factor}th point for performance ({len(plot_df):,} points shown)")
        else:
            plot_df = df
        
        # Create UV plot
        fig_uv = go.Figure()
        
        # Add UV trace
        fig_uv.add_trace(go.Scatter(
            x=plot_df['Volume_ml'],
            y=plot_df['UV_mAU'],
            mode='lines',
            name='UV Signal',
            line=dict(color='blue', width=2)
        ))
        
        # Add baseline
        fig_uv.add_trace(go.Scatter(
            x=plot_df['Volume_ml'],
            y=plot_df['UV_Baseline_mAU'],
            mode='lines',
            name='UV Baseline',
            line=dict(color='red', width=1, dash='dash')
        ))
        
        # Add fraction markers (limit to prevent overcrowding)
        fractions = df[df['Fraction'] != ''].copy()
        if not fractions.empty:
            # Limit number of fraction labels shown if too many
            if len(fractions) > 100:
                # Show every nth fraction to avoid overcrowding
                n = len(fractions) // 100
                fractions_to_show = fractions.iloc[::n]
                st.info(f"Showing every {n}th fraction label ({len(fractions_to_show)} of {len(fractions)} total)")
            else:
                fractions_to_show = fractions
            
            fig_uv.add_trace(go.Scatter(
                x=fractions_to_show['Volume_ml'],
                y=fractions_to_show['UV_mAU'],
                mode='markers+text',
                name='Fractions',
                marker=dict(size=8, color='green'),
                text=fractions_to_show['Fraction'],
                textposition="top center",
                textfont=dict(size=8)
            ))
        
        fig_uv.update_layout(
            title="Size Exclusion Chromatogram",
            xaxis_title="Volume (ml)",
            yaxis_title="UV Absorbance (mAU)",
            height=500,
            hovermode='x unified'
        )
        
        st.plotly_chart(fig_uv, use_container_width=True)
    
    with tab2:
        st.subheader("Multi-Parameter Analysis")
        
        # Use same decimated data if applicable
        if 'plot_df' not in locals():
            if len(df) > 10000:
                decimate_factor = len(df) // 5000
                plot_df = df.iloc[::decimate_factor]
                st.info(f"Plotting every {decimate_factor}th point for performance")
            else:
                plot_df = df
        
        # Create subplots
        fig_multi = make_subplots(
            rows=3, cols=1,
            shared_xaxes=True,
            vertical_spacing=0.05,
            subplot_titles=('UV Signal', 'Conductivity', 'Buffer B Concentration')
        )
        
        # UV plot
        fig_multi.add_trace(
            go.Scatter(x=plot_df['Volume_ml'], y=plot_df['UV_mAU'], name='UV', line=dict(color='blue')),
            row=1, col=1
        )
        
        # Conductivity plot
        fig_multi.add_trace(
            go.Scatter(x=plot_df['Volume_ml'], y=plot_df['Conductivity_mS_cm'], name='Conductivity', line=dict(color='orange')),
            row=2, col=1
        )
        
        # Concentration B plot
        fig_multi.add_trace(
            go.Scatter(x=plot_df['Volume_ml'], y=plot_df['Conc_B_percent'], name='Conc B', line=dict(color='green')),
            row=3, col=1
        )
        
        # Update axes
        fig_multi.update_xaxes(title_text="Volume (ml)", row=3, col=1)
        fig_multi.update_yaxes(title_text="UV (mAU)", row=1, col=1)
        fig_multi.update_yaxes(title_text="Cond (mS/cm)", row=2, col=1)
        fig_multi.update_yaxes(title_text="Conc B (%)", row=3, col=1)
        
        fig_multi.update_layout(height=800, showlegend=False, hovermode='x unified')
        
        st.plotly_chart(fig_multi, use_container_width=True)
    
    with tab3:
        st.subheader("Peak Analysis")
        
        # Volume range selector
        col1, col2 = st.columns(2)
        with col1:
            vol_min = st.number_input("Start Volume (ml)", 
                                    min_value=float(df['Volume_ml'].min()), 
                                    max_value=float(df['Volume_ml'].max()), 
                                    value=float(df['Volume_ml'].min()))
        with col2:
            vol_max = st.number_input("End Volume (ml)", 
                                    min_value=float(df['Volume_ml'].min()), 
                                    max_value=float(df['Volume_ml'].max()), 
                                    value=float(df['Volume_ml'].max()))
        
        # Filter data for selected range
        mask = (df['Volume_ml'] >= vol_min) & (df['Volume_ml'] <= vol_max)
        range_df = df[mask]
        
        if len(range_df) > 0:
            # Create zoomed plot
            fig_zoom = go.Figure()
            
            fig_zoom.add_trace(go.Scatter(
                x=range_df['Volume_ml'],
                y=range_df['UV_mAU'],
                mode='lines',
                name='UV Signal',
                line=dict(color='blue', width=2)
            ))
            
            # Find peaks (simple approach - local maxima)
            uv_values = range_df['UV_mAU'].values
            peak_indices = []
            for i in range(1, len(uv_values) - 1):
                if uv_values[i] > uv_values[i-1] and uv_values[i] > uv_values[i+1]:
                    if uv_values[i] > range_df['UV_mAU'].mean() + range_df['UV_mAU'].std():
                        peak_indices.append(i)
            
            # Mark peaks
            if peak_indices:
                peak_volumes = range_df.iloc[peak_indices]['Volume_ml']
                peak_heights = range_df.iloc[peak_indices]['UV_mAU']
                
                fig_zoom.add_trace(go.Scatter(
                    x=peak_volumes,
                    y=peak_heights,
                    mode='markers',
                    name='Detected Peaks',
                    marker=dict(size=10, color='red', symbol='triangle-up')
                ))
                
                # Peak statistics
                st.write(f"**Found {len(peak_indices)} peaks in selected range**")
                peak_data = pd.DataFrame({
                    'Volume (ml)': peak_volumes.values,
                    'Height (mAU)': peak_heights.values,
                    'Fraction': [range_df.iloc[i]['Fraction'] if range_df.iloc[i]['Fraction'] else 'N/A' for i in peak_indices]
                })
                st.dataframe(peak_data)
            
            fig_zoom.update_layout(
                title=f"Zoomed View: {vol_min:.2f} - {vol_max:.2f} ml",
                xaxis_title="Volume (ml)",
                yaxis_title="UV Absorbance (mAU)",
                height=400
            )
            
            st.plotly_chart(fig_zoom, use_container_width=True)
        else:
            st.warning("No data in selected range")
    
    with tab4:
        st.subheader("Data Table")
        
        # Display options
        col1, col2, col3 = st.columns(3)
        with col1:
            show_all = st.checkbox("Show all columns", value=False)
        with col2:
            num_rows = st.number_input("Number of rows to display", min_value=10, max_value=min(1000, len(df)), value=min(50, len(df)))
        with col3:
            if len(df) > 1000:
                sample_data = st.checkbox("Sample data (every nth row)", value=True)
            else:
                sample_data = False
        
        # Prepare data for display
        if sample_data and len(df) > 1000:
            # Calculate sampling rate
            sample_rate = max(1, len(df) // 1000)
            display_df = df.iloc[::sample_rate].head(num_rows)
            st.info(f"Showing every {sample_rate}th row from the dataset")
        else:
            display_df = df.head(num_rows)
        
        if show_all:
            st.dataframe(display_df, use_container_width=True)
        else:
            # Show only numeric columns by default
            numeric_cols = ['Volume_ml', 'UV_mAU', 'Conductivity_mS_cm', 'Conc_B_percent', 'UV_Baseline_mAU']
            st.dataframe(display_df[numeric_cols], use_container_width=True)
        
        # Summary statistics
        st.subheader("Summary Statistics")
        st.dataframe(df.describe(), use_container_width=True)
    
    with tab5:
        st.subheader("Export Clean Data")
        
        st.markdown("""
        The data has been cleaned and reorganized with:
        - Single volume column (ml)
        - Clear column headers with units
        - Numeric values properly parsed
        - String values cleaned (quotes removed)
        """)
        
        # CSV export
        csv_buffer = io.StringIO()
        df.to_csv(csv_buffer, index=False)
        csv_string = csv_buffer.getvalue()
        
        st.download_button(
            label="📥 Download Clean CSV",
            data=csv_string,
            file_name="clean_sec_data.csv",
            mime="text/csv"
        )
        
        # Excel export option (check if openpyxl is available)
        try:
            import openpyxl
            excel_available = True
        except ImportError:
            excel_available = False
        
        if excel_available:
            excel_buffer = io.BytesIO()
            with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
                df.to_excel(writer, sheet_name='SEC_Data', index=False)
                
                # Get the worksheet
                worksheet = writer.sheets['SEC_Data']
                
                # Auto-adjust column widths
                for column in df:
                    column_length = max(df[column].astype(str).map(len).max(), len(column))
                    col_idx = df.columns.get_loc(column)
                    if col_idx < 26:  # Only handle first 26 columns (A-Z)
                        worksheet.column_dimensions[chr(65 + col_idx)].width = column_length + 2
            
            excel_data = excel_buffer.getvalue()
            
            st.download_button(
                label="📥 Download Excel File",
                data=excel_data,
                file_name="clean_sec_data.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        else:
            st.info("Install 'openpyxl' to enable Excel export: pip install openpyxl")
        
        # Preview of exported data
        st.subheader("Export Preview")
        st.code(df.head(10).to_csv(index=False), language='csv')

else:
    st.info("👆 Please upload your SEC data file to begin visualization")
    
    st.markdown("""
    ### Expected File Format
    Your file should have:
    1. First row: Channel identifiers (e.g., "Chrom.1")
    2. Second row: Parameter names (UV, Cond, Conc B, etc.)
    3. Third row: Units (ml, mAU, mS/cm, %, etc.)
    4. Data rows: Tab-separated values
    
    Each parameter typically has two columns: volume (ml) and value.
    """)