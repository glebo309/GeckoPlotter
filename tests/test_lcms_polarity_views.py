import numpy as np
import pytest
from types import SimpleNamespace
from test_render_tab_performance import App
from test_file_controls import component
from services.data_store import DataStore, Bundle, BundleType, ComponentRole
from callbacks.lcms_callbacks import register_lcms_callbacks


def fixture(modes=('positive', 'negative')):
    store = DataStore()
    components = [component(mode, ComponentRole.MS_POSITIVE if mode == 'positive' else ComponentRole.MS_NEGATIVE)
                  for mode in modes]
    components.append(component('uv', ComponentRole.VWD_A))
    store.add_bundle(Bundle('sample', 'Sample', BundleType.LCMS, component_list=components))
    calls = []
    store.lcms_service = SimpleNamespace(has_spectral_data=lambda entry: entry['record']['id'] in modes,
        get_averaged_spectrum=lambda entry, start, end: (calls.append((entry['record']['id'], start, end)) or
            (np.array([100., 200.]), np.array([10., 20.]))))
    peak = SimpleNamespace(peak_id='peak', file_id='negative', rt=1., rt_start=.8, rt_end=1.2,
                           label='Peak', name='Peak')
    store.peak_service.get_peaks = lambda fid: [peak] if fid == 'negative' else []
    app = App(); register_lcms_callbacks(app, store)
    return app.functions, calls


@pytest.mark.parametrize('negative,expected', [('positive', 'positive'), ('negative', 'negative')])
def test_peak_mass_resolves_explicit_mode_even_when_source_is_negative(monkeypatch, negative, expected):
    functions, calls = fixture()
    monkeypatch.setattr('callbacks.lcms_callbacks._build_peak_mass_figure', lambda *args: ('figure', args[-1]))
    result = functions['show_peak_mass']('peak', negative, 'negative')
    assert calls == [(expected, .8, 1.2)]
    assert result[1] == ('−' if negative == 'negative' else '+')


def test_peak_mass_keeps_valid_mode_when_selecting_another_signal():
    functions, _ = fixture()
    result = functions['peak_mass_polarity_visibility']('uv', 'negative')
    assert result[0] == 'negative'
    assert result[1]['display'] == 'flex'
    assert not any(option['disabled'] for option in result[2])


@pytest.mark.parametrize('mode,negative', [('positive', False), ('negative', True)])
def test_single_mode_mass_controls_remain_visible_but_disable_unavailable_choice(mode, negative):
    functions, _ = fixture((mode,))
    result = functions['sync_polarity_toggle'](mode)
    assert result[0] == mode
    assert result[1]['display'] == 'flex'
    assert {option['value']: option['disabled'] for option in result[2]} == {'positive': negative, 'negative': not negative}
    assert result[4] == mode
    assert result[6] == result[2]
    result = functions['peak_mass_polarity_visibility']('uv', 'positive' if negative else 'negative')
    assert result[0] == mode
    assert result[1]['display'] == 'flex'
    assert {option['value']: option['disabled'] for option in result[2]} == {'positive': negative, 'negative': not negative}
    assert mode in result[3].lower()


def test_scan_and_eic_keep_negative_mode_when_selecting_uv():
    functions, _ = fixture()
    # File selection and slider configuration use the same spectral resolver.
    from callbacks.lcms_callbacks import _resolve_lcms_spectral_entry
    callback = functions['sync_polarity_toggle']
    store = next(cell.cell_contents for cell in callback.__closure__ if isinstance(cell.cell_contents, DataStore))
    assert _resolve_lcms_spectral_entry(store, 'negative', store.lcms_service)[0] == 'negative'
    assert _resolve_lcms_spectral_entry(store, 'uv', store.lcms_service)[0] == 'negative'
    assert callback('uv')[0] == 'negative'
    # Explicitly selecting positive is still respected.
    assert _resolve_lcms_spectral_entry(store, 'positive', store.lcms_service)[0] == 'positive'
    assert _resolve_lcms_spectral_entry(store, 'uv', store.lcms_service)[0] == 'positive'


def test_lower_controls_use_same_segmented_style_as_main_toolbar():
    from components.spectrum_polarity_control import create_spectrum_polarity_control
    import dash_mantine_components as dmc
    for prefix in ('ms', 'eic', 'peak-mass'):
        wrapper = create_spectrum_polarity_control(prefix)
        control = wrapper.children
        assert isinstance(control, dmc.SegmentedControl)
        assert control.id == prefix + '-polarity-toggle'
        assert control.value == 'positive'
        assert control.size == 'xs'
        assert [(o['label'], o['value']) for o in control.data] == [('+', 'positive'), ('−', 'negative')]


@pytest.mark.parametrize('control', ['ms', 'eic'])
@pytest.mark.parametrize('mode,source', [('positive', 'negative'), ('negative', 'positive')])
def test_segment_choice_selects_requested_source(monkeypatch, control, mode, source):
    functions, _ = fixture()
    monkeypatch.setattr('callbacks.lcms_callbacks.callback_context', SimpleNamespace(
        triggered=[{'prop_id': control + '-polarity-toggle.value'}]))
    args = (mode, source) if control == 'ms' else (source, mode)
    assert functions['polarity_toggle_switch'](*args, source) == mode


def test_scan_cursor_owner_is_resolved_spectral_component_even_when_uv_selected(monkeypatch):
    functions, _ = fixture()
    callback = functions['configure_scan_slider']
    store = next(cell.cell_contents for cell in callback.__closure__ if isinstance(cell.cell_contents, DataStore))
    from callbacks.lcms_callbacks import _resolve_lcms_spectral_entry
    _resolve_lcms_spectral_entry(store, 'negative', store.lcms_service)
    store.lcms_service.get_scan_count = lambda entry: 3
    store.lcms_service.extract_tic = lambda entry: (np.array([0., 1., 2.]), np.array([1., 9., 2.]))
    monkeypatch.setattr('callbacks.lcms_callbacks._scan_label', lambda *args: 'Scan 2')
    result = callback('uv', [{'id': fid} for fid in ('positive', 'negative', 'uv')])
    assert result[-1] == {'file_id': 'negative'}


@pytest.mark.parametrize('control', ['ms', 'eic'])
@pytest.mark.parametrize('previous_mode', ['positive', 'negative'])
def test_uv_selection_survives_programmatic_polarity_control_sync(monkeypatch, control, previous_mode):
    import dash
    from callbacks.lcms_callbacks import _resolve_lcms_spectral_entry
    functions,_=fixture()
    sync=functions['sync_polarity_toggle']
    store=next(cell.cell_contents for cell in sync.__closure__ if isinstance(cell.cell_contents,DataStore))
    _resolve_lcms_spectral_entry(store,previous_mode,store.lcms_service)
    values=sync('uv')
    monkeypatch.setattr('callbacks.lcms_callbacks.callback_context',SimpleNamespace(
        triggered=[{'prop_id':control+'-polarity-toggle.value'}]))
    with pytest.raises(dash.exceptions.PreventUpdate):
        functions['polarity_toggle_switch'](values[0],values[4],'uv')
    assert _resolve_lcms_spectral_entry(store,'uv',store.lcms_service)[0]==previous_mode
