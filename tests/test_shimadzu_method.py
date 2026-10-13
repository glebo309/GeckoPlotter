"""Instrument methods read from LabSolutions .lcm/.lcd files."""
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from services import shimadzu_method as sm  # noqa: E402
from services.metadata_display import group_metadata  # noqa: E402

REAL = Path('/Volumes/Paradisi/Group_Members/Glenn-Synology/SHIMZU')
LCM = REAL / 'general_method_1.24_95_1.26_100_3min.lcm'


def test_float_fields_are_little_endian_float32():
    assert sm._float('0AD7233C') == 0.01
    assert sm._float('6666663F') == 0.9
    assert sm._float('zz') is None


def test_time_program_groups_codes_by_time():
    xml = ('<TP Name="LC" UI="1" LI="1" UN="PUMP" PgN="PUMP$PROG">'
           '<TPLD Time="0000803F" Cmt=""><TPD ID="TMPGcode"><Val>4</Val><Type>17</Type></TPD>'
           '<TPD ID="TMPGdata"><Val>6666663F</Val><Type>4</Type></TPD></TPLD>'
           '<TPLD Time="0000803F" Cmt=""><TPD ID="TMPGcode"><Val>5</Val><Type>17</Type></TPD>'
           '<TPD ID="TMPGdata"><Val>0000A040</Val><Type>4</Type></TPD></TPLD>'
           '<TPLD Time="00004040" Cmt=""><TPD ID="TMPGcode"><Val>5</Val><Type>17</Type></TPD>'
           '<TPD ID="TMPGdata"><Val>0000BE42</Val><Type>4</Type></TPD></TPLD></TP>')
    assert sm._time_program(xml) == [{'time_min': 1.0, 'flow_ml_min': 0.9, 'b_percent': 5.0},
                                     {'time_min': 3.0, 'b_percent': 95.0}]


class _Part:
    def __init__(self, cid, metadata):
        self.component_id, self.metadata = cid, metadata


class _Bundle:
    def __init__(self, *parts):
        self.component_list = list(parts)


class _Store:
    def __init__(self, *parts):
        self.instrument_methods, self.instrument_method_files = {}, {}
        self._bundles = {'1': _Bundle(*parts)}


RUN = {'file_name': 'run.lcd', 'pump_program': [{'time_min': 1.0, 'b_percent': 5.0, 'flow_ml_min': 0.9}],
       'mobile_phase': {'A': 'Water', 'B': 'Acetonitrile'}, 'column_oven': {'temperature_c': 40.0, 'enabled': True},
       'run_identity': {'generated_utc': '2026-10-12T13:43:39+00:00', 'modified_utc': '2026-10-12T13:47:25+00:00'}}


def test_lcd_method_is_attached_by_the_timestamps_inside_both_files():
    mine = _Part('a', {'file_generated': '2026-10-12T15:43:39', 'file_modified': '2026-10-12T15:47:25',
                       'method_file': 'something_else.lcm', 'data_file': 'other.lcd'})
    other_run = _Part('b', {'file_generated': '2026-10-12T15:43:40', 'file_modified': '2026-10-12T15:47:25',
                            'method_file': 'run.lcm', 'data_file': 'run.lcd'})
    one_stamp_only = _Part('c', {'file_generated': '2026-10-12T15:43:39', 'data_file': 'run.lcd'})
    skewed = _Part('d', {'file_generated': '2026-10-12T15:43:39', 'file_modified': '2026-10-12T16:47:25'})
    store = _Store(mine, other_run, one_stamp_only, skewed)
    assert sm.register_method(store, RUN, b'bytes') == 1
    assert 'method_details' in mine.metadata
    for part in (other_run, one_stamp_only, skewed):
        assert 'method_details' not in part.metadata
    assert store.instrument_method_files == {sm.method_key(RUN): b'bytes'}

    groups = dict(group_metadata(mine.metadata))
    assert ('1 min', '5 % B, 0.9 mL/min') in groups['Gradient']
    assert ('Mobile phase B', 'Acetonitrile') in groups['Method']
    assert ('Column oven', '40 °C') in groups['Method']


LCM_METHOD = {'file_name': 'general_method_1.24_95_1.26_100_3min.lcm', 'sha256': 'ab',
       'pump_program': [{'time_min': 0.25, 'b_percent': 5.0, 'flow_ml_min': 0.9},
                        {'time_min': 1.24, 'b_percent': 95.0, 'flow_ml_min': 0.9}],
       'file_properties': {'modified_utc': '2026-09-15T14:49:21+00:00', 'modified_by': 'System Administrator'}}


def test_lcm_method_is_attached_by_the_method_file_the_export_names_and_checked_against_the_run_time():
    ran = _Part('a', {'method_file': 'General_Method_1.24_95_1.26_100_3min.lcm', 'acquired': '2026-10-12T15:43:55'})
    other = _Part('b', {'method_file': 'another.lcm', 'acquired': '2026-10-12T15:43:55'})
    unnamed = _Part('c', {'acquired': '2026-10-12T15:43:55'})
    store = _Store(ran, other, unnamed)
    assert sm.register_method(store, LCM_METHOD) == 1
    assert 'method_details' not in other.metadata and 'method_details' not in unnamed.metadata
    assert ran.metadata['method_key'] == sm.method_key(LCM_METHOD)
    check = dict(group_metadata(ran.metadata))['Method']
    assert any(label == 'Check against this run' and 'before this run' in text for label, text in check)


def test_the_check_says_so_when_the_method_was_saved_after_the_run():
    method = {**LCM_METHOD, 'file_properties': {'modified_utc': '2026-10-20T10:00:00+00:00'}}
    assert 'after this run' in sm._check_text(method, '2026-10-12T15:43:55')
    assert 'close to this run' in sm._check_text({**LCM_METHOD, 'file_properties': {'modified_utc': '2026-10-12T14:00:00+00:00'}},
                                                 '2026-10-12T15:43:55')
    assert sm._check_text(LCM_METHOD, None) is None


def test_gradient_overlay_is_drawn_once_per_method_on_its_own_axis():
    import plotly.graph_objects as go
    store = _Store()
    sm.register_method(store, LCM_METHOD)
    key = sm.method_key(LCM_METHOD)
    entries = [('a', {'metadata': {'method_key': key}}), ('b', {'metadata': {'method_key': key}}),
               ('c', {'metadata': {}})]
    figure = go.Figure(go.Scatter(x=[0, 1], y=[0, 1]))
    assert sm.add_gradient_overlay(figure, store, entries) == 1
    trace = figure.data[-1]
    assert list(trace.x) == [0.25, 1.24] and list(trace.y) == [5.0, 95.0] and trace.yaxis == 'y9'
    assert figure.layout.yaxis9.overlaying == 'y' and figure.layout.yaxis9.side == 'right'
    assert sm.add_gradient_overlay(go.Figure(), store, [('c', {'metadata': {}})]) == 0


def test_an_unreadable_file_is_reported_not_raised_as_an_os_error():
    with pytest.raises(sm.MethodFormatError):
        sm.read_method(b'not an ole file', 'x.lcm')


@pytest.mark.skipif(not LCM.exists(), reason='needs the HPLC method on the group share')
def test_real_method_matches_the_gradient_in_its_name():
    method = sm.read_method(LCM)
    program = {step['time_min']: step for step in method['pump_program']}
    assert program[1.24]['b_percent'] == 95.0 and program[1.26]['b_percent'] == 100.0   # "1.24_95_1.26_100"
    assert {step['flow_ml_min'] for step in method['pump_program']} == {0.9}
    assert method['mobile_phase'] == {'A': 'Water', 'B': 'Acetonitrile'}
    assert method['column_oven']['temperature_c'] == 40.0
    assert method['pressure_limit_bar'] == 1000


def test_methods_paragraph_reads_like_a_journal_methods_section():
    method = {'file_name': 'run.lcm', 'devices': {'pump': 'LC-40D XS', 'autosampler': 'SIL-40C XS',
                                                  'column_oven': 'CTO-40S', 'detector': 'SPD-M40'},
              'pump_program': [{'time_min': 0.25, 'b_percent': 5.0, 'flow_ml_min': 0.9},
                               {'time_min': 1.25, 'b_percent': 95.0, 'flow_ml_min': 0.9},
                               {'time_min': 2.0, 'b_percent': 95.0, 'flow_ml_min': 0.9}],
              'mobile_phase': {'A': 'Water', 'B': 'Acetonitrile'},
              'column_oven': {'temperature_c': 40.0, 'enabled': True}, 'autosampler': {'cooler_temperature_c': 25.0}}
    samples = [{'instrument': 'Shimadzu LC-PDA-1', 'injection_volume_ul': 1.0, 'wavelength_nm': 263.0,
                'bandwidth_nm': 4.0, 'software_version': '5.141'}]
    paragraph = sm.method_paragraph(method, samples)
    assert paragraph['heading'] == 'General procedure for HPLC–PDA analysis'
    text = paragraph['text']
    assert 'A linear gradient from 5% to 95% B over 1 min, followed by a hold at 95% B for 0.75 min, was applied ' \
           'at a flow rate of 0.9 mL min−1.' in text
    for expected in ('Shimadzu LC-PDA-1 system (LC-40D XS pump, SIL-40C XS autosampler and CTO-40S column oven)',
                     'mobile phase A (water) and mobile phase B (acetonitrile)', 'maintained at 40 °C',
                     'A volume of 1 µL was injected from an autosampler kept at 25 °C', 'SPD-M40 photodiode array',
                     'at 263 nm (bandwidth 4 nm)', 'LabSolutions (version 5.141)', '[column: not recorded'):
        assert expected in text


def test_gradient_is_held_to_the_end_of_the_run():
    import plotly.graph_objects as go
    store = _Store()
    sm.register_method(store, LCM_METHOD)
    entries = [('a', {'metadata': {'method_key': sm.method_key(LCM_METHOD), 'time_end_min': 3.5}})]
    figure = go.Figure()
    sm.add_gradient_overlay(figure, store, entries)
    assert list(figure.data[0].x)[-1] == 3.5 and list(figure.data[0].y)[-1] == 95.0


def test_status_overlay_draws_each_sample_once_in_its_chromatogram_colour():
    import plotly.graph_objects as go
    series = {'time_min': [0, 1, 2], 'values': [800.0, 820.0, 810.0], 'unit': 'bar'}
    meta = {'parent_bundle_id': 'bundle-1', 'instrument_status': {'Pump A Pressure': series}}
    figure = go.Figure(go.Scatter(x=[0, 1], y=[0, 1], line=dict(color='#cc0000'), meta={'file_id': 'c1'}))
    entries = [('Ch2', {'record': {'id': 'c1'}, 'metadata': meta}), ('Ch4', {'record': {'id': 'c2'}, 'metadata': meta}),
               ('other', {'record': {'id': 'c3'}, 'metadata': {}})]
    assert sm.add_status_overlay(figure, entries, 'Pump A Pressure') == 1       # Ch2 and Ch4 share one injection
    trace = figure.data[-1]
    assert list(trace.y) == [800.0, 820.0, 810.0] and trace.line.color == '#cc0000' and trace.yaxis == 'y9'
    assert figure.layout.yaxis9.title.text == 'Pump A Pressure (bar)'
    assert sm.add_status_overlay(go.Figure(), entries, 'Oven Temp.') == 0


def test_column_dwell_volume_and_fast_steps_in_the_methods_paragraph():
    method = {'file_name': 'run.lcm', 'devices': {}, 'mobile_phase': {},
              'pump_program': [{'time_min': 0.25, 'b_percent': 5.0, 'flow_ml_min': 0.9},
                               {'time_min': 1.24, 'b_percent': 95.0, 'flow_ml_min': 0.9},
                               {'time_min': 1.26, 'b_percent': 100.0, 'flow_ml_min': 0.9},
                               {'time_min': 1.63, 'b_percent': 100.0, 'flow_ml_min': 0.9},
                               {'time_min': 1.74, 'b_percent': 5.0, 'flow_ml_min': 0.9},
                               {'time_min': 2.48, 'b_percent': 5.0, 'flow_ml_min': 0.9}]}
    samples = [{'wavelength_nm': 263.0, 'bandwidth_nm': 4.0}, {'wavelength_nm': 250.0, 'bandwidth_nm': 4.0}]
    text = sm.method_paragraph(method, samples, 'Shimadzu Shim-pack Scepter C18-120 (1.9 µm, 2.1 × 100 mm)', 715)['text']
    assert 'on a Shimadzu Shim-pack Scepter C18-120 (1.9 µm, 2.1 × 100 mm).' in text and '[column' not in text
    assert ('A linear gradient from 5% to 95% B over 0.99 min, followed by a step to 100% B held for 0.39 min, '
            'a linear return from 100% to 5% B over 0.11 min and a hold at 5% B for 0.74 min, was applied at a flow rate '
            'of 0.9 mL min−1.') in text
    assert 'approximately 715 µL' in text
    assert 'at 250 and 263 nm (bandwidth 4 nm)' in text
    assert '[column' in sm.method_paragraph(method, samples)['text']          # no column given: placeholder


def test_gradient_at_the_column_inlet_is_shifted_by_dwell_volume_over_flow():
    import plotly.graph_objects as go
    store = _Store()
    program = [{'time_min': 0.25, 'b_percent': 5.0, 'flow_ml_min': 0.9}, {'time_min': 1.25, 'b_percent': 95.0, 'flow_ml_min': 0.9}]
    method = {**LCM_METHOD, 'pump_program': program}
    sm.register_method(store, method)
    entries = [('a', {'metadata': {'method_key': sm.method_key(method)}})]
    figure = go.Figure()
    sm.add_gradient_overlay(figure, store, entries, dwell_volume_ul=715)
    assert [round(x, 2) for x in figure.data[0].x] == [1.04, 2.04]            # 0.715 mL / 0.9 mL/min = 0.79 min
    assert figure.data[0].name == 'LC gradient at the column inlet (% B)'
