import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
from scipy import stats
import os
import glob

# Set page config
st.set_page_config(
    page_title="TsRTA Flow Cell Analysis",
    page_icon="🧪",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Title and description
st.title("🧪 TsRTA Flow Cell Activity Analysis")
st.markdown("""
**DIY Flow Cell Setup for Immobilized Enzyme Activity Measurement**
- Continuous monitoring using Vapourtec pump + frit syringe
- Eliminates sampling stress for fast reactions
- Real-time activity measurement at 245 nm
""")

# Experimental parameters
st.sidebar.header("⚗️ Experimental Parameters")
ext_coeff = st.sidebar.number_input("Extinction Coefficient (mM⁻¹cm⁻¹)", value=12.6, step=0.1)
path_length = st.sidebar.number_input("Path Length (cm)", value=0.5, step=0.1)
volume_ml = st.sidebar.number_input("Total Volume (mL)", value=5.0, step=0.1)
enzyme_conc = st.sidebar.number_input("Enzyme Concentration (mg/mL)", value=0.03, step=0.001, format="%.3f")

# Calculate derived parameters
total_enzyme_mg = enzyme_conc * volume_ml
volume_l = volume_ml / 1000

st.sidebar.markdown(f"""
**Calculated Parameters:**
- Total enzyme: {total_enzyme_mg:.3f} mg
- Volume: {volume_l:.3f} L
""")

# File loading function
@st.cache_data
def load_csv_files():
    """Load all CSV files in the current directory"""
    csv_files = glob.glob("tsrta_*.csv")
    csv_files.sort()
    
    datasets = {}
    for file in csv_files:
        try:
            # Read the full file content
            with open(file, 'r') as f:
                content = f.read()
            
            # Find data section
            lines = content.split('\n')
            data_start = None
            data_end = None
            
            for i, line in enumerate(lines):
                if 'Time (min),Abs' in line:
                    data_start = i + 1
                elif data_start and line.strip() and not ',' in line and 'Sample' in line:
                    data_end = i
                    break
            
            if data_start:
                data_lines = lines[data_start:data_end] if data_end else lines[data_start:]
                data_lines = [line for line in data_lines if line.strip() and ',' in line]
                
                # Parse the data
                rows = []
                for line in data_lines:
                    parts = line.strip().split(',')
                    if len(parts) >= 2:
                        try:
                            time_min = float(parts[0])
                            abs_orig = float(parts[1]) if parts[1] else np.nan
                            abs_corr = float(parts[2]) if len(parts) > 2 and parts[2] else abs_orig
                            rows.append([time_min, abs_orig, abs_corr])
                        except ValueError:
                            continue
                
                if rows:
                    df = pd.DataFrame(rows, columns=['Time_min', 'Abs_Original', 'Abs_Corrected'])
                    df['Time_s'] = df['Time_min'] * 60
                    df = df.dropna()
                    datasets[file] = df
                    
        except Exception as e:
            st.warning(f"Could not load {file}: {e}")
    
    return datasets

# Load data
datasets = load_csv_files()

if not datasets:
    st.error("No CSV files found! Please ensure tsrta_*.csv files are in the same directory.")
    st.stop()

st.success(f"Loaded {len(datasets)} datasets: {', '.join(datasets.keys())}")

# Dataset selection
st.header("📊 Data Visualization")
selected_files = st.multiselect(
    "Select datasets to analyze:",
    list(datasets.keys()),
    default=list(datasets.keys())[:3]  # Select first 3 by default
)

use_corrected = st.checkbox("Use corrected data (Column 3) where available", value=True)

if not selected_files:
    st.warning("Please select at least one dataset.")
    st.stop()

# Create visualization
fig = go.Figure()

colors = px.colors.qualitative.Plotly
dataset_info = {}

for i, file in enumerate(selected_files):
    df = datasets[file]
    
    # Choose which absorbance column to use
    abs_col = 'Abs_Corrected' if use_corrected else 'Abs_Original'
    
    # Store dataset info for analysis
    dataset_info[file] = {
        'time_s': df['Time_s'].values,
        'abs': df[abs_col].values,
        'time_range': f"{df['Time_s'].min():.1f}-{df['Time_s'].max():.1f}s",
        'abs_range': f"{df[abs_col].min():.3f}-{df[abs_col].max():.3f}",
        'points': len(df)
    }
    
    # Add trace
    fig.add_trace(go.Scatter(
        x=df['Time_s'],
        y=df[abs_col],
        mode='lines+markers',
        name=file.replace('.csv', '').replace('tsrta_', ''),
        line=dict(color=colors[i % len(colors)]),
        marker=dict(size=4),
        hovertemplate=f"<b>{file}</b><br>Time: %{{x:.1f}}s<br>Abs: %{{y:.4f}}<extra></extra>"
    ))
    
    # Show original vs corrected for files with corrections
    if use_corrected and not df['Abs_Original'].equals(df['Abs_Corrected']):
        fig.add_trace(go.Scatter(
            x=df['Time_s'],
            y=df['Abs_Original'],
            mode='lines',
            name=f"{file.replace('.csv', '').replace('tsrta_', '')} (original)",
            line=dict(color=colors[i % len(colors)], dash='dash', width=1),
            opacity=0.5,
            showlegend=False,
            hovertemplate=f"<b>{file} (original)</b><br>Time: %{{x:.1f}}s<br>Abs: %{{y:.4f}}<extra></extra>"
        ))

fig.update_layout(
    title="TsRTA Flow Cell Continuous Monitoring",
    xaxis_title="Time (seconds)",
    yaxis_title="Absorbance (245 nm)",
    hovermode='x unified',
    height=600,
    showlegend=True
)

st.plotly_chart(fig, use_container_width=True)

# Activity Analysis
st.header("🔬 Activity Analysis")

# Time window selection
col1, col2 = st.columns(2)
with col1:
    start_time = st.number_input("Analysis start time (s)", value=25, step=5)
with col2:
    end_time = st.number_input("Analysis end time (s)", value=80, step=5)

def calculate_activity(time_s, abs_values, start_t, end_t):
    """Calculate enzyme activity from kinetic data"""
    # Filter to analysis window
    mask = (time_s >= start_t) & (time_s <= end_t)
    if np.sum(mask) < 5:
        return None
    
    time_min = time_s[mask] / 60
    abs_filtered = abs_values[mask]
    
    # Linear regression
    slope, intercept, r_value, p_value, std_err = stats.linregress(time_min, abs_filtered)
    
    # Convert to activity
    slope_abs_per_min = slope
    slope_mM_per_min = slope_abs_per_min / (ext_coeff * path_length)
    slope_uM_per_min = slope_mM_per_min * 1000
    slope_umol_per_min = slope_uM_per_min * volume_l
    activity_U_per_mg = slope_umol_per_min / total_enzyme_mg
    
    return {
        'slope_abs_min': slope_abs_per_min,
        'slope_mM_min': slope_mM_per_min,
        'slope_uM_min': slope_uM_per_min,
        'slope_umol_min': slope_umol_per_min,
        'activity_U_mg': activity_U_per_mg,
        'r_squared': r_value**2,
        'p_value': p_value,
        'std_err': std_err,
        'n_points': np.sum(mask)
    }

# Calculate activities for all selected datasets
results = {}
for file in selected_files:
    info = dataset_info[file]
    result = calculate_activity(info['time_s'], info['abs'], start_time, end_time)
    if result:
        results[file] = result

# Display results table
if results:
    st.subheader(f"📈 Activity Results ({start_time}-{end_time}s window)")
    
    # Create results DataFrame
    results_data = []
    for file, result in results.items():
        results_data.append({
            'Dataset': file.replace('.csv', '').replace('tsrta_', ''),
            'Slope (abs/min)': f"{result['slope_abs_min']:.5f}",
            'R²': f"{result['r_squared']:.4f}",
            'Activity (U/mg)': f"{result['activity_U_mg']:.3f}",
            'Points': result['n_points'],
            'Quality': '✅ Excellent' if result['r_squared'] > 0.95 else '⚠️ Good' if result['r_squared'] > 0.8 else '❌ Poor'
        })
    
    results_df = pd.DataFrame(results_data)
    st.dataframe(results_df, use_container_width=True)
    
    # Calculation details
    st.subheader("🧮 Calculation Details")
    for file, result in results.items():
        with st.expander(f"Details for {file.replace('.csv', '').replace('tsrta_', '')}"):
            st.write(f"""
            **Step-by-step calculation:**
            1. Slope: {result['slope_abs_min']:.5f} abs/min
            2. Convert to mM/min: {result['slope_abs_min']:.5f} ÷ ({ext_coeff} × {path_length}) = {result['slope_mM_min']:.5f} mM/min
            3. Convert to µM/min: {result['slope_mM_min']:.5f} × 1000 = {result['slope_uM_min']:.3f} µM/min
            4. Convert to µmol/min: {result['slope_uM_min']:.3f} × {volume_l:.3f} L = {result['slope_umol_min']:.5f} µmol/min
            5. Calculate U/mg: {result['slope_umol_min']:.5f} ÷ {total_enzyme_mg:.3f} mg = **{result['activity_U_mg']:.3f} U/mg**
            
            **Statistics:**
            - R² = {result['r_squared']:.4f}
            - p-value = {result['p_value']:.2e}
            - Standard error = {result['std_err']:.5f}
            - Data points = {result['n_points']}
            """)
    
    # Summary statistics
    valid_activities = [r['activity_U_mg'] for r in results.values() if r['r_squared'] > 0.8]
    if len(valid_activities) > 1:
        mean_activity = np.mean(valid_activities)
        std_activity = np.std(valid_activities, ddof=1)
        
        st.subheader("📊 Summary Statistics")
        st.success(f"""
        **Flow Cell Method Results:**
        - Valid measurements (R² > 0.8): {len(valid_activities)}
        - Average activity: **{mean_activity:.2f} ± {std_activity:.2f} U/mg**
        """)
        
        # Comparison with batch method
        st.subheader("⚖️ Method Comparison")
        batch_activity = 2.89
        batch_std = 0.15
        
        comparison_data = pd.DataFrame({
            'Method': ['Batch (1 mL)', 'Flow Cell (5 mL)'],
            'Activity (U/mg)': [f"{batch_activity:.2f} ± {batch_std:.2f}", f"{mean_activity:.2f} ± {std_activity:.2f}"],
            'Volume': ['1 mL', f'{volume_ml} mL'],
            'Sampling': ['Manual pipetting', 'Continuous flow'],
            'Advantages': ['Standard method', 'No sampling stress, constant volume']
        })
        
        st.dataframe(comparison_data, use_container_width=True)
        
        # Agreement analysis
        percent_diff = abs(mean_activity - batch_activity) / batch_activity * 100
        if percent_diff < 30:
            st.success(f"✅ **Excellent agreement** between methods ({percent_diff:.1f}% difference)")
        else:
            st.warning(f"⚠️ **Moderate agreement** between methods ({percent_diff:.1f}% difference)")

else:
    st.warning("No valid results in the selected time window. Try adjusting the analysis window.")

# Raw data table
with st.expander("📋 View Raw Data"):
    for file in selected_files:
        st.subheader(f"Data from {file}")
        df_display = datasets[file].copy()
        df_display['Time_s'] = df_display['Time_s'].round(1)
        df_display['Abs_Original'] = df_display['Abs_Original'].round(4)
        df_display['Abs_Corrected'] = df_display['Abs_Corrected'].round(4)
        st.dataframe(df_display, use_container_width=True)

# Footer
st.markdown("---")
st.markdown("""
**About this analysis:**
- DIY flow cell setup using Vapourtec pump with frit syringe
- Continuous monitoring eliminates sampling stress for immobilized enzymes
- Activity calculated using Beer's Law: A = ε × c × l
- 1 Unit (U) = 1 µmol product formed per minute
""")
