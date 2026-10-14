/*
 * heartbeat.js
 * Tells the app this page is still open (see services/idle_exit.py), so a GeckoPlotter started without a window
 * can stop itself once the last tab is closed.
 */
(function () {
    'use strict';
    function beat() {
        try { fetch('/_gecko/alive', { method: 'POST', keepalive: true, cache: 'no-store' }).catch(function () {}); }
        catch (e) { /* the page is closing */ }
    }
    beat();
    window.setInterval(beat, 20000);
    document.addEventListener('visibilitychange', function () { if (!document.hidden) beat(); });
})();
