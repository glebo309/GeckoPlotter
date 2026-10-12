(function () {
    // Per-plot settings live in the browser. Switching plots applies the stored
    // settings to the single shared control set in one clientside call; the
    // server is only asked when a context has never been seen in this session.
    //
    // Reference implementations (kept in Python and parity-tested):
    //   resolveContext   <-> plot_settings_callbacks.resolve_plot_context
    //   controlValues    <-> plot_settings_callbacks.hydrate_plot_settings
    //   panelVisibility  <-> plot_settings_callbacks.panel_visibility
    var HIDDEN_ECHO = [2, 3, 4];   // hidden label inputs: nobody listens, always written

    function nu() { return window.dash_clientside.no_update; }
    function has(o, k) { return o != null && Object.prototype.hasOwnProperty.call(o, k); }
    function get(o, k, d) { return has(o, k) ? o[k] : d; }
    function nz(v) { return v === undefined ? null : v; }

    function deepEqual(a, b) {
        if (a === b) return true;
        if (a == null || b == null || typeof a !== 'object' || typeof b !== 'object') return false;
        if (Array.isArray(a) !== Array.isArray(b)) return false;
        if (Array.isArray(a)) {
            if (a.length !== b.length) return false;
            for (var i = 0; i < a.length; i++) if (!deepEqual(a[i], b[i])) return false;
            return true;
        }
        var ka = Object.keys(a), kb = Object.keys(b);
        if (ka.length !== kb.length) return false;
        for (var j = 0; j < ka.length; j++) {
            if (!has(b, ka[j]) || !deepEqual(a[ka[j]], b[ka[j]])) return false;
        }
        return true;
    }

    // ---- context key ------------------------------------------------------
    function contextKey(activeFile, viewMode, activeTab, plotTab) {
        var suffix = plotTab ? ':' + plotTab : '';
        if ((viewMode || 'raw') === 'raw') return 'shared:raw' + suffix;
        if (activeTab === 'peak-analysis' || activeTab === 'across-samples') return 'shared:' + activeTab + suffix;
        if (activeFile) return 'file:' + activeFile + suffix;
        return null;
    }

    function resolveContext(activeFile, viewMode, activeTab, plotTab, current) {
        var key = contextKey(activeFile, viewMode, activeTab, plotTab);
        return key === (current === undefined ? null : current) ? nu() : key;
    }

    // ---- settings -> controls ---------------------------------------------
    function layoutOpts(s) {
        var opts = [];
        if (get(s, 'show_grid_x', true)) opts.push('grid_x');
        if (get(s, 'show_grid_y', true)) opts.push('grid_y');
        if (get(s, 'show_tick_marks', true)) opts.push('ticks');
        if (get(s, 'show_minor_ticks', false)) opts.push('minor_ticks');
        if (get(s, 'show_frame', true)) opts.push('frame');
        return opts;
    }

    function labelModes(defaults, saved) {
        var stored = (saved && saved.axis_label_modes) || {};
        var out = {};
        [['x', 'x_label'], ['y', 'y1_label']].forEach(function (pair) {
            var value = get(saved, pair[1], undefined);
            var custom = value !== undefined && value !== null && value !== defaults[pair[1]];
            out[pair[0]] = stored[pair[0]] || (custom ? 'custom' : 'auto');
        });
        return out;
    }

    // Same merge hydrate_plot_settings performs for a saved context.
    function normalize(defaults, saved, key) {
        var s = Object.assign({}, defaults, saved || {}, {_context_key: key});
        s.axis_label_modes = labelModes(defaults, saved || {});
        return s;
    }

    function seriesCount(s) {
        return Math.max(1, Number(get(s, 'y1_series_count', 1)) || 1);
    }

    // Order is the order of plot_settings_callbacks.HYDRATED_CONTROLS.
    function controlValues(s) {
        var v = [
            s.plot_type, s.y1_stats, s.x_label, s.y1_label, s.y2_label,
            !!s.show_raw_points, !!s.y2_enable,
            get(s, 'smooth_window', 0), s.plot_type, !!s.auto_range, !!get(s, 'categorical_x', true),
            s.x_min, s.x_max, s.y_min, s.y_max, s.x_scale, s.y_scale,
            s.theme, s.palette, s.bg_color, s.paper_color,
            s.line_width, s.marker_size, s.line_style, s.marker_symbol, s.trace_opacity,
            s.bar_gap, s.bar_group_gap, s.title, s.font, s.font_size, s.title_font_size, s.tick_font_size,
            !!s.bold_title, !!s.show_legend, s.legend_pos, layoutOpts(s), s.tick_direction, s.grid_style,
            get(s, 'frame_width', 1), get(s, 'tick_length', 5), get(s, 'layout_mode', 'overlay'),
            !!get(s, 'shared_axis_labels', false), s.x_label, s.y1_label, get(s, 'subplot_spacing', 0.08),
            s.subplot_rows, s.subplot_cols, s.figure_width_mm, s.figure_height_mm,
            s.pub_preset, s.pub_dpi, s.export_format, s.link_x, s.y_scope
        ];
        return v.map(nz);
    }

    // Outputs: [current-plot-settings, ...controls, plot-settings-miss].
    // Inputs : context, cache, y1-series-count, ...live control values (hidden ones excluded).
    function hydrate(defaults, context, cache, y1Count) {
        var live = Array.prototype.slice.call(arguments, 4);
        var n = controlValues(normalize(defaults, {}, null)).length;
        var out = [];
        for (var i = 0; i < n + 2; i++) out.push(nu());
        var saved = context && cache ? cache[context] : null;
        if (!saved) {
            out[n + 1] = context === undefined ? null : context;   // not seen yet: ask the server once
            return out;
        }
        var s = normalize(defaults, saved, context);
        if (seriesCount(s) !== y1Count) {                           // series builder must be rebuilt
            out[n + 1] = context;
            return out;
        }
        var values = controlValues(s), j = 0;
        out[0] = s;
        for (var k = 0; k < n; k++) {
            if (HIDDEN_ECHO.indexOf(k) >= 0) { out[k + 1] = values[k]; continue; }
            if (!deepEqual(live[j++], values[k])) out[k + 1] = values[k];
        }
        return out;
    }

    // ---- cache maintenance + persistence gate ------------------------------
    // Outputs: [plot-settings-cache, plot-settings-persist].
    // A settings value that already equals its cached copy is a hydration echo
    // and must not be persisted again; only real changes reach the server.
    function trackSettings(settings, loaded, cache, activeContext) {
        var triggered = (window.dash_clientside.callback_context || {}).triggered || [];
        var ids = triggered.map(function (t) { return String(t.prop_id).split('.')[0]; });
        var settingsChanged = ids.indexOf('current-plot-settings') >= 0;
        var flush = ids.indexOf('loaded-files') >= 0;   // renames rewrite other contexts server-side
        var base = cache || {};
        var next = flush ? {} : base;
        var key = settings && (settings._context_key || activeContext);
        if (key && settings && Object.keys(settings).length && !deepEqual(next[key], settings)) {
            next = Object.assign({}, next);
            next[key] = settings;
            return [next, settingsChanged ? settings : nu()];
        }
        if (flush && Object.keys(base).length) return [next, nu()];
        return [nu(), nu()];
    }

    // ---- panel sync gate ---------------------------------------------------
    // Context-menu panels mirror settings only while open; when every panel is
    // closed (the normal case) no server callback needs to run at all.
    function panelsOpen(settings, tick) {
        var styles = Array.prototype.slice.call(arguments, 2);
        var open = styles.some(function (st) { return st && st.display !== 'none'; });
        return open ? (tick || 0) + 1 : nu();
    }

    // describe_figure only needs the owner and layout mode of the settings.
    function figureKey(settings, previous) {
        var key = {};
        if (has(settings, '_context_key')) key._context_key = settings._context_key;
        if (has(settings, 'layout_mode')) key.layout_mode = settings.layout_mode;
        return deepEqual(key, previous) ? nu() : key;
    }

    // ---- panel visibility (mirror of panel_visibility) ---------------------
    function panelVisibility(defaults, viewMode, settings) {
        var s = Object.assign({}, defaults, settings || {});
        var isRaw = (viewMode || 'raw') === 'raw';
        var plotType = get(s, 'plot_type', 'bar');
        var gridOrTicks = !!(s.show_grid_x || s.show_grid_y || s.show_tick_marks);
        function vis(show) { return show ? {} : {display: 'none'}; }
        var header = String(s._context_key || '').indexOf(':publication-') >= 0 ? 'Publication Plot Settings'
            : isRaw ? 'Raw Plot Settings' : 'Analysis Plot Settings';
        var bar = !isRaw && plotType === 'bar';
        var line = isRaw || plotType === 'line' || plotType === 'scatter';
        var marker = !isRaw && (plotType === 'scatter' || plotType === 'line');
        return [header, vis(!isRaw), vis(isRaw), vis(true), vis(bar), vis(line), vis(marker),
            vis(!get(s, 'auto_range', true)), vis(!isRaw), vis(get(s, 'show_legend', true)), vis(gridOrTicks)];
    }

    window.dash_clientside = Object.assign({}, window.dash_clientside, {
        plotSettingsCache: {
            contextKey: contextKey, resolveContext: resolveContext, normalize: normalize,
            controlValues: controlValues, hydrate: hydrate, trackSettings: trackSettings,
            panelsOpen: panelsOpen, figureKey: figureKey, panelVisibility: panelVisibility,
            HIDDEN_ECHO: HIDDEN_ECHO, deepEqual: deepEqual
        }
    });
}());
