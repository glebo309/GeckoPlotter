# OPUS Implementation Plan - GeckoPlotter V2 Phase 3

## 📋 Current State Analysis

### ✅ What's Already Implemented
Based on my analysis of the codebase:

1. **Data Layer (Phase 2 - COMPLETE)**
   - ✅ DataManager with file loading and storage
   - ✅ Multiple readers (chromatogram, UV-Vis CSV, LCMS CDF)
   - ✅ Bundle management for multi-file grouping
   - ✅ File upload system with tree display
   - ✅ Clean white theme with orange accents

2. **Basic UI Structure**
   - ✅ 4-panel resizable layout
   - ✅ File Explorer (top-left)
   - ✅ Toolbox placeholder (bottom-left)
   - ✅ Main Visualization area (top-right)
   - ✅ Data Overview panel (bottom-right) - **BUT NOT TABS YET**

3. **Partial Implementations**
   - ⚠️ Tab callbacks exist (`tab_callbacks.py`) but tabs NOT in UI
   - ⚠️ PlotManager exists but minimal functionality
   - ⚠️ Viz callbacks basic file selection only
   - ⚠️ No view mode toggle (Raw/Analysis)
   - ⚠️ No adaptive toolbox content

### 🔍 Gap Analysis

**Critical Missing Pieces for Phase 3:**
1. **Tab UI Structure**: The bottom-right panel is still "Data Overview" with a single container, NOT the 5-tab system
2. **View Mode Toggle**: No Raw/Analysis mode switch in main visualization
3. **DataManager Integration**: File selection doesn't fully drive all panels
4. **Toolbox Adaptation**: Static placeholder, not context-aware
5. **Shared Stores**: Some stores exist but not all required ones

## 🎯 Implementation Feasibility Assessment

### Is Your Phase 3 Plan Realistic? **YES, BUT...**

✅ **Strengths of the Plan:**
- Clear architecture with DataManager as single source of truth
- Modular approach aligns with existing codebase structure
- Tab framework already partially implemented in callbacks
- Clean separation of concerns already established

⚠️ **Challenges:**
- **Scope for One Prompt**: Full Phase 3 is ~15-20 components to modify/create
- **Table Editor Integration**: The `table_playground.py` is 1500 lines of tightly coupled code
- **Complex State Management**: 5 stores + multiple callbacks = intricate coordination

### 🚀 Recommended Approach: **Phase 3A (Foundation) → Phase 3B (Features)**

## 📐 What I Can Realistically Implement NOW (Phase 3A)

### 1. **Bottom-Right Tab Structure** ✅
- Convert single "Data Overview" panel to 5-tab system
- Add tab headers with proper styling
- Implement client-side tab switching
- Create empty containers for each tab
- Wire to `active-tab` store

### 2. **View Mode Toggle** ✅
- Add Raw/Analysis toggle button to main viz panel
- Create `view-mode` store
- Update PlotManager to handle both modes
- Connect to existing viz callbacks

### 3. **Core Store Infrastructure** ✅
- Add missing stores: `active-tab`, `view-mode`, `toolbox-settings`
- Update existing stores to proper structure
- Ensure all panels subscribe to shared state

### 4. **Basic Toolbox Adaptation** ✅
- Create toolbox content switcher based on active tab
- Add placeholder content for each context
- Wire to `active-tab` changes

### 5. **File Selection → Panel Updates** ✅
- Enhance file tree selection callback
- Ensure it updates all dependent panels
- Connect DataManager properly

## 🔮 What Comes Next (Phase 3B - Second Prompt)

### 1. **Tab Content Population**
- Migrate Peak Analysis logic from `tab_callbacks.py`
- Create Metadata tab content
- Add Across Samples comparison
- Stub Calibration tab

### 2. **Advanced Toolbox Features**
- Integration controls for Peak Analysis
- Export settings panel
- Plot customization controls
- Color palette selector

### 3. **Table Editor Preparation**
- Extract reusable components from `table_playground.py`
- Create modular table service
- Prepare Data Overview tab for editor

## 💡 Implementation Strategy for THIS Prompt

### Files to Create/Modify:
1. **`src/app.py`** - Add tab structure, view toggle, new stores
2. **`src/assets/css/main.css`** - Tab styling, view toggle styling
3. **`src/callbacks/tab_callbacks.py`** - Enhanced tab switching logic
4. **`src/callbacks/viz_callbacks.py`** - View mode handling
5. **`src/callbacks/toolbox_callbacks.py`** (NEW) - Adaptive toolbox content
6. **`src/services/plot_manager.py`** - Dual mode plotting support

### Implementation Order:
1. **First**: Update app.py with tab HTML structure and stores
2. **Second**: Add CSS for tabs and toggle
3. **Third**: Implement client-side tab switching
4. **Fourth**: Add view mode toggle and logic
5. **Fifth**: Create adaptive toolbox framework
6. **Sixth**: Wire everything to DataManager

## ✅ Success Criteria for This Implementation

After this implementation, you will have:

1. ✅ **5-tab structure** visible and switchable in bottom-right
2. ✅ **View mode toggle** in main visualization panel
3. ✅ **Adaptive toolbox** that changes with active tab
4. ✅ **All panels connected** through DataManager
5. ✅ **Clean architecture** ready for Phase 3B features
6. ✅ **No breaking changes** to existing functionality

## 🚫 What I Will NOT Do in This Prompt

1. ❌ Full Table Editor integration (too complex for one pass)
2. ❌ Complete Peak Analysis implementation (needs dedicated focus)
3. ❌ Export Manager implementation (Phase 3B)
4. ❌ Calibration logic (Phase 4)
5. ❌ Complex plot customization UI (Phase 3B)

## 📊 Risk Assessment

**Low Risk** ✅
- Tab UI structure (straightforward HTML/CSS)
- Client-side callbacks (proven pattern)
- Basic store management

**Medium Risk** ⚠️
- Toolbox adaptation logic (needs careful state management)
- View mode integration with existing plots

**High Risk** ❌ (Not attempting)
- Table Editor port (1500 lines of complex logic)
- Full feature implementation

## 🎬 Final Recommendation

**PROCEED WITH PHASE 3A IMPLEMENTATION**

This approach:
- ✅ Delivers tangible progress you can see immediately
- ✅ Creates the foundation for Table Editor integration
- ✅ Maintains architectural integrity
- ✅ Sets up clean hooks for Phase 3B
- ✅ Achievable in one prompt cycle

The Table Editor can then be cleanly integrated in the next prompt once this foundation is solid.

---

**Ready to implement Phase 3A? This will give you:**
- Working tab interface
- View mode toggle
- Adaptive toolbox
- Proper state management
- Clean architecture for Table Editor integration

*This is the right architectural step before the Table Editor.*
