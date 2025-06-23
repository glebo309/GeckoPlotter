import json
import pandas as pd
import streamlit as st
import copy
from models.calibration import create_calibration_functions

def validate_calibration_json(json_data):
    """
    Test and validate an imported JSON calibration file.
    
    Parameters:
    -----------
    json_data : dict
        Parsed JSON data to validate
        
    Returns:
    --------
    tuple
        (is_valid, message) where is_valid is a boolean and message is a string
    """
    # Check basic required structure
    if 'standards' not in json_data:
        return False, "Missing 'standards' field"
        
    # Check if there are any calibration models
    has_models = 'calibration_models' in json_data and len(json_data['calibration_models']) > 0
    
    # Validate models if present
    if has_models:
        for group_id, model in json_data['calibration_models'].items():
            required_fields = ['name', 'rt', 'model_type', 'formula', 'units']
            for field in required_fields:
                if field not in model:
                    return False, f"Model {group_id} missing required field: {field}"
            
            # Check parameters based on model type
            if 'parameters' not in model:
                return False, f"Model {group_id} missing parameters"
                
            params = model['parameters']
            model_type = model['model_type']
            
            if model_type == 'linear':
                if 'slope' not in params:
                    return False, f"Linear model {group_id} missing slope parameter"
            elif model_type == 'quadratic':
                for p in ['a', 'b']:  # c might be 0 for force_zero
                    if p not in params:
                        return False, f"Quadratic model {group_id} missing parameter: {p}"
            elif model_type == 'power law':
                for p in ['a', 'b']:
                    if p not in params:
                        return False, f"Power law model {group_id} missing parameter: {p}"
    
    # Validate standards
    for group_id, standards in json_data['standards'].items():
        if 'name' not in standards:
            return False, f"Standards group {group_id} missing name"
        
        # Check if there are at least some concentration values (other than name)
        conc_values = {k: v for k, v in standards.items() if k != 'name' and isinstance(v, (int, float))}
        if len(conc_values) < 1:
            return False, f"Standards group {group_id} has no concentration values"
    
    return True, "Valid calibration data"

def extract_standards_from_json(json_data, group_id):
    """
    Extract standard concentrations from JSON data.
    
    Parameters:
    -----------
    json_data : dict
        Parsed JSON data
    group_id : str
        Group ID to extract standards for
        
    Returns:
    --------
    dict
        Dictionary of standards
    """
    standards = {}
    
    # Check if the group exists in standards
    if 'standards' in json_data and group_id in json_data['standards']:
        standards_data = json_data['standards'][group_id]
        
        # Extract standard concentrations (skip the name field)
        for k, v in standards_data.items():
            if k != 'name' and isinstance(v, (int, float)):
                standards[k] = v
                
    # Also check if there are standards in the calibration model
    if ('calibration_models' in json_data and 
        group_id in json_data['calibration_models'] and
        'standards' in json_data['calibration_models'][group_id]):
        
        model_standards = json_data['calibration_models'][group_id]['standards']
        for k, v in model_standards.items():
            if isinstance(v, (int, float)):
                standards[k] = v
                
    return standards

def import_calibration_data(data, mode="merge"):
    """
    Import calibration data from a JSON object.
    
    Parameters:
    -----------
    data : dict
        Dictionary containing calibration data
    mode : str
        Import mode: 'merge' or 'replace'
        
    Returns:
    --------
    tuple
        (success, message)
    """
    try:
        # Start with fresh data if replace mode
        if mode == "replace":
            st.session_state.calibration_data = {
                'standards': {},
                'model_type': 'linear',
                'force_zero': False,
                'units': 'µg/mL'
            }
            st.session_state.calibration_models = {}
        
        # Process the standards from the imported data
        if "standards" in data:
            for group_id, standard_data in data["standards"].items():
                # Extract the name and raw_data
                name = standard_data.get("name", f"Group {group_id}")
                rt = standard_data.get("rt", 0.0)
                units = standard_data.get("units", "µg/mL")
                
                # Update calibration data units if present
                if "units" in standard_data:
                    st.session_state.calibration_data["units"] = standard_data["units"]
                
                # Create a new standard in calibration_data if it doesn't exist
                if group_id not in st.session_state.calibration_data["standards"]:
                    st.session_state.calibration_data["standards"][group_id] = {"name": name}
                
                # Process raw_data if available
                if "raw_data" in standard_data:
                    raw_data = standard_data["raw_data"]
                    
                    # Extract concentrations and areas
                    x_data = []  # Concentrations
                    y_data = []  # Areas
                    sample_names = []  # Sample names
                    
                    for item in raw_data:
                        x_data.append(item.get("concentration", 0))
                        y_data.append(item.get("area", 0))
                        sample_names.append(item.get("sample_name", "Unknown"))
                        
                        # Try to extract sample ID from name and add to calibration_data standards
                        try:
                            sample_id = item.get("sample_name", "").split(" ")[1]
                            if sample_id.isdigit():
                                st.session_state.calibration_data["standards"][group_id][sample_id] = item.get("concentration", 0)
                        except (IndexError, ValueError):
                            # If we can't extract a valid ID, use a timestamp as unique ID
                            import time
                            unique_id = str(int(time.time() * 1000))[-8:]
                            st.session_state.calibration_data["standards"][group_id][unique_id] = item.get("concentration", 0)
                    
                    # Create a calibration model from raw data
                    if len(x_data) >= 2:
                        # Import the calibration model function
                        from models.calibration import fit_calibration_model
                        
                        # Set model type (default to linear)
                        model_type = standard_data.get("model_type", "linear")
                        force_zero = standard_data.get("force_zero", False)
                        
                        # Fit calibration model
                        try:
                            cal_model = fit_calibration_model(
                                x_data, 
                                y_data, 
                                model_type=model_type,
                                force_zero=force_zero
                            )
                            
                            # Add metadata
                            cal_model['name'] = name
                            cal_model['rt'] = rt
                            cal_model['units'] = units
                            cal_model['standards'] = {str(i): x for i, x in enumerate(x_data, 1)}
                            
                            # Store calibration model
                            st.session_state.calibration_models[group_id] = cal_model
                        except Exception as e:
                            return False, f"Error fitting calibration model: {str(e)}"
        
        # Import calibration models directly if available
        if "calibration_models" in data:
            for group_id, model_data in data["calibration_models"].items():
                # If we already created this model from raw_data, skip
                if group_id in st.session_state.calibration_models:
                    continue
                    
                # Otherwise add it directly
                st.session_state.calibration_models[group_id] = model_data
                
                # The functions can't be serialized, so recreate them
                if "parameters" in model_data:
                    params = model_data["parameters"]
                    model_type = model_data.get("model_type", "linear")
                    
                    # Recreate predict_area function based on model type
                    if model_type == "linear":
                        m = params.get("m", 1.0)
                        b = params.get("b", 0.0)
                        
                        def predict_area(conc, m=m, b=b):
                            return m * conc + b
                            
                        def predict_concentration(area, m=m, b=b):
                            if m == 0:
                                return 0
                            return (area - b) / m
                            
                    elif model_type == "quadratic":
                        a = params.get("a", 0.0)
                        b = params.get("b", 1.0)
                        c = params.get("c", 0.0)
                        
                        def predict_area(conc, a=a, b=b, c=c):
                            return a * conc**2 + b * conc + c
                            
                        def predict_concentration(area, a=a, b=b, c=c):
                            # Solve quadratic equation: ax^2 + bx + (c-area) = 0
                            import numpy as np
                            if a == 0:
                                if b == 0:
                                    return 0
                                return (area - c) / b
                            
                            # Calculate discriminant
                            discriminant = b**2 - 4*a*(c-area)
                            if discriminant < 0:
                                return 0
                                
                            # Return the positive root
                            return (-b + np.sqrt(discriminant)) / (2*a)
                    
                    elif model_type == "power law":
                        a = params.get("a", 1.0)
                        b = params.get("b", 1.0)
                        
                        def predict_area(conc, a=a, b=b):
                            return a * conc**b
                            
                        def predict_concentration(area, a=a, b=b):
                            if a == 0 or b == 0:
                                return 0
                            return (area / a)**(1/b)
                    
                    # Add functions to the model
                    st.session_state.calibration_models[group_id]["predict_area"] = predict_area
                    st.session_state.calibration_models[group_id]["predict_concentration"] = predict_concentration
        
        return True, "Calibration data imported successfully!"
    except Exception as e:
        return False, f"Error importing data: {str(e)}"

def validate_calibration_json(data):
    """
    Validate the imported calibration JSON data.
    
    Parameters:
    -----------
    data : dict
        Dictionary containing calibration data
        
    Returns:
    --------
    tuple
        (is_valid, message) - Validation result and message
    """
    try:
        # Check if it's a dictionary
        if not isinstance(data, dict):
            return False, "Imported data is not a valid JSON object"
        
        # Check for required fields or structures
        has_standards = 'standards' in data and isinstance(data['standards'], dict)
        has_models = 'calibration_models' in data and isinstance(data['calibration_models'], dict)
        
        # Either standards or models must be present
        if not (has_standards or has_models):
            return False, "No valid calibration standards or models found in the file"
        
        # If we have models, validate their structure
        if has_models:
            for group_id, model in data['calibration_models'].items():
                # Check for required model fields
                required_fields = ['name', 'rt', 'model_type']
                for field in required_fields:
                    if field not in model:
                        return False, f"Model '{group_id}' is missing required field '{field}'"
                
                # Check for formula or parameters
                if 'formula' not in model and 'parameters' not in model:
                    return False, f"Model '{group_id}' is missing both 'formula' and 'parameters'"
        
        # If we have standards, validate their structure
        if has_standards:
            for group_id, standards in data['standards'].items():
                # Check if there's at least one concentration value
                has_concentration = False
                for key, value in standards.items():
                    if key != 'name' and isinstance(value, (int, float)):
                        has_concentration = True
                        break
                
                if not has_concentration:
                    return False, f"Standard group '{group_id}' has no concentration values"
        
        return True, "Validation successful"
    
    except Exception as e:
        return False, f"Error validating calibration data: {str(e)}"

def export_calibration_data():
    """
    Export calibration data from session state to JSON.
    
    Returns:
    --------
    str
        JSON string of the calibration data
    """
    # Create a copy of the calibration data to avoid modifying the original
    export_data = copy.deepcopy(st.session_state.calibration_data)
    
    # Add the calibration models (excluding function references)
    export_data['calibration_models'] = {}
    
    # Get selected calibration name for the filename
    selected_cal_name = "chromatogram_calibration_data"
    if st.session_state.calibration_models:
        selected_cal_name = next(iter(st.session_state.calibration_models.values()))['name']
    export_data['selected_name'] = selected_cal_name
    
    for group_id, model in st.session_state.calibration_models.items():
        # Create a copy without the function references
        model_export = {
            'name': model['name'],
            'rt': model['rt'],
            'model_type': model['model_type'],
            'force_zero': model['force_zero'],
            'r_squared': model['r_squared'],
            'formula': model['formula'],
            'units': model['units'],
            'parameters': model.get('parameters', {})
        }
        
        # Store all standard data points if available
        standards_dict = st.session_state.calibration_data['standards'].get(group_id, {})
        
        # Skip trying to access chromatograms by ID, just store the raw data
        model_export['standards'] = {k: v for k, v in standards_dict.items() if k != 'name'}
        
        # Store in export data
        export_data['calibration_models'][group_id] = model_export
    
    # Add additional metadata for export
    export_data['export_date'] = pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')
    export_data['app_version'] = "1.0.0"
    
    # Add peak detection settings used when calibration was created
    export_data['peak_detection_settings'] = copy.deepcopy(st.session_state.settings)
    
    # Convert to JSON
    json_data = json.dumps(export_data, indent=2)
    
    return json_data