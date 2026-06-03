(function () {
    'use strict';

    var armedClass = 'global-drop-zone--armed';
    var hideTimer = null;

    function zone() {
        return document.getElementById('global-drop-zone');
    }

    function eventHasFiles(event) {
        var transfer = event.dataTransfer;
        if (!transfer || !transfer.types) return false;
        for (var i = 0; i < transfer.types.length; i++) {
            if (transfer.types[i] === 'Files') return true;
        }
        return false;
    }

    function arm() {
        var el = zone();
        if (!el) return;
        if (hideTimer) {
            window.clearTimeout(hideTimer);
            hideTimer = null;
        }
        el.classList.add(armedClass);
    }

    function disarmSoon() {
        if (hideTimer) window.clearTimeout(hideTimer);
        hideTimer = window.setTimeout(function () {
            var el = zone();
            if (el) el.classList.remove(armedClass);
        }, 180);
    }

    window.addEventListener('dragenter', function (event) {
        if (!eventHasFiles(event)) return;
        arm();
    }, true);

    window.addEventListener('dragover', function (event) {
        if (!eventHasFiles(event)) return;
        event.preventDefault();
        arm();
    }, true);

    window.addEventListener('dragleave', function (event) {
        if (!eventHasFiles(event)) return;
        if (event.clientX <= 0 || event.clientY <= 0 ||
                event.clientX >= window.innerWidth || event.clientY >= window.innerHeight) {
            disarmSoon();
        }
    }, true);

    window.addEventListener('drop', function () {
        disarmSoon();
    }, true);

    window.addEventListener('keyup', function (event) {
        if (event.key === 'Escape') disarmSoon();
    }, true);
}());
