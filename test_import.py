#!/usr/bin/env python3

import sys
import os
sys.path.insert(0, 'src')

try:
    print("Testing imports...")
    from services.storage_manager import DataManager
    print("✅ DataManager import successful")
    
    from callbacks.upload_callbacks import register_upload_callbacks
    print("✅ upload_callbacks import successful")
    
    from callbacks.viz_callbacks import register_viz_callbacks  
    print("✅ viz_callbacks import successful")
    
    from callbacks.file_tree_callbacks import register_file_tree_callbacks
    print("✅ file_tree_callbacks import successful")
    
    print("🎉 All imports successful!")
    
except Exception as e:
    print(f"❌ Import error: {e}")
    import traceback
    traceback.print_exc()
