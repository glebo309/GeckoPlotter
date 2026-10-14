"""A dropped file's plot is drawn from the upload response, and it is the figure the normal render builds."""
import base64
from unittest.mock import patch

import numpy as np
import pandas as pd

from services.data_store import Bundle, BundleType, Component, ComponentRole, DataStore
from src.ingestion.types import ColumnRole, SourceCategory, StandardizedResult, FileIdentity


def _run(identifier='run', n=24001):
    t = np.linspace(0, 10, n)
    frame = pd.DataFrame({'Time (min)': t, 'Absorbance (mAU)': 500 * np.exp(-((t - 4) / 0.05) ** 2)})
    roles = {frame.columns[0]: ColumnRole.X, frame.columns[1]: ColumnRole.Y}
    sr = StandardizedResult(frame, roles, FileIdentity(identifier + '.txt', 'txt', 'fixture', 2),
                            source_category=SourceCategory.CHROMATOGRAM, metadata={})
    component = Component(identifier, ComponentRole.PRIMARY, identifier + '.txt', dataframe=frame, column_roles=roles,
                          metadata={}, source_category=SourceCategory.CHROMATOGRAM, standardized=sr)
    return Bundle(identifier, identifier, BundleType.CHROMATOGRAM, component_list=[component])


def _upload(store, bundle):
    from callbacks.upload_callbacks import register_upload_callbacks

    class App:
        functions = {}

        def callback(self, *args, **kwargs):
            def wrap(fn):
                self.functions[fn.__name__] = fn
                return fn
            return wrap

    app = App()
    register_upload_callbacks(app, store)
    sent = []
    content = 'data:text/plain;base64,' + base64.b64encode(b'fixture').decode()
    with patch('ingestion.ingest_file', return_value=bundle.primary.standardized, create=True), \
         patch('services.bundling_service.assign_bundles', return_value=[bundle]), \
         patch('dash.set_props', side_effect=lambda cid, props: sent.append((cid, props))):
        result = app.functions['handle_file_upload']([content], ['run.txt'], [0], [], 0)
    return result, sent


def test_the_upload_hands_the_new_tab_its_figure_built_like_the_normal_render():
    from callbacks.viz_callbacks import compose_raw_figure, _get_active_file_group, _tab_id_from_group
    from callbacks.plot_settings_callbacks import settings_for_context
    from services.plot_manager import PlotManager
    store = DataStore()
    result, sent = _upload(store, _run())
    try:
        painted = [props['data'] for cid, props in sent if cid == 'first-paint']
        assert len(painted) == 1
        tab = _tab_id_from_group(_get_active_file_group(store, result[2]))
        assert painted[0]['tab'] == tab
        figure = painted[0]['figure']
        assert figure.layout.meta['gecko_tab_id'] == tab
        assert len(figure.data) == 1 and len(figure.data[0].x) < 3100        # drawn thinned, 24,001 points stored
        expected = compose_raw_figure(store, PlotManager(), tab, _get_active_file_group(store, result[2]),
                                      settings_for_context(store, f'shared:raw:{tab}', result[2]), result[2],
                                      store.get_loaded_files_list(), file_order=None)
        assert figure.to_plotly_json() == expected.to_plotly_json()
    finally:
        import os
        for path in store.temp_files:
            if os.path.exists(path):
                os.unlink(path)
