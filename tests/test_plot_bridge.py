import json
from pathlib import Path
import dash
from dash import Input,Output


def test_bridge_keeps_existing_plot_callback_properties_without_a_graph():
    from components.plot_bridge import PlotBridge, install
    app=dash.Dash(__name__)
    install(app)
    figure={'data':[{'x':[0,1],'y':[1,2]}],'layout':{}}
    app.layout=PlotBridge(id='main-plot',figure=figure)
    @app.callback(Output('main-plot','figure'),Input('main-plot','clickData'))
    def clicked(value):return figure
    client=app.server.test_client()
    layout=client.get('/_dash-layout').get_json()
    assert layout['namespace']=='gecko_plot_bridge'
    assert layout['type']=='PlotBridge'
    assert layout['props']['figure']==figure
    assert {'figure','clickData','relayoutData'} <= set(app.layout._prop_names)
    assert '/_gecko/plotly.js' in client.get('/').text
    response=client.get('/_gecko/plotly.js')
    assert response.status_code==200 and b'plotly.js' in response.data[:100]
    assert client.get('/_gecko/plotly.js',headers={'If-None-Match':response.headers['ETag']}).status_code==304


def test_production_main_plot_uses_bridge():
    # The production module registers global Dash callbacks; isolate them from
    # the small test apps elsewhere in this suite.
    import subprocess
    import sys
    result=subprocess.run([sys.executable,'-c',"import app; from components.workspace_layout import walk; main=next(n for n in walk(app._layout_body) if getattr(n,'id',None)=='main-plot'); assert main._type=='PlotBridge'"],capture_output=True,text=True)
    assert result.returncode==0,result.stdout+result.stderr
