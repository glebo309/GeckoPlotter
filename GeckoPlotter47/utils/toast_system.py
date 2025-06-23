# utils/toast_system.py

import time
import uuid
import json
from dash import html, dcc, Input, Output, State, callback, callback_context, ALL


def create_toast_container():
    return html.Div([
        dcc.Store(id="toast-store", data=[]),  # Empty initially
        html.Div(id="toast-container", className="toast-container"),
        dcc.Interval(id="toast-cleanup-interval", interval=500, n_intervals=0)  # More frequent cleanup
    ])


def show_toast(message, toast_type="info", duration=3000):
    """
    Create a toast notification.
    
    Args:
        message: Toast message text
        toast_type: 'success', 'info', 'warning', 'error'
        duration: Duration in milliseconds
    
    Returns:
        Toast data object for the store
    """
    toast_id = str(uuid.uuid4())
    current_time = time.time() * 1000
    
    # Icon mapping
    icons = {
        'success': '✅',
        'info': 'ℹ️',
        'warning': '⚠️',
        'error': '❌'
    }
    
    return {
        'id': toast_id,
        'message': message,
        'type': toast_type,
        'icon': icons.get(toast_type, 'ℹ️'),
        'created_at': current_time,
        'duration': duration,
        'expires_at': current_time + duration,
        'animation_duration': duration / 1000  # Convert to seconds for CSS
    }

def register_toast_callbacks(app):
    """Register all toast-related callbacks."""
    
    # Render toasts
    @app.callback(
        Output("toast-container", "children"),
        Input("toast-store", "data")
    )
    def render_toasts(toast_data):
        if not toast_data:
            return []
        
        current_time = time.time() * 1000
        active_toasts = [t for t in toast_data if t['expires_at'] > current_time]
        
        toast_elements = []
        for toast in active_toasts:
            # Each toast gets the full lifecycle animation
            toast_element = html.Div([
                html.Div([
                    html.Span(toast['icon'], className="toast-icon"),
                    html.Span(toast['message'], className="toast-message"),
                    html.Button("×", 
                        className="toast-close",
                        id={'type': 'toast-close', 'index': toast['id']},
                        **{'data-toast-id': toast['id']}
                    )
                ], className="toast-content")
            ], 
                className=f"toast toast-{toast['type']}",
                id={'type': 'toast', 'index': toast['id']},
                style={
                    'animationName': 'toastLifecycle',
                    'animationDuration': f"{toast['animation_duration']}s",
                    'animationTimingFunction': 'ease',
                    'animationFillMode': 'forwards'
                }
            )
            
            toast_elements.append(toast_element)
        
        return toast_elements
    
    # Auto-cleanup expired toasts
    @app.callback(
        Output("toast-store", "data", allow_duplicate=True),
        Input("toast-cleanup-interval", "n_intervals"),
        State("toast-store", "data"),
        prevent_initial_call=True
    )
    def cleanup_expired_toasts(n_intervals, toast_data):
        if not toast_data:
            return toast_data
        
        current_time = time.time() * 1000
        active_toasts = [t for t in toast_data if t['expires_at'] > current_time]
        
        # Only update if something changed
        if len(active_toasts) != len(toast_data):
            return active_toasts
        
        return toast_data
    
    # Handle manual close
    @app.callback(
        Output("toast-store", "data", allow_duplicate=True),
        Input({'type': 'toast-close', 'index': ALL}, 'n_clicks'),
        State("toast-store", "data"),
        prevent_initial_call=True
    )
    def close_toast_manually(n_clicks, toast_data):
        if not n_clicks or not toast_data:
            return toast_data
        
        ctx = callback_context
        if ctx.triggered:
            # Extract toast ID from the triggered component
            try:
                import json
                button_id = json.loads(ctx.triggered[0]['prop_id'].split('.')[0])
                toast_id = button_id['index']
                
                # Remove the specific toast
                updated_toasts = [t for t in toast_data if t['id'] != toast_id]
                return updated_toasts
                
            except Exception as e:
                print(f"Error closing toast: {e}")
        
        return toast_data

# FIXED: Helper function to prevent duplicates
def add_toast_to_store(current_toasts, message, toast_type="info", duration=3000):
    """
    Helper function to add a new toast to the current toast store data.
    FIXED: Now prevents duplicates and manages the list properly.
    
    Usage in callbacks:
        new_toasts = add_toast_to_store(current_toasts, "Success!", "success")
        return new_toasts
    """
    if current_toasts is None:
        current_toasts = []
    
    # Clean up expired toasts first to prevent accumulation
    current_time = time.time() * 1000
    clean_toasts = [t for t in current_toasts if t['expires_at'] > current_time]
    
    # Create new toast
    new_toast = show_toast(message, toast_type, duration)
    
    # Return clean list + new toast (no duplicates)
    return clean_toasts + [new_toast]