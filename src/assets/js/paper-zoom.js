/**
 * Zoom and navigate the publication paper mock.
 * - Ctrl+wheel / pinch: zoom the paper preview only
 * - Arrow keys: pan when container is focused
 * - Browser-level zoom is blocked so the UI never scales
 */
(function () {
    var MIN_SCALE = 0.3;
    var MAX_SCALE = 4.0;
    var scale = 1.0;
    var PAN_STEP = 60;

    function applyScale() {
        var page = document.getElementById('pub-paper-page');
        var wrapper = document.getElementById('pub-paper-page-wrapper');
        var container = document.getElementById('pub-paper-container');
        if (!page || !wrapper || !container) return;

        page.style.transform = 'scale(' + scale + ')';
        page.style.transformOrigin = 'top center';

        if (scale > 1) {
            wrapper.style.width = (page.offsetWidth * scale) + 'px';
            wrapper.style.height = (page.offsetHeight * scale) + 'px';
            page.style.transformOrigin = 'top left';
            container.style.justifyContent = 'flex-start';
        } else {
            wrapper.style.width = '';
            wrapper.style.height = '';
            page.style.transformOrigin = 'top center';
            container.style.justifyContent = 'center';
        }
    }

    // Block ALL ctrl+wheel / pinch events at the document level so the
    // browser never zooms the page. Then only apply zoom when the event
    // originated inside the paper container.
    document.addEventListener('wheel', function (e) {
        if (!e.ctrlKey) return;

        // Always prevent browser zoom
        e.preventDefault();

        var container = document.getElementById('pub-paper-container');
        if (!container || !container.contains(e.target)) return;

        // Don't zoom when over the Plotly graph (it has its own interactions)
        if (e.target.closest && e.target.closest('#pub-preview-graph')) return;

        var delta = -e.deltaY * 0.01;
        scale = Math.min(MAX_SCALE, Math.max(MIN_SCALE, scale + delta));
        applyScale();
    }, { passive: false });

    // Block Ctrl/Cmd +/-/0 keyboard zoom
    document.addEventListener('keydown', function (e) {
        if ((e.ctrlKey || e.metaKey) && (e.key === '+' || e.key === '-' || e.key === '=' || e.key === '0')) {
            e.preventDefault();
        }
    });

    // Arrow keys pan the container
    document.addEventListener('keydown', function (e) {
        var container = document.getElementById('pub-paper-container');
        if (!container) return;
        var wrapper = container.closest('#pub-preview-wrapper');
        if (!wrapper || wrapper.style.display === 'none') return;
        if (!container.matches(':hover') && !container.contains(document.activeElement)) return;

        var tag = (e.target.tagName || '').toLowerCase();
        if (tag === 'input' || tag === 'textarea' || tag === 'select') return;

        var handled = false;
        switch (e.key) {
            case 'ArrowLeft':  container.scrollLeft -= PAN_STEP; handled = true; break;
            case 'ArrowRight': container.scrollLeft += PAN_STEP; handled = true; break;
            case 'ArrowUp':    container.scrollTop  -= PAN_STEP; handled = true; break;
            case 'ArrowDown':  container.scrollTop  += PAN_STEP; handled = true; break;
        }
        if (handled) e.preventDefault();
    });

    // Click on the grey area focuses the container (enables arrow keys)
    document.addEventListener('click', function (e) {
        var container = document.getElementById('pub-paper-container');
        if (!container || !container.contains(e.target)) return;
        if (e.target.closest && (e.target.closest('input, select, textarea, button') || e.target.closest('.js-plotly-plot'))) return;
        container.focus();
    });

    function init() {
        var container = document.getElementById('pub-paper-container');
        if (container && !container.hasAttribute('tabindex')) {
            container.setAttribute('tabindex', '0');
            container.style.outline = 'none';
        }
    }

    if (document.readyState === 'complete' || document.readyState === 'interactive') {
        setTimeout(init, 100);
    } else {
        document.addEventListener('DOMContentLoaded', init);
    }
})();
