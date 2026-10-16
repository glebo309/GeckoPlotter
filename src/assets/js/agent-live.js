// Live mode in the status bar (services/live_agent.py): what the agent is doing, drawn as three drops that drift
// apart and flow together again. Their paths come from smooth noise while working; otherwise they settle into one
// dot: grey without a connection, blue when connected, amber when stopped. The page asks the app once a second; when its change
// counter moves, it hands it to Dash (agent-live-version) and the screen redraws (callbacks/live_callbacks.py).
(function () {
    'use strict';
    var STATE = '/_gecko/agent/state', HERE = '/_gecko/agent/here', STOP = '/_gecko/agent/stop';
    var seen = null;                     // the change counter already drawn
    var current = {};
    var el = null, who = null, doing = null, stop = null;

    // -- smooth 1D noise (gradient noise, two octaves) --------------------------------------------------------------
    function grad(i, seed) { var s = Math.sin(i * 127.1 + seed * 311.7) * 43758.5453; return (s - Math.floor(s)) * 2 - 1; }
    function noise1(t, seed) {
        var i = Math.floor(t), f = t - i, u = f * f * (3 - 2 * f);
        var a = grad(i, seed) * f, b = grad(i + 1, seed) * (f - 1);
        return (a + (b - a) * u) * 2;
    }
    // Spread towards the edges (tanh), so the drops are often wholly apart and often one: about 12 % and 15 % of the time.
    function noise(t, seed) { return Math.tanh(2.6 * (0.7 * noise1(t, seed) + 0.3 * noise1(t * 2.3 + 17, seed + 5))); }

    // -- the drops --------------------------------------------------------------------------------------------------
    var W = 44, H = 16, NS = 'http://www.w3.org/2000/svg';
    var drops = [{ r: 3.4, seed: 1.3 }, { r: 3.0, seed: 4.7 }, { r: 2.6, seed: 9.1 }];
    var clock = Math.random() * 100, lastFrame = 0, spread = 0;

    function svg() {
        var root = document.createElementNS(NS, 'svg');
        root.setAttribute('width', W); root.setAttribute('height', H); root.setAttribute('viewBox', '0 0 ' + W + ' ' + H);
        root.setAttribute('class', 'agent-live-drops'); root.setAttribute('aria-hidden', 'true');
        root.innerHTML = '<defs><filter id="agent-live-goo" x="-30%" y="-60%" width="160%" height="220%">' +
            '<feGaussianBlur in="SourceGraphic" stdDeviation="1.5" result="b"/>' +
            '<feColorMatrix in="b" mode="matrix" values="1 0 0 0 0  0 1 0 0 0  0 0 1 0 0  0 0 0 16 -6.5"/></filter></defs>' +
            '<g filter="url(#agent-live-goo)"></g>';
        var group = root.querySelector('g');
        drops.forEach(function (d, i) {
            d.node = document.createElementNS(NS, 'circle');
            d.node.setAttribute('cx', W / 2); d.node.setAttribute('cy', H / 2);
            d.node.setAttribute('r', i === 0 ? d.r : 0); group.appendChild(d.node);
        });
        return root;
    }

    function frame(now) {
        window.requestAnimationFrame(frame);
        if (!el) show(current);                                      // Dash may mount after the first poll
        if (!el || el.hidden || now - lastFrame < 33) return;          // about 30 frames a second is plenty
        var dt = lastFrame ? Math.min((now - lastFrame) / 1000, 0.1) : 0;
        lastFrame = now;
        var working = (current.busy || current.working) && !current.stopped;
        spread = Math.max(0, Math.min(1, spread + (working ? dt : -dt) / 0.8));
        var ease = spread * spread * (3 - 2 * spread);                // split / merge over 0.8 seconds
        if (working) clock += dt * (current.busy ? 0.32 : 0.16);         // quicker while a call runs
        drops.forEach(function (d, i) {
            var x = W / 2 + noise(clock, d.seed) * (W / 2 - d.r - 1.5) * ease;
            var y = H / 2 + noise(clock * 0.8, d.seed + 50) * (H / 2 - d.r - 1) * ease;
            var r = i === 0 ? d.r : d.r * ease;
            d.node.setAttribute('cx', x.toFixed(2)); d.node.setAttribute('cy', y.toFixed(2));
            d.node.setAttribute('r', r.toFixed(2));
        });
    }

    // -- the status bar ---------------------------------------------------------------------------------------------
    function build() {
        el = document.getElementById('agent-live');
        if (!el || el.firstChild) return !!el;
        el.appendChild(svg());
        who = document.createElement('span'); who.className = 'agent-live-who';
        doing = document.createElement('span'); doing.className = 'agent-live-doing';
        stop = document.createElement('button'); stop.className = 'agent-live-stop'; stop.type = 'button';
        stop.addEventListener('click', function () {
            fetch(STOP, { method: 'POST', cache: 'no-store' }).then(function (r) { return r.json(); }).then(show).catch(function () {});
        });
        el.appendChild(who); el.appendChild(doing); el.appendChild(stop);
        return true;
    }

    function show(state) {
        current = state || {};
        if (!build()) return;
        var connected = current.connected || [];
        var working = !!(current.busy || current.working) && !current.stopped;
        var disconnected = !connected.length && !working && !current.stopped;
        el.hidden = false;
        el.classList.toggle('connected', !!connected.length);
        el.classList.toggle('busy', working);
        el.classList.toggle('stopped', !!current.stopped);
        who.hidden = doing.hidden = stop.hidden = disconnected;
        if (current.stopped || working) {
            who.textContent = (current.agent || connected.join(', ') || 'Agent') + ':';
            doing.textContent = current.stopped ? 'stopped' : !current.here ? 'works in another GeckoPlotter window' :
                current.busy ? current.doing : 'working';     // between its calls, until it has answered
        } else {
            who.textContent = connected.join(', ');
            doing.textContent = disconnected ? '' : 'connected';
        }
        el.title = disconnected ? 'No agent connected: connect one in About (click the logo)' :
            (working || !current.doing ? '' : 'Last: ' + current.doing);
        stop.textContent = current.stopped ? 'Let it work' : 'Stop';
        stop.title = current.stopped ? 'Let the agent work in GeckoPlotter again' : 'Refuse the agent’s calls until clicked again';
        if (typeof current.version !== 'number') return;
        if (seen === null) seen = current.version;                        // the page was drawn after these changes
        else if (current.version !== seen && window.dash_clientside && window.dash_clientside.set_props) {
            seen = current.version;
            window.dash_clientside.set_props('agent-live-version', { data: current.version });
        }
    }

    function ask() {
        fetch(STATE, { cache: 'no-store' }).then(function (r) { return r.ok ? r.json() : null; }).then(function (s) { if (s) show(s); })
            .catch(function () {});
    }

    var lastHere = 0;
    function here() {                                                     // the agent works in the window used last
        var now = Date.now();
        if (now - lastHere < 2000) return;
        lastHere = now;
        fetch(HERE, { method: 'POST', cache: 'no-store', keepalive: true }).then(ask).catch(function () {});
    }

    // -- the view the agent's call is about (services/live_focus): open the side view, then point it --------------
    function whenThere(id, then, tries) {
        if (document.getElementById(id)) { window.setTimeout(then, 700); return; }   // after the view's own setup
        if ((tries || 0) < 40) window.setTimeout(function () { whenThere(id, then, (tries || 0) + 1); }, 100);
    }
    function applyView(view) {
        var set = window.dash_clientside && window.dash_clientside.set_props;
        if (!view || !(view.side || view.results) || !set) return window.dash_clientside.no_update;
        if (view.results) {
            set('active-tab', { data: view.results });
            if (view.results === 'calibration' && view.calibration) {
                whenThere('cal-active-model', function () { set('cal-active-model', { value: view.calibration }); });
            }
        }
        if (!view.side) return view.version;
        set('side-tabs', { value: view.side });
        if (view.side === 'ms-scan' && view.scan != null) {
            whenThere('ms-scan-slider', function () {
                set('ms-scan-client-input', { value: null });
                window.setTimeout(function () { set('ms-scan-client-input', { value: view.scan }); }, 50);
            });
        } else if (view.side === 'ms-peak-mass' && view.peak) {
            whenThere('peak-mass-selector', function () {
                if (view.polarity) set('peak-mass-polarity-toggle', { value: view.polarity });
                set('peak-mass-selector', { value: view.peak });
            });
        }
        return view.version;
    }
    window.dash_clientside = window.dash_clientside || {};
    window.dash_clientside.geckoLive = { applyView: applyView };

    window.setInterval(function () { if (!document.hidden) ask(); }, 1000);
    window.addEventListener('focus', here);
    document.addEventListener('pointerdown', here, true);
    document.addEventListener('visibilitychange', function () { if (!document.hidden) here(); });
    show(current);
    here();
    window.requestAnimationFrame(frame);
})();
