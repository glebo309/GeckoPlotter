# ui/custom_uploader_simple.py

import streamlit as st
import streamlit.components.v1 as components
import os
import tempfile
import base64
import json
import time

def render_custom_uploader():
    """
    Render a custom HTML file uploader that bypasses Streamlit's file extension validation.
    Uses a simplified approach compatible with older Streamlit versions.
    """
    # Create a unique session ID
    if "upload_session_id" not in st.session_state:
        st.session_state.upload_session_id = str(int(time.time()))
        st.session_state.last_file_check = 0
    
    session_id = st.session_state.upload_session_id
    storage_key = f"custom_uploader_{session_id}"
    
    # Create the HTML component for file upload
    upload_html = f"""
    <div style="border: 2px dashed #4CAF50; border-radius: 8px; padding: 20px; margin: 10px 0; text-align: center;">
        <h3 style="margin-top: 0;">Upload LC-MS CSV File</h3>
        <p>Use this for CSV files with spaces or special characters in filename</p>
        <input type="file" id="fileUpload" accept=".csv,.CSV" style="display: none;" onchange="handleFileSelect(event)">
        <button onclick="document.getElementById('fileUpload').click()" 
                style="background-color: #4CAF50; color: white; padding: 10px 15px; 
                       border: none; border-radius: 4px; cursor: pointer;">
            Select File
        </button>
        <div id="fileName" style="margin-top: 10px; font-style: italic;"></div>
        <div id="uploadStatus" style="margin-top: 10px;"></div>
        
        <script>
            // Function to handle file selection
            function handleFileSelect(event) {{
                const file = event.target.files[0];
                if (file) {{
                    document.getElementById('fileName').textContent = 'Selected: ' + file.name;
                    
                    // Read file content
                    const reader = new FileReader();
                    reader.onload = function(e) {{
                        const content = e.target.result;
                        
                        // Convert ArrayBuffer to Base64
                        const uint8Array = new Uint8Array(content);
                        let binary = '';
                        for (let i = 0; i < uint8Array.byteLength; i++) {{
                            binary += String.fromCharCode(uint8Array[i]);
                        }}
                        const base64 = btoa(binary);
                        
                        // Store file data
                        const fileData = {{
                            name: file.name,
                            content: base64,
                            size: file.size,
                            timestamp: Date.now()
                        }};
                        
                        // Store in localStorage
                        localStorage.setItem('{storage_key}', JSON.stringify(fileData));
                        
                        document.getElementById('uploadStatus').innerHTML = 
                            '<span style="color: green;">✓ File ready. </span> ' +
                            '<button onclick="window.location.reload()" ' +
                            'style="background-color: #2196F3; color: white; padding: 5px 10px; ' +
                            'border: none; border-radius: 4px; cursor: pointer;">Process File</button>';
                    }};
                    reader.readAsArrayBuffer(file);
                }}
            }}
        </script>
    </div>
    """
    
    # Render the upload component
    components.html(upload_html, height=220)
    
    # Create a component to check for file data
    check_file_js = f"""
    <div id="fileDataOutput" style="display:none;"></div>
    <script>
        // Check if we have file data in localStorage
        const fileDataStr = localStorage.getItem('{storage_key}');
        if (fileDataStr) {{
            try {{
                const fileData = JSON.parse(fileDataStr);
                // Only process if it's a recent upload
                if (fileData && fileData.timestamp) {{
                    document.getElementById('fileDataOutput').textContent = fileDataStr;
                }}
            }} catch (e) {{
                console.error("Error parsing file data:", e);
            }}
        }}
    </script>
    """
    
    # Render the file data check component
    file_data_component = components.html(check_file_js, height=0)
    
    # Get element text (if any) using st.markdown and st.components.v1
    html_output = components.html("""
    <script>
        const output = document.getElementById('fileDataOutput');
        if (output && output.textContent) {
            window.parent.postMessage({
                type: 'streamlit:getComponentValue',
                value: output.textContent
            }, '*');
        }
    </script>
    """, height=0)
    
    # Create a button to process the file
    if st.button("Check for Uploaded File", key="check_file_btn"):
        st.session_state.last_file_check = time.time()
    
    # Display upload status
    if time.time() - st.session_state.last_file_check < 5:
        status = st.empty()
        status.info("Checking for uploaded file...")
        
        # Create a manual data extractor
        data_output = components.html(f"""
        <div id="output"></div>
        <script>
            // Check if we have file data in localStorage
            const fileDataStr = localStorage.getItem('{storage_key}');
            if (fileDataStr) {{
                document.getElementById('output').textContent = 'Found: ' + JSON.parse(fileDataStr).name;
                
                // Clean up localStorage
                localStorage.removeItem('{storage_key}');
            }} else {{
                document.getElementById('output').textContent = 'No file found';
            }}
        </script>
        """, height=30)
        
        # Check for file data from localStorage
        file_data_str = st.text_input("Enter extracted file data (for debugging)", key="file_data_input", 
                                    label_visibility="collapsed")
        
        if file_data_str:
            try:
                # Parse the file data
                file_data = json.loads(file_data_str)
                
                # Decode base64 content
                file_content = base64.b64decode(file_data['content'])
                
                # Create temporary file
                with tempfile.NamedTemporaryFile(delete=False, suffix='.csv') as temp_file:
                    temp_file.write(file_content)
                    temp_path = temp_file.name
                
                # Return file info
                return {
                    "name": file_data['name'],
                    "path": temp_path,
                    "size": file_data.get('size', len(file_content))
                }
                
            except Exception as e:
                st.error(f"Error processing uploaded file: {str(e)}")
                import traceback
                st.error(traceback.format_exc())
    
    return None