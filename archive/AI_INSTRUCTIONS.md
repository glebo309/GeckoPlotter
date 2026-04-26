# GeckoPlotter V2 - AI Development Strategy & Migration Plan

## 🎯 Project Overview

**Goal**: Migrate from the buggy, monolithic DashPlotter codebase to a clean, modular GeckoPlotter V2 with proper architecture and maintainable code.

**Philosophy**: UI-first approach → Clean architecture → Gradual feature migration → EASY FIX IS KING!

---

## 📊 Old Codebase Analysis

### ✅ **What's Good to Reuse**

#### **1. Data Readers (HIGH PRIORITY)**
- **Location**: `/DashPlotter/readers/`
- **Quality**: Well-structured, functional
- **Files to migrate**:
  - `base_reader.py` - Good inheritance pattern
  - `chromatogram_reader.py` - Handles TXT/CSV chromatograms
  - `lcms_cdf_reader.py` - CDF file parsing (LC-MS)
  - `lcms_vwd_cdf_reader.py` - UV-VIS CDF files
  - `uvvis_csv_reader.py` - CSV UV-VIS data
  - `chromeleon_bundle_reader.py` - Complex multi-file handling

#### **2. Peak Detection & Integration (MEDIUM PRIORITY)**
- **Location**: `/DashPlotter/utils/peak_integration.py`
- **Quality**: Advanced algorithms, well-tested
- **Features**: 
  - Scipy-based peak detection
  - Baseline correction
  - Integration calculations
  - Advanced boundary detection

#### **3. Data Manager Pattern (MEDIUM PRIORITY)**
- **Location**: `/DashPlotter/data_manager.py`
- **Quality**: Good central data handling
- **Features**:
  - File type detection
  - Reader management
  - Data caching
  - Bundle handling for multi-file formats

#### **4. Export Functionality (LOW PRIORITY)**
- **Location**: `/DashPlotter/utils/export_options.py`
- **Quality**: Comprehensive export options
- **Features**: Multiple format support, data packaging

### ❌ **What's Problematic (DON'T MIGRATE)**

#### **1. Callback System**
- **Problem**: Monolithic, tightly coupled
- **Location**: `/DashPlotter/callbacks/` (76K+ lines in viz_callbacks.py!)
- **Issues**: 
  - Massive files with mixed concerns
  - Hard to debug and maintain
  - No clear separation of responsibilities

#### **2. Layout System**
- **Problem**: Complex, non-responsive
- **Location**: `/DashPlotter/layouts/`
- **Issues**: 
  - Fixed layouts, poor UX
  - Mixed styling and logic
  - No proper component structure

#### **3. File Tree Manager**
- **Problem**: Overly complex for simple task
- **Location**: `/DashPlotter/file_tree_manager.py`
- **Issues**: 19K lines for file tree management

---

## 🚀 Migration Strategy

- ✅ **Phase 1 DONE**: Clean UI with proper resizable layout
- ✅ **Phase 2 DONE**: Data layer migration - readers, storage manager, basic upload
- 🔄 **Phase 3 NEXT**: Visualization core - plotting, basic interactions
- 🔄 **Phase 4 FUTURE**: Advanced features - peak detection, export, complex analysis

### **Phase 2: Data Layer (COMPLETED - HIGH PRIORITY)**
**Goal**: Get data flowing through the new system ✅

#### **Step 2.1: Migrate Data Readers ✅**
```
✅ base_reader.py → /src/services/readers/base_reader.py
✅ chromatogram_reader.py → Cleaned up, removed debug prints, proper type hints
✅ uvvis_csv_reader.py → Simplified, focused on core functionality
✅ Created proper __init__.py files for package structure
```

#### **Step 2.2: Create Storage Manager ✅**
```
✅ /src/services/storage_manager.py - Extended existing file with DataManager class
✅ Integrates file upload processing with data loading
✅ Proper temp file management and cleanup
✅ Clean separation of concerns
```

#### **Step 2.3: File Upload System ✅**
```
✅ /src/callbacks/upload_callbacks.py - New modular upload system
✅ Integrated with new DataManager
✅ Proper error handling and logging
✅ Clear Files functionality added to UI
✅ Updated main app.py to use new system
```

### **Phase 3: Visualization Core (NEXT - MEDIUM PRIORITY)**
**Goal**: Basic plotting functionality

---

## **LCMS Bundle Integration Plan (HIGH PRIORITY)**

- **Scope Overview**
  - Reuse legacy readers in `DashPlotter/readers/` (`LCMSCDFReader`, `LCMSVWDCDFReader`, `LCMSBundleReader`) as references for porting into `GeckoPlotter_V2/src/readers/`.
  - Deliver LCMS bundles that behave like existing HPLC bundles and UV-Vis CSV wells, including auto plot refresh, tree controls, and visibility toggles.

- **Step 1 – Reader Layer (src/readers/)**
  - **[Import/Port Readers]** Create `lcms_cdf_reader.py` and `lcms_vwd_cdf_reader.py` in `GeckoPlotter_V2/src/readers/`, preserving metadata extraction (ionization mode, scan counts, mass/RT ranges, instrument info) and TIC/UV dataframe outputs (`Time (min)`, `Intensity`, `Intensity (mAU)`).
  - **[Bundle Reader Adapter]** Implement an `lcms_bundle_reader.py` helper to assemble paired POS/NEG (and optional VWD) datasets, mirroring `DashPlotter/readers/lcms_bundle_reader.py` for combined metadata summaries.
  - **[Unit Hooks]** Ensure each reader exposes `get_data()`, `get_metadata()`, `get_file_name()`, and convenience methods (`get_scan_count()`, `get_retention_time_range()`) expected by `storage_manager`.

- **Step 2 – Storage Manager Enhancements (`src/services/storage_manager.py`)**
  - **[Type Detection]** Extend `detect_file_type()` to classify LCMS MS vs VWD `.cdf` files using filename heuristics/metadata as in legacy `data_manager.py` (lines ~35-140).
  - **[Base Name Normalization]** Port `extract_lcms_base_name()` to compute bundle keys (`sampleName_LCMS_BUNDLE`).
  - **[Bundle Tracking]** Introduce `self.lcms_bundles` map with component slots (`ms_positive`, `ms_negative`, `vwd_a`, `vwd_b`, `files`). Accumulate entries during uploads and keep raw component readers for per-mode plotting.
  - **[Metadata Synthesis]** Implement `_create_lcms_bundle_metadata()` to aggregate sample info, scan counts, RT ranges, mass ranges, instrument details, and component availability. Align field names with existing HPLC/CSV metadata for downstream reuse.
  - **[Persistence]** Store bundle records in `loaded_files` with `type: 'lcms_bundle'`, while retaining individual component entries under internal keys for plotting. Ensure temp file cleanup mirrors current logic.

- **Step 3 – File Tree & UI (`src/callbacks/upload_callbacks.py`, `src/services/storage_manager.py`)**
  - **[Tree Items]** Update `get_bundled_tree_items()` (and related helpers) to emit LCMS bundles as expandable parents with child nodes for available components (`bundle_id|ms_positive`, etc.).
  - **[Initial State]** Default parents to expanded state upon first creation, honoring collapse-state preservation already implemented for CSV wells.
  - **[Controls]** Ensure delete, visibility, and selection callbacks treat LCMS nodes consistently with HPLC/CSV (auto updates, toggle icons, no duplicate entries).

- **Step 4 – Visualization (`src/services/plot_manager.py`, `src/callbacks/file_tree_callbacks.py`)**
  - **[Plot Routing]** Extend `PlotManager` to handle LCMS bundle IDs and child selectors, delegating to new helpers (`create_lcms_tic_plot`, `create_lcms_uv_plot`). Reuse styling/metadata annotations from `DashPlotter/plot/lcms.py`.
  - **[Auto Updates]** When visibility or deletion events impact LCMS components, trigger the same auto-refresh pipeline used for HPLC/CSV (`file_tree_callbacks.handle_file_deletion`, visibility toggles) so plots update without manual re-selection.
  - **[Future Hooks]** Reserve structure for extracted ion chromatograms/mass spectra later; keep placeholders analogous to legacy TODOs.

- **Step 5 – Testing & Parity**
  - **[Unit Tests]** Add focused tests for base name extraction, bundle metadata assembly, and reader outputs (if feasible within current test suite).
  - **[Manual QA]** Verify multi-component uploads: POS only, NEG only, POS+NEG, and POS+NEG+VWD combinations. Confirm tree behavior (expand/collapse, delete, visibility), auto plot updates, and metadata display within the Data Analysis tab.
  - **[Regression Checks]** Ensure existing CSV wells and HPLC bundles remain unaffected (no duplicate nodes, auto-plot continues to function).

- **Step 6 – Implementation Sequence**
  - **1.** Port/implement readers (Step 1).
  - **2.** Extend `storage_manager` detection + bundle tracking (Step 2).
  - **3.** Update file tree generation + callbacks (Step 3).
  - **4.** Expand plot manager + visualization callbacks (Step 4).
  - **5.** Execute manual QA + document nuances (Step 5).

- **Parity Requirement**
  - Explicitly mirror HPLC/CSV user experience: tree controls, auto plot refresh on deletion/visibility, expand/collapse persistence, icons, and child selection behavior.

---

#### **Step 3.1: Plot Manager**
New File: /src/services/plot_manager.py
- Clean plotting logic
- Plotly figure generation
- Basic customization
```

#### **Step 3.2: Visualization Callbacks**
```
New File: /src/callbacks/viz_callbacks.py
- Simple plot updates
- Data selection
- Basic interactions
- Keep under 500 lines!
```

### **Phase 4: Advanced Features (LOW PRIORITY)**
**Goal**: Migrate advanced functionality

#### **Step 4.1: Peak Detection**
```
Migrate: utils/peak_integration.py → /src/services/peak_detection.py
- Clean up the API
- Modularize functions
- Add proper error handling
```

#### **Step 4.2: Export System**
```
Migrate: utils/export_options.py → /src/services/export_manager.py
- Simplify export options
- Modern file handling
```

---

## 🏗️ Architecture Principles

### **1. Modular Design**
```
/src/
├── services/          # Business logic (NO UI)
│   ├── readers/       # File format handlers
│   ├── storage_manager.py
│   ├── plot_manager.py
│   └── peak_detection.py
├── callbacks/         # UI event handlers (SMALL FILES)
├── components/        # Reusable UI components
└── utils/            # Helper functions
```

### **2. Single Responsibility**
- Each file has ONE clear purpose
- Max 500 lines per callback file
- Clear separation of concerns
- Easy to test and debug

### **3. Easy Fix Philosophy**
- **Prefer simple solutions over clever ones**
- **Copy-paste-modify over complex inheritance**
- **Clear naming over brevity**
- **Explicit over implicit**

---

## 📋 Implementation Checklist

### **Phase 2 Tasks (IMMEDIATE)**

#### **Data Readers Migration**
- [ ] Copy `base_reader.py` to `/src/services/readers/`
- [ ] Copy `chromatogram_reader.py` and clean up
- [ ] Copy `uvvis_csv_reader.py` and simplify
- [ ] Test basic file loading with new readers
- [ ] Create simple storage manager
- [ ] Implement basic file upload

#### **Integration Points**
- [ ] Connect readers to storage manager
- [ ] Update file tree to use new storage
- [ ] Basic file selection and display
- [ ] Simple error handling and feedback

### **Phase 3 Tasks (NEXT)**
- [ ] Basic plot generation from loaded data
- [ ] Simple plot customization
- [ ] Data selection and filtering
- [ ] Export basic functionality

### **Phase 4 Tasks (LATER)**
- [ ] Advanced peak detection
- [ ] Baseline correction
- [ ] Complex export options
- [ ] Advanced plot features

---

## 🚨 Critical Rules

### **DO:**
- Keep callback files under 500 lines
- Use clear, descriptive names
- Test each component independently
- Document complex algorithms
- Prefer composition over inheritance

### **DON'T:**
- Create monolithic files like the old codebase
- Mix UI logic with business logic
- Copy complex callback patterns
- Over-engineer simple features
- Ignore the "Easy Fix" principle

---

## 🔧 Development Workflow

### **For Each Feature Migration:**

1. **Analyze**: Understand what the old code does
2. **Simplify**: Remove unnecessary complexity
3. **Isolate**: Create focused, single-purpose modules
4. **Test**: Verify functionality works
5. **Integrate**: Connect to the new architecture
6. **Document**: Update this file with progress

### **Quality Gates:**
- No file over 500 lines (except data processing)
- Clear separation of concerns
- Proper error handling
- Simple, testable functions
- Good naming conventions

---

## 📈 Success Metrics

- **Code Quality**: Smaller, focused files
- **Maintainability**: Easy to understand and modify
- **Functionality**: All original features working
- **Performance**: Fast, responsive UI
- **User Experience**: Clean, intuitive interface

---

**Remember: EASY FIX IS KING! Simple, working code beats complex, clever code every time.**
