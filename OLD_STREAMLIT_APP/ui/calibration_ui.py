#ui/calibration_ui.py

import streamlit as st
import numpy as np
import pandas as pd
import json
import plotly.graph_objects as go
from models.calibration import fit_calibration_model, group_peaks_by_retention_time
from utils.file_utils import validate_calibration_json, extract_standards_from_json, import_calibration_data, export_calibration_data
from ui.plot import plot_calibration_curve, plot_residuals


def render_calibration_tabs(preprocessed_data):
    """
    Render the calibration and quantification tabs.
    
    Returns:
    --------
    None
    """
    # Tabs for different calibration functions
    cal_tabs = st.tabs(["Calibration Setup", "Calibration Curves", "Export/Import"])
    
    # Tab 1: Calibration Setup
    with cal_tabs[0]:
        render_calibration_setup()
    
    # Tab 2: Calibration Curves
    with cal_tabs[1]:
        render_calibration_curves()
    
    # Tab 3: Export/Import
    with cal_tabs[2]:
        render_export_import()

def render_calibration_setup():
    """
    Render the calibration setup UI for creating calibration curves.
    
    Returns:
    --------
    None
    """
    st.write("Set up calibration standards by assigning concentrations to peaks in samples.")
    
    # Get all peak groups for selection
    peak_groups = []
    group_names = []
    
    # Only attempt to find groups if we have some peaks
    if any(len(peaks) > 0 for peaks in st.session_state.selected_peaks.values()):
        # Collect all peaks 
        all_peaks = []
        for chrom_id, peaks in st.session_state.selected_peaks.items():
            for peak in peaks:
                peak_info = {
                    'chromatogram_id': chrom_id,
                    'chromatogram_name': st.session_state.chromatograms[chrom_id]['name'],
                    'peak_id': peak['id'],
                    'peak_name': peak.get('name', f"Peak {peak['id']}"),
                    'midpoint': peak['Midpoint (min)'],
                    'area': peak['Area (a.u.·min)'],
                }
                all_peaks.append(peak_info)
        
        # Group peaks by retention time
        peak_groups = group_peaks_by_retention_time(all_peaks)
        
        # Create readable names for each peak group
        for i, group in enumerate(peak_groups):
            avg_time = sum(p['midpoint'] for p in group) / len(group)
            
            # Use consistent peak name if all peaks in the group have the same name
            peak_names = set(p['peak_name'] for p in group)
            if len(peak_names) == 1:
                group_name = next(iter(peak_names))
            else:
                # Otherwise use generic name with retention time
                group_name = f"Peak Group at {avg_time:.2f} min"
            
            group_names.append(group_name)
    
    # Select a peak group for calibration
    if group_names:
        # Add option for "Select a peak group..."
        group_options = ["Select a peak group..."] + group_names
        
        selected_group_name = st.selectbox(
            "Peak Group for Calibration",
            options=group_options
        )
        
        if selected_group_name != "Select a peak group...":
            # Get the index of the selected group
            group_idx = group_names.index(selected_group_name)
            selected_group = peak_groups[group_idx]
            
            # Display the samples in this group
            st.write("**Samples containing this peak:**")
            for peak in selected_group:
                st.write(f"- {peak['chromatogram_name']} (RT: {peak['midpoint']:.2f} min, Area: {peak['area']:.2f} a.u.·min)")
            
            # Create a unique ID for this group based on average retention time
            avg_rt = sum(p['midpoint'] for p in selected_group) / len(selected_group)
            group_id = f"group_{avg_rt:.2f}"
            
            # Set up the calibration for this group
            st.write("---")
            st.write("**Calibration Settings**")
            
            col1, col2 = st.columns(2)
            
            with col1:
                # Model type selection
                model_type = st.radio(
                    "Calibration Model", 
                    ["Linear", "Quadratic", "Power Law"],
                    index=["Linear", "Quadratic", "Power Law"].index(
                        st.session_state.calibration_data.get('model_type', 'Linear').capitalize()
                    )
                )
                
                # Update model type in session state
                st.session_state.calibration_data['model_type'] = model_type.lower()
                
                # Force through zero option
                force_zero = st.checkbox(
                    "Force through zero", 
                    value=st.session_state.calibration_data.get('force_zero', False)
                )
                
                # Update force_zero in session state
                st.session_state.calibration_data['force_zero'] = force_zero
                
                # Show the formula based on selected model
                st.write("**Model Equation:**")
                if model_type == "Linear":
                    formula = "y = mx + b" if not force_zero else "y = mx"
                elif model_type == "Quadratic":
                    formula = "y = ax² + bx + c" if not force_zero else "y = ax² + bx"
                else:  # Power Law
                    formula = "y = ax^b"
                
                st.write(f"_{formula}_")
                
                # Add calibration name input field
                cal_name = st.text_input(
                    "Calibration Name", 
                    value=st.session_state.calibration_data.get('standards', {}).get(group_id, {}).get('name', selected_group_name),
                    key=f"cal_name_{group_id}"
                )
                
                # Concentration units selection
                units = st.selectbox(
                    "Concentration Units", 
                    ["µg/mL", "mg/mL", "µM", "mM", "mg/L"],
                    index=["µg/mL", "mg/mL", "µM", "mM", "mg/L"].index(
                        st.session_state.calibration_data.get('units', 'µg/mL')
                    )
                )
                # Update units in session state
                st.session_state.calibration_data['units'] = units
            
            with col2:
                # Initialize the standards for this group if not present
                if group_id not in st.session_state.calibration_data['standards']:
                    st.session_state.calibration_data['standards'][group_id] = {'name': cal_name}
                else:
                    st.session_state.calibration_data['standards'][group_id]['name'] = cal_name
                
                # Sample assignment - which samples are standards and their concentrations
                st.write("**Assign Standard Concentrations:**")
                
                # For each chromatogram in the group, allow setting a standard concentration
                for peak in selected_group:
                    chrom_id = peak['chromatogram_id']
                    chrom_name = peak['chromatogram_name']
                    
                    # Check if we already have a concentration for this chromatogram
                    default_value = ""
                    if str(chrom_id) in st.session_state.calibration_data['standards'][group_id]:
                        default_value = str(st.session_state.calibration_data['standards'][group_id][str(chrom_id)])
                    
                    # Input field for concentration
                    conc_str = st.text_input(
                        f"Concentration for {chrom_name} ({units})", 
                        value=default_value,
                        key=f"conc_{group_id}_{chrom_id}"
                    )
                    
                    # Update the concentration in the session state
                    try:
                        if conc_str:
                            conc = float(conc_str)
                            st.session_state.calibration_data['standards'][group_id][str(chrom_id)] = conc
                        else:
                            # If the field is empty, remove this chromatogram from standards
                            if str(chrom_id) in st.session_state.calibration_data['standards'][group_id]:
                                del st.session_state.calibration_data['standards'][group_id][str(chrom_id)]
                    except ValueError:
                        st.error(f"Please enter a valid number for {chrom_name}")
            
            # Button to generate or update the calibration curve
            if st.button("Generate Calibration Curve", key=f"gen_cal_{group_id}"):
                # Get only the concentration values (skip the 'name' field)
                valid_standards = {k: v for k, v in st.session_state.calibration_data['standards'][group_id].items() 
                                if k != 'name' and isinstance(v, (int, float))}
                
                # Check if we have enough data points
                if len(valid_standards) < 2:
                    st.error("Please assign concentrations to at least 2 samples.")
                elif model_type == "Quadratic" and len(valid_standards) < 3 and not force_zero:
                    st.error("Quadratic fit requires at least 3 points (or 2 points with 'Force through zero').")
                else:
                    # Collect x and y data for calibration
                    x_data = []  # Concentrations
                    y_data = []  # Areas
                    sample_names = []  # Sample names
                    
                    for chrom_id_str, concentration in valid_standards.items():
                        chrom_id = int(chrom_id_str)
                        
                        # Find the peak in this group from this chromatogram
                        matching_peak = next((p for p in selected_group if p['chromatogram_id'] == chrom_id), None)
                        
                        if matching_peak:
                            x_data.append(concentration)
                            y_data.append(matching_peak['area'])
                            sample_names.append(matching_peak['chromatogram_name'])
                    
                    # Fit calibration model
                    if x_data and y_data:
                        cal_model = fit_calibration_model(
                            x_data, 
                            y_data, 
                            model_type=model_type.lower(), 
                            force_zero=force_zero
                        )
                        
                        # Add metadata
                        cal_model['name'] = cal_name
                        cal_model['rt'] = avg_rt
                        cal_model['units'] = units
                        
                        # Store calibration model
                        st.session_state.calibration_models[group_id] = cal_model
                        
                        st.success(f"Calibration curve generated for {cal_name}. View it in the 'Calibration Curves' tab.")
                        st.session_state.force_redraw = True
    else:
        st.info("No peak groups found. Add peaks to multiple samples first.")

def render_calibration_curves():
    """
    Render the calibration curves UI for viewing and using calibration models.
    
    Returns:
    --------
    None
    """
    st.write("View and use calibration curves for quantification.")
    
    # Check if we have any calibration data
    has_standards = len(st.session_state.calibration_data['standards']) > 0
    has_models = len(st.session_state.calibration_models) > 0
    
    if not has_standards and not has_models:
        st.info("No calibration curves have been set up yet. Go to the 'Calibration Setup' tab to create one or import existing curves.")
    else:
        # List all calibrated peak groups
        calibrated_groups = []
        
        # First, add any models that exist in calibration_models
        for group_id, model in st.session_state.calibration_models.items():
            calibrated_groups.append({
                'id': group_id,
                'name': model['name'],
                'rt': model['rt'],
                'type': 'model',  # Mark as a model type
                'model': model    # Store the full model
            })
        
        # Check for standard sets that might need calculation
        if has_standards:
            # Collect all peaks 
            all_peaks = []
            for chrom_id, peaks in st.session_state.selected_peaks.items():
                for peak in peaks:
                    peak_info = {
                        'chromatogram_id': chrom_id,
                        'chromatogram_name': st.session_state.chromatograms[chrom_id]['name'],
                        'peak_id': peak['id'],
                        'peak_name': peak.get('name', f"Peak {peak['id']}"),
                        'midpoint': peak['Midpoint (min)'],
                        'area': peak['Area (a.u.·min)'],
                    }
                    all_peaks.append(peak_info)
            
            # Group peaks by retention time
            peak_groups = group_peaks_by_retention_time(all_peaks)
            
            for group_id, standards_data in st.session_state.calibration_data['standards'].items():
                # Skip if we already have a model for this group
                if group_id in st.session_state.calibration_models:
                    continue
                    
                # Skip entries that don't have concentration values (only have name)
                concentration_values = {k: v for k, v in standards_data.items() 
                                    if k != 'name' and isinstance(v, (int, float))}
                
                if len(concentration_values) >= 2:  # Only include groups with at least 2 standards
                    # Extract average retention time from group_id
                    try:
                        avg_rt = float(group_id.split('_')[1])
                        
                        # Find a matching peak group by retention time
                        matching_group = None
                        for i, group in enumerate(peak_groups):
                            group_avg_rt = sum(p['midpoint'] for p in group) / len(group)
                            if abs(group_avg_rt - avg_rt) < 0.01:  # Within 0.01 min
                                matching_group = group
                                break
                        
                        if matching_group:
                            # Use the custom name or group name
                            peak_names = set(p['peak_name'] for p in matching_group)
                            if len(peak_names) == 1:
                                group_name = next(iter(peak_names))
                            else:
                                group_name = f"Peak Group at {avg_rt:.2f} min"
                                
                            display_name = standards_data.get('name', group_name)
                            
                            calibrated_groups.append({
                                'id': group_id,
                                'name': display_name,
                                'rt': avg_rt,
                                'type': 'standards',  # Mark as standards type
                                'standards': concentration_values,
                                'matching_group': matching_group
                            })
                    except (IndexError, ValueError):
                        # Skip groups with invalid IDs
                        pass
        
        if not calibrated_groups:
            st.info("No complete calibration curves found. Make sure to assign at least 2 concentration values in the 'Calibration Setup' tab or import calibration data.")
        else:
            # Select a calibration curve to view
            cal_options = [g['name'] for g in calibrated_groups]
            selected_cal = st.selectbox("Select Calibration Curve", options=cal_options)
            
            # Find the selected calibration group
            selected_cal_group = next(g for g in calibrated_groups if g['name'] == selected_cal)
            
            # Add a toggle for showing current chromatogram points
            show_current_points = st.checkbox("Show current chromatogram points on curve", value=True)
            
            # Get the group ID
            group_id = selected_cal_group['id']
            
            # In the calibration curve plotting section, plot the appropriate curve
            if selected_cal_group['type'] == 'model':
                
                # For existing models
                render_existing_calibration_model(selected_cal_group, show_current_points)

                # Add note about current settings
                st.subheader("Peak Detection Settings")

                with st.container():
                    # Add a light gray background to simulate an expander look
                    st.markdown("""
                    <style>
                    .calibration-settings {
                        background-color: #f0f2f6;
                        border-radius: 5px;
                        padding: 10px;
                        margin-bottom: 10px;
                    }
                    </style>
                    """, unsafe_allow_html=True)
                    
                    st.markdown('<div class="calibration-settings">', unsafe_allow_html=True)

            else:
                # For new standards that need a model calculated
                render_new_calibration_model(selected_cal_group, show_current_points)



def render_existing_calibration_model(selected_cal_group, show_current_points):
    """
    Render an existing calibration model.
    
    Parameters:
    -----------
    selected_cal_group : dict
        Dictionary containing selected calibration group info
    show_current_points : bool
        Whether to show current samples on the plot
        
    Returns:
    --------
    None
    """
    model = selected_cal_group['model']
    group_id = selected_cal_group['id']
    predict_area = model.get('predict_area', lambda x: x)
    predict_concentration = model.get('predict_concentration', lambda x: x)
    
    # Get model parameters and statistics
    model_type = model['model_type']
    force_zero = model['force_zero']
    units = model['units']
    r_squared = model['r_squared']
    formula_text = model['formula'].replace("y =", "Area =").replace("x", "Concentration")
    parameters = model.get('parameters', {})
    
    # Get the standards from both possible locations
    standards = model.get('standards', {})
    if not standards and group_id in st.session_state.calibration_data.get('standards', {}):
        standards = {k: v for k, v in st.session_state.calibration_data['standards'][group_id].items() 
                    if k != 'name' and isinstance(v, (int, float))}
    
    # Create calibration data points
    cal_x_data = []
    cal_y_data = []
    cal_sample_names = []
    
    # Process standards directly from imported data
    for sample_id, concentration in standards.items():
        if isinstance(concentration, (int, float)):
            # Try to find the actual area from a matching peak if available
            area_found = False
            
            try:
                # Check if this is a chromatogram ID in our current session
                chrom_id = int(sample_id)
                if chrom_id in st.session_state.chromatograms:
                    chrom_name = st.session_state.chromatograms[chrom_id]['name']
                    
                    # Look for a peak in this chromatogram that matches the RT
                    if chrom_id in st.session_state.selected_peaks:
                        for peak in st.session_state.selected_peaks[chrom_id]:
                            if abs(peak['Midpoint (min)'] - model['rt']) < 0.2:
                                # Use the actual measured area
                                actual_area = peak['Area (a.u.·min)']
                                cal_x_data.append(concentration)
                                cal_y_data.append(actual_area)
                                cal_sample_names.append(f"{chrom_name} (measured)")
                                area_found = True
                                break
            except (ValueError, TypeError):
                # Not a valid chromatogram ID or peak not found
                pass
            
            # If we couldn't find actual area data, use the model to calculate expected area
            if not area_found:
                area = predict_area(concentration)
                cal_x_data.append(concentration)
                cal_y_data.append(area)
                
                # Create a nice sample name
                try:
                    chrom_id = int(sample_id)
                    if chrom_id in st.session_state.chromatograms:
                        chrom_name = st.session_state.chromatograms[chrom_id]['name']
                    else:
                        chrom_name = f"Standard {sample_id}"
                except (ValueError, TypeError):
                    chrom_name = f"Standard {sample_id}"
                    
                cal_sample_names.append(f"{chrom_name} (from model)")
    
    # Find current peaks in all active chromatograms that match the retention time
    current_areas = []
    current_concs = []
    current_sample_names = []
    
    if show_current_points:
        # Loop through all chromatograms
        for chrom_id, chrom_data in st.session_state.chromatograms.items():
            # Skip if has no peaks
            if chrom_id not in st.session_state.selected_peaks:
                continue
            
            # Find matching peaks by retention time
            for peak in st.session_state.selected_peaks[chrom_id]:
                if abs(peak['Midpoint (min)'] - model['rt']) < 0.2:
                    # Found a matching peak
                    area = peak['Area (a.u.·min)']
                    
                    # Calculate concentration using the calibration curve
                    concentration = predict_concentration(area)
                    
                    # Check if this sample was already in the calibration standards
                    if (str(chrom_id) in st.session_state.calibration_data.get('standards', {}).get(group_id, {}) and 
                        str(chrom_id) != 'name'):
                        # This is a calibration standard, skip it
                        continue
                    
                    # Add to our lists of current samples
                    current_areas.append(area)
                    current_concs.append(concentration)
                    current_sample_names.append(chrom_data['name'])
    
    # Create x values for the curve
    if cal_x_data:
        x_range = max(cal_x_data) - min(cal_x_data)
        x_min = max(0, min(cal_x_data) - 0.1 * x_range)
        x_max = max(cal_x_data) + 0.1 * x_range
        x_curve = np.linspace(x_min, x_max, 100)
    else:
        x_curve = np.linspace(0, 10, 100)  # Default range
    
    # Generate y values for the curve
    y_curve = np.array([predict_area(x) for x in x_curve])
    
    # Create current points dictionary
    current_points = None
    if current_areas:
        current_points = {
            'areas': current_areas,
            'concentrations': current_concs,
            'sample_names': current_sample_names
        }
    
    # Create model info dictionary
    model_info = {
        'name': model['name'],
        'formula': formula_text,
        'r_squared': r_squared,
        'std_error': model.get('std_error', 0)
    }
    
    # Plot calibration curve
    fig = plot_calibration_curve(
        cal_x_data, cal_y_data, cal_sample_names, 
        x_curve, y_curve, 
        current_points, model_info, units
    )
    
    # Display the plot
    st.plotly_chart(fig, use_container_width=True)
    
    # Show calibration standards table
    if cal_x_data:
        st.subheader("Calibration Standards")
        
        # Create a dataframe for the calibration standards
        cal_data = []
        for i, (x, y, sample) in enumerate(zip(cal_x_data, cal_y_data, cal_sample_names)):
            predicted = predict_area(x)
            residual = y - predicted
            percent_error = (residual / y) * 100 if y != 0 else 0
            
            cal_data.append({
                "Standard": sample,
                f"Concentration ({units})": x,
                "Area (a.u.·min)": y,
                "Predicted Area": predicted,
                "Residual": residual,
                "% Error": percent_error
            })
        
        # Display as dataframe
        cal_df = pd.DataFrame(cal_data)
        st.dataframe(cal_df)
        
        # Download button for calibration data
        csv = cal_df.to_csv(index=False)
        st.download_button(
            label=f"Download Calibration Data as CSV",
            data=csv,
            file_name=f"calibration_{selected_cal_group['name'].replace(' ', '_')}.csv",
            mime="text/csv",
        )
        
        # Show residuals plot (optional)
        if st.checkbox("Show Residuals Plot", value=False):
            fig_residuals = plot_residuals(cal_x_data, cal_y_data, predict_area, cal_sample_names, units)
            st.plotly_chart(fig_residuals, use_container_width=True)

def render_new_calibration_model(selected_cal_group, show_current_points):
    """
    Render a new calibration model from standards data.
    
    Parameters:
    -----------
    selected_cal_group : dict
        Dictionary containing selected calibration group info
    show_current_points : bool
        Whether to show current samples on the plot
        
    Returns:
    --------
    None
    """
    group_id = selected_cal_group['id']
    standards = selected_cal_group['standards']
    matching_group = selected_cal_group['matching_group']
    
    # Get model settings from global settings
    model_type = st.session_state.calibration_data['model_type']
    force_zero = st.session_state.calibration_data['force_zero']
    units = st.session_state.calibration_data['units']
    
    # Create x and y data for calibration plot
    x_data = []
    y_data = []
    sample_names = []
    
    for chrom_id_str, concentration in standards.items():
        chrom_id = int(chrom_id_str)
        
        # Find the peak in this chromatogram that belongs to the group
        matching_peak = next((p for p in matching_group if p['chromatogram_id'] == chrom_id), None)
        
        if matching_peak:
            x_data.append(concentration)
            y_data.append(matching_peak['area'])
            sample_names.append(matching_peak['chromatogram_name'])
    
    # Sort by concentration
    if x_data and y_data and sample_names:
        sorted_data = sorted(zip(x_data, y_data, sample_names))
        x_data = [d[0] for d in sorted_data]
        y_data = [d[1] for d in sorted_data]
        sample_names = [d[2] for d in sorted_data]
    
    # Fit the calibration model if we have enough data
    if len(x_data) >= 2:
        cal_model = fit_calibration_model(
            x_data, 
            y_data, 
            model_type=model_type.lower(), 
            force_zero=force_zero
        )
        
        # Add metadata
        cal_model['name'] = selected_cal_group['name']
        cal_model['rt'] = selected_cal_group['rt']
        cal_model['units'] = units
        
        # Extract functions
        predict_area = cal_model['predict_area']
        predict_concentration = cal_model['predict_concentration']
        r_squared = cal_model['r_squared']
        formula_text = cal_model['formula'].replace("y =", "Area =").replace("x", "Concentration")
        
        # Find current peaks in all active chromatograms that match the retention time
        current_areas = []
        current_concs = []
        current_sample_names = []
        
        if show_current_points:
            # Loop through all chromatograms
            for chrom_id, chrom_data in st.session_state.chromatograms.items():
                # Skip if has no peaks or if it's a calibration standard
                if (chrom_id not in st.session_state.selected_peaks or 
                    str(chrom_id) in standards):
                    continue
                
                # Find matching peaks by retention time
                for peak in st.session_state.selected_peaks[chrom_id]:
                    if abs(peak['Midpoint (min)'] - selected_cal_group['rt']) < 0.2:
                        # Found a matching peak
                        area = peak['Area (a.u.·min)']
                        
                        # Calculate concentration using the calibration curve
                        concentration = predict_concentration(area)
                        
                        # Add to our lists of current samples
                        current_areas.append(area)
                        current_concs.append(concentration)
                        current_sample_names.append(chrom_data['name'])
        
        # Create x values for the curve
        if x_data:
            x_range = max(x_data) - min(x_data)
            x_min = max(0, min(x_data) - 0.1 * x_range)
            x_max = max(x_data) + 0.1 * x_range
            x_curve = np.linspace(x_min, x_max, 100)
        else:
            x_curve = np.linspace(0, 10, 100)  # Default range
        
        # Generate y values for the curve
        y_curve = np.array([predict_area(x) for x in x_curve])
        
        # Create current points dictionary
        current_points = None
        if current_areas:
            current_points = {
                'areas': current_areas,
                'concentrations': current_concs,
                'sample_names': current_sample_names
            }
        
        # Create model info dictionary
        model_info = {
            'name': selected_cal_group['name'],
            'formula': formula_text,
            'r_squared': r_squared,
            'std_error': cal_model.get('std_error', 0)
        }
        
        # Plot calibration curve
        fig = plot_calibration_curve(
            x_data, y_data, sample_names, 
            x_curve, y_curve, 
            current_points, model_info, units
        )
        
        # Display the plot
        st.plotly_chart(fig, use_container_width=True)
        
        # Show calibration standards table
        if x_data:
            st.subheader("Calibration Standards")
            
            # Create a dataframe for the calibration standards
            cal_data = []
            for i, (x, y, sample) in enumerate(zip(x_data, y_data, sample_names)):
                predicted = predict_area(x)
                residual = y - predicted
                percent_error = (residual / y) * 100 if y != 0 else 0
                
                cal_data.append({
                    "Standard": sample,
                    f"Concentration ({units})": x,
                    "Area (a.u.·min)": y,
                    "Predicted Area": predicted,
                    "Residual": residual,
                    "% Error": percent_error
                })
            
            # Display as dataframe
            cal_df = pd.DataFrame(cal_data)
            st.dataframe(cal_df)
            
            # Download button for calibration data
            csv = cal_df.to_csv(index=False)
            st.download_button(
                label=f"Download Calibration Data as CSV",
                data=csv,
                file_name=f"calibration_{selected_cal_group['name'].replace(' ', '_')}.csv",
                mime="text/csv",
            )

            # Show residuals plot (optional)
            if st.checkbox("Show Residuals Plot", value=False):
                fig_residuals = plot_residuals(x_data, y_data, predict_area, sample_names, units)
                st.plotly_chart(fig_residuals, use_container_width=True)

def render_export_import():
    """
    Render the export/import UI for calibration data.
    
    Returns:
    --------
    None
    """
    st.write("Export or import calibration settings and curves.")
    
    # Export section
    st.subheader("Export Calibration Data")
    
    if not st.session_state.calibration_data['standards']:
        st.info("No calibration data available to export.")
    else:
        # Export button
        json_data = export_calibration_data()
        st.download_button(
            label="Download Complete Calibration Data",
            data=json_data,
            file_name="chromatogram_calibration_data.json",
            mime="application/json",
        )
        
        st.write("This file contains all calibration settings, model parameters, and standard data points.")

    # Import section
    st.subheader("Import Calibration Data")
    uploaded_file = st.file_uploader("Upload Calibration JSON", type=['json'], key="export_import_uploader")

    if uploaded_file is not None:
        try:
            # Read the file
            json_data = uploaded_file.read().decode('utf-8-sig')
            
            if not json_data.strip():  # Check if the file is empty after decoding
                st.error("The file is empty!")
            else:
                # Parse the JSON data
                imported_data = json.loads(json_data)

                # Validate the imported data
                is_valid, message = validate_calibration_json(imported_data)
                if not is_valid:
                    st.error(f"Invalid calibration file: {message}")
                else:
                    st.success("Valid calibration file detected!")
                    
                    # Show import options
                    st.write("**Imported Calibration Settings:**")
                    st.write(f"- Export Date: {imported_data.get('export_date', 'Unknown')}")
                    st.write(f"- App Version: {imported_data.get('app_version', 'Unknown')}")
                    
                    # Check what's in the file
                    has_models = 'calibration_models' in imported_data and len(imported_data['calibration_models']) > 0
                    has_standards = 'standards' in imported_data and len(imported_data['standards']) > 0
                    
                    if has_models:
                        st.write(f"- Number of Calibration Models: {len(imported_data['calibration_models'])}")
                        
                        # List the models
                        st.write("**Calibration Models:**")
                        for group_id, model in imported_data['calibration_models'].items():
                            st.write(f"- {model.get('name', 'Unnamed')} (RT: {model.get('rt', 0):.2f} min, {model.get('model_type', 'unknown').capitalize()} model, R²: {model.get('r_squared', 0):.4f})")
                    
                    elif has_standards:
                        st.write(f"- Number of Standard Sets: {len(imported_data['standards'])}")
                        
                        # List the standard sets
                        st.write("**Standard Sets:**")
                        for group_id, standards in imported_data['standards'].items():
                            name = standards.get('name', f"Group {group_id}")
                            st.write(f"- {name}")
                    
                    # Import button
                    import_mode = st.radio(
                        "Import Mode",
                        ["Merge with existing", "Replace existing"],
                        index=0,
                        key="import_mode"
                    )
                    
                    if st.button("Import Calibration Data", key="import_button"):
                        # Import the data
                        success, message = import_calibration_data(imported_data, mode=import_mode.lower().split()[0])
                        if success:
                            st.success(message)
                            st.session_state.force_redraw = True
                        else:
                            st.error(message)
        
        except Exception as e:
            st.error(f"Error importing calibration file: {str(e)}")

