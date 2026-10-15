// Inactive tab panels are not drawn (keepMounted=False on the Tabs): every drawn Dash component is re-checked on each
// store update, so hidden panels slowed every callback. Dash 3.0 draws a panel's contents, when it is opened, from a
// copy its parent took on the parent's own last render. Anything a callback changed while the panel was hidden (a new
// table, the metadata, an input's value) would show stale, and so would changes made while the panel was open once it
// is closed and opened again. So a panel whose contents changed is re-rendered when it is hidden (its contents stay
// undrawn) and holds the current contents by the time it is opened. A panel opened by the same update that changed it
// is refreshed right after it is drawn.
(function () {
    'use strict';
    var TABS = ['toolbox-tabs', 'analysis-tabs', 'side-tabs'];
    var seen = {}, shown = {}, queued = false;

    function at(layout, path) {
        var node = layout;
        for (var i = 0; i < path.length && node; i++) node = node[path[i]];
        return node;
    }

    function refresh(store, path, node) {
        store.dispatch({type: 'ON_PROP_CHANGE', payload: {
            itempath: path, props: {children: node.props.children}, renderType: 'internal', source: 'response'}});
    }

    function check(store) {
        queued = false;
        var state = store.getState(), strs = (state.paths && state.paths.strs) || {};
        TABS.forEach(function (id) {
            var tabsPath = strs[id], tabs = tabsPath && at(state.layout, tabsPath);
            if (!tabs || !tabs.props || tabs.props.keepMounted !== false || !Array.isArray(tabs.props.children)) return;
            tabs.props.children.forEach(function (panel, i) {
                if (!panel || panel.type !== 'TabsPanel' || !panel.props || panel.props.keepMounted) return;
                var path = tabsPath.concat(['props', 'children', i]), key = path.join('.');
                var open = panel.props.value === tabs.props.value, wasOpen = shown[key];
                shown[key] = open;
                if (!(key in seen)) { seen[key] = panel; return; }      // first sight: drawn from the current layout
                if (seen[key] === panel) return;                         // nothing changed since the last refresh
                // Refresh a hidden panel (changed while hidden, or changed while open and now closed: it would reopen
                // from the old copy) and one opened by the same update that changed it. An open panel draws its own
                // changes; it is refreshed when it closes.
                if (open && wasOpen) return;
                refresh(store, path, panel);
                seen[key] = at(store.getState().layout, path);
            });
        });
    }

    function attach() {
        var store = (window.dash_stores && window.dash_stores[0]) || window.store;
        if (!store || !store.subscribe) { setTimeout(attach, 50); return; }
        store.subscribe(function () {
            if (queued) return;
            queued = true;
            Promise.resolve().then(function () { check(store); });
        });
    }
    attach();
})();
