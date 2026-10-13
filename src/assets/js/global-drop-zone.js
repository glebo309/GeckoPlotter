// Drop files from Finder anywhere on the window to open them.
//
// Every drop outside the places that already accept files (the file explorer, the project picker, ...) is handed to
// the main upload input, so it goes through exactly the same import path as the "+" button: instrument files,
// projects (.gecko), methods (.lcm) and whole folders. While files are dragged over the window a hint is shown.
(function () {
    'use strict';

    var OWN_ZONES = '#drop-zone, #global-drop-zone, #session-open-upload, #cal-load-upload, #recipe-apply-upload';
    var MAX_FILES = 500;
    var overlay = null;
    var hideTimer = null;

    function hasFiles(event) {
        var types = event.dataTransfer && event.dataTransfer.types;
        if (!types) return false;
        for (var i = 0; i < types.length; i++) if (types[i] === 'Files') return true;
        return false;
    }

    function inOwnZone(event) {
        var target = event.target;
        return !!(target && target.closest && target.closest(OWN_ZONES));
    }

    function showHint() {
        if (hideTimer) { window.clearTimeout(hideTimer); hideTimer = null; }
        if (!overlay) {
            overlay = document.createElement('div');
            overlay.className = 'gecko-drop-overlay';
            overlay.setAttribute('aria-hidden', 'true');
            overlay.innerHTML = '<div class="gecko-drop-overlay__title">Drop files to open</div>' +
                '<div class="gecko-drop-overlay__subtitle">Shimadzu .lcd or .txt, Agilent, CSV, Excel, .lcm methods, ' +
                '.gecko projects, or a whole folder</div>';
        }
        if (!overlay.parentNode) document.body.appendChild(overlay);
    }

    function hideHint() {
        if (hideTimer) { window.clearTimeout(hideTimer); hideTimer = null; }
        if (overlay && overlay.parentNode) overlay.parentNode.removeChild(overlay);
    }

    function hideSoon() {
        if (hideTimer) window.clearTimeout(hideTimer);
        hideTimer = window.setTimeout(hideHint, 160);
    }

    // Files of a drop, with folders expanded. Falls back to the plain file list.
    function collectFiles(dataTransfer) {
        var items = dataTransfer.items;
        var entries = [];
        if (items && items.length && typeof items[0].webkitGetAsEntry === 'function') {
            for (var i = 0; i < items.length; i++) {
                var entry = items[i].kind === 'file' ? items[i].webkitGetAsEntry() : null;
                if (entry) entries.push(entry);
            }
        }
        if (!entries.length) return Promise.resolve(Array.prototype.slice.call(dataTransfer.files || []));
        var files = [];
        function walk(entry) {
            if (files.length >= MAX_FILES) return Promise.resolve();
            if (entry.isFile) {
                return new Promise(function (resolve) {
                    entry.file(function (file) { files.push(file); resolve(); }, function () { resolve(); });
                });
            }
            if (!entry.isDirectory) return Promise.resolve();
            return new Promise(function (resolve) {
                var reader = entry.createReader();
                var children = [];
                (function read() {
                    reader.readEntries(function (batch) {
                        if (!batch.length) {
                            children.reduce(function (chain, child) {
                                return chain.then(function () { return walk(child); });
                            }, Promise.resolve()).then(resolve);
                        } else {
                            children = children.concat(Array.prototype.slice.call(batch));
                            read();
                        }
                    }, function () { resolve(); });
                })();
            });
        }
        return entries.reduce(function (chain, entry) {
            return chain.then(function () { return walk(entry); });
        }, Promise.resolve()).then(function () { return files; });
    }

    function hand(files) {
        if (!files.length) return;
        var fast = window.GeckoFastUpload;
        if (fast && !files.some(fast.isProject)) { fast.upload(files.slice(0, MAX_FILES), 'upload-button'); return; }
        var input = document.querySelector('#upload-button input[type="file"]');
        if (!input) return;
        var transfer = new DataTransfer();
        files.slice(0, MAX_FILES).forEach(function (file) { transfer.items.add(file); });
        input.files = transfer.files;
        input.dispatchEvent(new Event('change', {bubbles: true}));
    }

    function onDragOver(event) {
        if (!hasFiles(event)) return;
        if (inOwnZone(event)) { hideSoon(); return; }
        event.preventDefault();                 // makes the whole window a valid drop target
        if (event.dataTransfer) event.dataTransfer.dropEffect = 'copy';
        showHint();
    }

    function onDragLeave(event) {
        if (!hasFiles(event)) return;
        if (event.clientX <= 0 || event.clientY <= 0 ||
                event.clientX >= window.innerWidth || event.clientY >= window.innerHeight) hideSoon();
    }

    function onDrop(event) {
        if (!hasFiles(event)) return;
        hideHint();
        if (inOwnZone(event) || event.defaultPrevented) return;
        event.preventDefault();
        event.stopPropagation();
        collectFiles(event.dataTransfer).then(hand);
    }

    window.addEventListener('dragenter', onDragOver, true);
    window.addEventListener('dragover', onDragOver, true);
    window.addEventListener('dragleave', onDragLeave, true);
    window.addEventListener('drop', onDrop, true);
    window.addEventListener('keyup', function (event) { if (event.key === 'Escape') hideHint(); }, true);
    window.GeckoDropAnywhere = {collectFiles: collectFiles, hasFiles: hasFiles};
}());
