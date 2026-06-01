/**
 * Zoom and navigate the publication preview mock.
 * - Ctrl+wheel / pinch: zoom the visible paper or slide preview
 * - Arrow keys: pan the visible preview container when focused/hovered
 * - Browser-level zoom is blocked so the app chrome does not scale
 */
(function () {
    var MIN_SCALE = 0.3;
    var MAX_SCALE = 4.0;
    var scale = 1.0;
    var PAN_STEP = 60;

    function visible(el) {
        return !!el && window.getComputedStyle(el).display !== 'none';
    }

    function getActivePreview() {
        var paperContainer = document.getElementById('pub-paper-container');
        var slideContainer = document.getElementById('pub-slide-container');

        if (visible(slideContainer)) {
            return {
                container: slideContainer,
                wrapper: document.getElementById('pub-slide-page-wrapper'),
                page: document.getElementById('pub-slide-page')
            };
        }

        return {
            container: paperContainer,
            wrapper: document.getElementById('pub-paper-page-wrapper'),
            page: document.getElementById('pub-paper-page')
        };
    }

    function setPreviewFocusability() {
        ['pub-paper-container', 'pub-slide-container'].forEach(function (id) {
            var container = document.getElementById(id);
            if (!container) return;
            if (!container.hasAttribute('tabindex')) {
                container.setAttribute('tabindex', '0');
            }
            container.style.outline = 'none';
        });
    }

    function previewBaseSize(preview) {
        var page = preview.page;
        return {
            width: page ? page.offsetWidth : 0,
            height: page ? page.offsetHeight : 0
        };
    }

    function centerIfScrollable(preview) {
        var container = preview.container;
        var wrapper = preview.wrapper;
        if (!container || !wrapper) return;

        var extraX = wrapper.offsetWidth - container.clientWidth;
        var extraY = wrapper.offsetHeight - container.clientHeight;
        container.scrollLeft = extraX > 0 ? extraX / 2 : 0;
        container.scrollTop = extraY > 0 ? extraY / 2 : 0;
    }

    function applyScale(anchor) {
        var preview = getActivePreview();
        if (!preview.container || !preview.wrapper || !preview.page) return;

        var container = preview.container;
        var wrapper = preview.wrapper;
        var page = preview.page;
        var base = previewBaseSize(preview);
        if (!base.width || !base.height) return;

        var oldWidth = wrapper.offsetWidth || base.width;
        var oldHeight = wrapper.offsetHeight || base.height;
        var rect = container.getBoundingClientRect();

        var ratioX = 0.5;
        var ratioY = 0.5;
        if (anchor) {
            ratioX = (container.scrollLeft + anchor.clientX - rect.left) / oldWidth;
            ratioY = (container.scrollTop + anchor.clientY - rect.top) / oldHeight;
        } else if (oldWidth > 0 && oldHeight > 0) {
            ratioX = (container.scrollLeft + container.clientWidth / 2) / oldWidth;
            ratioY = (container.scrollTop + container.clientHeight / 2) / oldHeight;
        }

        var scaledWidth = base.width * scale;
        var scaledHeight = base.height * scale;

        wrapper.style.width = scaledWidth + 'px';
        wrapper.style.height = scaledHeight + 'px';
        wrapper.style.display = 'inline-block';
        wrapper.style.flexShrink = '0';

        page.style.transform = 'scale(' + scale + ')';
        page.style.transformOrigin = 'top left';

        container.style.justifyContent = scaledWidth <= container.clientWidth ? 'center' : 'flex-start';
        container.style.alignItems = scaledHeight <= container.clientHeight ? 'center' : 'flex-start';

        if (anchor) {
            container.scrollLeft = Math.max(0, scaledWidth * ratioX - (anchor.clientX - rect.left));
            container.scrollTop = Math.max(0, scaledHeight * ratioY - (anchor.clientY - rect.top));
        } else {
            centerIfScrollable(preview);
        }
    }

    function zoom(delta, anchor) {
        scale = Math.min(MAX_SCALE, Math.max(MIN_SCALE, scale + delta));
        applyScale(anchor);
    }

    // Block ALL ctrl+wheel / pinch events at the document level so the browser
    // never zooms the page. Then apply preview zoom when the event originated
    // inside whichever publication preview container is visible.
    document.addEventListener('wheel', function (e) {
        if (!e.ctrlKey) return;
        e.preventDefault();

        var preview = getActivePreview();
        if (!preview.container || !preview.container.contains(e.target)) return;

        zoom(-e.deltaY * 0.01, { clientX: e.clientX, clientY: e.clientY });
    }, { passive: false });

    // Block Ctrl/Cmd +/-/0 keyboard zoom from changing browser zoom.
    document.addEventListener('keydown', function (e) {
        if ((e.ctrlKey || e.metaKey) && (e.key === '+' || e.key === '-' || e.key === '=' || e.key === '0')) {
            e.preventDefault();
        }
    });

    // Arrow keys pan the active visible preview container.
    document.addEventListener('keydown', function (e) {
        var preview = getActivePreview();
        var container = preview.container;
        if (!container) return;

        var wrapper = container.closest('#pub-preview-wrapper');
        if (!wrapper || window.getComputedStyle(wrapper).display === 'none') return;
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

    // Click on the grey preview area focuses the active container.
    document.addEventListener('click', function (e) {
        var preview = getActivePreview();
        var container = preview.container;
        if (!container || !container.contains(e.target)) return;
        if (e.target.closest && e.target.closest('input, select, textarea, button')) return;
        container.focus();
    });

    function init() {
        setPreviewFocusability();
        applyScale();

        ['pub-paper-container', 'pub-slide-container'].forEach(function (id) {
            var container = document.getElementById(id);
            if (!container || container.__geckoZoomObserved) return;
            container.__geckoZoomObserved = true;
            new MutationObserver(function () {
                window.requestAnimationFrame(applyScale);
            }).observe(container, { attributes: true, attributeFilter: ['style', 'class'] });
        });
    }

    if (document.readyState === 'complete' || document.readyState === 'interactive') {
        setTimeout(init, 100);
    } else {
        document.addEventListener('DOMContentLoaded', init);
    }

    window.addEventListener('resize', function () {
        window.requestAnimationFrame(applyScale);
    });

    window.__geckoPublicationPreviewZoom = {
        reset: function () {
            scale = 1.0;
            applyScale();
        },
        apply: applyScale
    };
})();
