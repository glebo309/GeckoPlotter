# File: readers/lcms_bundle_reader.py
import os
import re
from .base_reader import BaseReader
from .lcms_cdf_reader import LCMSCDFReader

class LCMSBundleReader(BaseReader):
    """Handle LC-MS bundles with positive and negative mode CDF files"""
    
    def __init__(self):
        super().__init__()
        self.base_name = None
        self.positive_reader = None
        self.negative_reader = None
        self.metadata = {}
        self.combined_data = None
        
    def load_bundle(self, base_name, pos_file_data, neg_file_data, extra_files=None):
        """Load a bundle from positive and negative file data"""
        try:
            self.base_name = base_name
            self.file_name = f"{base_name} (LC-MS Bundle)"
            
            print(f"\n{'='*80}")
            print(f"📦 LC-MS BUNDLE CREATION: {base_name}")
            print(f"{'='*80}")
            
            # Load positive mode file
            if pos_file_data:
                pos_filename, pos_content = pos_file_data
                print(f"📈 Loading POSITIVE mode: {pos_filename}")
                
                self.positive_reader = LCMSCDFReader()
                success = self.positive_reader.load_file(pos_filename, extra_files)
                
                if success:
                    print(f"   ✅ Positive mode loaded: {self.positive_reader.get_scan_count()} scans")
                else:
                    print(f"   ❌ Failed to load positive mode")
            
            # Load negative mode file  
            if neg_file_data:
                neg_filename, neg_content = neg_file_data
                print(f"📉 Loading NEGATIVE mode: {neg_filename}")
                
                self.negative_reader = LCMSCDFReader()
                success = self.negative_reader.load_file(neg_filename, extra_files)
                
                if success:
                    print(f"   ✅ Negative mode loaded: {self.negative_reader.get_scan_count()} scans")
                else:
                    print(f"   ❌ Failed to load negative mode")
            
            # Create combined metadata
            self._create_combined_metadata()
            
            # Create combined data (use positive as primary, could be enhanced later)
            if self.positive_reader and self.positive_reader.get_data() is not None:
                self.combined_data = self.positive_reader.get_data()
            elif self.negative_reader and self.negative_reader.get_data() is not None:
                self.combined_data = self.negative_reader.get_data()
            
            print(f"✅ Bundle created successfully")
            print(f"{'='*80}\n")
            
            return True
            
        except Exception as e:
            print(f"❌ Bundle creation error: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def _create_combined_metadata(self):
        """Create combined metadata from both modes"""
        self.metadata = {
            'bundle_type': 'lcms_pos_neg',
            'base_name': self.base_name,
            'has_positive': self.positive_reader is not None,
            'has_negative': self.negative_reader is not None
        }
        
        # Get metadata from positive mode (primary)
        if self.positive_reader:
            pos_meta = self.positive_reader.get_metadata()
            self.metadata.update({
                'pos_' + k: v for k, v in pos_meta.items()
            })
            
            # Use positive mode for primary info
            self.metadata.update({
                'scan_count': pos_meta.get('scan_count', 0),
                'retention_time_range': pos_meta.get('retention_time_range', 'Unknown'),
                'mass_range': pos_meta.get('mass_range', (0, 0)),
                'max_intensity': pos_meta.get('max_intensity', 0),
                'sample_name': pos_meta.get('sample_name', 'Unknown Sample'),
                'instrument_name': pos_meta.get('instrument_name', 'Unknown')
            })
        
        # Get metadata from negative mode
        if self.negative_reader:
            neg_meta = self.negative_reader.get_metadata()
            self.metadata.update({
                'neg_' + k: v for k, v in neg_meta.items()
            })
            
            # If no positive mode, use negative as primary
            if not self.positive_reader:
                self.metadata.update({
                    'scan_count': neg_meta.get('scan_count', 0),
                    'retention_time_range': neg_meta.get('retention_time_range', 'Unknown'),
                    'mass_range': neg_meta.get('mass_range', (0, 0)),
                    'max_intensity': neg_meta.get('max_intensity', 0),
                    'sample_name': neg_meta.get('sample_name', 'Unknown Sample'),
                    'instrument_name': neg_meta.get('instrument_name', 'Unknown')
                })
        
        # Combined summary
        modes = []
        if self.positive_reader:
            pos_scans = self.positive_reader.get_scan_count()
            modes.append(f"POS({pos_scans})")
        if self.negative_reader:
            neg_scans = self.negative_reader.get_scan_count()
            modes.append(f"NEG({neg_scans})")
        
        self.metadata['ionization_modes'] = ' + '.join(modes)
        self.metadata['summary'] = f"LC-MS Bundle: {' + '.join(modes)}"
    
    # Required BaseReader methods
    def get_data(self):
        """Return combined data (positive mode primary)"""
        return self.combined_data
    
    def get_file_name(self):
        """Return bundle display name"""
        return getattr(self, 'file_name', 'LC-MS Bundle')
    
    def get_metadata(self):
        """Return combined metadata"""
        return self.metadata
    
    # Bundle-specific methods
    def get_positive_reader(self):
        """Get positive mode reader"""
        return self.positive_reader
    
    def get_negative_reader(self):
        """Get negative mode reader"""
        return self.negative_reader
    
    def has_positive_mode(self):
        """Check if bundle has positive mode data"""
        return self.positive_reader is not None
    
    def has_negative_mode(self):
        """Check if bundle has negative mode data"""
        return self.negative_reader is not None
    
    def get_positive_data(self):
        """Get positive mode TIC data"""
        if self.positive_reader:
            return self.positive_reader.get_data()
        return None
    
    def get_negative_data(self):
        """Get negative mode TIC data"""
        if self.negative_reader:
            return self.negative_reader.get_data()
        return None
    
    def get_mode_info(self):
        """Get information about available modes"""
        info = {
            'positive': {
                'available': self.has_positive_mode(),
                'scans': self.positive_reader.get_scan_count() if self.positive_reader else 0,
                'rt_range': self.positive_reader.get_retention_time_range() if self.positive_reader else (0, 0),
                'max_intensity': self.positive_reader.get_max_intensity() if self.positive_reader else 0
            },
            'negative': {
                'available': self.has_negative_mode(),
                'scans': self.negative_reader.get_scan_count() if self.negative_reader else 0,
                'rt_range': self.negative_reader.get_retention_time_range() if self.negative_reader else (0, 0),
                'max_intensity': self.negative_reader.get_max_intensity() if self.negative_reader else 0
            }
        }
        return info