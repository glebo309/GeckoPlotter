// Many plot tabs (an LC-MS sequence opens one per run): the tab bar scrolls sideways (mouse wheel too, the active tab
// kept in view, faded edges where tabs are hidden), and the button after it lists every tab, with a filter, to jump to.
(function () {
    'use strict';
    var list = null;

    function bar() { return document.getElementById('plot-tab-bar'); }
    function more() { return document.getElementById('plot-tab-more'); }
    function tabs() { var b = bar(); return b ? Array.prototype.slice.call(b.querySelectorAll('.plot-tab-btn')) : []; }
    function label(tab) {
        var span = tab.querySelector('[id*="plot-tab-label"]') || tab;
        return (span.textContent || '').trim();
    }

    function update() {
        var b = bar(), m = more();
        if (!b || !m) return;
        var hidden = b.scrollWidth - b.clientWidth > 1;
        b.classList.toggle('overflow-left', b.scrollLeft > 1);
        b.classList.toggle('overflow-right', b.scrollLeft < b.scrollWidth - b.clientWidth - 1);
        m.hidden = !hidden;
        m.textContent = '▾ ' + tabs().length;
        m.setAttribute('aria-label', 'All ' + tabs().length + ' plot tabs');
    }

    function revealActive() {
        var active = bar() && bar().querySelector('.plot-tab-btn.active');
        if (active && active.scrollIntoView) active.scrollIntoView({block: 'nearest', inline: 'nearest'});
        update();
    }

    function close() {
        if (!list) return;
        list.remove();
        list = null;
        var m = more();
        if (m) m.setAttribute('aria-expanded', 'false');
    }

    function open() {
        var m = more();
        if (!m) return;
        close();
        list = document.createElement('div');
        list.className = 'plot-tab-list';
        list.setAttribute('role', 'listbox');
        var input = document.createElement('input');
        input.type = 'search';
        input.placeholder = 'Find a tab';
        input.setAttribute('aria-label', 'Find a plot tab');
        var items = document.createElement('div');
        items.className = 'items';
        list.appendChild(input);
        list.appendChild(items);

        function render() {
            var query = input.value.trim().toLowerCase();
            items.innerHTML = '';
            var shown = tabs().filter(function (tab) { return !query || label(tab).toLowerCase().indexOf(query) !== -1; });
            shown.forEach(function (tab, i) {
                var item = document.createElement('button');
                item.type = 'button';
                item.textContent = label(tab);
                item.title = label(tab);
                item.setAttribute('role', 'option');
                if (tab.classList.contains('active')) item.classList.add('current');
                if (i === 0 && query) item.classList.add('focus');
                item.addEventListener('click', function () { close(); tab.click(); setTimeout(revealActive, 60); });
                items.appendChild(item);
            });
            if (!shown.length) {
                var none = document.createElement('div');
                none.className = 'none';
                none.textContent = 'No tab matches';
                items.appendChild(none);
            }
        }
        input.addEventListener('input', render);
        input.addEventListener('keydown', function (event) {
            if (event.key === 'Escape') { event.preventDefault(); close(); m.focus(); }
            if (event.key === 'Enter') {
                var first = items.querySelector('button.focus') || items.querySelector('button');
                if (first) first.click();
            }
            event.stopPropagation();
        });
        render();
        document.body.appendChild(list);
        var r = m.getBoundingClientRect();
        list.style.top = (r.bottom + 6) + 'px';
        list.style.left = Math.max(8, Math.min(r.right - list.offsetWidth, window.innerWidth - list.offsetWidth - 8)) + 'px';
        m.setAttribute('aria-expanded', 'true');
        var current = items.querySelector('.current');
        if (current) current.scrollIntoView({block: 'nearest'});
        input.focus();
    }

    document.addEventListener('click', function (event) {
        if (event.target.closest && event.target.closest('#plot-tab-more')) {
            if (list) close(); else open();
            return;
        }
        if (list && !list.contains(event.target)) close();
    });
    document.addEventListener('wheel', function (event) {
        var b = bar();
        if (!b || !b.contains(event.target) || b.scrollWidth <= b.clientWidth) return;
        if (Math.abs(event.deltaY) > Math.abs(event.deltaX)) {
            b.scrollLeft += event.deltaY;
            event.preventDefault();
        }
    }, {passive: false});
    document.addEventListener('scroll', function (event) { if (event.target === bar()) update(); }, true);
    window.addEventListener('resize', update);

    var watched = null;
    var observer = new MutationObserver(function () { setTimeout(revealActive, 0); });
    (function attach() {
        var b = bar();
        if (b && b !== watched) {
            observer.disconnect();
            observer.observe(b, {childList: true, subtree: true, attributes: true, attributeFilter: ['class']});
            watched = b;
            revealActive();
        }
        setTimeout(attach, 1000);
    })();
})();
