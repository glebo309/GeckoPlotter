(function() {
    document.addEventListener('keydown', function(event) {
        if (event.key !== 'Enter' && event.key !== ' ') return;
        var row = event.target.closest('.file-tree-item');
        if (!row) return;
        event.preventDefault();
        row.click();
    });

    // -----------------------------------------------------------------------
    // 0. Finder-style multi-selection (client-side only, published to the
    //    'file-multi-selection' store so eye/trash callbacks can act on all rows)
    // -----------------------------------------------------------------------
    // Pure selection logic. `order` is the visible row keys top to bottom;
    // mods is {toggle, range}. Plain click selects just the clicked key.
    function computeSelection(state, order, key, mods) {
        var keys = (state && state.keys) || [];
        var anchor = state && state.anchor;
        mods = mods || {};
        if (mods.range) {
            var from = order.indexOf(anchor != null ? anchor : (keys.length ? keys[0] : key));
            var to = order.indexOf(key);
            if (from < 0) from = to;
            if (to < 0) return {keys: keys.slice(), anchor: anchor};
            var span = order.slice(Math.min(from, to), Math.max(from, to) + 1);
            var base = mods.toggle ? keys.filter(function(k) { return span.indexOf(k) < 0; }) : [];
            // The anchor stays put so repeated shift-clicks pivot around it.
            return {keys: base.concat(span), anchor: order[from]};
        }
        if (mods.toggle) {
            var at = keys.indexOf(key);
            return {keys: at >= 0 ? keys.filter(function(k) { return k !== key; }) : keys.concat([key]), anchor: key};
        }
        return {keys: [key], anchor: key};
    }
    window._geckoComputeSelection = computeSelection;

    var selection = {keys: [], anchor: null};
    var lastActiveSeen;

    function rowKey(row) {
        var key = row.getAttribute && row.getAttribute('data-file-key');
        if (key) return key;
        try { return row.id && row.id.charAt(0) === '{' ? JSON.parse(row.id).index : null; } catch (_) { return null; }
    }

    function treeRows() {
        return Array.prototype.slice.call(document.querySelectorAll('.file-tree-item'));
    }

    // Rows in on-screen order; rows inside a collapsed group/bundle are skipped.
    function visibleRowKeys(rows) {
        return rows.filter(function(r) { return r.offsetParent !== null; }).map(rowKey).filter(Boolean);
    }

    function publishSelection() {
        if (window.dash_clientside && window.dash_clientside.set_props) {
            window.dash_clientside.set_props('file-multi-selection', {data: selection.keys.slice()});
        }
    }

    function paintSelection(rows) {
        var chosen = {};
        selection.keys.forEach(function(k) { chosen[k] = true; });
        rows.forEach(function(row) {
            var key = rowKey(row);
            if (key && chosen[key]) row.classList.add('multi-selected');
            else row.classList.remove('multi-selected');
        });
    }

    function setSelection(next) {
        selection = next;
        paintSelection(treeRows());
        publishSelection();
    }

    // The active file may be a component of a sample row; resolve it to that row's key.
    function activeRowKey(rows, fileId) {
        for (var i = 0; i < rows.length; i++) {
            var id = null, sources = [];
            try { id = rows[i].id && rows[i].id.charAt(0) === '{' ? JSON.parse(rows[i].id).index : null; } catch (_) {}
            try { sources = JSON.parse(rows[i].getAttribute('data-sample-sources') || '[]'); } catch (_) {}
            if (fileId && (id === fileId || sources.indexOf(fileId) >= 0)) return rowKey(rows[i]);
        }
        return null;
    }

    // Re-apply after the tree re-renders; forget rows that no longer exist.
    window._geckoApplyMultiSelection = function() {
        if (!selection.keys.length) return;
        var rows = treeRows();
        var present = {};
        rows.forEach(function(r) { present[rowKey(r)] = true; });
        var kept = selection.keys.filter(function(k) { return present[k]; });
        paintSelection(rows);
        if (kept.length !== selection.keys.length) {
            selection = {keys: kept, anchor: present[selection.anchor] ? selection.anchor : null};
            paintSelection(rows);
            publishSelection();
        }
    };

    window._geckoGetFileSelection = function() { return selection.keys.slice(); };

    // Cmd/Ctrl-click toggles and Shift-click selects a range without activating the file
    // (Dash never sees the click); a plain click keeps the optimistic highlight below and
    // also resets the selection to that single row. The server's selection arrives a few
    // hundred ms later and agrees.
    document.addEventListener('click', function(event) {
        var target = event.target;
        if (!target || !target.closest) return;
        var row = target.closest('.file-tree-item');
        if (!row || target.closest('button, a, input, [id*="delete-btn"], [id*="visibility-btn"]')) return;
        var key = rowKey(row);
        var toggle = !!(event.metaKey || event.ctrlKey), range = !!event.shiftKey;
        if (key && (toggle || range)) {
            event.preventDefault();
            event.stopPropagation();
            var rows = treeRows();
            var state = selection;
            if (!state.keys.length) {
                // Nothing picked yet: the highlighted active file is the implicit first selection.
                var seed = activeRowKey(rows, window.__geckoActiveFile);
                if (seed) state = {keys: [seed], anchor: seed};
            }
            setSelection(computeSelection(state, visibleRowKeys(rows), key, {toggle: toggle, range: range}));
            return;
        }
        var id = null;
        try { id = row.id && row.id.charAt(0) === '{' ? JSON.parse(row.id).index : null; } catch (_) {}
        if (key) setSelection({keys: [key], anchor: key});
        if (id && window._geckoApplyActiveFile) window._geckoApplyActiveFile(id);
    }, true);

    // -----------------------------------------------------------------------
    // 1. File tree visual state — called by Dash clientside callback
    //    (MutationObservers on dcc.Store don't work in Dash 3.x)
    // -----------------------------------------------------------------------
    window._geckoApplyActiveFile = function(fileId) {
        window.__geckoActiveFile = fileId;
        document.querySelectorAll('.file-tree-item').forEach(function(el) {
            var elId = null;
            try {
                var raw = el.id;
                if (raw && raw.charAt(0) === '{') {
                    elId = JSON.parse(raw).index;
                }
            } catch(_) {}
            var belongsToSample = false;
            try { belongsToSample = JSON.parse(el.getAttribute('data-sample-sources') || '[]').indexOf(fileId) >= 0; } catch (_) {}
            if (elId && (elId === fileId || belongsToSample)) {
                el.classList.add('selected');
            } else {
                el.classList.remove('selected');
            }
        });
        // A *changed* active file outside the multi-selection (tab switch, upload, ...) ends it.
        // Re-applying the same active file after a re-render must not.
        if (fileId !== lastActiveSeen) {
            lastActiveSeen = fileId;
            if (selection.keys.length) {
                var activeKey = activeRowKey(treeRows(), fileId);
                if (activeKey && selection.keys.indexOf(activeKey) < 0) setSelection({keys: [], anchor: null});
            }
        }
    };

    window._geckoApplyHiddenFiles = function(hiddenIds) {
        window.__geckoHiddenFiles = hiddenIds || [];
        var hiddenSet = new Set(hiddenIds || []);
        document.querySelectorAll('button[id*="visibility-btn"]').forEach(function(button) {
            var fileId;
            try { fileId = JSON.parse(button.id).index; } catch (_) { return; }
            var hidden = hiddenSet.has(fileId);
            var icon = button.querySelector('img[data-visible-src]');
            if (icon) {
                icon.src = icon.getAttribute(hidden ? 'data-hidden-src' : 'data-visible-src');
            }
            var label = hidden ? 'Show trace' : 'Hide trace';
            button.title = label;
            button.setAttribute('aria-label', label);
            button.setAttribute('aria-pressed', hidden ? 'false' : 'true');
        });
        // Grouped files: dim the .draggable-file-item wrapper
        document.querySelectorAll('.draggable-file-item').forEach(function(el) {
            var fid = el.getAttribute('data-file-id');
            if (fid && hiddenSet.has(fid)) {
                el.classList.add('file-hidden');
            } else {
                el.classList.remove('file-hidden');
            }
        });
        // Bundle children & ungrouped files: dim the parent grid row
        document.querySelectorAll('.file-tree-item').forEach(function(el) {
            var elId = null;
            try {
                var raw = el.id;
                if (raw && raw.charAt(0) === '{') {
                    elId = JSON.parse(raw).index;
                }
            } catch(_) {}
            if (!elId) return;
            if (el.closest('.draggable-file-item')) return;
            var row = el.parentElement;
            if (!row) return;
            if (hiddenSet.has(elId)) {
                row.classList.add('file-hidden');
            } else {
                row.classList.remove('file-hidden');
            }
        });
    };

    // -----------------------------------------------------------------------
    // 2. Group collapse/expand on header click
    // -----------------------------------------------------------------------
    var groupCollapseState = {};

    function initGroupCollapse() {
        document.querySelectorAll('.file-group-header').forEach(function(header) {
            if (header._collapseInit || (header.classList && header.classList.contains('native-disclosure'))) return;
            header._collapseInit = true;
            header.style.cursor = 'pointer';
            header.style.userSelect = 'none';
            var existingContainer = header.nextElementSibling;
            try {
                var groupId = JSON.parse(existingContainer.id).index;
                if (groupCollapseState[groupId]) existingContainer.style.display = 'none';
            } catch (_) {}
            header.setAttribute('role', 'button');
            header.setAttribute('tabindex', '0');
            header.setAttribute('aria-expanded', existingContainer && existingContainer.style.display === 'none' ? 'false' : 'true');
            header.addEventListener('keydown', function (event) {
                if (event.target !== header || (event.key !== 'Enter' && event.key !== ' ')) return;
                event.preventDefault();
                header.click();
            });

            header.addEventListener('click', function(e) {
                if (e.target.tagName === 'BUTTON' || e.target.closest('button')) return;

                var container = header.nextElementSibling;
                if (!container || !container.classList.contains('file-group-container')) return;

                var isCollapsed = container.style.display === 'none';
                container.style.display = isCollapsed ? '' : 'none';
                header.setAttribute('aria-expanded', isCollapsed ? 'true' : 'false');

                var indicator = header.querySelector('.collapse-indicator');
                if (!indicator) {
                    indicator = document.createElement('span');
                    indicator.className = 'collapse-indicator';
                    indicator.style.cssText = 'margin-right:4px;font-size:9px;transition:transform 0.15s;display:inline-block;';
                    header.insertBefore(indicator, header.firstChild);
                }
                indicator.textContent = isCollapsed ? '▼' : '▶';

                try {
                    var parsed = JSON.parse(container.id);
                    groupCollapseState[parsed.index] = !isCollapsed;
                } catch(_) {}
            });

            if (!header.querySelector('.collapse-indicator')) {
                var indicator = document.createElement('span');
                indicator.className = 'collapse-indicator';
                indicator.style.cssText = 'margin-right:4px;font-size:9px;display:inline-block;';
                indicator.textContent = existingContainer && existingContainer.style.display === 'none' ? '▶' : '▼';
                header.insertBefore(indicator, header.firstChild);
            }
        });
    }

    // -----------------------------------------------------------------------
    // 3. Cross-group drag-drop (move files between groups / create new group)
    // -----------------------------------------------------------------------
    function initCrossGroupDrop() {
        document.querySelectorAll('.file-group-header').forEach(function(header) {
            if (header._crossDropInit) return;
            header._crossDropInit = true;

            header.addEventListener('dragover', function(e) {
                e.preventDefault();
                e.dataTransfer.dropEffect = 'move';
                header.style.backgroundColor = '#f0f0f0';
                header.style.borderBottom = '2px solid #1a1a1a';
            });

            header.addEventListener('dragleave', function() {
                header.style.backgroundColor = '';
                header.style.borderBottom = '';
            });

            header.addEventListener('drop', function(e) {
                e.preventDefault();
                e.stopPropagation();
                header.style.backgroundColor = '';
                header.style.borderBottom = '';

                var fileId = e.dataTransfer.getData('text/plain');
                if (!fileId) return;

                var container = header.nextElementSibling;
                var targetGroup = null;
                if (container) {
                    try {
                        targetGroup = JSON.parse(container.id).index;
                    } catch(_) {}
                }

                var srcEl = document.querySelector('.draggable-file-item[data-file-id="' + fileId + '"]');
                var sourceGroup = null;
                if (srcEl && srcEl.parentNode) {
                    try {
                        sourceGroup = JSON.parse(srcEl.parentNode.id).index;
                    } catch(_) {}
                }

                if (sourceGroup && targetGroup && sourceGroup !== targetGroup) {
                    fireGroupMoveEvent(fileId, sourceGroup, targetGroup);
                }
            });
        });

        var fileTree = document.getElementById('file-tree');
        if (fileTree && !fileTree._crossDropInit) {
            fileTree._crossDropInit = true;

            fileTree.addEventListener('dragover', function(e) {
                var target = e.target;
                if (target === fileTree || target.classList.contains('file-group-header')) {
                    e.preventDefault();
                    e.dataTransfer.dropEffect = 'move';
                }
            });

            fileTree.addEventListener('drop', function(e) {
                if (e.target !== fileTree) return;
                e.preventDefault();

                var fileId = e.dataTransfer.getData('text/plain');
                if (!fileId) return;

                var srcEl = document.querySelector('.draggable-file-item[data-file-id="' + fileId + '"]');
                var sourceGroup = null;
                if (srcEl && srcEl.parentNode) {
                    try {
                        sourceGroup = JSON.parse(srcEl.parentNode.id).index;
                    } catch(_) {}
                }

                if (sourceGroup) {
                    fireGroupMoveEvent(fileId, sourceGroup, null);
                }
            });
        }
    }

    function fireGroupMoveEvent(fileId, sourceGroup, targetGroup) {
        if (window.dash_clientside && window.dash_clientside.set_props) {
            window.dash_clientside.set_props('group-move-event', {
                data: {
                    file_id: fileId,
                    source_group: sourceGroup,
                    target_group: targetGroup,
                    ts: Date.now()
                }
            });
        }
    }

    // -----------------------------------------------------------------------
    // 4. Re-init interactive features after DOM changes
    // -----------------------------------------------------------------------
    var treeEl = document.getElementById('file-tree');
    if (treeEl) {
        new MutationObserver(function() {
            initGroupCollapse();
        }).observe(treeEl, { childList: true, subtree: true });
    }

    var observer = new MutationObserver(function() {
        initGroupCollapse();
        initCrossGroupDrop();
        window._geckoApplyActiveFile(window.__geckoActiveFile);
        window._geckoApplyHiddenFiles(window.__geckoHiddenFiles);
        window._geckoApplyMultiSelection();
    });
    observer.observe(document.body, { childList: true, subtree: true });
    document.addEventListener('DOMContentLoaded', function() {
        initGroupCollapse();
        initCrossGroupDrop();
    });
})();
