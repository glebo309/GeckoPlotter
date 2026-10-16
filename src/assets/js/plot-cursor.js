// The pointer over the plot shows what a drag will do: zoom (crosshair), integrate (crosshair with a small peak: the
// Integrate tool, Shift held, or Auto resting on a peak), pan (Cmd/Ctrl), edit text. The values under the pointer
// (Plotly's hover box) show only with the Inspect tool (magnifier button), which Auto never switches on or off.
(function () {
    'use strict';
    var KEY = 'gecko.inspect';
    var inspecting = false;
    try { inspecting = window.localStorage.getItem(KEY) === '1'; } catch (e) { inspecting = false; }
    var last = null;                                    // the last pointer or key event, for the modifier keys

    function plot() { return window.geckoActivePlot ? window.geckoActivePlot() : document.querySelector('[data-workspace-plot]'); }

    function tool(gd, event) {
        if (document.body.classList.contains('gecko-text-edit-mode')) return 'text';
        if (event && (event.metaKey || event.ctrlKey)) return 'pan';
        if (gd.__geckoManualIntegrationMode === 'draw' || (event && event.shiftKey) ||
            window.__geckoAutoIntegrateNear === true) return 'integrate';
        return inspecting ? 'inspect' : 'zoom';
    }

    function refresh(event) {
        if (event) last = event;
        var gd = plot();
        if (!gd) return;
        var wanted = tool(gd, last);
        if (gd.dataset.geckoCursor !== wanted) gd.dataset.geckoCursor = wanted;
    }

    function sync() {
        document.body.classList.toggle('gecko-inspect-mode', inspecting);
        var button = document.getElementById('plot-tool-inspect');
        if (button) {
            button.classList.toggle('active', inspecting);
            button.setAttribute('aria-pressed', inspecting ? 'true' : 'false');
        }
        refresh();
    }

    function toggle() {
        inspecting = !inspecting;
        try { window.localStorage.setItem(KEY, inspecting ? '1' : '0'); } catch (e) { /* the choice lasts this visit */ }
        sync();
    }

    document.addEventListener('click', function (event) {
        var target = event.target;
        if (target && target.closest && target.closest('#plot-tool-inspect')) toggle();
    }, true);
    // After auto-integrate.js has decided whether the pointer rests on a peak (it listens without capture too).
    document.addEventListener('pointermove', function (event) { setTimeout(function () { refresh(event); }, 0); });
    document.addEventListener('keydown', refresh, true);
    document.addEventListener('keyup', refresh, true);
    document.addEventListener('click', function () { setTimeout(refresh, 0); });
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', sync); else sync();
    var tries = 0, wait = setInterval(function () {        // the toolbar is drawn by Dash after this script runs
        sync();
        if (document.getElementById('plot-tool-inspect') || ++tries > 40) clearInterval(wait);
    }, 250);
})();
