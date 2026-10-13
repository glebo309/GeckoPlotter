"""A trace keeps its colour when other traces are hidden or shown."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
import pytest  # noqa: E402

FIXTURES = os.path.join(os.path.dirname(__file__), 'ingestion', 'fixtures')


@pytest.fixture(autouse=True)
def ingestion_import(monkeypatch):
    # PlotManager imports `ingestion.types`; tests/ingestion would shadow it.
    import src.ingestion.types as types
    monkeypatch.setitem(sys.modules, 'ingestion.types', types)


def _make_record(path, file_id):
    import base64
    with open(path, 'rb') as handle:
        raw = handle.read()
    return {'id': file_id, 'name': os.path.basename(path), 'type': 'csv', 'size': len(raw),
            'size_display': f'{len(raw)} B', 'last_modified': 0, 'last_modified_display': '', 'preview': '',
            'encoded': f'data:text/csv;base64,{base64.b64encode(raw).decode()}'}


def _load_file(dm, record):
    return dm.load_file_data(record)


def _colors(dm, records, group):
    import plotly.graph_objects as go
    from callbacks.viz_callbacks import _collect_visible_files, _trace_color_slots, _assign_color_slots
    from services.plot_manager import PlotManager
    from services.plot_settings_service import PlotSettingsService
    visible = _collect_visible_files(dm, None, records, target_group_override=group)
    figure = PlotManager().create_multi_file_plot(visible, 'overlay')
    _assign_color_slots(figure, _trace_color_slots(dm, group, records, None))
    PlotSettingsService.apply_to_figure(figure, PlotSettingsService.get_defaults())
    return {t.meta['file_id']: t.line.color for t in figure.data}


def test_hiding_a_trace_does_not_recolour_the_others():
    from services.storage_manager import DataManager
    from callbacks.viz_callbacks import _get_overlay_group
    dm = DataManager()
    records = []
    for index, label in enumerate(['a', 'b', 'c']):
        record = _make_record(os.path.join(FIXTURES, 'simple_xy.csv'), f'file-{index}')
        record['name'] = f'sample_{label}.csv'
        _load_file(dm, record)
        records.append(record)
    first = dm.loaded_data['file-0']
    group = _get_overlay_group(first.get('metadata', {}), first)
    before = _colors(dm, records, group)
    assert len(before) >= 2
    hidden = sorted(before)[0]
    dm.visibility_state = {hidden: False}
    after = _colors(dm, records, group)
    assert hidden not in after
    for file_id, color in after.items():
        assert color == before[file_id]


def test_stacked_panes_share_one_y_label():
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots
    from services.plot_settings_service import PlotSettingsService
    fig = make_subplots(rows=3, cols=1, shared_xaxes=True)
    for row in (1, 2, 3):
        fig.add_trace(go.Scatter(x=[0, 1], y=[0, row]), row=row, col=1)
        fig.update_yaxes(title_text='Absorbance (mAU)', row=row, col=1)
    settings = PlotSettingsService.get_defaults()
    PlotSettingsService.apply_to_figure(fig, settings)
    PlotSettingsService.share_stacked_y_label(fig, settings)
    assert all(not (fig.layout[k].title.text or '') for k in ('yaxis', 'yaxis2', 'yaxis3'))
    labels = [a.text for a in fig.layout.annotations]
    assert labels.count('Absorbance (mAU)') == 1


def test_publication_view_replaces_the_live_shared_y_label():
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots
    from services.plot_settings_service import PlotSettingsService, LIVE_SHARED_Y
    from services.publication_figure import editable_publication_figure
    fig = make_subplots(rows=3, cols=1, shared_xaxes=True)
    for row in (1, 2, 3):
        fig.add_trace(go.Scatter(x=[0, 1], y=[0, row], meta={'file_id': str(row)}), row=row, col=1)
        fig.update_yaxes(title_text='Absorbance (mAU)', row=row, col=1)
    settings = PlotSettingsService.get_defaults()
    PlotSettingsService.apply_to_figure(fig, settings)
    PlotSettingsService.share_stacked_y_label(fig, settings)
    assert [a.name for a in fig.layout.annotations] == [LIVE_SHARED_Y]
    source = fig.to_plotly_json()
    out = editable_publication_figure(source, {'layout_mode': 'stacked', 'shared_axis_labels': True}, {})
    names = [a.name for a in out.layout.annotations]
    assert LIVE_SHARED_Y not in names
    assert names.count('gecko-shared-y') == 1
    out = editable_publication_figure(source, {'layout_mode': 'stacked', 'shared_axis_labels': False}, {})
    assert LIVE_SHARED_Y not in [a.name for a in out.layout.annotations]
    assert out.layout.yaxis.title.text == 'Absorbance (mAU)'
