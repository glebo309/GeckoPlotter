const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

// Results come from a vm realm: compare structure through JSON, identity for no_update.
const plain = v => JSON.parse(JSON.stringify(v));
const deq = (a, b) => assert.deepStrictEqual(plain(a), plain(b));
const NO_UPDATE = {unchanged: true};
const DEFAULTS = {
    plot_type: 'bar', x_label: 'Retention Time (min)', y1_label: 'Signal (mAU)', y2_label: '', y1_stats: [],
    show_raw_points: false, y2_enable: false, y1_series_count: 1, auto_range: true, x_min: null, x_max: null,
    y_min: null, y_max: null, x_scale: 'linear', y_scale: 'linear', categorical_x: true, theme: 'plotly_white',
    palette: 'okabe', bg_color: '#ffffff', paper_color: '#ffffff', line_width: 1.5, line_style: 'solid',
    marker_size: 6, marker_symbol: 'circle', trace_opacity: 1, smooth_window: 0, bar_gap: 0.2, bar_group_gap: 0.1,
    title: '', shared_axis_labels: true, font: 'Arial', font_size: 10, title_font_size: 12, tick_font_size: 14,
    bold_title: true, show_legend: true, legend_pos: 'top-right', show_grid_x: false, show_grid_y: false,
    show_tick_marks: true, show_minor_ticks: false, tick_direction: 'outside', tick_length: 5, frame_width: 1,
    show_frame: true, grid_style: 'solid', layout_mode: 'overlay', subplot_spacing: 0.08, subplot_rows: 1,
    subplot_cols: 1, figure_width_mm: 84, figure_height_mm: 63, pub_preset: 'single-col', pub_dpi: 300,
    export_format: 'png', link_x: true, y_scope: 'independent', trace_overrides: {}, axis_overrides: {},
    axis_label_modes: {}, axis_label_overrides: {},
};

function load(triggered) {
    const window = {dash_clientside: {no_update: NO_UPDATE, callback_context: {triggered: triggered || []}}};
    vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../../src/assets/js/plot-settings-cache.js'), 'utf8'), {window});
    return window.dash_clientside;
}
const api = () => load().plotSettingsCache;
const N = api().controlValues(api().normalize(DEFAULTS, {}, 'k')).length;

test('control list has one value per hydrated control', () => {
    assert.equal(N, 55);
});

test('context key follows view mode, analysis tab, file and plot tab', () => {
    const c = api();
    assert.equal(c.resolveContext('f', 'raw', 'data-overview', 'lcms', null), 'shared:raw:lcms');
    assert.equal(c.resolveContext('f', undefined, 'data-overview', null, null), 'shared:raw');
    assert.equal(c.resolveContext('f', 'analysis', 'peak-analysis', 't', null), 'shared:peak-analysis:t');
    assert.equal(c.resolveContext('f', 'analysis', 'across-samples', null, null), 'shared:across-samples');
    assert.equal(c.resolveContext('f', 'analysis', 'data-overview', 't', null), 'file:f:t');
    assert.equal(c.resolveContext(null, 'analysis', 'data-overview', 't', 'file:f:t'), null);
});

test('an unchanged context is not re-resolved', () => {
    const c = api();
    assert.equal(c.resolveContext('uv', 'raw', 'data-overview', 'lcms', 'shared:raw:lcms'), NO_UPDATE);
    assert.equal(c.resolveContext(null, 'analysis', 'x', null, null), NO_UPDATE);
    assert.equal(c.resolveContext(null, 'analysis', 'x', null, undefined), NO_UPDATE);
});

function liveFor(values) {   // live control values, hidden mirrors excluded
    return values.filter((_, i) => !api().HIDDEN_ECHO.includes(i));
}

test('a cached context hydrates the settings and every control that differs', () => {
    const c = api();
    const cache = {'shared:raw:b': {line_width: 3, title: 'B', plot_type: 'scatter'}};
    const current = c.controlValues(c.normalize(DEFAULTS, {}, 'shared:raw:a'));
    const out = c.hydrate(DEFAULTS, 'shared:raw:b', cache, 1, ...liveFor(current));
    assert.equal(out.length, N + 2);
    assert.equal(out[0]._context_key, 'shared:raw:b');
    assert.equal(out[0].line_width, 3);
    assert.equal(out[0].axis_label_modes.x, 'auto');
    assert.equal(out[out.length - 1], NO_UPDATE);
    const target = c.controlValues(out[0]);
    const changed = target.map((v, i) => out[i + 1] !== NO_UPDATE ? i : -1).filter(i => i >= 0);
    // plot-type (+ its pt- twin), the title and the line width differ; hidden mirrors are always written
    const differing = target.map((v, i) => JSON.stringify(v) !== JSON.stringify(current[i]) ? i : -1).filter(i => i >= 0);
    deq(changed, [...new Set([...differing, ...c.HIDDEN_ECHO])].sort((a, b) => a - b));
    assert.ok(differing.length >= 3);
});

test('controls that already show the stored values are left alone', () => {
    const c = api();
    const cache = {'shared:raw:b': {}};
    const same = c.controlValues(c.normalize(DEFAULTS, {}, 'shared:raw:b'));
    const out = c.hydrate(DEFAULTS, 'shared:raw:b', cache, 1, ...liveFor(same));
    const written = out.slice(1, N + 1).map((v, i) => v === NO_UPDATE ? -1 : i).filter(i => i >= 0);
    deq(written, c.HIDDEN_ECHO);
});

test('an unseen context asks the server instead of guessing', () => {
    const c = api();
    const out = c.hydrate(DEFAULTS, 'shared:raw:new', {'shared:raw:b': {}}, 1, ...Array(N - 3).fill(null));
    assert.equal(out[out.length - 1], 'shared:raw:new');
    assert.ok(out.slice(0, -1).every(v => v === NO_UPDATE));
    const none = c.hydrate(DEFAULTS, null, {}, 1, ...Array(N - 3).fill(null));
    assert.equal(none[none.length - 1], null);
    assert.ok(none.slice(0, -1).every(v => v === NO_UPDATE));
});

test('a different series count goes to the server so the series builder is rebuilt', () => {
    const c = api();
    const out = c.hydrate(DEFAULTS, 'shared:raw:b', {'shared:raw:b': {y1_series_count: 3}}, 1, ...Array(N - 3).fill(null));
    assert.equal(out[out.length - 1], 'shared:raw:b');
    assert.ok(out.slice(0, -1).every(v => v === NO_UPDATE));
    const same = c.hydrate(DEFAULTS, 'shared:raw:b', {'shared:raw:b': {y1_series_count: 3}}, 3, ...Array(N - 3).fill(null));
    assert.equal(same[same.length - 1], NO_UPDATE);
});

test('hydration never mutates the cached entry', () => {
    const c = api();
    const entry = {line_width: 3};
    const cache = {k: entry};
    c.hydrate(DEFAULTS, 'k', cache, 1, ...Array(N - 3).fill(null));
    deq(entry, {line_width: 3});
    deq(Object.keys(cache), ['k']);
});

test('a custom axis label is classified like the server does', () => {
    const c = api();
    deq(c.normalize(DEFAULTS, {x_label: 'Wavelength / nm'}, 'k').axis_label_modes, {x: 'custom', y: 'auto'});
    deq(c.normalize(DEFAULTS, {x_label: 'A', axis_label_modes: {x: 'auto'}}, 'k').axis_label_modes, {x: 'auto', y: 'auto'});
    deq(c.normalize(DEFAULTS, {y1_label: null}, 'k').axis_label_modes, {x: 'auto', y: 'auto'});
});

test('layout checklist reflects grid, tick, minor and frame flags', () => {
    const c = api();
    const opts = s => c.controlValues(c.normalize(DEFAULTS, s, 'k'))[36];
    deq(opts({}), ['ticks', 'frame']);
    deq(opts({show_grid_x: true, show_minor_ticks: true, show_frame: false}), ['grid_x', 'ticks', 'minor_ticks']);
});

function track(triggered, ...args) {
    return load(triggered).plotSettingsCache.trackSettings(...args);
}

test('a changed setting is cached and persisted, its hydration echo is not', () => {
    const edited = {_context_key: 'shared:raw:a', line_width: 2};
    const [cache, persist] = track([{prop_id: 'current-plot-settings.data'}], edited, [], {}, 'shared:raw:a');
    deq(cache, {'shared:raw:a': edited});
    assert.equal(persist, edited);
    const echo = JSON.parse(JSON.stringify(edited));
    const [cache2, persist2] = track([{prop_id: 'current-plot-settings.data'}], echo, [], cache, 'shared:raw:a');
    assert.equal(cache2, NO_UPDATE);
    assert.equal(persist2, NO_UPDATE);
});

test('a late settings value is filed under its own context, not the active one', () => {
    const late = {_context_key: 'shared:raw:a', line_width: 2};
    const [cache, persist] = track([{prop_id: 'current-plot-settings.data'}], late, [], {'shared:raw:b': {_context_key: 'shared:raw:b'}}, 'shared:raw:b');
    deq(Object.keys(cache).sort(), ['shared:raw:a', 'shared:raw:b']);
    assert.equal(persist, late);
});

test('empty settings are ignored', () => {
    const [cache, persist] = track([{prop_id: 'current-plot-settings.data'}], {}, [], {}, 'shared:raw:a');
    assert.equal(cache, NO_UPDATE);
    assert.equal(persist, NO_UPDATE);
});

test('loaded-files changes drop other contexts but keep the active settings without re-persisting', () => {
    const active = {_context_key: 'shared:raw:a', line_width: 2};
    const stale = {'shared:raw:a': active, 'shared:raw:b': {_context_key: 'shared:raw:b'}};
    const [cache, persist] = track([{prop_id: 'loaded-files.data'}], active, ['f'], stale, 'shared:raw:a');
    deq(cache, {'shared:raw:a': active});
    assert.equal(persist, NO_UPDATE);
    const renamed = Object.assign({}, active, {trace_overrides: {x: 1}});
    const both = track([{prop_id: 'current-plot-settings.data'}, {prop_id: 'loaded-files.data'}], renamed, ['f'], stale, 'shared:raw:a');
    deq(both[0], {'shared:raw:a': renamed});
    assert.equal(both[1], renamed);
});

test('panel gate ticks only while a context-menu panel is open', () => {
    const c = api();
    const closed = {display: 'none'};
    assert.equal(c.panelsOpen({}, 4, closed, closed, closed, closed, closed), NO_UPDATE);
    assert.equal(c.panelsOpen({}, 4, undefined, null, closed, closed, closed), NO_UPDATE);
    assert.equal(c.panelsOpen({}, 4, closed, {display: 'block', left: '8px'}, closed, closed, closed), 5);
    assert.equal(c.panelsOpen({}, undefined, {position: 'fixed'}, closed, closed, closed, closed), 1);
});

test('figure key changes only with the owner or layout mode', () => {
    const c = api();
    const first = c.figureKey({_context_key: 'a', layout_mode: 'stacked', line_width: 2}, {});
    deq(first, {_context_key: 'a', layout_mode: 'stacked'});
    assert.equal(c.figureKey({_context_key: 'a', layout_mode: 'stacked', line_width: 5}, first), NO_UPDATE);
    deq(c.figureKey({_context_key: 'b', layout_mode: 'stacked'}, first), {_context_key: 'b', layout_mode: 'stacked'});
    assert.equal(c.figureKey({}, {}), NO_UPDATE);
});

test('panel visibility follows view mode, plot type and toggles', () => {
    const c = api();
    const hide = {display: 'none'};
    deq(c.panelVisibility(DEFAULTS, 'raw', {_context_key: 'shared:raw:x'}),
        ['Raw Plot Settings', hide, {}, {}, hide, {}, hide, hide, hide, {}, {}]);
    assert.equal(c.panelVisibility(DEFAULTS, 'raw', {_context_key: 'shared:raw:publication-a'})[0], 'Publication Plot Settings');
    deq(c.panelVisibility(DEFAULTS, 'analysis', {plot_type: 'bar', auto_range: false, show_legend: false}),
        ['Analysis Plot Settings', {}, hide, {}, {}, hide, hide, {}, {}, hide, {}]);
    deq(c.panelVisibility(DEFAULTS, 'analysis', {plot_type: 'scatter', show_tick_marks: false}).slice(4, 7), [hide, {}, {}]);
    deq(c.panelVisibility(DEFAULTS, 'analysis', {show_tick_marks: false})[10], hide);
});
