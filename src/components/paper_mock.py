"""Mock A4 journal paper page for publication preview."""

from dash import dcc, html
import dash_mantine_components as dmc


PUB_PRESETS = {
    'single-col': {'w': 992, 'h': 744, 'mm_w': 84, 'mm_h': 63, 'label': 'Single-column (84 mm)'},
    'full-width': {'w': 2055, 'h': 1228, 'mm_w': 174, 'mm_h': 104, 'label': 'Full-width (174 mm)'},
    'presentation': {'w': 1920, 'h': 1080, 'mm_w': 254, 'mm_h': 143, 'label': 'Presentation (16:9)'},
}

PAGE_SCREEN_WIDTH = 680
PAGE_SCREEN_HEIGHT = int(PAGE_SCREEN_WIDTH * 297 / 210)
PAGE_PX_PER_MM = PAGE_SCREEN_WIDTH / 210
PAGE_SIDE_MARGIN = PAGE_PX_PER_MM * 18
PAGE_COLUMN_GAP = PAGE_PX_PER_MM * 6


def _paragraph(lines, last_width=55):
    """Justified paragraph: full-width lines + shorter last line (3.5 px bars, 6 px apart).

    One element painted with CSS gradients, not one per line: every Dash component on the page is re-checked on each
    store update, and the ~200 bars of this mock were a seventh of all components.
    """
    bar = 'linear-gradient(#d5d5d5, #d5d5d5)'
    full = (lines - 1) * 6
    return html.Div(style={
        'height': f'{full + 3.5}px', 'marginBottom': '6.5px',
        'background': (f'{bar} left bottom / {last_width}% 3.5px no-repeat, '
                       f'repeating-linear-gradient(#d5d5d5 0 3.5px, transparent 3.5px 6px) left top / 100% {full}px no-repeat'),
    })


def _section_header(text):
    return html.Div(text, style={
        'fontWeight': '700', 'fontSize': '7px', 'marginBottom': '2px',
        'marginTop': '5px', 'color': '#333', 'fontFamily': 'Arial, sans-serif',
    })


def create_paper_mock():
    preset_bar = html.Div(
        style={
            'display': 'flex', 'alignItems': 'center', 'gap': '8px',
            'padding': '8px 12px', 'borderBottom': '1px solid #e0e0e0',
            'background': '#fafafa', 'flexShrink': '0', 'flexWrap': 'wrap',
        },
        children=[
            dmc.SegmentedControl(id='pub-view-mode', value='page', size='xs',
                data=[{'label':'Page preview','value':'page'}, {'label':'Figure','value':'figure'}]),
            dmc.SegmentedControl(
                id='pub-preset', value='single-col',
                data=[
                    {'label': 'Single-column (84 mm)', 'value': 'single-col'},
                    {'label': 'Full-width (174 mm)', 'value': 'full-width'},
                    {'label': 'Presentation (16:9)', 'value': 'presentation'},
                ],
                size='xs',
            ),
            html.Div(id='pub-export-controls', style={'display':'flex','alignItems':'center',
                'gap':'8px','marginLeft':'auto','flexShrink':0}, children=[
            html.Span(id='pub-dim-readout', style={'fontSize': '11px', 'color': '#888', 'whiteSpace':'nowrap'}),
            dmc.NumberInput(
                id='pub-dpi', debounce=True, value=300, min=72, max=1200, step=50,
                size='xs', style={'width': '80px'}, suffix=' DPI',
            ),
            dmc.Select(
                id='pub-export-format', value='png',
                data=[{'label': f.upper(), 'value': f} for f in ['png', 'svg', 'pdf', 'tiff']],
                size='xs', style={'width': '80px'},
                clearable=False, allowDeselect=False,
            ),
            dmc.Button('Export', id='pub-export-btn', size='xs', variant='filled'),
            ]),
            html.Span(id='pub-export-status', role='status', style={'fontSize':'11px','color':'#666'}),
        ],
    )

    figure_slot = html.Div(
        id='pub-figure-slot',
        children=[
            dcc.Store(id='pub-preview-graph', data={}),
            dcc.Store(id='figure-label-edit'),
            html.Div(id='pub-plot-workspace', style={'width':'100%', 'height':'100%', 'position':'relative'}),
            html.Div(id='pub-workspace-sync', style={'display':'none'}),
        ],
        style={'margin': '4px 0', 'overflow': 'hidden', 'aspectRatio': '84 / 63', 'width': f'{84 * PAGE_PX_PER_MM}px'},
    )

    caption = html.Div(
        [html.Span('Figure 1. ', style={'fontWeight': '700'}),
         html.Span('Caption placeholder — describe your figure here.', style={'color': '#555'})],
        style={'fontSize': '6px', 'fontFamily': 'Arial, sans-serif',
               'textAlign': 'center', 'marginTop': '1px', 'marginBottom': '4px', 'color': '#444'},
    )

    left_col = html.Div(
        style={'flex': '1', 'minWidth': '0'},
        children=[
            _section_header('1. Introduction'),
            _paragraph(8, 62),
            _paragraph(7, 48),
            _paragraph(6, 55),
            figure_slot,
            caption,
            _paragraph(6, 70),
            _paragraph(7, 38),
            _paragraph(5, 52),
            _paragraph(6, 44),
            _section_header('4. Discussion'),
            _paragraph(8, 58),
            _paragraph(7, 42),
            _paragraph(6, 65),
            _paragraph(7, 50),
        ],
    )

    right_col = html.Div(
        id='pub-right-col',
        style={'flex': '1', 'minWidth': '0'},
        children=[
            _paragraph(7, 55),
            _paragraph(6, 42),
            _paragraph(8, 60),
            _section_header('2. Methods'),
            _paragraph(9, 60),
            _paragraph(8, 50),
            _paragraph(7, 45),
            _paragraph(6, 55),
            _section_header('2.1 Materials'),
            _paragraph(7, 48),
            _paragraph(6, 52),
            _section_header('2.2 Instrumentation'),
            _paragraph(8, 58),
            _paragraph(7, 42),
            _section_header('3. Results'),
            _paragraph(9, 58),
            _paragraph(8, 40),
            _paragraph(7, 65),
            _paragraph(6, 52),
            _paragraph(8, 48),
        ],
    )

    two_col_body = html.Div(
        id='pub-two-col-body',
        style={'display': 'flex', 'gap': f'{PAGE_COLUMN_GAP}px'},
        children=[left_col, right_col],
    )

    paper_page = html.Div(
        id='pub-paper-page',
        style={
            'width': f'{PAGE_SCREEN_WIDTH}px',
            'minHeight': f'{PAGE_SCREEN_HEIGHT}px',
            'background': 'white',
            'paddingTop': '24px', 'paddingBottom': '24px',
            'paddingLeft': f'{PAGE_SIDE_MARGIN}px', 'paddingRight': f'{PAGE_SIDE_MARGIN}px',
            'boxShadow': '0 2px 12px rgba(0,0,0,0.15)',
            'fontFamily': 'Arial, sans-serif',
            'fontSize': '6px', 'lineHeight': '1.4',
            'outline': '1px solid #ddd', 'boxSizing': 'border-box',
        },
        children=[
            html.Div('Title of the Research Paper', style={
                'textAlign': 'center', 'fontWeight': '700', 'fontSize': '9px',
                'marginBottom': '3px',
            }),
            html.Div('G. Author, F. Paradisi — Journal Name, 2026', style={
                'textAlign': 'center', 'color': '#666', 'fontSize': '6px',
                'fontStyle': 'italic', 'marginBottom': '8px',
            }),
            _section_header('Abstract'),
            _paragraph(4, 70),
            two_col_body,
        ],
    )

    # Presentation slide mock (16:9)
    SLIDE_WIDTH = 720
    SLIDE_HEIGHT = int(SLIDE_WIDTH * 9 / 16)

    slide_figure_slot = html.Div(
        id='pub-slide-figure-slot',
        children=[
            html.Div(id='pub-slide-workspace', style={'width':'100%', 'height':'100%', 'position':'relative'}),
        ],
        style={
            'overflow': 'hidden',
            'width': '100%', 'aspectRatio': '254 / 143',
        },
    )

    slide_page = html.Div(
        id='pub-slide-page',
        style={
            'width': f'{SLIDE_WIDTH}px',
            'height': f'{SLIDE_HEIGHT}px',
            'background': 'white',
            'padding': '28px 36px',
            'boxShadow': '0 2px 12px rgba(0,0,0,0.15)',
            'fontFamily': 'Arial, sans-serif',
            'border': '1px solid #ddd', 'boxSizing': 'border-box',
            'display': 'flex', 'flexDirection': 'column',
        },
        children=[
            html.Div('Presentation Title', style={
                'fontWeight': '700', 'fontSize': '16px',
                'marginBottom': '4px', 'color': '#333',
            }),
            html.Div('G. Author — Group Meeting, 2026', style={
                'fontSize': '9px', 'color': '#888',
                'marginBottom': '12px',
            }),
            html.Div(
                style={'flex': '1', 'display': 'flex', 'gap': '16px',
                       'alignItems': 'stretch', 'minHeight': '0'},
                children=[
                    html.Div(slide_figure_slot, id='pub-slide-chart-column', style={
                        'flex': '1 1 0', 'minWidth': 0, 'display': 'flex', 'alignItems': 'center',
                    }),
                    html.Div([
                        html.Div('Key points', style={
                            'fontWeight': '700', 'fontSize': '12px',
                            'marginBottom': '10px', 'color': '#333',
                        }),
                        html.Ul([
                            html.Li('Main observation from the current figure'),
                            html.Li('Comparison across samples or conditions'),
                            html.Li('Next experiment or decision point'),
                        ], style={
                            'fontSize': '11px', 'lineHeight': '1.55',
                            'paddingLeft': '18px', 'margin': '0', 'color': '#444',
                        }),
                    ], id='pub-slide-notes', style={
                        'flex': '0 0 150px', 'minWidth':0, 'boxSizing':'border-box',
                        'borderLeft': '3px solid #1f77b4',
                        'paddingLeft': '16px', 'alignSelf': 'center',
                    }),
                ],
            ),
        ],
    )

    slide_page_wrapper = html.Div(
        id='pub-slide-page-wrapper',
        style={'display': 'inline-block', 'flexShrink': '0'},
        children=[slide_page],
    )

    slide_container = html.Div(
        id='pub-slide-container',
        style={
            'flex': '1', 'overflow': 'auto', 'background': '#e8e8e8',
            'display': 'none', 'justifyContent': 'center',
            'alignItems': 'center', 'padding': '20px',
        },
        children=[slide_page_wrapper],
    )

    paper_page_wrapper = html.Div(
        id='pub-paper-page-wrapper',
        style={'display': 'inline-block', 'flexShrink': '0'},
        children=[paper_page],
    )

    paper_container = html.Div(
        id='pub-paper-container',
        style={
            'flex': '1', 'overflow': 'auto', 'background': '#e8e8e8',
            'display': 'flex', 'justifyContent': 'center',
            'alignItems': 'flex-start', 'padding': '20px',
        },
        children=[paper_page_wrapper],
    )

    return html.Div(
        id='pub-preview-wrapper',
        style={
            'display': 'none', 'flexDirection': 'column',
            'height': '100%', 'width': '100%',
            'position': 'absolute', 'top': '0', 'left': '0',
            'zIndex': '10', 'background': '#e8e8e8',
        },
        children=[preset_bar,
            html.Div(id='pub-figure-container', style={'flex':'1','minHeight':0,'position':'relative',
                'padding':'24px','display':'none','background':'#edf0ed'}, children=[
                html.Div(id='pub-figure-workspace', style={'position':'relative','width':'100%','height':'100%',
                    'minHeight':0,'flex':'1'})]),
            paper_container, slide_container],
    )
