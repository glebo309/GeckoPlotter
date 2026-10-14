// Fast uploads: send each file as raw bytes (gzip-compressed when the browser can) to /_gecko/upload and give the
// upload callbacks a short token instead of Dash's base64 text. A 20 MB Shimadzu run travels as about 14 MB instead of
// 27 MB of text, an ASCII export as about 8 MB instead of 23 MB, and nothing is base64-encoded, sent inside JSON or
// parsed again. Projects (.gecko, .zip) keep the normal path. Any failure falls back to the normal path too.
(function () {
    'use strict';

    var ENDPOINT = '/_gecko/upload';
    var TOKEN_PREFIX = 'gecko-upload:';
    var MIN_COMPRESS = 256 * 1024;
    var PARALLEL = 3;
    var legacy = false;                       // set while we hand files to Dash's own upload on purpose

    function isProject(file) { return /\.(gecko|zip)$/i.test(file.name || ''); }
    function anyProject(files) { for (var i = 0; i < files.length; i++) if (isProject(files[i])) return true; return false; }
    function megabytes(bytes) { return (bytes / 1e6).toFixed(bytes >= 1e7 ? 0 : 1) + ' MB'; }

    function status(text) {
        if (window.dash_clientside && window.dash_clientside.set_props) {
            window.dash_clientside.set_props('status-text', {children: text});
        }
    }

    // Compressing pays off over a network (the shared lab server); when GeckoPlotter runs on this computer (the
    // one-click launcher) it only costs time: 7 ASCII exports of 17.6 MB took ~3 s to gzip and unzip again.
    var LOCAL = /^(localhost|127\.0\.0\.1|\[::1\])$/.test(window.location.hostname);

    function send(file) {
        var compress = !LOCAL && typeof CompressionStream === 'function' && file.size > MIN_COMPRESS;
        var body = compress
            ? new Response(file.stream().pipeThrough(new CompressionStream('gzip'))).blob()
            : Promise.resolve(file);
        return body.then(function (blob) {
            return fetch(ENDPOINT, {
                method: 'POST', body: blob,
                headers: {'X-Gecko-Name': encodeURIComponent(file.name), 'X-Gecko-Encoding': compress ? 'gzip' : 'identity'}
            });
        }).then(function (response) {
            if (!response.ok) throw new Error('upload refused');
            return response.json();
        }).then(function (result) {
            return {token: result.token, file: file};
        });
    }

    function sendAll(files) {
        var results = new Array(files.length);
        var next = 0, done = 0, total = files.reduce(function (s, f) { return s + f.size; }, 0);
        return new Promise(function (resolve, reject) {
            function pump() {
                if (next >= files.length) return;
                var index = next++;
                send(files[index]).then(function (item) {
                    results[index] = item;
                    done += 1;
                    status('Sent ' + done + ' of ' + files.length + ' files (' + megabytes(total) + ' in all)…');
                    if (done === files.length) resolve(results); else pump();
                }, reject);
            }
            for (var i = 0; i < Math.min(PARALLEL, files.length); i++) pump();
        });
    }

    function handOverToDash(files, target) {
        // Dash's own base64 path, used for projects and when the fast path fails.
        var input = document.querySelector('#' + target + ' input[type="file"]');
        if (!input || !window.DataTransfer) return;
        var transfer = new DataTransfer();
        files.forEach(function (file) { transfer.items.add(file); });
        legacy = true;
        try {
            input.files = transfer.files;
            input.dispatchEvent(new Event('change', {bubbles: true}));
        } finally {
            legacy = false;
        }
    }

    function upload(files, target) {
        files = Array.prototype.slice.call(files);
        if (!files.length) return;
        status('Sending ' + files.length + (files.length === 1 ? ' file' : ' files') + '…');
        sendAll(files).then(function (items) {
            window.dash_clientside.set_props(target, {
                contents: items.map(function (item) { return TOKEN_PREFIX + item.token; }),
                filename: items.map(function (item) { return item.file.name; }),
                last_modified: items.map(function (item) { return Math.round((item.file.lastModified || Date.now()) / 1000); })
            });
        }, function () {
            status('Fast upload failed; sending the normal way…');
            handOverToDash(files, target);
        });
    }

    function targetOf(element) {
        var zone = element && element.closest && element.closest('#upload-button, #drop-zone');
        return zone ? zone.id : null;
    }

    function usable() {
        return window.fetch && window.dash_clientside && window.dash_clientside.set_props;
    }

    // The file pickers of the "+" button and of the explorer.
    window.addEventListener('change', function (event) {
        var input = event.target;
        if (legacy || !input || input.type !== 'file' || !usable()) return;
        var target = targetOf(input);
        if (!target || !input.files || !input.files.length || anyProject(input.files)) return;
        event.stopImmediatePropagation();
        event.preventDefault();
        var files = Array.prototype.slice.call(input.files);
        try { input.value = ''; } catch (error) { /* a second pick of the same file must fire again */ }
        upload(files, target);
    }, true);

    // Files dropped on the explorer (folders included). Drops elsewhere are taken by global-drop-zone.js.
    window.addEventListener('drop', function (event) {
        if (legacy || !usable()) return;
        var target = targetOf(event.target);
        var transfer = event.dataTransfer;
        if (target !== 'drop-zone' || !transfer || !transfer.files || !transfer.files.length) return;
        if (anyProject(transfer.files)) return;
        event.preventDefault();
        event.stopPropagation();
        var collect = window.GeckoDropAnywhere && window.GeckoDropAnywhere.collectFiles;
        (collect ? collect(transfer) : Promise.resolve(Array.prototype.slice.call(transfer.files))).then(function (files) {
            upload(files, 'drop-zone');
        });
    }, true);

    window.GeckoFastUpload = {upload: upload, isProject: isProject};
}());
