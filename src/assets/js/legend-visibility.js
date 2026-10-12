(function(){ 'use strict';
window.GeckoLegendVisibility={bind:function(gd){
if(gd.__geckoLegendBound)return;gd.__geckoLegendBound=true;
        gd.on('plotly_legendclick', function (event) {
            if (gd.__geckoLegendDragged || (event.event && event.event.button !== 0)) return false;
            var trace = gd.data[event.curveNumber], meta = trace && trace.meta;
            if (!meta || !meta.file_id) return;
            var buttons = document.querySelectorAll('[id*="visibility-btn"]');
            for (var button of buttons) {
                try {
                    var id = JSON.parse(button.id);
                    if (id.index === meta.file_id) {
                        window.dash_clientside.set_props(id, {n_clicks: Date.now()});
                        return false;
                    }
                } catch (_) {}
            }
        });
        gd.on('plotly_legenddoubleclick', function () { return false; });

}};})();
