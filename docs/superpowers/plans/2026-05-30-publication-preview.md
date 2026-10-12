# Publication Preview Tab — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a "Publication" plot tab that embeds a live Plotly graph inside a mock A4 journal paper page, updated live by Plot Settings, with built-in export.

**Architecture:** A new always-present plot tab (`id="publication"`) renders in the same `main-plot` area. When active, `master_render` builds the figure at the selected preset dimensions (single-column 84mm / full-width 174mm) and the layout swaps the normal `dcc.Graph` display for a paper mock container with a separate `pub-preview-graph` inside it. A dedicated callback renders the publication figure into `pub-preview-graph`. Export reads from that graph.

**Tech Stack:** Dash 3.x, Plotly 6.x, Dash Mantine Components (dmc), kaleido 0.2.1

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `src/components/paper_mock.py` | **Create** | `create_paper_mock()` returns the full paper page HTML component with embedded `dcc.Graph(id='pub-preview-graph')` and preset bar |
| `src/callbacks/publication_preview_callbacks.py` | **Create** | Callback: render figure into `pub-preview-graph` when Publication tab is active; preset change handler; export-from-preview handler |
| `app.py` | **Modify** | Add Publication tab to `plot-tabs` store default, add `pub-preview-graph` + paper mock container to layout, add `dcc.Store('pub-preset')`, register new callbacks |
| `src/callbacks/viz_callbacks.py` | **Modify** | `master_render`: skip rendering for publication tab (it has its own callback), `render_tab_bar`: always include Publication tab, `sync_plot_tabs`: preserve publication tab |

---

### Task 1: Create the Paper Mock Component

**Files:**
- Create: `src/components/paper_mock.py`

This component builds the visual mock A4 paper page with grey text blocks, section headers, and a slot for the figure graph.

- [ ] **Step 1: Create `src/components/paper_mock.py`**

```python
"""Mock A4 journal paper page for publication preview."""

from dash import dcc, html
import dash_mantine_components as dmc


# Publication preset dimensions (px at 300 DPI)
PUB_PRESETS = {
    'single-col': {'w': 992, 'h': 744, 'mm_w': 84, 'mm_h': 63, 'label': 'Single-column (84 mm)'},
    'full-width': {'w': 2055, 'h': 1541, 'mm_w': 174, 'mm_h': 131, 'label': 'Full-width (174 mm)'},
}

# A4 page proportions: 210 x 297 mm. We render at a fixed screen width and
# scale the height proportionally.
PAGE_SCREEN_WIDTH = 680  # px — fits comfortably in the right panel
PAGE_SCREEN_HEIGHT = int(PAGE_SCREEN_WIDTH * 297 / 210)  # ~962 px


def _grey_lines(count, widths=None):
    """Generate grey bars simulating text lines."""
    if widths is None:
        import itertools
        base = [95, 88, 92, 80, 85, 90, 78, 87, 93, 82]
        widths = list(itertools.islice(itertools.cycle(base), count))
    return [
        html.Div(style={
            'background': '#ddd',
            'height': '4px',
            'width': f'{w}%',
            'marginBottom': '3px',
            'borderRadius': '1px',
        }) for w in widths[:count]
    ]


def _section_header(text):
    return html.Div(text, style={
        'fontWeight': '700',
        'fontSize': '8px',
        'marginBottom': '3px',
        'marginTop': '6px',
        'color': '#333',
        'fontFamily': 'Arial, sans-serif',
    })


def create_paper_mock():
    """Return the full publication preview layout: preset bar + paper page.

    The paper page contains a dcc.Graph(id='pub-preview-graph') positioned
    according to the selected preset.  The surrounding grey-bar text is
    purely decorative.
    """
    preset_bar = html.Div(
        style={
            'display': 'flex',
            'alignItems': 'center',
            'gap': '12px',
            'padding': '8px 12px',
            'borderBottom': '1px solid #e0e0e0',
            'background': '#fafafa',
            'flexShrink': '0',
        },
        children=[
            html.Span('Preset:', style={'fontSize': '12px', 'fontWeight': '600', 'color': '#555'}),
            dmc.SegmentedControl(
                id='pub-preset',
                value='single-col',
                data=[
                    {'label': 'Single-column (84 mm)', 'value': 'single-col'},
                    {'label': 'Full-width (174 mm)', 'value': 'full-width'},
                ],
                size='xs',
            ),
            html.Div(style={'flex': '1'}),
            html.Span(id='pub-dim-readout',
                      style={'fontSize': '11px', 'color': '#888'}),
            dmc.Select(
                id='pub-export-format',
                value='png',
                data=[{'label': f.upper(), 'value': f} for f in ['png', 'svg', 'pdf']],
                size='xs',
                style={'width': '80px'},
                clearable=False,
                allowDeselect=False,
            ),
            dmc.Button('Export', id='pub-export-btn', size='xs', variant='filled'),
            dcc.Download(id='pub-export-download'),
        ],
    )

    # -- Build the paper page mock --
    # The figure slot is a div that will contain the dcc.Graph; its width
    # is set dynamically by a callback based on the preset.

    figure_slot = html.Div(
        id='pub-figure-slot',
        children=[
            dcc.Graph(
                id='pub-preview-graph',
                figure={},
                responsive=False,
                style={'width': '100%', 'height': '100%'},
                config={
                    'responsive': False,
                    'displayModeBar': False,
                    'displaylogo': False,
                    'staticPlot': False,
                    'scrollZoom': False,
                },
            ),
        ],
        style={
            'border': '2px solid #0066cc',
            'borderRadius': '3px',
            'background': '#fafcff',
            'margin': '6px 0',
            'overflow': 'hidden',
        },
    )

    caption = html.Div(
        [
            html.Span('Figure 1. ', style={'fontWeight': '700'}),
            html.Span('Caption placeholder — describe your figure here.',
                       style={'color': '#666'}),
        ],
        style={
            'fontSize': '7px',
            'fontFamily': 'Arial, sans-serif',
            'textAlign': 'center',
            'marginTop': '2px',
            'marginBottom': '6px',
            'color': '#444',
        },
    )

    # Left column content (text + figure)
    left_col = html.Div(
        style={'flex': '1', 'minWidth': '0'},
        children=[
            _section_header('1. Introduction'),
            *_grey_lines(6),
            figure_slot,
            caption,
            *_grey_lines(3),
        ],
    )

    # Right column content (text only)
    right_col = html.Div(
        id='pub-right-col',
        style={'flex': '1', 'minWidth': '0'},
        children=[
            *_grey_lines(4),
            _section_header('2. Methods'),
            *_grey_lines(10),
            _section_header('3. Results'),
            *_grey_lines(8),
        ],
    )

    two_col_body = html.Div(
        id='pub-two-col-body',
        style={'display': 'flex', 'gap': '12px'},
        children=[left_col, right_col],
    )

    paper_page = html.Div(
        id='pub-paper-page',
        style={
            'width': f'{PAGE_SCREEN_WIDTH}px',
            'minHeight': f'{PAGE_SCREEN_HEIGHT}px',
            'background': 'white',
            'padding': '28px 32px',
            'boxShadow': '0 2px 12px rgba(0,0,0,0.15)',
            'fontFamily': 'Arial, sans-serif',
            'fontSize': '7px',
            'lineHeight': '1.4',
            'border': '1px solid #ddd',
            'boxSizing': 'border-box',
        },
        children=[
            # Paper title
            html.Div('Title of the Research Paper', style={
                'textAlign': 'center', 'fontWeight': '700', 'fontSize': '10px',
                'marginBottom': '4px',
            }),
            html.Div('G. Author, F. Paradisi — Journal Name, 2026', style={
                'textAlign': 'center', 'color': '#666', 'fontSize': '7px',
                'fontStyle': 'italic', 'marginBottom': '12px',
            }),
            # Abstract
            _section_header('Abstract'),
            *_grey_lines(4, widths=[98, 95, 92, 70]),
            # Two-column body
            two_col_body,
        ],
    )

    # Scrollable container with grey background
    paper_container = html.Div(
        id='pub-paper-container',
        style={
            'flex': '1',
            'overflow': 'auto',
            'background': '#e8e8e8',
            'display': 'flex',
            'justifyContent': 'center',
            'padding': '20px',
        },
        children=[paper_page],
    )

    return html.Div(
        id='pub-preview-wrapper',
        style={
            'display': 'none',
            'flexDirection': 'column',
            'height': '100%',
            'width': '100%',
            'position': 'absolute',
            'top': '0',
            'left': '0',
            'zIndex': '10',
            'background': '#e8e8e8',
        },
        children=[preset_bar, paper_container],
    )
```

- [ ] **Step 2: Verify the file is importable**

Run: `cd /Users/glenn/_CODE/GeckoPlotter_DASH/GeckoPlotter_V2 && python3 -c "from components.paper_mock import create_paper_mock, PUB_PRESETS; print('OK', list(PUB_PRESETS.keys()))"`

Expected: `OK ['single-col', 'full-width']`

---

### Task 2: Add the Paper Mock to the App Layout

**Files:**
- Modify: `app.py` (lines ~746-778, the `right-top-panel` viz-container area)

Add the paper mock component alongside the existing `main-plot` graph. The paper mock starts hidden (`display: none`) and is toggled visible when the Publication tab is active.

- [ ] **Step 1: Add import at top of `app.py`**

After the existing component imports (around line 34), add:

```python
from components.paper_mock import create_paper_mock
```

- [ ] **Step 2: Add the paper mock component inside the viz-container**

In `app.py`, the viz-container div (line ~748) currently contains only the `dcc.Graph(id='main-plot')`. Add the paper mock right after it, inside the same parent div. The paper mock uses `position: absolute` and overlays the main plot when visible.

Find the `panel-content viz-container` div (around line 747-778) and add `create_paper_mock()` after the closing of the `dcc.Graph`:

```python
html.Div(
    className='panel-content viz-container',
    style={'position': 'relative'},  # ADD: position relative for absolute child
    children=[
        dcc.Graph(
            id='main-plot',
            # ... existing config unchanged ...
        ),
        create_paper_mock(),  # ADD: paper mock overlay
    ],
),
```

The key change is:
1. Add `style={'position': 'relative'}` to the viz-container div
2. Add `create_paper_mock()` as a second child after the `dcc.Graph`

- [ ] **Step 3: Add the `pub-preset` store**

In the stores section of `app.py` (around line 145-165, where all the `dcc.Store` components live), add:

```python
dcc.Store(id='pub-preview-preset', data='single-col'),
```

- [ ] **Step 4: Verify the app starts without errors**

Run: `cd /Users/glenn/_CODE/GeckoPlotter_DASH/GeckoPlotter_V2 && timeout 10 python3 app.py 2>&1 | head -20`

Expected: App starts on port 8050 without import errors.

---

### Task 3: Register the Publication Tab in the Tab Bar

**Files:**
- Modify: `src/callbacks/viz_callbacks.py` (functions `sync_plot_tabs` at line 406 and `render_tab_bar` at line 479)

The Publication tab is always present — it's not auto-created from file data like raw tabs. We need to ensure it's always appended to the tab list and rendered in the tab bar.

- [ ] **Step 1: Append the Publication tab in `sync_plot_tabs`**

In `sync_plot_tabs` (line 406), right before the `return new_tabs, next_active` statement (line 472), append the publication tab:

```python
        # Always include the Publication preview tab
        pub_tab = {'id': 'publication', 'label': 'Publication', 'type': 'publication'}
        new_tabs.append(pub_tab)

        return new_tabs, next_active
```

- [ ] **Step 2: Style the Publication tab distinctly in `render_tab_bar`**

In `render_tab_bar` (line 479), the publication tab should look slightly different — maybe a small icon or different style. But for MVP, just make sure it renders correctly. No changes needed to `render_tab_bar` itself — it already renders any tab from the list.

However, the tab's button click handler (`handle_tab_click` at line 517) uses pattern-matching callbacks on `{'type': 'plot-tab-btn', 'index': ALL}` — this will work automatically for our new tab since `render_tab_bar` creates buttons with that pattern.

Verify no changes needed by reading `handle_tab_click`:

```python
    def handle_tab_click(n_clicks_list, current_tab):
        ctx = dash.callback_context
        if not ctx.triggered:
            raise dash.exceptions.PreventUpdate
        prop_id = ctx.triggered[0]['prop_id']
        # Extracts the tab ID from the pattern match — works for any tab ID
```

- [ ] **Step 3: Verify the Publication tab appears**

Run the app, load a file, and confirm "Publication" appears as the last tab in the plot tab bar.

---

### Task 4: Create the Publication Preview Callback

**Files:**
- Create: `src/callbacks/publication_preview_callbacks.py`

This is the core callback: when the Publication tab is active, render the figure into `pub-preview-graph` and show the paper mock overlay. When any other tab is active, hide the overlay.

- [ ] **Step 1: Create `src/callbacks/publication_preview_callbacks.py`**

```python
"""Publication preview callbacks — render figure in paper mock."""

import base64
import logging
import sys

import dash
from dash import Input, Output, State, html
import plotly.graph_objects as go

log = logging.getLogger('geckoplotter.pub_preview')
if not log.handlers:
    _h = logging.StreamHandler(sys.stderr)
    _h.setFormatter(logging.Formatter('%(message)s'))
    log.addHandler(_h)
    log.setLevel(logging.DEBUG)


def register_publication_preview_callbacks(app, data_manager):
    """Register all publication preview callbacks."""

    from services.plot_settings_service import PlotSettingsService, DEFAULT_PLOT_SETTINGS
    from callbacks.viz_callbacks import _collect_visible_files, _get_active_file_group
    from services.plot_manager import PlotManager
    from components.paper_mock import PUB_PRESETS, PAGE_SCREEN_WIDTH

    plot_manager = PlotManager()

    # ── Toggle paper mock visibility ─────────────────────────────────
    @app.callback(
        [Output('pub-preview-wrapper', 'style'),
         Output('main-plot', 'style')],
        Input('active-plot-tab', 'data'),
        prevent_initial_call=True,
    )
    def toggle_pub_preview(active_tab_id):
        if active_tab_id == 'publication':
            return (
                {'display': 'flex', 'flexDirection': 'column', 'height': '100%',
                 'width': '100%', 'position': 'absolute', 'top': '0', 'left': '0',
                 'zIndex': '10', 'background': '#e8e8e8'},
                {'width': '100%', 'height': '100%', 'display': 'none'},
            )
        return (
            {'display': 'none'},
            {'width': '100%', 'height': '100%'},
        )

    # ── Render figure into pub-preview-graph ─────────────────────────
    @app.callback(
        Output('pub-preview-graph', 'figure'),
        [Input('active-plot-tab', 'data'),
         Input('current-plot-settings', 'data'),
         Input('pub-preset', 'value'),
         Input('render-trigger', 'data'),
         Input('active-file', 'data')],
        [State('loaded-files', 'data'),
         State('plot-tabs', 'data'),
         State('file-order', 'data'),
         State('custom-plot-figures', 'data')],
        prevent_initial_call=True,
    )
    def render_pub_figure(active_tab_id, plot_settings, preset, render_trigger,
                          active_file, loaded_files, plot_tabs, file_order,
                          custom_figures):
        if active_tab_id != 'publication':
            raise dash.exceptions.PreventUpdate

        p = PUB_PRESETS.get(preset, PUB_PRESETS['single-col'])
        fig_w = p['w']
        fig_h = p['h']

        s = {**DEFAULT_PLOT_SETTINGS, **(plot_settings or {})}
        layout_mode = s.get('layout_mode', 'overlay')

        # Find the most recent raw tab to source data from
        raw_tabs = [t for t in (plot_tabs or [])
                    if t.get('type') == 'raw']
        if not raw_tabs:
            empty = go.Figure()
            empty.update_layout(
                width=fig_w, height=fig_h,
                xaxis={'visible': False}, yaxis={'visible': False},
                annotations=[dict(text='Load data to preview',
                                  xref='paper', yref='paper',
                                  x=0.5, y=0.5, showarrow=False,
                                  font=dict(size=14, color='#999'))],
            )
            return empty

        # Use the first raw tab's group to collect files
        source_tab = raw_tabs[0]
        group_key = tuple(source_tab.get('group_key', []))

        visible_files = _collect_visible_files(
            data_manager, active_file, loaded_files,
            target_group_override=group_key, file_order=file_order)

        if not visible_files:
            empty = go.Figure()
            empty.update_layout(width=fig_w, height=fig_h)
            return empty

        figure = plot_manager.create_multi_file_plot(visible_files, layout_mode)

        # Apply smoothing
        smooth_window = s.get('smooth_window', 0)
        if smooth_window >= 3:
            from scipy.signal import savgol_filter
            import numpy as np
            poly_order = min(3, smooth_window - 1)
            fig_obj = go.Figure(figure) if isinstance(figure, dict) else figure
            for trace in fig_obj.data:
                if hasattr(trace, 'y') and trace.y is not None:
                    y = np.asarray(trace.y, dtype=float)
                    if len(y) > smooth_window:
                        trace.y = tuple(savgol_filter(y, smooth_window, poly_order))
            figure = fig_obj

        # Apply plot settings
        fig_obj = go.Figure(figure) if isinstance(figure, dict) else figure
        ps = PlotSettingsService.from_dict(s)
        PlotSettingsService.apply_to_figure(fig_obj, ps)

        # Constrain to publication dimensions
        fig_obj.update_layout(
            width=fig_w,
            height=fig_h,
            autosize=False,
            uirevision='pub-preview',
        )

        return fig_obj

    # ── Update figure slot size based on preset ──────────────────────
    @app.callback(
        [Output('pub-figure-slot', 'style'),
         Output('pub-right-col', 'style'),
         Output('pub-dim-readout', 'children')],
        Input('pub-preset', 'value'),
        prevent_initial_call=True,
    )
    def update_preset_layout(preset):
        p = PUB_PRESETS.get(preset, PUB_PRESETS['single-col'])
        readout = f"{p['mm_w']} × {p['mm_h']} mm · 300 DPI"

        # Calculate the figure slot width as a fraction of the paper page.
        # A4 text area ≈ 170mm (210mm - 20mm margins each side).
        # Two columns ≈ 80mm each with ~10mm gap.
        # single-col (84mm) ≈ one column ≈ 48% of page width
        # full-width (174mm) ≈ full text width ≈ 100% of page width
        base_slot_style = {
            'border': '2px solid #0066cc',
            'borderRadius': '3px',
            'background': '#fafcff',
            'margin': '6px 0',
            'overflow': 'hidden',
        }

        if preset == 'full-width':
            # Full-width: figure spans both columns — hide right column,
            # figure takes full width
            slot_style = {**base_slot_style, 'width': '100%'}
            right_style = {'display': 'none'}
        else:
            # Single-column: figure fits in one column
            slot_style = {**base_slot_style, 'width': '100%'}
            right_style = {'flex': '1', 'minWidth': '0'}

        return slot_style, right_style, readout

    # ── Export from preview ───────────────────────────────────────────
    @app.callback(
        Output('pub-export-download', 'data'),
        Input('pub-export-btn', 'n_clicks'),
        [State('pub-preview-graph', 'figure'),
         State('pub-export-format', 'value'),
         State('pub-preset', 'value')],
        prevent_initial_call=True,
    )
    def export_from_preview(n_clicks, fig_data, fmt, preset):
        if not n_clicks or not fig_data:
            return dash.no_update

        p = PUB_PRESETS.get(preset, PUB_PRESETS['single-col'])
        fig = go.Figure(fig_data)
        width = p['w']
        height = p['h']
        scale = 3  # 300 DPI effective

        export_svc = data_manager.export_service

        try:
            if fmt == 'svg':
                svg_bytes = export_svc.export_figure_svg(fig, width=width, height=height)
                return dict(
                    content=base64.b64encode(svg_bytes).decode(),
                    filename='figure.svg', base64=True)
            elif fmt == 'pdf':
                pdf_bytes = fig.to_image(
                    format='pdf', width=width, height=height,
                    scale=scale, engine='kaleido')
                return dict(
                    content=base64.b64encode(pdf_bytes).decode(),
                    filename='figure.pdf', base64=True)
            else:  # png
                png_bytes = export_svc.export_figure_png(
                    fig, width=width, height=height, scale=scale)
                return dict(
                    content=base64.b64encode(png_bytes).decode(),
                    filename='figure.png', base64=True)
        except Exception as e:
            log.exception(f"Publication export failed: {e}")
            return dash.no_update
```

- [ ] **Step 2: Verify the file is importable**

Run: `cd /Users/glenn/_CODE/GeckoPlotter_DASH/GeckoPlotter_V2 && python3 -c "from callbacks.publication_preview_callbacks import register_publication_preview_callbacks; print('OK')"`

Expected: `OK`

---

### Task 5: Register Callbacks and Wire Up in `app.py`

**Files:**
- Modify: `app.py` (imports section ~line 37, and callback registration section ~line 1230+)

- [ ] **Step 1: Add import for the new callback module**

After the existing callback imports (around line 42), add:

```python
from callbacks.publication_preview_callbacks import register_publication_preview_callbacks
```

- [ ] **Step 2: Register the callbacks**

Find where other callbacks are registered (search for `register_export_callbacks` in `app.py`). Add nearby:

```python
register_publication_preview_callbacks(app, data_manager)
```

- [ ] **Step 3: Verify the app starts and the Publication tab works**

Run: `cd /Users/glenn/_CODE/GeckoPlotter_DASH/GeckoPlotter_V2 && python3 app.py`

Test in browser:
1. Open http://localhost:8050
2. Upload a chromatogram file
3. Verify the "Publication" tab appears in the plot tab bar
4. Click the "Publication" tab
5. Verify the paper mock page appears with the figure embedded
6. Switch preset between Single-column and Full-width — figure should resize
7. Change a Plot Setting (e.g., line width) — the preview figure should update live
8. Click Export — a PNG should download

---

### Task 6: Prevent `master_render` from Conflicting

**Files:**
- Modify: `src/callbacks/viz_callbacks.py` (inside `master_render` at line ~1097)

When the Publication tab is active, `master_render` should not try to render into `main-plot` — the main plot is hidden and the publication callback handles its own graph. Add an early return.

- [ ] **Step 1: Add early return for publication tab**

In `master_render`, right after the tab lookup (around line 1115-1117), add:

```python
        # Publication tab has its own dedicated callback and graph
        if tab.get('type') == 'publication':
            return dash.no_update, dash.no_update
```

This goes right after:
```python
        tab = next((t for t in plot_tabs if t['id'] == active_tab_id), None)
        if not tab:
            return plot_manager.create_empty_plot("Upload files to get started"), None
```

And before the `# -- Custom plot tab --` block.

- [ ] **Step 2: Verify no callback conflicts**

Run the app, switch between Raw and Publication tabs. Verify:
- Raw tab: main plot renders normally
- Publication tab: paper mock shows, main plot hidden, no console errors about circular dependencies or multiple outputs

---

### Task 7: Full Integration Test

**Files:** None (manual testing)

- [ ] **Step 1: Start the app and load test data**

Run: `cd /Users/glenn/_CODE/GeckoPlotter_DASH/GeckoPlotter_V2 && python3 app.py`

Upload a chromatogram file (or any data file you have).

- [ ] **Step 2: Test the publication preview workflow**

1. Click the "Publication" tab in the plot tab bar
2. Verify: paper mock page appears with grey text blocks and your figure embedded
3. The preset bar shows "Single-column (84 mm)" selected
4. The dimension readout shows "84 × 63 mm · 300 DPI"
5. Switch to "Full-width (174 mm)" — the right column disappears, figure spans full width
6. Switch back to "Single-column" — right column reappears

- [ ] **Step 3: Test live Plot Settings updates**

1. While on the Publication tab, switch to Plot Settings in the toolbox (left panel)
2. Change line width from 2 to 4 — figure in the paper mock updates immediately
3. Change font to "Times New Roman" — axis labels update
4. Toggle frame off — black border around plot disappears
5. Change color palette — trace colors update

- [ ] **Step 4: Test export**

1. Select PNG format, click Export — downloads `figure.png`
2. Open the PNG — verify it's at publication dimensions (992×744 px or 2055×1541 px)
3. Select SVG format, click Export — downloads `figure.svg`
4. Select PDF format, click Export — downloads `figure.pdf`

- [ ] **Step 5: Test tab switching**

1. Switch to Raw tab — main plot reappears, paper mock disappears
2. Switch back to Publication — paper mock reappears with current figure
3. Switch to a Custom tab (if one exists) — verify it works normally
4. Switch back to Publication — still works

- [ ] **Step 6: Test the two-panel focus workflow**

1. Drag the left panel divider to collapse the file explorer
2. Drag the bottom panel divider to collapse the data tables
3. You should have a clean split: Plot Settings on the left, Paper preview on the right
4. Adjust settings — preview updates live
5. Export — works correctly
