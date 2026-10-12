(function () {
    // Inspectors need identities and appearance, never the measurement arrays.
    function summarize(figure, previous) {
        if (!figure) return previous == null ? window.dash_clientside.no_update : null;
        var data = (figure.data || []).map(function (trace) {
            var item = {};
            ['type', 'name', 'fill', 'opacity'].forEach(function (key) {
                if (trace[key] !== undefined) item[key] = trace[key];
            });
            if (trace.meta) {
                item.meta = {};
                ['file_id', 'pda_preview', 'pda_source_id'].forEach(function (key) {
                    if (trace.meta[key] !== undefined) item.meta[key] = trace.meta[key];
                });
            }
            if (trace.line) {
                item.line = {};
                ['color', 'width', 'dash'].forEach(function (key) {
                    if (trace.line[key] !== undefined && !Array.isArray(trace.line[key])) item.line[key] = trace.line[key];
                });
            }
            if (trace.marker && typeof trace.marker.color === 'string') item.marker = {color: trace.marker.color};
            return item;
        });
        var layout = {}, source = figure.layout || {};
        Object.keys(source).forEach(function (key) {
            if (/^[xy]axis\d*$/.test(key) || key === 'meta' || key === 'title') layout[key] = source[key];
        });
        var result = {data: data, layout: layout};
        return JSON.stringify(result) === JSON.stringify(previous) ? window.dash_clientside.no_update : result;
    }
    window.dash_clientside = Object.assign({}, window.dash_clientside, {
        inspectorContext: {summarize: summarize}
    });
}());
