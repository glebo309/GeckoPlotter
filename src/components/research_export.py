"""Research package controls, alongside the existing figure export workflow."""
from dash import html, dcc
import dash_mantine_components as dmc
from services.lab_defaults import default_column


def create_research_export():
    return html.Div([
        html.Div([html.Span('FAIR-data package'), html.A('?', href='/assets/fair-data.html', target='_blank', rel='noopener noreferrer', title='About FAIR data (opens in a new tab)', **{'aria-label':'About FAIR data (opens in a new tab)'}, className='fair-help-link')], className='toolbox-section-title fair-package-heading'),
        dmc.TextInput(id='pkg-title', label='Dataset title', placeholder='Dataset for …', size='xs', mb=8),
        dmc.Textarea(id='pkg-description', label='Description', autosize=True, minRows=2, size='xs', mb=8),
        dmc.TextInput(id='pkg-creators', label='Authors', placeholder='Family name, Given name; …', size='xs', mb=8),
        dmc.Accordion(variant='default', children=[dmc.AccordionItem(value='details', children=[
            dmc.AccordionControl('Repository details'), dmc.AccordionPanel([
                dmc.TextInput(id='pkg-orcid', label='First author ORCID', size='xs', mb=8),
                dmc.TextInput(id='pkg-affiliation', label='Affiliation', size='xs', mb=8),
                dmc.TextInput(id='pkg-record-url', label='Dataset DOI or URL', size='xs', mb=8),
                dmc.TextInput(id='pkg-article-doi', label='Related article DOI', size='xs', mb=8),
                dmc.Select(id='pkg-license', label='Data license', placeholder='Choose a license', size='xs', mb=8,
                    data=['CC-BY-4.0','CC0-1.0','CC-BY-SA-4.0']),
                dmc.TextInput(id='pkg-funding', label='Funding / grant numbers', size='xs', mb=8),
                dmc.TextInput(id='pkg-keywords', label='Keywords', placeholder='Comma separated', size='xs', mb=8),
                dmc.TextInput(id='pkg-column', label='HPLC column', value=default_column(), size='xs', mb=8,
                              description='Group routine column from the UHPLC SOP; the instrument files do not record it. Change it if another column was installed.',
                              placeholder='Manufacturer, phase (particle size, dimensions)'),
                dmc.Textarea(id='pkg-methods', label='Methods and sample information', autosize=True, minRows=3, size='xs', mb=8),
                dmc.Checkbox(id='pkg-include-code', label='Include analysis code', checked=False, size='xs', mt=8),
            ])])]),
        dmc.MultiSelect(id='pkg-formats', label='Figure formats', value=['svg','pdf','png'],
            data=[{'label':f.upper(),'value':f} for f in ('svg','pdf','png','tiff','html')], size='xs', mb=8),
        dmc.Text('All loaded data · current figure · size and resolution above', size='xs', c='dimmed', mb=8),
        dmc.Button('Download FAIR-data ZIP', id='pkg-download-btn', variant='default', size='xs', fullWidth=True),
        html.Div(id='pkg-status', role='status', style={'fontSize':'12px','marginTop':'8px'}),
        dcc.Store(id='pkg-request'), dcc.Download(id='pkg-download'),
    ])
