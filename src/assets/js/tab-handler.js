// Tab handler for GeckoPlotter V2
window.dash_clientside = Object.assign({}, window.dash_clientside, {
    tabs: {
        // Handle main data analysis tabs
        handleDataTabs: function(data_clicks, peak_clicks, across_clicks, metadata_clicks, calibration_clicks) {
            const ctx = window.dash_clientside.callback_context;
            if (!ctx.triggered || ctx.triggered.length === 0) {
                return 'data-overview';
            }
            
            const triggeredId = ctx.triggered[0].prop_id.split('.')[0];
            const tabMap = {
                'data-overview-tab': 'data-overview',
                'peak-analysis-tab': 'peak-analysis',
                'across-samples-tab': 'across-samples',
                'metadata-tab': 'metadata',
                'calibration-tab': 'calibration'
            };
            
            return tabMap[triggeredId] || 'data-overview';
        },
        
        // Update tab UI based on active tab
        updateDataTabUI: function(activeTab) {
            // Update tab buttons
            const tabs = ['data-overview', 'peak-analysis', 'across-samples', 'metadata', 'calibration'];
            const classNames = {};
            
            tabs.forEach(tab => {
                const isActive = tab === activeTab;
                classNames[`${tab}-tab`] = isActive ? 'tab-button active' : 'tab-button';
                classNames[`${tab}-container`] = isActive ? 'tab-content active' : 'tab-content';
            });
            
            return classNames;
        },
        
        // Handle toolbox tabs
        handleToolboxTabs: function(plot_clicks, integration_clicks, export_clicks) {
            const ctx = window.dash_clientside.callback_context;
            if (!ctx.triggered || ctx.triggered.length === 0) {
                return 'plot-tools';
            }
            
            const triggeredId = ctx.triggered[0].prop_id.split('.')[0];
            const tabMap = {
                'plot-tools-tab': 'plot-tools',
                'integration-tab': 'integration',
                'export-tab': 'export'
            };
            
            return tabMap[triggeredId] || 'plot-tools';
        },
        
        // Update toolbox tab UI
        updateToolboxTabUI: function(activeTab) {
            const tabs = ['plot-tools', 'integration', 'export'];
            const updates = {};
            
            tabs.forEach(tab => {
                const isActive = tab === activeTab;
                const btnId = `${tab}-tab`;
                const containerId = `${tab.replace('-', '-')}-container`;
                
                // Update button classes
                updates[btnId] = {
                    className: isActive ? 'toolbox-tab-button active' : 'toolbox-tab-button'
                };
                
                // Update container visibility
                updates[containerId] = {
                    style: { display: isActive ? 'block' : 'none' }
                };
            });
            
            return updates;
        },
        
        // Handle view mode toggle
        handleViewMode: function(raw_clicks, analysis_clicks) {
            const ctx = window.dash_clientside.callback_context;
            if (!ctx.triggered || ctx.triggered.length === 0) {
                return 'raw';
            }
            
            const triggeredId = ctx.triggered[0].prop_id.split('.')[0];
            return triggeredId === 'analysis-mode-btn' ? 'analysis' : 'raw';
        },
        
        // Update view mode button UI
        updateViewModeUI: function(viewMode) {
            const isRaw = viewMode === 'raw';
            return {
                'raw-mode-btn': {
                    className: isRaw ? 'mode-btn active' : 'mode-btn'
                },
                'analysis-mode-btn': {
                    className: !isRaw ? 'mode-btn active' : 'mode-btn'
                }
            };
        }
    }
});
