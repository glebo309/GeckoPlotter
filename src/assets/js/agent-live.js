// Live mode in the status bar (services/live_agent.py): what the agent is doing, drawn as three drops that drift
// apart and flow together again. Their paths come from smooth noise, so the motion never repeats: slow and grey while
// the agent waits, quicker and green while it works. The page asks the app once a second; when the app's change
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
    function noise(t, seed) { return 0.7 * noise1(t, seed) + 0.3 * noise1(t * 2.3 + 17, seed + 5); }

    // -- the drops --------------------------------------------------------------------------------------------------
    var W = 34, H = 16, NS = 'http://www.w3.org/2000/svg';
    var drops = [{ r: 3.6, seed: 1.3 }, { r: 3.1, seed: 4.7 }, { r: 2.6, seed: 9.1 }];
    var clock = Math.random() * 100, lastFrame = 0;

    function svg() {
        var root = document.createElementNS(NS, 'svg');
        root.setAttribute('width', W); root.setAttribute('height', H); root.setAttribute('viewBox', '0 0 ' + W + ' ' + H);
        root.setAttribute('class', 'agent-live-drops'); root.setAttribute('aria-hidden', 'true');
        root.innerHTML = '<defs><filter id="agent-live-goo" x="-30%" y="-60%" width="160%" height="220%">' +
            '<feGaussianBlur in="SourceGraphic" stdDeviation="1.5" result="b"/>' +
            '<feColorMatrix in="b" mode="matrix" values="1 0 0 0 0  0 1 0 0 0  0 0 1 0 0  0 0 0 16 -6.5"/></filter></defs>' +
            '<g filter="url(#agent-live-goo)"></g>';
        var group = root.querySelector('g');
        drops.forEach(function (d) { d.node = document.createElementNS(NS, 'circle'); d.node.setAttribute('r', d.r); group.appendChild(d.node); });
        return root;
    }

    function frame(now) {
        window.requestAnimationFrame(frame);
        if (!el || el.hidden || now - lastFrame < 33) return;          // about 30 frames a second is plenty
        var dt = lastFrame ? Math.min((now - lastFrame) / 1000, 0.1) : 0;
        lastFrame = now;
        clock += dt * (current.busy ? 0.32 : 0.07);                      // working: quicker; waiting: barely drifting
        drops.forEach(function (d) {
            var x = W / 2 + noise(clock, d.seed) * (W / 2 - d.r - 1.5);
            var y = H / 2 + noise(clock * 0.8, d.seed + 50) * (H / 2 - d.r - 1);
            d.node.setAttribute('cx', x.toFixed(2)); d.node.setAttribute('cy', y.toFixed(2));
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
        el.hidden = !current.agent && !current.stopped;                 // nothing until an agent has called
        el.classList.toggle('busy', !!current.busy);
        el.classList.toggle('stopped', !!current.stopped);
        who.textContent = (current.agent || 'Agent') + ':';
        if (current.stopped) doing.textContent = 'stopped';
        else if (!current.here) doing.textContent = 'works in another GeckoPlotter window';
        else doing.textContent = current.busy ? current.doing : 'ready';
        el.title = current.busy || !current.doing ? '' : 'Last: ' + current.doing;
        stop.textContent = current.stopped ? 'Let it work' : 'Stop';
        stop.title = current.stopped ? 'Let the agent work in GeckoPlotter again' : 'Refuse the agent’s calls until clicked again';
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

    window.setInterval(function () { if (!document.hidden) ask(); }, 1000);
    window.addEventListener('focus', here);
    document.addEventListener('pointerdown', here, true);
    document.addEventListener('visibilitychange', function () { if (!document.hidden) here(); });
    here();
    window.requestAnimationFrame(frame);
})();
