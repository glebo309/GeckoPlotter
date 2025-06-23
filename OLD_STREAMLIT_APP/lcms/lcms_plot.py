

# lcms/lcms_plot.py

import netCDF4 as nc
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import os
import plotly.io as pio

# Configure Plotly to open in browser
pio.renderers.default = "browser"

def is_ms_spectra_file(file_path):
    """
    Check if the file contains mass spectral data.
    
    Parameters:
    file_path (str): Path to the CDF file
    
    Returns:
    bool: True if the file contains mass spectral data
    """
    try:
        data = nc.Dataset(file_path, 'r')
        has_ms_data = 'mass_values' in data.variables and 'intensity_values' in data.variables
        data.close()
        return has_ms_data
    except:
        return False

def get_tic_from_spectra(file_path):
    """
    Extract Total Ion Current (TIC) from a spectra file.
    
    Parameters:
    file_path (str): Path to the CDF file
    
    Returns:
    tuple: (retention_times, tic_values)
    """
    try:
        data = nc.Dataset(file_path, 'r')
        retention_times = data.variables['scan_acquisition_time'][:]
        total_intensity = data.variables['total_intensity'][:]
        data.close()
        return retention_times, total_intensity
    except Exception as e:
        print(f"Error extracting TIC: {e}")
        return None, None

def get_mass_spectrum_at_scan(file_path, scan_index):
    """
    Extract a mass spectrum at a specific scan index.
    
    Parameters:
    file_path (str): Path to the CDF file
    scan_index (int): Index of the scan to extract
    
    Returns:
    tuple: (mz_values, intensity_values, retention_time)
    """
    try:
        data = nc.Dataset(file_path, 'r')
        scan_indices = data.variables['scan_index'][:]
        point_counts = data.variables['point_count'][:]
        
        # Get the start and end indices for the mass values and intensities
        if scan_index >= len(scan_indices):
            print(f"Scan index {scan_index} out of range. Max index is {len(scan_indices)-1}")
            data.close()
            return None, None, None
        
        start_idx = scan_indices[scan_index]
        if scan_index < len(scan_indices) - 1:
            end_idx = scan_indices[scan_index + 1]
        else:
            end_idx = start_idx + point_counts[scan_index]
        
        # Extract the mass values and intensities for this scan
        mz_values = data.variables['mass_values'][start_idx:end_idx]
        intensity_values = data.variables['intensity_values'][start_idx:end_idx]
        retention_time = data.variables['scan_acquisition_time'][scan_index]
        
        data.close()
        return mz_values, intensity_values, retention_time
    except Exception as e:
        print(f"Error extracting mass spectrum: {e}")
        import traceback
        traceback.print_exc()
        return None, None, None

def get_mass_spectrum_at_time(file_path, retention_time):
    """
    Extract a mass spectrum at a specific retention time.
    
    Parameters:
    file_path (str): Path to the CDF file
    retention_time (float): Retention time in minutes
    
    Returns:
    tuple: (mz_values, intensity_values, actual_retention_time)
    """
    try:
        data = nc.Dataset(file_path, 'r')
        scan_times = data.variables['scan_acquisition_time'][:]
        
        # Convert retention time to seconds if given in minutes
        if retention_time < 20:  # Assuming retention time is in minutes if < 20
            retention_time_sec = retention_time * 60
        else:
            retention_time_sec = retention_time
        
        # Find the closest scan to the specified retention time
        closest_scan_idx = np.argmin(np.abs(scan_times - retention_time_sec))
        actual_time = scan_times[closest_scan_idx]
        
        data.close()
        
        # Get the mass spectrum at this scan index
        return get_mass_spectrum_at_scan(file_path, closest_scan_idx)
    except Exception as e:
        print(f"Error getting mass spectrum at time: {e}")
        return None, None, None

def plot_tic_chromatogram(file_path):
    """
    Plot the TIC chromatogram from a mass spec file.
    
    Parameters:
    file_path (str): Path to the CDF file
    
    Returns:
    fig: Plotly figure
    """
    try:
        # Check if this is a spectra file
        if is_ms_spectra_file(file_path):
            retention_times, total_intensity = get_tic_from_spectra(file_path)
            if retention_times is None:
                return None
            
            # Convert to minutes for display
            retention_times_min = retention_times / 60
            
            # Create figure
            fig = go.Figure()
            
            # Add TIC trace
            fig.add_trace(go.Scatter(
                x=retention_times_min,
                y=total_intensity,
                mode='lines',
                name='TIC',
                line=dict(color='blue', width=1.5),
                hovertemplate='Time: %{x:.2f} min<br>Intensity: %{y:,.0f}<extra></extra>'
            ))
            
            # Update layout
            fig.update_layout(
                title=f"Total Ion Chromatogram<br><sup>{os.path.basename(file_path)}</sup>",
                xaxis_title="Retention Time (minutes)",
                yaxis_title="Total Ion Intensity",
                template="plotly_white",
                hovermode="closest"
            )
            
            return fig
        else:
            print("Not a MS spectra file")
            return None
    except Exception as e:
        print(f"Error plotting TIC chromatogram: {e}")
        import traceback
        traceback.print_exc()
        return None

def create_interactive_ms_viewer(file_path):
    """
    Create a simple interactive Mass Spectrometry data viewer.
    This creates a figure with the TIC chromatogram and a placeholder for the mass spectrum.
    The mass spectrum is updated when the user clicks on the TIC chromatogram.
    
    Parameters:
    file_path (str): Path to the CDF file
    
    Returns:
    fig: Plotly figure with both TIC and mass spectrum
    """
    try:
        # Check if this is a spectra file
        if not is_ms_spectra_file(file_path):
            print("Not a MS spectra file")
            return None
        
        # Get TIC data
        retention_times, total_intensity = get_tic_from_spectra(file_path)
        if retention_times is None:
            return None
        
        # Convert to minutes for display
        retention_times_min = retention_times / 60
        
        # Get first mass spectrum for initial display
        mz_values, intensity_values, _ = get_mass_spectrum_at_scan(file_path, 0)
        
        # Create subplots with 2 rows
        fig = make_subplots(
            rows=2, cols=1,
            subplot_titles=["Total Ion Chromatogram (Click to select a time point)", 
                           "Mass Spectrum"],
            vertical_spacing=0.2,
            row_heights=[0.4, 0.6]
        )
        
        # Add TIC trace
        fig.add_trace(
            go.Scatter(
                x=retention_times_min,
                y=total_intensity,
                mode='lines',
                name='TIC',
                line=dict(color='blue', width=1.5),
                hovertemplate='Time: %{x:.2f} min<br>Intensity: %{y:,.0f}<extra></extra>'
            ),
            row=1, col=1
        )
        
        # Add mass spectrum trace (initial state)
        fig.add_trace(
            go.Scatter(
                x=mz_values,
                y=intensity_values,
                mode='lines',
                name='Mass Spectrum',
                line=dict(color='red', width=1),
                hovertemplate='m/z: %{x:.4f}<br>Intensity: %{y:,.0f}<extra></extra>'
            ),
            row=2, col=1
        )
        
        # Update layout
        fig.update_layout(
            title=f"Mass Spectrometry Data Viewer<br><sup>{os.path.basename(file_path)}</sup>",
            height=800,
            template="plotly_white",
            hovermode="closest",
            showlegend=False
        )
        
        # Update axes
        fig.update_xaxes(title_text="Retention Time (min)", row=1, col=1)
        fig.update_yaxes(title_text="Intensity", row=1, col=1)
        fig.update_xaxes(title_text="m/z", row=2, col=1)
        fig.update_yaxes(title_text="Intensity", row=2, col=1)
        
        # Add annotation for instruction
        fig.add_annotation(
            text="Select a point on the TIC chromatogram to view the mass spectrum at that time",
            xref="paper",
            yref="paper",
            x=0.5,
            y=0.6,
            showarrow=False,
            font=dict(size=12)
        )
        
        return fig
    except Exception as e:
        print(f"Error creating interactive MS viewer: {e}")
        import traceback
        traceback.print_exc()
        return None

def extract_eic(file_path, mz_value, tolerance=0.5):
    """
    Extract an Extracted Ion Chromatogram (EIC) for a specific m/z value.
    
    Parameters:
    file_path (str): Path to the CDF file
    mz_value (float): m/z value to extract
    tolerance (float): m/z tolerance (±)
    
    Returns:
    tuple: (retention_times, intensities)
    """
    try:
        # Open the file
        data = nc.Dataset(file_path, 'r')
        
        # Get scan information
        scan_indices = data.variables['scan_index'][:]
        point_counts = data.variables['point_count'][:]
        scan_times = data.variables['scan_acquisition_time'][:]
        
        # Initialize array for the EIC
        eic_intensities = np.zeros(len(scan_times))
        
        # Extract the EIC
        for scan_idx in range(len(scan_times)):
            start_idx = scan_indices[scan_idx]
            if scan_idx < len(scan_indices) - 1:
                end_idx = scan_indices[scan_idx + 1]
            else:
                end_idx = start_idx + point_counts[scan_idx]
            
            mz_values = data.variables['mass_values'][start_idx:end_idx]
            intensity_values = data.variables['intensity_values'][start_idx:end_idx]
            
            # Find intensities within the m/z tolerance
            mask = (mz_values >= mz_value - tolerance) & (mz_values <= mz_value + tolerance)
            if np.any(mask):
                eic_intensities[scan_idx] = np.sum(intensity_values[mask])
        
        # Close the file
        data.close()
        
        # Convert retention times to minutes
        retention_times_min = scan_times / 60
        
        return retention_times_min, eic_intensities
    except Exception as e:
        print(f"Error extracting EIC: {e}")
        import traceback
        traceback.print_exc()
        return None, None

def plot_eic(file_path, mz_value, tolerance=0.5):
    """
    Plot an Extracted Ion Chromatogram (EIC) for a specific m/z value.
    
    Parameters:
    file_path (str): Path to the CDF file
    mz_value (float): m/z value to extract
    tolerance (float): m/z tolerance (±)
    
    Returns:
    fig: Plotly figure
    """
    try:
        retention_times, intensities = extract_eic(file_path, mz_value, tolerance)
        if retention_times is None:
            return None
        
        # Create figure
        fig = go.Figure()
        
        # Add EIC trace
        fig.add_trace(go.Scatter(
            x=retention_times,
            y=intensities,
            mode='lines',
            name=f'm/z {mz_value} ± {tolerance}',
            line=dict(color='blue', width=1.5),
            hovertemplate='Time: %{x:.2f} min<br>Intensity: %{y:,.0f}<extra></extra>'
        ))
        
        # Update layout
        fig.update_layout(
            title=f"Extracted Ion Chromatogram (EIC) for m/z {mz_value} ± {tolerance}<br><sup>{os.path.basename(file_path)}</sup>",
            xaxis_title="Retention Time (minutes)",
            yaxis_title="Intensity",
            template="plotly_white",
            hovermode="closest"
        )
        
        return fig
    except Exception as e:
        print(f"Error plotting EIC: {e}")
        import traceback
        traceback.print_exc()
        return None

def create_mass_spec_dashboard(file_path):
    """
    Create a comprehensive dashboard for exploring mass spectrometry data.
    
    Parameters:
    file_path (str): Path to the CDF file
    
    Returns:
    None (saves HTML file)
    """
    try:
        # First check if the file has MS data
        if not is_ms_spectra_file(file_path):
            print(f"File {file_path} does not appear to contain mass spectral data")
            return
        
        # Extract TIC data
        retention_times, total_intensity = get_tic_from_spectra(file_path)
        retention_times_min = retention_times / 60
        
        # Get initial mass spectrum (first scan)
        mz_values, intensity_values, _ = get_mass_spectrum_at_scan(file_path, 0)
        
        # Create a figure with 3 subplots:
        # 1. TIC chromatogram
        # 2. Mass spectrum
        # 3. EIC (initially empty)
        fig = make_subplots(
            rows=3, cols=1,
            subplot_titles=["Total Ion Chromatogram (Click to select time point)", 
                           "Mass Spectrum (Click to view EIC)", 
                           "Extracted Ion Chromatogram (EIC)"],
            vertical_spacing=0.1,
            row_heights=[0.25, 0.4, 0.25]
        )
        
        # Add TIC trace
        fig.add_trace(
            go.Scatter(
                x=retention_times_min,
                y=total_intensity,
                mode='lines',
                name='TIC',
                line=dict(color='blue', width=1.5),
                hovertemplate='Time: %{x:.2f} min<br>Intensity: %{y:,.0f}<extra></extra>'
            ),
            row=1, col=1
        )
        
        # Add vertical line to show current scan in TIC
        fig.add_trace(
            go.Scatter(
                x=[retention_times_min[0], retention_times_min[0]],
                y=[0, np.max(total_intensity)],
                mode='lines',
                name='Current Scan',
                line=dict(color='red', width=1, dash='dash'),
                hoverinfo='skip'
            ),
            row=1, col=1
        )
        
        # Add mass spectrum trace
        fig.add_trace(
            go.Scatter(
                x=mz_values,
                y=intensity_values,
                mode='lines',
                name='Mass Spectrum',
                line=dict(color='blue', width=1),
                hovertemplate='m/z: %{x:.4f}<br>Intensity: %{y:,.0f}<extra></extra>'
            ),
            row=2, col=1
        )
        
        # Add placeholder for EIC
        fig.add_trace(
            go.Scatter(
                x=[0],
                y=[0],
                mode='lines',
                name='EIC',
                line=dict(color='green', width=1.5),
                hovertemplate='Time: %{x:.2f} min<br>Intensity: %{y:,.0f}<extra></extra>'
            ),
            row=3, col=1
        )
        
        # Update layout
        fig.update_layout(
            title=f"Mass Spectrometry Data Explorer<br><sup>{os.path.basename(file_path)}</sup>",
            height=900,
            template="plotly_white",
            hovermode="closest",
            showlegend=False
        )
        
        # Update axes
        fig.update_xaxes(title_text="Retention Time (min)", row=1, col=1)
        fig.update_yaxes(title_text="Intensity", row=1, col=1)
        fig.update_xaxes(title_text="m/z", row=2, col=1)
        fig.update_yaxes(title_text="Intensity", row=2, col=1)
        fig.update_xaxes(title_text="Retention Time (min)", row=3, col=1)
        fig.update_yaxes(title_text="Intensity", row=3, col=1)
        
        # Generate HTML
        html_output = f"ms_explorer_{os.path.splitext(os.path.basename(file_path))[0]}.html"
        
        # Since we can't easily implement the client-side interactivity here,
        # create a simple wrapper that will explain how to use a pure Python approach
        with open(html_output, 'w') as f:
            f.write(f"""<!DOCTYPE html>
<html>
<head>
    <title>Mass Spectrometry Data Explorer</title>
    <script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
</head>
<body>
    <h1>Mass Spectrometry Data Explorer</h1>
    <p>File: {os.path.basename(file_path)}</p>
    <p>This is a static preview of the MS data. For full interactivity, run the Python script and follow these steps:</p>
    <ol>
        <li>Run the main script and select option 3 (Interactive MS Viewer)</li>
        <li>Click on the TIC chromatogram to view the mass spectrum at that retention time</li>
        <li>For Extracted Ion Chromatograms, use option 5 and enter a specific m/z value</li>
    </ol>
    <div id="tic-plot"></div>
    <div id="ms-plot"></div>
    <div id="eic-plot"></div>
    
    <script>
        // Create basic plots without interactivity
        var ticData = {{
            x: [{",".join(map(str, retention_times_min))}],
            y: [{",".join(map(str, total_intensity))}],
            type: 'scatter',
            mode: 'lines',
            name: 'TIC',
            line: {{color: 'blue', width: 1.5}}
        }};
        
        var msData = {{
            x: [{",".join(map(str, mz_values[:300]))}],
            y: [{",".join(map(str, intensity_values[:300]))}],
            type: 'scatter',
            mode: 'lines',
            name: 'Mass Spectrum',
            line: {{color: 'blue', width: 1}}
        }};
        
        Plotly.newPlot('tic-plot', [ticData], {{
            title: 'Total Ion Chromatogram',
            xaxis: {{title: 'Retention Time (min)'}},
            yaxis: {{title: 'Intensity'}},
            margin: {{t: 50, l: 80, r: 50, b: 50}}
        }});
        
        Plotly.newPlot('ms-plot', [msData], {{
            title: 'Mass Spectrum (First Scan)',
            xaxis: {{title: 'm/z'}},
            yaxis: {{title: 'Intensity'}},
            margin: {{t: 50, l: 80, r: 50, b: 50}}
        }});
        
        Plotly.newPlot('eic-plot', [{{
            x: [0],
            y: [0],
            type: 'scatter',
            mode: 'lines',
            name: 'EIC',
            line: {{color: 'green', width: 1.5}}
        }}], {{
            title: 'Extracted Ion Chromatogram (Select m/z in MS plot)',
            xaxis: {{title: 'Retention Time (min)'}},
            yaxis: {{title: 'Intensity'}},
            margin: {{t: 50, l: 80, r: 50, b: 50}}
        }});
    </script>
</body>
</html>""")
        
        print(f"Created MS Explorer preview in {html_output}")
        print("For full interactivity, use the Python script directly.")
        
        # Also show the initial view
        fig.show()
        
        return fig
    except Exception as e:
        print(f"Error creating MS dashboard: {e}")
        import traceback
        traceback.print_exc()
        return None

# Main application for running the script
if __name__ == "__main__":
    # List all CDF files in the current directory
    cdf_files = [f for f in os.listdir() if f.endswith('.cdf')]
    
    if not cdf_files:
        print("No CDF files found in the current directory.")
    else:
        # Look for MS spectra files
        ms_spectra_files = [f for f in cdf_files if is_ms_spectra_file(f)]
        
        if not ms_spectra_files:
            print("No files with mass spectral data found.")
            print("Checking for files with 'spectra' in the name...")
            
            # Try to find files with 'spectra' in the name
            potential_ms_files = [f for f in cdf_files if 'spectra' in f.lower()]
            
            if potential_ms_files:
                print("Found potential MS files:")
                for i, file in enumerate(potential_ms_files):
                    print(f"{i+1}. {file}")
                
                # Let user select a file
                file_idx = int(input("Enter the number of the file to analyze: ")) - 1
                if 0 <= file_idx < len(potential_ms_files):
                    selected_file = potential_ms_files[file_idx]
                else:
                    print("Invalid selection")
                    exit()
            else:
                print("No potential MS files found. Available files:")
                for i, file in enumerate(cdf_files):
                    print(f"{i+1}. {file}")
                
                # Let user select a file
                file_idx = int(input("Enter the number of the file to analyze: ")) - 1
                if 0 <= file_idx < len(cdf_files):
                    selected_file = cdf_files[file_idx]
                else:
                    print("Invalid selection")
                    exit()
        else:
            print("Found MS files:")
            for i, file in enumerate(ms_spectra_files):
                print(f"{i+1}. {file}")
            
            # Let user select a file
            file_idx = int(input("Enter the number of the file to analyze: ")) - 1
            if 0 <= file_idx < len(ms_spectra_files):
                selected_file = ms_spectra_files[file_idx]
            else:
                print("Invalid selection")
                exit()
        
        # Main menu
        while True:
            print("\nMass Spectrometry Data Analysis Menu:")
            print("1. Plot TIC Chromatogram")
            print("2. View Mass Spectrum at Specific Retention Time")
            print("3. Interactive MS Viewer")
            print("4. Extract Ion Chromatogram (EIC)")
            print("5. Create Comprehensive MS Dashboard")
            print("0. Exit")
            
            choice = input("Enter your choice: ")
            
            if choice == '0':
                break
            
            if choice == '1':
                fig = plot_tic_chromatogram(selected_file)
                if fig:
                    fig.show()
            
            elif choice == '2':
                rt = float(input("Enter retention time in minutes: "))
                fig = plot_mass_spectrum(selected_file, retention_time=rt)
                if fig:
                    fig.show()
            
            elif choice == '3':
                fig = create_interactive_ms_viewer(selected_file)
                if fig:
                    fig.show()
                    print("Click on the TIC to view the mass spectrum at that time point.")
                    print("Note: Full interactivity requires running in an environment that supports Plotly callbacks.")
            
            elif choice == '4':
                mz = float(input("Enter m/z value: "))
                tolerance = float(input("Enter m/z tolerance (default 0.5): ") or "0.5")
                fig = plot_eic(selected_file, mz, tolerance)
                if fig:
                    fig.show()
            
            elif choice == '5':
                create_mass_spec_dashboard(selected_file)
            
            else:
                print("Invalid choice. Please try again.")