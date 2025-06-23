// Tab functionality for GeckoPlotter sidebar
window.dash_clientside = Object.assign({}, window.dash_clientside, {
    clientside: {
        // Tab switching functionality for sidebar tabs only
        // Tab switching for sidebar tabs
        switch_tab: function(n_clicks_sample, n_clicks_peak, n_clicks_plot, n_clicks_export) {
            const ctx = window.dash_clientside.callback_context;
            
            if (!ctx.triggered.length) {
                return window.dash_clientside.no_update;
            }
            
            const triggered_id = ctx.triggered[0].prop_id.split('.')[0];
            
            // Only affect sidebar tabs - not the HPLC analysis tabs
            // Find all sidebar tab buttons (those not in the analysis-tabs class)
            const sidebarTabButtons = document.querySelectorAll('.tab-header:not(.analysis-tabs) .tab-button');
            const sidebarPanels = document.querySelectorAll('.tab-panel:not([data-tab-content])');
            
            // Remove active class from sidebar tabs and panels only
            sidebarTabButtons.forEach(btn => btn.classList.remove('active'));
            sidebarPanels.forEach(panel => panel.classList.remove('active'));
            
            // Add active class based on which tab was clicked
            let activeTab = 'sample'; // default
            
            switch(triggered_id) {
                case 'sample-tab-btn':
                    activeTab = 'sample';
                    break;
                case 'peak-tab-btn':
                    activeTab = 'peak';
                    break;
                case 'plot-tab-btn':
                    activeTab = 'plot';
                    break;
                case 'export-tab-btn':
                    activeTab = 'export';
                    break;
            }
            
            // Activate the clicked sidebar tab
            const activeButton = document.querySelector(`#${triggered_id}`);
            const activePanel = document.getElementById(`${activeTab}-tab`);
            
            if (activeButton) activeButton.classList.add('active');
            if (activePanel) activePanel.classList.add('active');
            
            return window.dash_clientside.no_update;
        },
        
        // Tab switching for HPLC analysis tabs
        switch_analysis_tab: function(n_clicks_integration, n_clicks_across, n_clicks_calibration) {
            const ctx = window.dash_clientside.callback_context;
            
            if (!ctx.triggered.length) {
                return window.dash_clientside.no_update;
            }
            
            const triggered_id = ctx.triggered[0].prop_id.split('.')[0];
            
            // Only affect HPLC analysis tabs
            const analysisTabButtons = document.querySelectorAll('.analysis-tabs .tab-button');
            const analysisPanels = document.querySelectorAll('[data-tab-content]');
            
            // Remove active class from analysis tabs and panels only
            analysisTabButtons.forEach(btn => btn.classList.remove('active'));
            analysisPanels.forEach(panel => panel.classList.remove('active'));
            
            // Add active class based on which tab was clicked
            let activeTab = 'integration'; // default
            
            switch(triggered_id) {
                case 'integration-tab-btn':
                    activeTab = 'integration';
                    break;
                case 'across-samples-tab-btn':
                    activeTab = 'across-samples';
                    break;
                case 'calibration-tab-btn':
                    activeTab = 'calibration';
                    break;
            }
            
            // Activate the clicked analysis tab
            const activeButton = document.querySelector(`#${triggered_id}`);
            const activePanel = document.querySelector(`[data-tab-content="${activeTab}"]`);
            
            if (activeButton) activeButton.classList.add('active');
            if (activePanel) activePanel.classList.add('active');
            
            return window.dash_clientside.no_update;
        },
        
        // Sample item selection
        select_sample: function(n_clicks) {
            const ctx = window.dash_clientside.callback_context;
            
            if (!ctx.triggered.length) {
                return window.dash_clientside.no_update;
            }
            
            // Get the clicked sample item
            const triggeredElement = document.getElementById(ctx.triggered[0].prop_id.split('.')[0]);
            
            if (triggeredElement && triggeredElement.classList.contains('sample-item')) {
                // Remove active class from all sample items
                document.querySelectorAll('.sample-item').forEach(item => {
                    item.classList.remove('active');
                });
                
                // Add active class to clicked item
                triggeredElement.classList.add('active');
            }
            
            return window.dash_clientside.no_update;
        }
    }
});

// Initialize tab functionality when DOM is loaded
document.addEventListener('DOMContentLoaded', function() {
    // Add click event listeners to tab buttons
    document.addEventListener('click', function(e) {
        if (e.target.classList.contains('tab-button')) {
            const tabName = e.target.getAttribute('data-tab');
            const tabHeader = e.target.closest('.tab-header');
            
            if (tabHeader) {
                // Find all tab buttons and panels within this tab group
                const tabButtons = tabHeader.querySelectorAll('.tab-button');
                const tabContent = tabHeader.nextElementSibling;
                
                if (tabContent && tabContent.classList.contains('tab-content')) {
                    const tabPanels = tabContent.querySelectorAll('[data-tab-content]');
                    
                    // Remove active class from all tabs and panels in this group
                    tabButtons.forEach(btn => btn.classList.remove('active'));
                    tabPanels.forEach(panel => panel.classList.remove('active'));
                    
                    // Add active class to clicked tab
                    e.target.classList.add('active');
                    
                    // Add active class to corresponding panel
                    const targetPanel = tabContent.querySelector(`[data-tab-content="${tabName}"]`);
                    if (targetPanel) {
                        targetPanel.classList.add('active');
                    }
                } else {
                    // Legacy tab handling for sidebar tabs
                    // Check if this is a sidebar tab or an analysis tab
                    const isSidebarTab = ['sample', 'peak', 'plot', 'export'].includes(tabName);
                    const isAnalysisTab = ['integration', 'across-samples', 'calibration'].includes(tabName);
                    
                    if (isSidebarTab) {
                        // Only affect sidebar tabs
                        const sidebarTabButtons = document.querySelectorAll('.tab-header:not(.analysis-tabs) .tab-button');
                        const sidebarPanels = document.querySelectorAll('.tab-panel:not([data-tab-content])');
                        
                        // Remove active class from sidebar tabs and panels
                        sidebarTabButtons.forEach(btn => btn.classList.remove('active'));
                        sidebarPanels.forEach(panel => panel.classList.remove('active'));
                        
                        // Add active class to clicked tab and corresponding panel
                        e.target.classList.add('active');
                        const targetPanel = document.getElementById(`${tabName}-tab`);
                        if (targetPanel) {
                            targetPanel.classList.add('active');
                        }
                    } else if (isAnalysisTab) {
                        // Only affect analysis tabs
                        const analysisTabButtons = document.querySelectorAll('.analysis-tabs .tab-button');
                        const analysisPanels = document.querySelectorAll('[data-tab-content]');
                        
                        // Remove active class from analysis tabs and panels
                        analysisTabButtons.forEach(btn => btn.classList.remove('active'));
                        analysisPanels.forEach(panel => panel.classList.remove('active'));
                        
                        // Add active class to clicked tab and corresponding panel
                        e.target.classList.add('active');
                        const targetPanel = document.querySelector(`[data-tab-content="${tabName}"]`);
                        if (targetPanel) {
                            targetPanel.classList.add('active');
                        }
                    }
                }
            }
        }
        
        // Handle sample item clicks
        if (e.target.closest('.sample-item')) {
            const sampleItem = e.target.closest('.sample-item');
            
            // Remove active class from all sample items
            document.querySelectorAll('.sample-item').forEach(item => {
                item.classList.remove('active');
            });
            
            // Add active class to clicked item
            sampleItem.classList.add('active');
        }
    });
});