"""Skip callback outputs that equal what the browser already holds.

Dash re-triggers every downstream callback for an output even when its value did not change. In this app more
than half of all output updates were repeats, so a single click fanned out into dozens of pointless callbacks
(and each costs the renderer a pass over the whole layout).

For small, plain outputs the browser's current value is sent along as an extra ``State``. If the freshly computed
value is identical, the output becomes ``no_update`` and nothing downstream runs. Comparing with the client's
actual value (not a server-side memory of what was sent) keeps this correct when responses are discarded,
inputs are edited by the user or JavaScript sets props.
"""
from __future__ import annotations

import functools
import json

from dash import Input, Output, State, no_update

# Never compared: large values (the extra State would cost more than it saves) ...
DENY_PROPS = {'figure', 'contents', 'derived_virtual_data', 'selected_cells', 'active_cell'}
DENY_IDS = {'pub-data-store', 'loaded-files', 'file-ui-state', 'table-editor-container', 'metadata-container',
            'file-tree', 'main-plot', 'plot-workspace', 'tab-zoom-memory', 'zoom-state'}
DENY_ID_PROPS = {('pub-table', 'data'), ('pub-table', 'style_data_conditional')}  # thousands of rows
# ... and values that are re-written on purpose to re-trigger consumers.
DENY_ID_PARTS = ('trigger', 'event', 'revision', 'close', 'request', 'counter', 'active-file', 'selected-peak',
                 'baseline-mode', 'undo', 'redo', 'keyboard-action')
# `children` is only compared for small text/control outputs.
CHILDREN_OK = {'inspector-figure-name', 'inspector-figure-summary', 'axis-inspector-cards', 'ms-scan-label',
               'selected-peak-keyboard-state', 'int-detection-target', 'eic-active-list', 'peak-mass-info',
               'ms-spectrum-info', 'pt-panel-header', 'status-text', 'file-info', 'mode-indicator'}


# Opt-in by component-id prefix. Comparing outputs that sit in the integration path made peak integration flaky,
# so only families that are plainly derived UI are compared. Extend with GECKO_DEDUPE_FAMILIES="prefix,prefix".
SAFE_FAMILIES = ('analysis-nav-', 'ms-', 'eic-', 'peak-mass-', 'cross-', 'cal-', 'pub-', 'axis-ctx-', 'legend-ctx-',
                 'trace-ctx-', 'title-ctx-', 'label-ctx-', 'axis-context-', 'legend-context-', 'trace-context-',
                 'title-context-', 'label-context-', 'y2-controls', 'plot-export-data', 'toolbox-')


def _families():
    import os
    extra = tuple(x.strip() for x in os.environ.get('GECKO_DEDUPE_FAMILIES', '').split(',') if x.strip())
    return SAFE_FAMILIES + extra


def eligible(output):
    """True for an ``Output`` whose value may be compared with the client's current one."""
    cid, prop = output.component_id, output.component_property
    if not isinstance(cid, str) or prop in DENY_PROPS or cid in DENY_IDS or (cid, prop) in DENY_ID_PROPS:
        return False
    if not cid.startswith(_families()):
        return False
    if any(part in cid for part in DENY_ID_PARTS):
        return False
    if prop == 'children':
        return cid in CHILDREN_OK
    return True


def _canonical(value):
    """JSON-normalised copy of plain JSON data (``None`` for anything that is not)."""
    try:
        return json.loads(json.dumps(value, sort_keys=True, allow_nan=False))
    except (TypeError, ValueError):
        return None


def _plain(value):
    """True when *value* survives a JSON round trip (so equality of the copies means something)."""
    try:
        json.dumps(value, allow_nan=False)
        return True
    except (TypeError, ValueError):
        return False


def same_as_client(new, current):
    a, b = _canonical(new), _canonical(current)
    return _plain(new) and _plain(current) and a == b


def dedupe_results(result, outputs, current_values):
    """Replace results equal to *current_values* by ``no_update``; others are left untouched."""
    many = isinstance(outputs, (list, tuple))
    values = list(result) if many and isinstance(result, (list, tuple)) else [result]
    if len(values) != len(current_values):
        return result
    changed = False
    for i, (new, current) in enumerate(zip(values, current_values)):
        if current_values[i] is _SKIP or new is no_update:
            continue
        if same_as_client(new, current):
            values[i] = no_update
            changed = True
    if not changed:
        return result
    return tuple(values) if many else values[0]


_SKIP = object()


def _split(args, kwargs):
    """(outputs, inputs_arg, states_arg, count) for plain ``callback(Output(s), inputs, state)`` calls.

    Dash passes the callback its arguments in the order they were declared in the *lists* (an ``Input`` placed in
    the State list keeps its position there), so the lists are kept exactly as given and only extended at the end.
    Flat ``callback(Output, Input, State, ...)`` calls are typed by Dash (all Inputs, then all States).
    Returns ``None`` for anything else.
    """
    if not args or any(key in kwargs for key in ('output', 'inputs', 'state')):
        return None
    first, rest = args[0], list(args[1:])
    if rest and isinstance(rest[-1], bool):  # positional prevent_initial_call
        return None
    deps = (Input, State)
    if rest and isinstance(rest[0], (list, tuple)) and len(rest) <= 2:
        inputs_arg = list(rest[0])
        states_arg = rest[1] if len(rest) == 2 else []
        states_arg = list(states_arg) if isinstance(states_arg, (list, tuple)) else [states_arg]
        if all(isinstance(x, deps) for x in (*inputs_arg, *states_arg)):
            return first, inputs_arg, states_arg, len(inputs_arg) + len(states_arg)
        return None
    flat = []
    for item in rest:
        flat.extend(item) if isinstance(item, (list, tuple)) else flat.append(item)
    if not all(isinstance(x, deps) for x in flat):
        return None
    return (first, [x for x in flat if isinstance(x, Input)], [x for x in flat if isinstance(x, State)],
            len(flat))


def install(app):
    """Wrap ``app.callback`` so eligible outputs are compared with the browser's value.

    Set GECKO_OUTPUT_DEDUPE=0 to turn it off.
    """
    import os
    if os.environ.get('GECKO_OUTPUT_DEDUPE', '1') == '0':
        return app
    original = app.callback

    def callback(*args, **kwargs):
        parts = _split(args, kwargs)
        if parts is None or kwargs.get('background') or kwargs.get('no_output'):
            return original(*args, **kwargs)
        first, inputs, states, declared = parts
        outputs = list(first) if isinstance(first, (list, tuple)) else [first]
        if not outputs or not all(isinstance(o, Output) for o in outputs):
            return original(*args, **kwargs)
        picked = [i for i, o in enumerate(outputs) if eligible(o)]
        if not picked:
            return original(*args, **kwargs)
        # Extra States go last so the callback's own argument order is untouched.
        extra = [State(outputs[i].component_id, outputs[i].component_property) for i in picked]
        decorate = original(first, inputs, [*states, *extra], **kwargs)
        n = len(picked)
        arity = declared + n

        def wrap(fn):
            @functools.wraps(fn)
            def inner(*call_args, **call_kwargs):
                if len(call_args) < arity:  # called directly (tests, tools) without the browser's extra States
                    return fn(*call_args, **call_kwargs)
                current = call_args[len(call_args) - n:]
                result = fn(*call_args[:len(call_args) - n], **call_kwargs)
                full = [_SKIP] * len(outputs)
                for slot, value in zip(picked, current):
                    full[slot] = value
                return dedupe_results(result, first, full)
            return decorate(inner)
        return wrap

    app.callback = callback
    return app
