# models/calibration.py

import numpy as np
from scipy.optimize import curve_fit
from scipy import stats

def create_calibration_functions(model_type, params, force_zero=False):
    """
    Create calibration functions from parameters for different model types.
    
    Parameters:
    -----------
    model_type : str
        Type of calibration model ('linear', 'quadratic', or 'power law')
    params : dict
        Parameters for the model
    force_zero : bool, optional
        Whether to force the model through zero (default: False)
        
    Returns:
    --------
    tuple of functions
        (predict_area, predict_concentration) functions
    """
    if model_type == 'linear':
        slope = params.get('slope', 1.0)
        intercept = params.get('intercept', 0.0) if not force_zero else 0.0
        
        def predict_area(concentration):
            return slope * concentration + intercept
        
        def predict_concentration(area):
            return (area - intercept) / slope if slope != 0 else 0
            
    elif model_type == 'quadratic':
        a = params.get('a', 0.0)
        b = params.get('b', 0.0)
        c = params.get('c', 0.0) if not force_zero else 0.0
        
        def predict_area(concentration):
            return a * concentration**2 + b * concentration + c
        
        def predict_concentration(area):
            if a == 0:  # Linear case
                return (area - c) / b if b != 0 else 0
            
            # Quadratic formula: x = (-b ± sqrt(b² - 4a(c - area))) / 2a
            discriminant = b**2 - 4 * a * (c - area)
            if discriminant < 0:
                return 0  # No real solution
            
            # Choose the smallest positive concentration
            conc1 = (-b + np.sqrt(discriminant)) / (2 * a)
            conc2 = (-b - np.sqrt(discriminant)) / (2 * a)
            
            if conc1 > 0 and conc2 > 0:
                return min(conc1, conc2)
            elif conc1 > 0:
                return conc1
            elif conc2 > 0:
                return conc2
            else:
                return 0  # No positive solution
                
    elif model_type == 'power law':
        a = params.get('a', 1.0)
        b = params.get('b', 1.0)
        
        def predict_area(concentration):
            return a * concentration**b
        
        def predict_concentration(area):
            return (area / a)**(1 / b) if a != 0 and b != 0 else 0
            
    else:
        # Default to linear model if unknown type
        def predict_area(concentration):
            return concentration
        
        def predict_concentration(area):
            return area
            
    return predict_area, predict_concentration

def fit_calibration_model(concentrations, areas, model_type='linear', force_zero=False):
    """
    Fit a calibration model to concentration and area data.
    
    Parameters:
    -----------
    concentrations : array-like
        Concentration values
    areas : array-like
        Area values corresponding to concentrations
    model_type : str, optional
        Type of calibration model (default: 'linear')
    force_zero : bool, optional
        Whether to force the model through zero (default: False)
        
    Returns:
    --------
    dict
        Dictionary containing model parameters and statistics
    """
    x_array = np.array(concentrations)
    y_array = np.array(areas)
    
    # Dictionary to store results
    result = {
        'model_type': model_type,
        'force_zero': force_zero,
        'parameters': {},
        'r_squared': 0,
        'formula': ''
    }
    
    if model_type == 'linear':
        if force_zero:
            # Force through zero: y = mx
            slope = np.sum(x_array * y_array) / np.sum(x_array * x_array)
            intercept = 0
            
            # Calculate R²
            y_pred = slope * x_array
            ss_tot = np.sum((y_array - np.mean(y_array))**2)
            ss_res = np.sum((y_array - y_pred)**2)
            r_squared = 1 - (ss_res / ss_tot)
            
            # Store parameters
            result['parameters'] = {'slope': slope, 'intercept': 0}
            result['r_squared'] = r_squared
            result['formula'] = f"y = {slope:.4g}x"
            
        else:
            # Standard linear regression
            slope, intercept, r_value, p_value, std_err = stats.linregress(x_array, y_array)
            
            # Store parameters
            result['parameters'] = {'slope': slope, 'intercept': intercept}
            result['r_squared'] = r_value**2
            result['formula'] = f"y = {slope:.4g}x + {intercept:.4g}"
            result['std_error'] = std_err
            
    elif model_type == 'quadratic':
        if force_zero:
            # Force through zero: y = ax² + bx
            def quad_fit_zero(x, a, b):
                return a * x**2 + b * x
            
            # Fit quadratic model through (0,0)
            params, covariance = curve_fit(quad_fit_zero, x_array, y_array)
            a, b = params
            
            # Predict values
            y_pred = quad_fit_zero(x_array, a, b)
            
            # Calculate R²
            ss_tot = np.sum((y_array - np.mean(y_array))**2)
            ss_res = np.sum((y_array - y_pred)**2)
            r_squared = 1 - (ss_res / ss_tot)
            
            # Store parameters
            result['parameters'] = {'a': a, 'b': b, 'c': 0}
            result['r_squared'] = r_squared
            result['formula'] = f"y = {a:.4g}x² + {b:.4g}x"
            
        else:
            # Full quadratic: y = ax² + bx + c
            def quad_fit(x, a, b, c):
                return a * x**2 + b * x + c
            
            # Initial parameter guess
            init_guess = [0, 1, 0]
            
            # Fit quadratic model
            params, covariance = curve_fit(quad_fit, x_array, y_array, p0=init_guess)
            a, b, c = params
            
            # Predict values
            y_pred = quad_fit(x_array, a, b, c)
            
            # Calculate R²
            ss_tot = np.sum((y_array - np.mean(y_array))**2)
            ss_res = np.sum((y_array - y_pred)**2)
            r_squared = 1 - (ss_res / ss_tot)
            
            # Store parameters
            result['parameters'] = {'a': a, 'b': b, 'c': c}
            result['r_squared'] = r_squared
            result['formula'] = f"y = {a:.4g}x² + {b:.4g}x + {c:.4g}"
            
    elif model_type == 'power law':
        # Power law: y = a * x^b
        def power_law(x, a, b):
            return a * x**b
        
        # Log transform for initial guess
        with np.errstate(divide='ignore', invalid='ignore'):
            log_x = np.log(x_array)
            log_y = np.log(y_array)
            
            # Filter out any NaN or inf values
            valid_indices = ~(np.isnan(log_x) | np.isnan(log_y) | np.isinf(log_x) | np.isinf(log_y))
            
            if np.sum(valid_indices) >= 2:  # Need at least 2 points for regression
                slope, intercept, r_value, p_value, std_err = stats.linregress(
                    log_x[valid_indices], 
                    log_y[valid_indices]
                )
                init_a = np.exp(intercept)
                init_b = slope
            else:
                init_a = 1.0
                init_b = 1.0
        
        # Fit power law model
        try:
            params, covariance = curve_fit(power_law, x_array, y_array, p0=[init_a, init_b])
            a, b = params
            
            # Predict values
            y_pred = power_law(x_array, a, b)
            
            # Calculate R²
            ss_tot = np.sum((y_array - np.mean(y_array))**2)
            ss_res = np.sum((y_array - y_pred)**2)
            r_squared = 1 - (ss_res / ss_tot)
            
            # Store parameters
            result['parameters'] = {'a': a, 'b': b}
            result['r_squared'] = r_squared
            result['formula'] = f"y = {a:.4g}x^{b:.4g}"
            
        except (RuntimeError, ValueError):
            # Fallback to linear model if fitting fails
            slope, intercept, r_value, p_value, std_err = stats.linregress(x_array, y_array)
            
            result['model_type'] = 'linear'  # Override to linear
            result['parameters'] = {'slope': slope, 'intercept': intercept}
            result['r_squared'] = r_value**2
            result['formula'] = f"y = {slope:.4g}x + {intercept:.4g}"
            result['std_error'] = std_err
    
    # Calculate standard error of estimate
    if len(x_array) > 2:
        if 'y_pred' in locals():
            residuals = y_array - y_pred
            result['std_error'] = np.sqrt(np.sum(residuals**2) / (len(x_array) - 2))
    
    # Create prediction functions
    predict_area, predict_concentration = create_calibration_functions(
        result['model_type'], 
        result['parameters'], 
        force_zero
    )
    
    # Add functions to result
    result['predict_area'] = predict_area
    result['predict_concentration'] = predict_concentration
    
    return result

def group_peaks_by_retention_time(all_peaks, time_window=0.2):
    """
    Group peaks from different chromatograms by retention time.
    
    Parameters:
    -----------
    all_peaks : list
        List of peak dictionaries with chromatogram info
    time_window : float, optional
        Time window for grouping peaks (default: 0.2)
        
    Returns:
    --------
    list
        List of peak groups
    """
    # Sort all peaks by midpoint time
    all_peaks.sort(key=lambda p: p['midpoint'])
    
    # Group peaks by proximity (considering them the same compound)
    peak_groups = []
    current_group = []
    
    for peak in all_peaks:
        if not current_group:
            current_group = [peak]
        else:
            # Check if this peak is close to the ones in the current group
            avg_midpoint = sum(p['midpoint'] for p in current_group) / len(current_group)
            if abs(peak['midpoint'] - avg_midpoint) <= time_window:
                # This peak is close enough, add to current group
                current_group.append(peak)
            else:
                # Start a new group
                peak_groups.append(current_group)
                current_group = [peak]
    
    # Add the last group if it exists
    if current_group:
        peak_groups.append(current_group)
    
    return peak_groups