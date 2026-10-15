"""UV channels exported without their wavelength (Agilent VWD CSV) get it once, for every run, and keep it."""
from types import SimpleNamespace

from services import detector_wavelengths as dw


def _store(*metas):
    components = [SimpleNamespace(metadata=dict(m)) for m in metas]
    return SimpleNamespace(_bundles={'run': SimpleNamespace(component_list=components)}), components


def test_entered_wavelength_names_every_run_of_that_detector_and_is_remembered(tmp_path, monkeypatch):
    monkeypatch.setenv('GECKO_SETTINGS_DIR', str(tmp_path))
    csv_a = {'is_uv_data': True, 'detector_name': 'VWD1A', 'wavelength': None}
    csv_b = {'is_uv_data': True, 'detector_name': 'VWD1B', 'wavelength': None}
    cdf_a = {'is_uv_data': True, 'detector_name': 'VWD1A', 'wavelength': 254}      # the file says so: kept
    store, (a, b, c) = _store(csv_a, csv_b, cdf_a)
    assert dw.needs_wavelength(a.metadata) == 'VWD1A' and dw.needs_wavelength(c.metadata) is None
    assert dw.set_wavelength(store, 'VWD1A', 280) == 1
    assert a.metadata['wavelength_nm'] == 280 and c.metadata['wavelength'] == 254 and b.metadata['wavelength'] is None
    later, (d,) = _store(csv_a)                                                    # a run loaded later
    assert dw.apply_remembered(later) == 1 and d.metadata['wavelength_nm'] == 280
    assert dw.needs_wavelength(d.metadata) == 'VWD1A'                              # still editable
