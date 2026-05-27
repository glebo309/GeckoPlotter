// Push contentEditable tab renames into the tab-rename-event store via set_props
(function() {
    document.addEventListener('focusout', function(e) {
        var el = e.target;
        if (!el || el.contentEditable !== 'true') return;
        var id;
        try { id = JSON.parse(el.id); } catch(_) { return; }
        if (!id || id.type !== 'plot-tab-label') return;
        var text = (el.textContent || '').trim();
        if (!text) return;
        if (window.dash_clientside && window.dash_clientside.set_props) {
            window.dash_clientside.set_props('tab-rename-event', {
                data: { tab_id: id.index, new_label: text, ts: Date.now() }
            });
        }
    });

    document.addEventListener('keydown', function(e) {
        var el = e.target;
        if (!el || el.contentEditable !== 'true') return;
        if (e.key === 'Enter') { e.preventDefault(); el.blur(); }
    });
})();
