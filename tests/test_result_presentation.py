import pandas as pd
from callbacks.tab_callbacks import _result_columns


def test_concentration_units_move_to_heading_without_changing_values():
    frame = pd.DataFrame([{'Sample':'A', 'Concentration':14.71683211,
        'Concentration units':'mM', 'Calibration':'Analyte', 'Calibration status':'Calibrated'}])
    cols = _result_columns(frame, set())
    assert [c['id'] for c in cols] == ['Sample','Concentration']
    assert cols[1]['name'] == 'Concentration (mM)'
    assert frame.iloc[0]['Concentration'] == 14.71683211


def test_mixed_units_remain_explicit_and_calibration_metadata_is_not_a_column():
    frame = pd.DataFrame({'Concentration':[1.,2.], 'Concentration units':['mM','mg/mL'],
                          'Calibration status':['Calibrated','Outside calibration range']})
    cols = _result_columns(frame, set())
    assert [c['id'] for c in cols] == ['Concentration','Concentration units']
    assert cols[1]['name'] == 'Units'
