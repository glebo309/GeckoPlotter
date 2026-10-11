(function() {
    document.addEventListener('keydown', function(event) {
        if (event.key !== 'Enter' && event.key !== ' ') return;
        var row = event.target.closest('.file-tree-item');
        if (!row) return;
        event.preventDefault();
        row.click();
    });

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
            if (elId && elId === fileId) {
                el.classList.add('selected');
            } else {
                el.classList.remove('selected');
            }
        });
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
            if (header._collapseInit) return;
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
    });
    observer.observe(document.body, { childList: true, subtree: true });
    document.addEventListener('DOMContentLoaded', function() {
        initGroupCollapse();
        initCrossGroupDrop();
    });
})();
