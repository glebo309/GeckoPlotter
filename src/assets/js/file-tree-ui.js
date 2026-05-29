(function() {
    // -----------------------------------------------------------------------
    // 1. Dim hidden files in the file tree (CSS-only, no tree re-render)
    // -----------------------------------------------------------------------
    function applyHiddenFiles(hiddenIds) {
        if (!hiddenIds) hiddenIds = [];
        var hiddenSet = new Set(hiddenIds);
        document.querySelectorAll('.draggable-file-item').forEach(function(el) {
            var fid = el.getAttribute('data-file-id');
            if (fid && hiddenSet.has(fid)) {
                el.style.opacity = '0.45';
            } else {
                el.style.opacity = '';
            }
        });
    }

    // Watch the hidden-files store
    var hiddenStore = document.getElementById('hidden-files');
    if (hiddenStore) {
        new MutationObserver(function() {
            try {
                var data = JSON.parse(hiddenStore.textContent || '[]');
                applyHiddenFiles(data);
            } catch(e) {}
        }).observe(hiddenStore, { childList: true, characterData: true, subtree: true });
    }

    // Also apply after tree re-renders (file tree DOM changes)
    var treeEl = document.getElementById('file-tree');
    if (treeEl) {
        new MutationObserver(function() {
            var hs = document.getElementById('hidden-files');
            if (hs) {
                try {
                    var data = JSON.parse(hs.textContent || '[]');
                    applyHiddenFiles(data);
                } catch(e) {}
            }
            var af = document.getElementById('active-file');
            if (af) {
                try { applyActiveFile(JSON.parse(af.textContent || '')); } catch(_) {}
            }
            initGroupCollapse();
        }).observe(treeEl, { childList: true, subtree: true });
    }

    // -----------------------------------------------------------------------
    // 1b. CSS-only active-file selection highlight (avoids full tree re-render)
    // -----------------------------------------------------------------------
    function applyActiveFile(fileId) {
        document.querySelectorAll('.file-tree-item').forEach(function(el) {
            var elId = null;
            try {
                var raw = el.id;
                if (raw && raw.charAt(0) === '{') {
                    elId = JSON.parse(raw).index;
                }
            } catch(_) {}
            if (elId && elId === fileId) {
                el.style.backgroundColor = '#fff5f0';
                el.style.borderLeft = '2px solid #ff6b35';
                el.style.fontWeight = '500';
            } else {
                el.style.backgroundColor = '';
                el.style.borderLeft = '';
                el.style.fontWeight = '';
            }
        });
    }

    var activeFileStore = document.getElementById('active-file');
    if (activeFileStore) {
        new MutationObserver(function() {
            try {
                var raw = activeFileStore.textContent || '';
                var fid = JSON.parse(raw);
                applyActiveFile(fid);
            } catch(_) {}
        }).observe(activeFileStore, { childList: true, characterData: true, subtree: true });
    }

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

            header.addEventListener('click', function(e) {
                // Don't collapse if clicking the sort button
                if (e.target.tagName === 'BUTTON' || e.target.closest('button')) return;

                var container = header.nextElementSibling;
                if (!container || !container.classList.contains('file-group-container')) return;

                var isCollapsed = container.style.display === 'none';
                container.style.display = isCollapsed ? '' : 'none';

                // Update collapse indicator
                var indicator = header.querySelector('.collapse-indicator');
                if (!indicator) {
                    indicator = document.createElement('span');
                    indicator.className = 'collapse-indicator';
                    indicator.style.cssText = 'margin-right:4px;font-size:9px;transition:transform 0.15s;display:inline-block;';
                    header.insertBefore(indicator, header.firstChild);
                }
                indicator.textContent = isCollapsed ? '▼' : '▶';

                // Persist state
                try {
                    var parsed = JSON.parse(container.id);
                    groupCollapseState[parsed.index] = !isCollapsed;
                } catch(_) {}
            });

            // Add initial collapse indicator
            if (!header.querySelector('.collapse-indicator')) {
                var indicator = document.createElement('span');
                indicator.className = 'collapse-indicator';
                indicator.style.cssText = 'margin-right:4px;font-size:9px;display:inline-block;';
                indicator.textContent = '▼';
                header.insertBefore(indicator, header.firstChild);
            }
        });
    }

    // -----------------------------------------------------------------------
    // 3. Cross-group drag-drop (move files between groups / create new group)
    // -----------------------------------------------------------------------
    function initCrossGroupDrop() {
        // Make group headers drop targets (merge into group)
        document.querySelectorAll('.file-group-header').forEach(function(header) {
            if (header._crossDropInit) return;
            header._crossDropInit = true;

            header.addEventListener('dragover', function(e) {
                e.preventDefault();
                e.dataTransfer.dropEffect = 'move';
                header.style.backgroundColor = '#fff5f0';
                header.style.borderBottom = '2px solid #ff6b35';
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

                // Find target group ID from next sibling container
                var container = header.nextElementSibling;
                var targetGroup = null;
                if (container) {
                    try {
                        targetGroup = JSON.parse(container.id).index;
                    } catch(_) {}
                }

                // Find source group
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

        // Make the file-tree itself a drop target (drop outside any group = new group)
        var fileTree = document.getElementById('file-tree');
        if (fileTree && !fileTree._crossDropInit) {
            fileTree._crossDropInit = true;

            fileTree.addEventListener('dragover', function(e) {
                // Only highlight if dragging over the tree background, not a child
                var target = e.target;
                if (target === fileTree || target.classList.contains('file-group-header')) {
                    e.preventDefault();
                    e.dataTransfer.dropEffect = 'move';
                }
            });

            fileTree.addEventListener('drop', function(e) {
                // Only handle drops directly on the tree (not on group containers)
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
    // Initialize on DOM changes
    // -----------------------------------------------------------------------
    var observer = new MutationObserver(function() {
        initGroupCollapse();
        initCrossGroupDrop();
    });
    observer.observe(document.body, { childList: true, subtree: true });
    document.addEventListener('DOMContentLoaded', function() {
        initGroupCollapse();
        initCrossGroupDrop();
    });
})();
