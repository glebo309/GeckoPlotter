// Tab functionality for GeckoPlotter sidebar
window.dash_clientside = Object.assign({}, window.dash_clientside, {
    clientside: {
        // Tab switching functionality
        switch_tab: function(n_clicks_sample, n_clicks_peak, n_clicks_plot, n_clicks_export) {
            const ctx = window.dash_clientside.callback_context;
            
            if (!ctx.triggered.length) {
                return window.dash_clientside.no_update;
            }
            
            const triggered_id = ctx.triggered[0].prop_id.split('.')[0];
            
            // Remove active class from all tabs and panels
            const tabButtons = document.querySelectorAll('.tab-button');
            const tabPanels = document.querySelectorAll('.tab-panel');
            
            tabButtons.forEach(btn => btn.classList.remove('active'));
            tabPanels.forEach(panel => panel.classList.remove('active'));
            
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
            
            // Activate the clicked tab
            const activeButton = document.querySelector(`[data-tab="${activeTab}"]`);
            const activePanel = document.getElementById(`${activeTab}-tab`);
            
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
            
            // Remove active class from all tabs and panels
            document.querySelectorAll('.tab-button').forEach(btn => btn.classList.remove('active'));
            document.querySelectorAll('.tab-panel').forEach(panel => panel.classList.remove('active'));
            
            // Add active class to clicked tab and corresponding panel
            e.target.classList.add('active');
            const targetPanel = document.getElementById(`${tabName}-tab`);
            if (targetPanel) {
                targetPanel.classList.add('active');
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