"""Read numeric Plotly arrays before and after browser serialization."""
import base64
import numpy as np


def numeric_plot_array(values):
    """Accept ordinary arrays and Plotly 6's binary JSON representation."""
    if isinstance(values, dict) and 'bdata' in values:
        array = np.frombuffer(base64.b64decode(values['bdata']), dtype=values['dtype'])
        if values.get('shape'):
            array = array.reshape(tuple(int(n) for n in str(values['shape']).split(',')))
        return array.astype(float, copy=False)
    return np.asarray(values, dtype=float)
