// Action names only. Never read control values, plot contents, document text or error messages.
(function () {
    'use strict';
    var last = {}, endpoint = '/_gecko/diagnostics/event';
    function send(event) {
        if (!window.fetch) return;
        window.fetch(endpoint, {method:'POST', headers:{'Content-Type':'application/json'},
            body:JSON.stringify(event), keepalive:true}).catch(function () {});
    }
    function control(target) {
        var node = target && target.closest && target.closest('button, input, select, [role="button"], [role="tab"], [role="switch"]');
        if (!node || !node.id) return null;
        var id = node.id;
        if (id[0] === '{') {
            try { id = JSON.parse(id).type; } catch (_) { return null; }
        }
        return typeof id === 'string' && /^[a-z][a-z0-9-]{0,80}$/.test(id) ? id : null;
    }
    ['click','change'].forEach(function (action) {
        document.addEventListener(action, function (event) {
            var id = control(event.target), key = action + ':' + id, now = Date.now();
            if (!id || now - (last[key] || 0) < 300) return;
            last[key] = now;
            send({event:'ui_action',control:id,action:action});
        }, true);
    });
    function error(value) {
        var name = value && value.name;
        send({event:'client_error',error_type:typeof name === 'string' && /^[A-Za-z]+Error$/.test(name) ? name : 'Error'});
    }
    window.addEventListener('error', function (event) { error(event.error); });
    window.addEventListener('unhandledrejection', function (event) { error(event.reason); });
    send({event:'page_loaded'});
})();
