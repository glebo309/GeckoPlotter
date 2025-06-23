// assets/zoom_handler.js
// Custom zoom behavior for GeckoPlotter

window.dash_clientside = window.dash_clientside || {};
window.dash_clientside.clientside = window.dash_clientside.clientside || {};

// Track double-click state
let doubleClickState = {};

// Custom double-click handler
document.addEventListener('DOMContentLoaded', function() {
    // Listen for Plotly double-click events
    document.addEventListener('plotly_doubleclick', function(eventData) {
        if (!eventData || !eventData.event) return;
        
        const plotDiv = eventData.event.target.closest('.js-plotly-plot');
        if (!plotDiv) return;
        
        const plotId = plotDiv.id;
        
        // Initialize state for this plot if not exists
        if (!doubleClickState[plotId]) {
            doubleClickState[plotId] = 0;
        }
        
        // Increment double-click count
        doubleClickState[plotId]++;
        
        if (doubleClickState[plotId] === 1) {
            // First double-click: Reset to sidebar values if they exist
            eventData.event.preventDefault();
            
            // Get sidebar input values
            const xMin = document.getElementById('x-min-input')?.value;
            const xMax = document.getElementById('x-max-input')?.value;
            const yMin = document.getElementById('y-min-input')?.value;
            const yMax = document.getElementById('y-max-input')?.value;
            
            // Only update if sidebar values exist
            if (xMin && xMax || yMin && yMax) {
                const update = {
                    'xaxis.range': (xMin && xMax) ? [parseFloat(xMin), parseFloat(xMax)] : null,
                    'yaxis.range': (yMin && yMax) ? [parseFloat(yMin), parseFloat(yMax)] : null
                };
                
                // Remove null values
                Object.keys(update).forEach(key => {
                    if (update[key] === null) delete update[key];
                });
                
                // Apply the update if we have any values
                if (Object.keys(update).length > 0) {
                    Plotly.relayout(plotDiv, update);
                } else {
                    // No sidebar values, do normal reset
                    doubleClickState[plotId] = 0;
                    Plotly.relayout(plotDiv, {
                        'xaxis.autorange': true,
                        'yaxis.autorange': true
                    });
                }
            } else {
                // No sidebar values, do normal reset
                doubleClickState[plotId] = 0;
                Plotly.relayout(plotDiv, {
                    'xaxis.autorange': true,
                    'yaxis.autorange': true
                });
            }
            
            // Reset count after a delay
            setTimeout(() => {
                doubleClickState[plotId] = 0;
            }, 1000);
            
        } else {
            // Second double-click or timeout: Full reset
            doubleClickState[plotId] = 0;
            // Let default behavior happen (full autorange)
        }
    });
    
    // Reset state when plot is updated
    const observer = new MutationObserver(function(mutations) {
        mutations.forEach(function(mutation) {
            if (mutation.type === 'childList') {
                // Reset double-click state for all plots when content changes
                doubleClickState = {};
            }
        });
    });
    
    // Observe plot containers for changes
    const plotContainers = document.querySelectorAll('#ms-plot, #uv-chromatogram-plot, #uvvis-plate-plot, #spectra-plot');
    plotContainers.forEach(container => {
        observer.observe(container, { childList: true, subtree: true });
    });
});