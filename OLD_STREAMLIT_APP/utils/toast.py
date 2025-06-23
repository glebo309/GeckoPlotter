import streamlit as st
import time
import uuid

def init_toast_container():
    """Initialize the toast notification container at app startup."""
    # No longer needed but kept for compatibility
    return st.container()

def show_toast(message, type="info", duration=3):
    """Add a toast message."""
    # Create toast key using the current timestamp for uniqueness
    toast_key = f"toast_{str(uuid.uuid4())}"
    
    # Store in session state with expiration time
    st.session_state[toast_key] = {
        "message": message,
        "type": type,
        "created_at": time.time(),
        "duration": duration
    }
import streamlit as st
import time
import uuid

def init_toast_container():
    """Initialize the toast notification container at app startup."""
    # No longer needed but kept for compatibility
    return st.container()

def show_toast(message, type="info", duration=3):
    """Add a toast message."""
    # Create toast key using the current timestamp for uniqueness
    toast_key = f"toast_{str(uuid.uuid4())}"
    
    # Store in session state with expiration time
    st.session_state[toast_key] = {
        "message": message,
        "type": type,
        "created_at": time.time(),
        "duration": duration
    }
def render_toasts():
    """Render floating toast notifications using CSS animations."""
    # Find all toast keys in session state
    toast_keys = [k for k in st.session_state.keys() if k.startswith("toast_")]
    current_time = time.time()
    
    # Remove toasts that are more than 10 seconds old (cleanup)
    for k in list(toast_keys):  # Use list() to avoid modifying during iteration
        if current_time - st.session_state[k]["created_at"] > 10:
            del st.session_state[k]
    
    # Re-check for remaining toasts
    toast_keys = [k for k in st.session_state.keys() if k.startswith("toast_")]
    
    # If we have no toasts, return early
    if not toast_keys:
        return
    
    # Create CSS with animations
    toast_css = """
    <style>
        .fixed-toast-container {
            position: fixed;
            top: 70px;
            right: 20px;
            z-index: 9999;
            width: 300px;
            pointer-events: none;
        }
        .fixed-toast {
            margin-bottom: 10px;
            padding: 15px;
            border-radius: 6px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.15);
            font-size: 14px;
            pointer-events: auto;
            animation-name: toastLifecycle;
            animation-timing-function: ease;
            animation-fill-mode: forwards;
        }
        .fixed-toast-info {
            background-color: #f0f7ff;
            border-left: 4px solid #3b82f6;
            color: #1e40af;
        }
        .fixed-toast-success {
            background-color: #f0fdf4;
            border-left: 4px solid #22c55e;
            color: #166534;
        }
        .fixed-toast-warning {
            background-color: #fffbeb;
            border-left: 4px solid #f59e0b;
            color: #854d0e;
        }
        .fixed-toast-error {
            background-color: #fef2f2;
            border-left: 4px solid #ef4444;
            color: #991b1b;
        }
        @keyframes toastLifecycle {
            0% { transform: translateX(100%); opacity: 0; }
            10% { transform: translateX(0); opacity: 1; }
            90% { transform: translateX(0); opacity: 1; }
            100% { transform: translateX(30%); opacity: 0; }
        }
    </style>
    """
    
    # Render the CSS
    st.markdown(toast_css, unsafe_allow_html=True)
    
    # Render the toast container
    toast_html = '<div class="fixed-toast-container">'
    
    for k in toast_keys:
        toast = st.session_state[k]
        toast_class = f"fixed-toast fixed-toast-{toast['type']}"
        
        # Use the total duration for the animation
        duration = toast["duration"]
        
        # Create the toast with animation
        toast_html += f'<div class="{toast_class}" style="animation-duration: {duration}s;">{toast["message"]}</div>'
    
    toast_html += '</div>'
    
    # Use a single empty to avoid multiple containers
    st.markdown(toast_html, unsafe_allow_html=True)