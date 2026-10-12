"""Peak display geometry follows the rendered signal; measurements stay immutable."""
import numpy as np
from services.plot_arrays import numeric_plot_array


def peak_id_for_trace(trace):
    if trace.meta != 'peak_overlay' or trace.customdata is None or not len(trace.customdata):
        return None
    item = trace.customdata[0]
    return item[0] if isinstance(item, (list, tuple, np.ndarray)) else item


def register_peak_geometry(fig, peak):
    """Carry integration bounds and source ownership through publication snapshots."""
    if not peak.poly_x or not peak.poly_y:
        return
    baseline = None
    if getattr(peak, 'q1', None) is not None and getattr(peak, 'q2', None) is not None:
        baseline = [list(peak.q1), list(peak.q2)]
    elif peak.p_line and len(peak.p_line) == 2:
        baseline = [list(point) for point in peak.p_line]
    if baseline is None:
        n = len(peak.poly_x) // 2
        baseline = [[peak.poly_x[-1], peak.poly_y[-1]], [peak.poly_x[n], peak.poly_y[n]]]
    meta = dict(fig.layout.meta or {})
    geometry = dict(meta.get('gecko_peak_geometry', {}))
    geometry[peak.peak_id] = {'file_id': peak.file_id, 'bounds':[min(peak.poly_x), max(peak.poly_x)], 'baseline':baseline}
    if peak.source == 'deconvolved':
        geometry[peak.peak_id]['fitted_polygon'] = [list(peak.poly_x), list(peak.poly_y)]
    if peak.source == 'detected':
        n = len(peak.poly_x) // 2
        geometry[peak.peak_id]['baseline_points'] = [peak.poly_x[n:][::-1], peak.poly_y[n:][::-1]]
    fig.layout.meta = {**meta, 'gecko_peak_geometry':geometry}


def refresh_peak_display(fig):
    """Rebuild fill tops from current source Y values, keeping original baselines."""
    geometry = dict((fig.layout.meta or {}).get('gecko_peak_geometry', {}))
    sources = {trace.meta['file_id']:trace for trace in fig.data
               if isinstance(trace.meta, dict) and trace.meta.get('file_id') and not getattr(trace, 'fill', None)}
    # Migrate publication snapshots created before display geometry was stored.
    # Compare their original polygon top against the unsmoothed source signal.
    for trace in fig.data:
        peak_id = peak_id_for_trace(trace)
        if not peak_id or peak_id in geometry or trace.fill != 'toself' or len(trace.x) < 4:
            continue
        n = len(trace.x) // 2
        candidates = [source for source in sources.values()
                      if (source.xaxis or 'x', source.yaxis or 'y') == (trace.xaxis or 'x', trace.yaxis or 'y')]
        scored = []
        for source in candidates:
            try:
                x = numeric_plot_array(source.x)
                y = numeric_plot_array(source.meta.get('gecko_original_y', source.y))
                order = np.argsort(x)
                score = np.mean((np.asarray(trace.y[:n])-np.interp(trace.x[:n], x[order], y[order])) ** 2)
                if np.isfinite(score):
                    scored.append((score, source))
            except (TypeError, ValueError):
                continue
        if scored:
            source = min(scored, key=lambda pair:pair[0])[1]
            geometry[peak_id] = {'file_id':source.meta['file_id'], 'bounds':[min(trace.x), max(trace.x)],
                                'baseline':[[trace.x[-1], trace.y[-1]], [trace.x[n], trace.y[n]]]}
    if geometry:
        fig.layout.meta = {**(fig.layout.meta or {}), 'gecko_peak_geometry':geometry}
    for trace in fig.data:
        peak_id = peak_id_for_trace(trace)
        spec = geometry.get(peak_id)
        if not spec or spec['file_id'] not in sources:
            continue
        source = sources[spec['file_id']]
        trace.xaxis, trace.yaxis = source.xaxis or 'x', source.yaxis or 'y'
        if spec.get('fitted_polygon'):
            if trace.fill == 'toself':
                trace.x, trace.y = spec['fitted_polygon']
                trace.customdata = [peak_id] * len(trace.x)
            continue
        try:
            x, y = numeric_plot_array(source.x), numeric_plot_array(source.y)
        except (TypeError, ValueError):
            continue
        if x.ndim != 1 or y.ndim != 1 or len(x) != len(y):
            continue
        finite = np.isfinite(x) & np.isfinite(y)
        x, y = x[finite], y[finite]
        if len(x) < 2:
            continue
        order = np.argsort(x, kind='stable')
        x, y = x[order], y[order]
        if trace.fill == 'toself':
            lo, hi = spec['bounds']
            xs = np.unique(np.r_[lo, x[(x > lo) & (x < hi)], hi])
            ys = np.interp(xs, x, y)
            (x0, y0), (x1, y1) = spec['baseline']
            if x1 == x0:
                continue
            baseline = (np.interp(xs, *spec['baseline_points']) if spec.get('baseline_points')
                        else y0 + (y1-y0) * (xs-x0) / (x1-x0))
            trace.x = np.r_[xs, xs[::-1]].tolist()
            trace.y = np.r_[ys, np.minimum(baseline, ys)[::-1]].tolist()
            trace.customdata = [peak_id] * len(trace.x)
        elif trace.mode == 'text':
            trace.y = np.interp(trace.x, x, y).tolist()
    for shape in fig.layout.shapes or ():
        peak_id = (shape.name or '').removeprefix('baseline:')
        spec = geometry.get(peak_id)
        if spec and spec['file_id'] in sources:
            source = sources[spec['file_id']]
            shape.xref, shape.yref = source.xaxis or 'x', source.yaxis or 'y'
