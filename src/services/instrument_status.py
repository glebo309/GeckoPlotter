"""Fixed acquisition traces: share their arrays in undo and record digests in history."""
import hashlib

import numpy as np


KEYS = ('time_min', 'values')


def summary(trace):
    if not isinstance(trace, dict) or not all(key in trace for key in KEYS):
        return trace
    immutable = all(isinstance(trace[key], np.ndarray) and not trace[key].flags.writeable for key in KEYS)
    digest = trace.get('data_sha256') if immutable else None
    if not digest:
        hasher = hashlib.sha256()
        for key in KEYS:
            array = np.asarray(trace[key], dtype='<f8')
            hasher.update(str(array.shape).encode('ascii'))
            hasher.update(array.tobytes())
        digest = hasher.hexdigest()
    return {**{k: v for k, v in trace.items() if k not in KEYS},
            'points': len(trace['values']), 'data_sha256': digest}


def freeze(traces):
    result = {}
    for name, trace in traces.items():
        if not isinstance(trace, dict) or not all(key in trace for key in KEYS):
            result[name] = trace
            continue
        fixed = dict(trace)
        for key in KEYS:
            value = trace[key]
            if not isinstance(value, np.ndarray) or value.flags.writeable:
                value = np.array(value, dtype=float, copy=True)
                value.setflags(write=False)
            fixed[key] = value
        # Imported contents are authoritative; do not trust a digest supplied with mutable arrays.
        fixed.pop('data_sha256', None)
        fixed['data_sha256'] = summary(fixed)['data_sha256']
        result[name] = fixed
    return result
