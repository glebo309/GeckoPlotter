"""LC-MS viewer callbacks.

Wires the MS Analysis bottom-panel tab:
  - Click on main-plot chromatogram → mass spectrum display
  - EIC extraction from m/z input → overlay on main plot
"""
from __future__ import annotations

import logging

import dash
from dash import Input, Output, State, html, dcc, callback_context
import plotly.graph_objects as go
import numpy as np

log = logging.getLogger(__name__)


def register_lcms_callbacks(app, data_manager):
    """Register LC-MS viewer callbacks against *app*."""

    lcms_svc = data_manager.lcms_service

    from services.data_store import BundleType, ComponentRole

    # ------------------------------------------------------------------
    # 1. Click on main-plot → update mass spectrum figure
    # ------------------------------------------------------------------
    @app.callback(
        [Output('ms-spectrum-graph', 'figure'),
         Output('ms-spectrum-info', 'children'),
         Output('ms-scan-slider', 'value', allow_duplicate=True),
         Output('ms-scan-label', 'children', allow_duplicate=True)],
        [Input('main-plot', 'clickData'),
         Input('eic-graph', 'clickData')],
        State('active-file', 'data'),
        prevent_initial_call=True,
    )
    def update_mass_spectrum(main_click_data, eic_click_data, active_file):
        trigger_id = callback_context.triggered[0]['prop_id'].split('.')[0] if callback_context.triggered else ''
        click_data = eic_click_data if trigger_id == 'eic-graph' else main_click_data
        if not click_data or not active_file:
            return _empty_spectrum("Click on the chromatogram to view a mass spectrum"), "", dash.no_update, dash.no_update

        resolved = _resolve_lcms_spectral_entry(data_manager, active_file, lcms_svc)
        file_id, file_data = resolved if resolved else (None, None)
        if not file_data or not lcms_svc.has_spectral_data(file_data):
            return _empty_spectrum("No mass spectral data for this file"), "", dash.no_update, dash.no_update

        point = click_data['points'][0]
        rt = point.get('x', 0)

        fig, status, scan_idx = _build_spectrum_at_time(lcms_svc, file_data, rt)
        return fig, _source_status(trigger_id, status), scan_idx, _scan_label(lcms_svc, file_data, scan_idx)

    @app.callback(
        [Output('ms-scan-slider', 'min'),
         Output('ms-scan-slider', 'max'),
         Output('ms-scan-slider', 'value'),
         Output('ms-scan-label', 'children'),
         Output('ms-active-subplot-idx', 'data')],
        [Input('active-file', 'data')],
        State('loaded-files', 'data'),
        prevent_initial_call=True,
    )
    def configure_scan_slider(active_file, loaded_files):
        resolved = _resolve_lcms_spectral_entry(data_manager, active_file, lcms_svc)
        file_id, file_data = resolved if resolved else (None, None)
        if not file_data or not lcms_svc.has_spectral_data(file_data):
            return 0, 1, 0, 'No scan selected', {'file_id': None}

        n_scans = max(lcms_svc.get_scan_count(file_data), 1)
        time_arr, _ = lcms_svc.extract_tic(file_data)
        apex_idx = 0
        if time_arr.size:
            try:
                _, intensity = lcms_svc.extract_tic(file_data)
                apex_idx = int(np.argmax(intensity)) if intensity.size else 0
            except ValueError:
                apex_idx = 0
        apex_idx = min(max(apex_idx, 0), n_scans - 1)
        return 0, n_scans - 1, apex_idx, _scan_label(lcms_svc, file_data, apex_idx), {'file_id': file_id}

    # ------------------------------------------------------------------
    # Polarity toggle: sync both toggles from active-file selection
    # ------------------------------------------------------------------
    @app.callback(
        [Output('ms-polarity-toggle', 'value'), Output('ms-polarity-toggle-wrapper', 'style'),
         Output('ms-polarity-toggle', 'data'), Output('ms-polarity-toggle-wrapper', 'title'),
         Output('eic-polarity-toggle', 'value'), Output('eic-polarity-toggle-wrapper', 'style'),
         Output('eic-polarity-toggle', 'data'), Output('eic-polarity-toggle-wrapper', 'title')],
        Input('active-file', 'data'), prevent_initial_call=True,
    )
    def sync_polarity_toggle(active_file):
        """Show the selected spectral mode and disable only unavailable modes."""
        bundle = _lcms_bundle(data_manager, active_file)
        style = {'display': 'flex' if bundle else 'none', 'alignItems': 'center', 'gap': '2px'}
        positive = _polarity_spectral_entry(data_manager, active_file, False, lcms_svc) is not None if bundle else False
        negative = _polarity_spectral_entry(data_manager, active_file, True, lcms_svc) is not None if bundle else False
        value = 'negative' if negative and not positive else 'positive'
        if positive and negative:
            resolved = _resolve_lcms_spectral_entry(data_manager, active_file, lcms_svc)
            if resolved:
                selected = next((c for c in bundle.component_list if c.component_id == resolved[0]), None)
                value = 'negative' if selected and selected.role == ComponentRole.MS_NEGATIVE else 'positive'
        options = _spectrum_polarity_options(positive, negative)
        result = (value, style, options, _polarity_availability(positive, negative))
        return result + result

    # ------------------------------------------------------------------
    # Polarity toggle: switch active file when either toggle is clicked
    # ------------------------------------------------------------------
    @app.callback(
        Output('active-file', 'data', allow_duplicate=True),
        [Input('ms-polarity-toggle', 'value'),
         Input('eic-polarity-toggle', 'value')],
        State('active-file', 'data'),
        prevent_initial_call=True,
    )
    def polarity_toggle_switch(ms_value, eic_value, active_file):
        """Switch active MS component when either polarity toggle is clicked."""
        if active_file is None:
            raise dash.exceptions.PreventUpdate

        trigger = callback_context.triggered[0]['prop_id'] if callback_context.triggered else ''
        value = eic_value if 'eic-polarity' in trigger else ms_value
        if value not in ('positive', 'negative'):
            raise dash.exceptions.PreventUpdate
        is_negative = value == 'negative'

        bundle = data_manager.get_bundle(active_file) if hasattr(data_manager, 'get_bundle') else None
        if not bundle and hasattr(data_manager, 'get_bundle_for_component'):
            bundle = data_manager.get_bundle_for_component(active_file)
        if not bundle or bundle.bundle_type != BundleType.LCMS:
            raise dash.exceptions.PreventUpdate

        target = _polarity_spectral_entry(data_manager, active_file, is_negative, lcms_svc)
        if not target or target[0] == active_file:
            raise dash.exceptions.PreventUpdate
        # File selection synchronizes both controls. That echo is not a user
        # request to replace the selected UV channel with its spectral source.
        current = _resolve_lcms_spectral_entry(data_manager, active_file, lcms_svc)
        if current and current[0] == target[0]:
            raise dash.exceptions.PreventUpdate
        return target[0]

    @app.callback(
        [Output('ms-spectrum-graph', 'figure', allow_duplicate=True),
         Output('ms-spectrum-info', 'children', allow_duplicate=True),
         Output('ms-scan-label', 'children', allow_duplicate=True)],
        Input('ms-scan-slider', 'value'),
        State('active-file', 'data'),
        prevent_initial_call=True,
    )
    def scrub_mass_spectrum(scan_idx, active_file):
        resolved = _resolve_lcms_spectral_entry(data_manager, active_file, lcms_svc)
        file_id, file_data = resolved if resolved else (None, None)
        if scan_idx is None or not file_data or not lcms_svc.has_spectral_data(file_data):
            return dash.no_update, dash.no_update, dash.no_update
        fig, status, resolved_idx = _build_spectrum_at_scan(lcms_svc, file_data, int(scan_idx))
        return fig, _source_status('slider', status), _scan_label(lcms_svc, file_data, resolved_idx)

    @app.callback(
        Output('ms-scan-slider', 'value', allow_duplicate=True),
        Input('ms-scan-client-input', 'value'),
        State('ms-scan-slider', 'value'),
        prevent_initial_call=True,
    )
    def sync_client_scan_event(input_scan_idx, current_scan_idx):
        """Bridge browser plot drag/click scan events back into the Dash slider."""
        if input_scan_idx is None:
            return dash.no_update
        try:
            scan_idx = int(input_scan_idx)
            current_idx = int(current_scan_idx) if current_scan_idx is not None else None
        except (TypeError, ValueError):
            return dash.no_update
        if current_idx == scan_idx:
            return dash.no_update
        return scan_idx

    app.clientside_callback(
        """
        function(scanIdx, activeTab, activeFile, source, figure) {
            var hidden = {
                position: 'absolute',
                display: 'none',
                top: '0px',
                left: '0px',
                height: '0px',
                width: '18px',
                borderLeft: '2px dotted #111',
                zIndex: 30,
                pointerEvents: 'auto',
                cursor: 'col-resize'
            };

            function visibleStyle(left, top, height) {
                return {
                    position: 'absolute',
                    display: 'block',
                    top: top + 'px',
                    left: left + 'px',
                    height: Math.max(0, height) + 'px',
                    width: '18px',
                    borderLeft: '2px dotted #111',
                    zIndex: 30,
                    pointerEvents: 'auto',
                    cursor: 'col-resize'
                };
            }

            var sliderRoot = document.getElementById('ms-scan-slider');
            var active = !!(sliderRoot && sliderRoot.getClientRects && sliderRoot.getClientRects().length);
            // Set ownership even while the viewer or source trace is hidden.
            window.__geckoLcmsScanState = {sourceFileId: source && source.file_id, idx: scanIdx};
            var cursor = window.GeckoLcmsScanCursor;
            if (cursor) cursor.sync();
            var overlay = document.getElementById('lcms-scan-cursor-overlay');
            var host = overlay ? overlay.parentElement : null;
            var handle = sliderRoot ? sliderRoot.querySelector('[role="slider"]') : null;

            if ((activeTab !== 'ms-scan' && activeTab !== 'ms-eic' && activeTab !== 'ms-peak-mass') || !active || scanIdx === null || scanIdx === undefined || !host || !handle) {
                return hidden;
            }

            var rect = cursor ? cursor.plotRect() : null;
            if (!rect) return hidden;

            var maxIdx = Number(handle.getAttribute('aria-valuemax'));
            if (!Number.isFinite(maxIdx) || maxIdx <= 0) {
                return hidden;
            }

            var idx = Math.max(0, Math.min(Math.round(Number(scanIdx)), Math.round(maxIdx)));
            var hostRect = host.getBoundingClientRect();
            var left = rect.left - hostRect.left + (idx / maxIdx) * rect.width;
            var top = rect.top - hostRect.top;
            var height = rect.height;

            return visibleStyle(left, top, height);
        }
        """,
        Output('lcms-scan-cursor-overlay', 'style'),
        [Input('ms-scan-slider', 'value'),
         Input('active-tab', 'data'),
         Input('active-file', 'data'),
         Input('ms-active-subplot-idx', 'data')],
        State('main-plot', 'figure'),
        prevent_initial_call=True,
    )

    # ------------------------------------------------------------------
    # 2. EIC extraction → overlay on main plot
    # ------------------------------------------------------------------
    @app.callback(
        [Output('render-trigger', 'data', allow_duplicate=True),
         Output('eic-graph', 'figure', allow_duplicate=True),
         Output('eic-active-list', 'children', allow_duplicate=True),
         Output('ms-spectrum-graph', 'figure', allow_duplicate=True),
         Output('ms-scan-slider', 'value', allow_duplicate=True),
         Output('ms-scan-label', 'children', allow_duplicate=True),
         Output('ms-spectrum-info', 'children', allow_duplicate=True)],
        Input('eic-extract-btn', 'n_clicks'),
        [State('eic-mz-input', 'value'),
         State('eic-tolerance-input', 'value'),
         State('active-file', 'data'),
         State('render-trigger', 'data')],
        prevent_initial_call=True,
    )
    def extract_eic_trigger(n_clicks, mz_value, tolerance, active_file, current_trigger):
        if not n_clicks:
            return dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update
        if mz_value is None:
            return (
                dash.no_update,
                _empty_eic("Enter a target m/z"),
                dash.no_update,
                dash.no_update,
                dash.no_update,
                dash.no_update,
                "Enter a target m/z before extracting an EIC",
            )

        resolved = _resolve_lcms_spectral_entry(data_manager, active_file, lcms_svc)
        file_id, file_data = resolved if resolved else (None, None)
        if not file_data or not lcms_svc.has_spectral_data(file_data):
            return (
                dash.no_update,
                _empty_eic("No LC-MS spectral data for this selection"),
                [],
                _empty_spectrum("No LC-MS spectral data for this selection"),
                dash.no_update,
                dash.no_update,
                "No LC-MS spectral data for this selection",
            )

        tolerance = tolerance or 0.5

        try:
            eic_time, eic_intensity = lcms_svc.extract_eic(
                file_data, float(mz_value), float(tolerance)
            )
        except (ValueError, KeyError) as exc:
            return dash.no_update, _empty_eic(str(exc)), dash.no_update, dash.no_update, dash.no_update, dash.no_update, str(exc)

        overlay = {
            'mz': float(mz_value),
            'tolerance': float(tolerance),
            'time': eic_time,
            'intensity': eic_intensity,
        }
        if hasattr(data_manager, 'add_lcms_eic_overlay'):
            data_manager.add_lcms_eic_overlay(file_id, overlay)
        else:
            file_data.setdefault('eic_overlays', []).append(overlay)

        _extract_eic_other_polarity(data_manager, lcms_svc, active_file, file_id, mz_value, tolerance)

        eic_list = _get_eic_list(data_manager, file_id, file_data)
        apex_idx = int(np.argmax(eic_intensity)) if eic_intensity.size else 0
        apex_rt = float(eic_time[apex_idx]) if eic_time.size else 0.0
        spectrum_fig, spectrum_status, scan_idx = _build_spectrum_at_time(lcms_svc, file_data, apex_rt)
        status = (
            f"Extracted EIC m/z {float(mz_value):.4g} +/- {float(tolerance):.3g} "
            f"| Spectrum source: EIC apex | {spectrum_status}"
        )
        return (
            (current_trigger or 0) + 1,
            _build_eic_figure(eic_list),
            _render_eic_list(eic_list),
            spectrum_fig,
            scan_idx,
            _scan_label(lcms_svc, file_data, scan_idx),
            status,
        )

    @app.callback(
        Output('eic-active-list', 'children'),
        [Input('render-trigger', 'data'),
         Input('active-file', 'data')],
    )
    def update_eic_list(_, active_file):
        if not active_file:
            return []
        resolved = _resolve_lcms_spectral_entry(data_manager, active_file, lcms_svc)
        file_id, file_data = resolved if resolved else (None, None)
        if not file_data:
            return []
        return _render_eic_list(_get_eic_list(data_manager, file_id, file_data))

    @app.callback(
        Output('eic-graph', 'figure'),
        [Input('render-trigger', 'data'),
         Input('active-file', 'data')],
    )
    def update_eic_graph(_, active_file):
        if not active_file:
            return _empty_eic("Select an LC-MS file to extract an EIC")

        resolved = _resolve_lcms_spectral_entry(data_manager, active_file, lcms_svc)
        file_id, file_data = resolved if resolved else (None, None)
        if not file_data:
            return _empty_eic("No LC-MS spectral data for this selection")

        return _build_eic_figure(_get_eic_list(data_manager, file_id, file_data))

    @app.callback(
        [Output('render-trigger', 'data', allow_duplicate=True),
         Output('eic-graph', 'figure', allow_duplicate=True),
         Output('eic-active-list', 'children', allow_duplicate=True),
         Output('ms-spectrum-graph', 'figure', allow_duplicate=True),
         Output('ms-scan-slider', 'value', allow_duplicate=True),
         Output('ms-scan-label', 'children', allow_duplicate=True),
         Output('ms-spectrum-info', 'children', allow_duplicate=True)],
        Input('eic-clear-btn', 'n_clicks'),
        [State('active-file', 'data'),
         State('render-trigger', 'data')],
        prevent_initial_call=True,
    )
    def clear_eic_overlays(n_clicks, active_file, current_trigger):
        if not n_clicks or not active_file:
            return dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update
        resolved = _resolve_lcms_spectral_entry(data_manager, active_file, lcms_svc)
        file_id, file_data = resolved if resolved else (None, None)
        if file_id and hasattr(data_manager, 'clear_lcms_eic_overlays'):
            data_manager.clear_lcms_eic_overlays(file_id)
        elif file_data:
            file_data.pop('eic_overlays', None)
        _clear_eic_other_polarity(data_manager, active_file, file_id)
        return (
            (current_trigger or 0) + 1,
            _empty_eic("Extract an EIC to view it here"),
            _render_eic_list([]),
            dash.no_update,
            dash.no_update,
            dash.no_update,
            "Cleared EICs",
        )

    # ------------------------------------------------------------------
    # 3. Peak Mass - populate selector and show averaged spectrum
    # ------------------------------------------------------------------
    @app.callback(
        Output('peak-mass-selector', 'data'),
        [Input('peak-change-trigger', 'data'),
         Input('active-file', 'data')],
    )
    def update_peak_mass_selector(_, active_file):
        if not active_file:
            return []
        ps = data_manager.peak_service
        peaks = ps.get_peaks(active_file) or []
        if not peaks:
            bundle = data_manager.get_bundle(active_file) if hasattr(data_manager, 'get_bundle') else None
            if not bundle and hasattr(data_manager, 'get_bundle_for_component'):
                bundle = data_manager.get_bundle_for_component(active_file)
            if bundle:
                for comp in bundle.component_list:
                    peaks = ps.get_peaks(comp.component_id) or []
                    if peaks:
                        break
        options = []
        for p in peaks:
            label = p.label or p.name or p.peak_id
            if getattr(p, 'source', None) == 'deconvolved':
                detail = f"{label}  (apex {_component_apex_rt(p):.3f} min)"
            else:
                detail = f"{label}  (RT {p.rt_start:.2f}–{p.rt_end:.2f} min)"
            options.append({'label': detail, 'value': p.peak_id})
        return options

    @app.callback(
        [Output('peak-mass-polarity-toggle', 'value'), Output('peak-mass-polarity-wrapper', 'style'),
         Output('peak-mass-polarity-toggle', 'data'), Output('peak-mass-polarity-wrapper', 'title')],
        [Input('active-file', 'data'), Input('peak-mass-polarity-toggle', 'value')],
        prevent_initial_call=True,
    )
    def peak_mass_polarity_visibility(active_file, value='positive'):
        bundle = _lcms_bundle(data_manager, active_file)
        style = {'display': 'flex' if bundle else 'none', 'alignItems': 'center', 'gap': '2px'}
        positive = _polarity_spectral_entry(data_manager, active_file, False, lcms_svc) is not None if bundle else False
        negative = _polarity_spectral_entry(data_manager, active_file, True, lcms_svc) is not None if bundle else False
        selected = value if positive and negative and value in ('positive', 'negative') else ('negative' if negative else 'positive')
        return selected, style, _spectrum_polarity_options(positive, negative), _polarity_availability(positive, negative)

    @app.callback(
        [Output('peak-mass-graph', 'figure'),
         Output('peak-mass-info', 'children')],
        [Input('peak-mass-selector', 'value'),
         Input('peak-mass-polarity-toggle', 'value')],
        State('active-file', 'data'),
        prevent_initial_call=True,
    )
    def show_peak_mass(peak_id, polarity, active_file):
        use_negative = polarity == 'negative'
        if not peak_id or not active_file:
            return _empty_peak_mass("Select a peak to view its mass spectrum"), ""

        ps = data_manager.peak_service

        def _find(fid):
            for p in (ps.get_peaks(fid) or []):
                if p.peak_id == peak_id:
                    return fid, p
            return None, None

        file_id, peak = _find(active_file)
        if not peak:
            bundle = data_manager.get_bundle(active_file) if hasattr(data_manager, 'get_bundle') else None
            if not bundle and hasattr(data_manager, 'get_bundle_for_component'):
                bundle = data_manager.get_bundle_for_component(active_file)
            if bundle:
                for comp in bundle.component_list:
                    file_id, peak = _find(comp.component_id)
                    if peak:
                        break

        if not peak:
            return _empty_peak_mass("Peak not found"), ""

        resolved = _polarity_spectral_entry(data_manager, active_file, bool(use_negative), lcms_svc)
        if not resolved:
            mode = 'negative' if use_negative else 'positive'
            return _empty_peak_mass(f"No {mode}-mode mass spectral data available"), ""
        _, file_data = resolved
        polarity_label = "−" if use_negative else "+"
        # Compare exactly the selected retention-time window in either mode.
        # A second integration is not needed to inspect its mass spectrum.

        if getattr(peak, 'source', None) == 'deconvolved':
            # Components share integration bounds, but not their apex. Averaging
            # those bounds would return precisely the same spectrum for all of them.
            apex = _component_apex_rt(peak)
            times, _ = lcms_svc.extract_tic(file_data)
            times = np.asarray(times, dtype=float)[:lcms_svc.get_scan_count(file_data)]
            valid = np.flatnonzero(np.isfinite(times))
            if not valid.size or not times[valid].min() <= apex <= times[valid].max():
                return _empty_peak_mass("No MS scans at component apex"), f"Component apex {apex:.3f} min"
            candidates = valid[(times[valid] >= peak.rt_start) & (times[valid] <= peak.rt_end)]
            if not candidates.size:
                return _empty_peak_mass("No MS scans at component apex"), f"Component apex {apex:.3f} min"
            scan = int(candidates[np.argmin(np.abs(times[candidates] - apex))])
            mz, intensity = lcms_svc.get_mass_spectrum(file_data, scan)
            if not mz.size:
                return _empty_peak_mass("No spectrum in component apex scan"), ""
            description = f"Apex scan {times[scan]:.3f} min · may contain mixed ions"
            return _build_peak_mass_figure(mz, intensity, peak, polarity_label, description)

        mz, intensity = lcms_svc.get_averaged_spectrum(file_data, peak.rt_start, peak.rt_end)
        if mz.size == 0:
            return _empty_peak_mass("No scans in peak RT window"), ""

        return _build_peak_mass_figure(mz, intensity, peak, polarity_label)

    @app.callback(
        [Output('peak-mass-selector', 'value', allow_duplicate=True),
         Output('selected-peak-idx', 'data', allow_duplicate=True),
         Output('active-file', 'data', allow_duplicate=True),
         Output('render-trigger', 'data', allow_duplicate=True)],
        [Input('selected-peak-idx', 'data'), Input('peak-mass-selector', 'value')],
        [State('active-file', 'data'), State('render-trigger', 'data'), State('view-mode', 'data')],
        prevent_initial_call=True,
    )
    def sync_peak_mass_to_click(selected_peak_id, dropdown_peak_id, active_file, render_counter, view_mode):
        """Sync explicit peak choices, keeping the spectrum when handles dismiss."""
        unchanged = (dash.no_update,) * 4
        if not active_file or (view_mode or 'raw') != 'raw' or not _lcms_bundle(data_manager, active_file):
            return unchanged
        trigger = callback_context.triggered[0]['prop_id'].split('.')[0] if callback_context.triggered else ''
        from_dropdown = trigger == 'peak-mass-selector'
        peak_id = dropdown_peak_id if from_dropdown else selected_peak_id
        if selected_peak_id == dropdown_peak_id:
            return unchanged
        if not peak_id:
            # Plot deselection only dismisses editing handles. The analysis
            # panel keeps its last peak until another is chosen or cleared.
            return ((dash.no_update, None, dash.no_update, (render_counter or 0) + 1)
                    if from_dropdown else unchanged)

        sources = [active_file]
        bundle = data_manager.get_bundle(active_file) or data_manager.get_bundle_for_component(active_file)
        if bundle:
            sources.extend([bundle.bundle_id, *(component.component_id for component in bundle.component_list)])
        peak = next((peak for file_id in dict.fromkeys(sources)
                     for peak in data_manager.peak_service.get_peaks(file_id)
                     if peak.peak_id == peak_id), None)
        if peak is None:
            return unchanged
        owner = peak.file_id if peak.file_id != active_file else dash.no_update
        if from_dropdown:
            # selected-peak-idx is a render State, so explicitly refresh the
            # figure to move the selected fill and editable baseline handles.
            return dash.no_update, peak_id, owner, (render_counter or 0) + 1
        return peak_id, dash.no_update, owner, ((render_counter or 0) + 1 if owner is not dash.no_update else dash.no_update)


def _empty_peak_mass(message: str) -> go.Figure:
    fig = go.Figure()
    fig.update_layout(
        template='plotly_white',
        margin=dict(l=50, r=20, t=10, b=38),
        xaxis=dict(visible=False),
        yaxis=dict(visible=False),
        annotations=[dict(
            text=message, xref='paper', yref='paper',
            x=0.5, y=0.5, showarrow=False,
            font=dict(size=13, color='#999'),
        )],
    )
    return fig


def _mass_peak_annotations(mz, relative_intensity, limit=6):
    """Label distinct dominant ion apices, with room between their m/z labels."""
    from scipy.signal import find_peaks

    x = np.asarray(mz, dtype=float)
    y = np.asarray(relative_intensity, dtype=float)
    valid = np.isfinite(x) & np.isfinite(y)
    x, y = x[valid], y[valid]
    if not x.size or np.max(y) <= 0:
        return []
    order = np.argsort(x, kind='stable')
    x, y = x[order], y[order]
    span = float(np.ptp(x))
    spacing = max(span * .055, .01)
    # Distant centroid ions are independent peaks even when consecutive in
    # the array. Within a contiguous profile, collapse shoulders/plateaus.
    boundaries = np.r_[0, np.flatnonzero(np.diff(x) >= spacing) + 1, x.size]
    candidates = []
    for start, end in zip(boundaries[:-1], boundaries[1:]):
        peaks, _ = find_peaks(np.r_[-np.inf, y[start:end], -np.inf],
                              height=np.max(y) * .10)
        candidates.extend(peaks + start - 1)
    ranked = sorted(candidates, key=lambda i: (-y[i], x[i]))
    chosen = []
    for index in ranked:
        if all(abs(x[index] - x[other]) >= spacing for other in chosen):
            chosen.append(index)
            if len(chosen) >= limit:
                break
    return [dict(name='gecko-ms-peak', x=float(x[i]), y=float(y[i]), xref='x', yref='y',
                 text=f'{x[i]:.2f}', showarrow=False, yanchor='bottom', yshift=4,
                 xanchor=('left' if x[i] < x[0] + spacing else
                          'right' if x[i] > x[-1] - spacing else 'center'),
                 font=dict(size=10, color='#333333')) for i in chosen]


def _component_apex_rt(peak):
    """The fitted EMG maximum, which is later than its center parameter."""
    from lmfit.models import ExponentialGaussianModel

    params = getattr(peak, 'fit_params', None) or {}
    if all(key in params for key in ('sigma', 'gamma', 'amplitude')):
        x = np.linspace(peak.rt_start, peak.rt_end, 800)
        curve = ExponentialGaussianModel().eval(
            x=x, center=params.get('center', peak.rt), sigma=params['sigma'],
            gamma=params['gamma'], amplitude=params['amplitude'])
        if np.all(np.isfinite(curve)) and np.max(curve) > 0:
            return float(x[np.argmax(curve)])
    return float(peak.rt)


def _build_peak_mass_figure(mz, intensity, peak, polarity_label="+", spectrum_description=None):
    display = np.asarray(intensity, dtype=float)
    max_int = np.nanmax(display) if display.size else 1.0
    rel = display / max_int * 100 if max_int > 0 else display

    fig = go.Figure()
    TraceType = go.Scattergl if mz.size > 1200 else go.Scatter

    xs, ys, cd = [], [], []
    for x_val, y_val, i_val in zip(mz, rel, intensity):
        xs.extend([x_val, x_val, None])
        ys.extend([0, y_val, None])
        cd.extend([i_val, i_val, None])

    fig.add_trace(TraceType(
        x=xs, y=ys, mode='lines',
        line=dict(color='#6B46C1', width=1),
        customdata=cd,
        meta={'gecko_mass_spectrum':True},
        hovertemplate=(
            'm/z: %{x:.4g}<br>'
            'Intensity: %{customdata:.4g}<br>'
            'Relative: %{y:.1f}%<extra></extra>'
        ),
        showlegend=False,
    ))
    fig.update_layout(
        template='plotly_white',
        margin=dict(l=48, r=16, t=20, b=38),
        xaxis_title='m/z',
        yaxis_title='Relative Intensity (%)',
        hovermode='closest',
        yaxis=dict(range=[0, 116], showgrid=False, showline=True,
                   mirror=True, linecolor='#ccc', linewidth=1),
        xaxis=dict(showgrid=False, showline=True, mirror=True,
                   linecolor='#ccc', linewidth=1),
        uirevision='peak-mass',
        annotations=_mass_peak_annotations(mz, rel),
    )

    label = peak.label or peak.name or peak.peak_id
    top_peaks = ", ".join(a.text for a in fig.layout.annotations) or "none"
    description = spectrum_description or f"RT {peak.rt_start:.2f}–{peak.rt_end:.2f} min"
    info = f"{label} | {description} | Mode: {polarity_label} | Top m/z: {top_peaks}"

    return fig, info


def _empty_spectrum(message: str) -> go.Figure:
    fig = go.Figure()
    fig.update_layout(
        template='plotly_white',
        margin=dict(l=50, r=20, t=30, b=40),
        xaxis=dict(visible=False),
        yaxis=dict(visible=False),
        annotations=[dict(
            text=message, xref='paper', yref='paper',
            x=0.5, y=0.5, showarrow=False,
            font=dict(size=13, color='#999'),
        )],
    )
    return fig


def _empty_eic(message: str) -> go.Figure:
    fig = go.Figure()
    fig.update_layout(
        template='plotly_white',
        margin=dict(l=50, r=20, t=28, b=36),
        xaxis=dict(visible=False),
        yaxis=dict(visible=False),
        annotations=[dict(
            text=message, xref='paper', yref='paper',
            x=0.5, y=0.5, showarrow=False,
            font=dict(size=13, color='#999'),
        )],
    )
    return fig


def _source_status(source, status):
    labels = {
        'main-plot': 'Spectrum source: TIC click',
        'eic-graph': 'Spectrum source: EIC click',
        'slider': 'Spectrum source: scan scrubber',
    }
    prefix = labels.get(source)
    return f"{prefix} | {status}" if prefix else status


def _scan_label(lcms_svc, file_data, scan_idx):
    try:
        time_arr, _ = lcms_svc.extract_tic(file_data)
        rt = float(time_arr[int(scan_idx)]) if len(time_arr) > int(scan_idx) else 0.0
        total = max(lcms_svc.get_scan_count(file_data), 1)
        return f"Scan {int(scan_idx)} / {total - 1} | RT {rt:.3f} min"
    except (ValueError, IndexError, TypeError):
        return f"Scan {int(scan_idx)}"


def _main_figure_without_scan_line(current_figure):
    if not current_figure:
        return dash.no_update

    figure = {
        'data': list(current_figure.get('data', [])),
        'layout': dict(current_figure.get('layout', {})),
    }
    shapes = [
        shape for shape in figure['layout'].get('shapes', [])
        if shape.get('name') != 'lcms-scan-line'
    ]
    if shapes:
        figure['layout']['shapes'] = shapes
    else:
        figure['layout'].pop('shapes', None)
    return figure


def _main_figure_with_scan_line(current_figure, rt):
    figure = _main_figure_without_scan_line(current_figure)
    if figure is dash.no_update:
        return dash.no_update

    layout = figure.setdefault('layout', {})
    shapes = list(layout.get('shapes', []))
    shapes.append({
        'type': 'line',
        'name': 'lcms-scan-line',
        'xref': 'x',
        'yref': 'paper',
        'x0': rt,
        'x1': rt,
        'y0': 0,
        'y1': 1,
        'layer': 'above',
        'editable': False,
        'line': {
            'color': '#111111',
            'width': 1.5,
            'dash': 'dot',
        },
    })
    layout['shapes'] = shapes
    layout['uirevision'] = layout.get('uirevision', 'main-plot')
    return figure


def _build_spectrum_at_time(lcms_svc, file_data, rt):
    try:
        scan_idx = lcms_svc.get_scan_index_at_time(file_data, rt)
    except (ValueError, IndexError) as exc:
        return _empty_spectrum(str(exc)), str(exc), 0
    return _build_spectrum_at_scan(lcms_svc, file_data, scan_idx)


def _build_spectrum_at_scan(lcms_svc, file_data, scan_idx):
    try:
        n_scans = max(lcms_svc.get_scan_count(file_data), 1)
        scan_idx = min(max(int(scan_idx), 0), n_scans - 1)
        mz, intensity = lcms_svc.get_mass_spectrum(file_data, scan_idx)
        time_arr, _ = lcms_svc.extract_tic(file_data)
        rt = float(time_arr[scan_idx]) if time_arr.size > scan_idx else 0.0
    except (ValueError, IndexError) as exc:
        return _empty_spectrum(str(exc)), str(exc), 0

    display_intensity = np.asarray(intensity, dtype=float)
    max_int = np.nanmax(display_intensity) if display_intensity.size else 1.0
    rel_intensity = display_intensity / max_int * 100 if max_int > 0 else display_intensity

    fig = go.Figure()
    TraceType = go.Scattergl if mz.size > 1200 else go.Scatter

    xs = []
    ys = []
    cd = []
    for x_val, y_val, i_val in zip(mz, rel_intensity, intensity):
        xs.extend([x_val, x_val, None])
        ys.extend([0, y_val, None])
        cd.extend([i_val, i_val, None])

    fig.add_trace(TraceType(
        x=xs, y=ys, mode='lines',
        line=dict(color='#2B6CB0', width=1),
        customdata=cd,
        meta={'gecko_mass_spectrum':True},
        hovertemplate=(
            'm/z: %{x:.4g}<br>'
            'Intensity: %{customdata:.4g}<br>'
            'Relative: %{y:.1f}%<extra></extra>'
        ),
        showlegend=False,
    ))
    fig.update_layout(
        template='plotly_white',
        margin=dict(l=48, r=16, t=20, b=38),
        xaxis_title='m/z',
        yaxis_title='Relative Intensity (%)',
        hovermode='closest',
        yaxis=dict(range=[0, 116], showgrid=False, showline=True, mirror=True, linecolor='#ccc', linewidth=1),
        xaxis=dict(showgrid=False, showline=True, mirror=True, linecolor='#ccc', linewidth=1),
        uirevision='ms-spectrum',
        annotations=_mass_peak_annotations(mz, rel_intensity),
    )

    if mz.size > 0:
        top_peaks = ", ".join(a.text for a in fig.layout.annotations) or "none"
        return fig, f"Scan {scan_idx} at {rt:.3f} min | Top m/z: {top_peaks}", scan_idx

    return fig, f"Scan {scan_idx} at {rt:.3f} min | no peaks", scan_idx


def _get_eic_list(data_manager, file_id, file_data):
    if not file_id or not file_data:
        return []
    if hasattr(data_manager, 'get_lcms_eic_overlays'):
        return data_manager.get_lcms_eic_overlays(file_id)
    return file_data.get('eic_overlays', [])


def _lcms_bundle(data_manager, active_file):
    from services.data_store import BundleType
    bundle = data_manager.get_bundle(active_file) if active_file else None
    if not bundle and active_file:
        bundle = data_manager.get_bundle_for_component(active_file)
    return bundle if bundle and bundle.bundle_type == BundleType.LCMS else None


def _polarity_spectral_entry(data_manager, active_file, negative, lcms_svc):
    from services.data_store import ComponentRole
    bundle = _lcms_bundle(data_manager, active_file)
    if not bundle:
        return None
    role = ComponentRole.MS_NEGATIVE if negative else ComponentRole.MS_POSITIVE
    for component in bundle.component_list:
        if component.role == role:
            entry = data_manager.get_data_by_id(component.component_id)
            if entry and lcms_svc.has_spectral_data(entry):
                return component.component_id, entry
    return None


def _spectrum_polarity_options(positive, negative):
    return [{'label': '+', 'value': 'positive', 'disabled': not positive},
            {'label': '−', 'value': 'negative', 'disabled': not negative}]


def _polarity_availability(positive, negative):
    if positive and negative:
        return 'Switch between positive and negative mass spectra'
    if positive or negative:
        return 'Only ' + ('positive' if positive else 'negative') + '-mode mass spectral data available'
    return 'No mass spectral data available'


def _opposite_polarity_component(data_manager, active_file, current_file_id):
    """Return (component_id, file_data) for the opposite polarity, or (None, None)."""
    from services.data_store import BundleType, ComponentRole
    bundle = None
    if hasattr(data_manager, 'get_bundle'):
        bundle = data_manager.get_bundle(active_file)
    if not bundle and hasattr(data_manager, 'get_bundle_for_component'):
        bundle = data_manager.get_bundle_for_component(active_file)
    if not bundle or bundle.bundle_type != BundleType.LCMS:
        return None, None

    lookup_id = current_file_id or active_file
    current = next((c for c in bundle.component_list if c.component_id == lookup_id), None)
    if not current:
        return None, None

    if current.role == ComponentRole.MS_POSITIVE:
        other = bundle.get_component(ComponentRole.MS_NEGATIVE)
    elif current.role == ComponentRole.MS_NEGATIVE:
        other = bundle.get_component(ComponentRole.MS_POSITIVE)
    else:
        return None, None

    if not other:
        return None, None
    other_data = data_manager.get_data_by_id(other.component_id)
    return other.component_id, other_data


def _extract_eic_other_polarity(data_manager, lcms_svc, active_file, current_file_id, mz_value, tolerance):
    """Silently extract the same EIC from the opposite polarity component."""
    other_id, other_data = _opposite_polarity_component(data_manager, active_file, current_file_id)
    if not other_data or not lcms_svc.has_spectral_data(other_data):
        return
    try:
        eic_time, eic_intensity = lcms_svc.extract_eic(other_data, float(mz_value), float(tolerance))
    except (ValueError, KeyError):
        return
    overlay = {'mz': float(mz_value), 'tolerance': float(tolerance), 'time': eic_time, 'intensity': eic_intensity}
    if hasattr(data_manager, 'add_lcms_eic_overlay'):
        data_manager.add_lcms_eic_overlay(other_id, overlay)
    else:
        other_data.setdefault('eic_overlays', []).append(overlay)


def _clear_eic_other_polarity(data_manager, active_file, current_file_id):
    """Clear EIC overlays from the opposite polarity component."""
    other_id, other_data = _opposite_polarity_component(data_manager, active_file, current_file_id)
    if not other_id:
        return
    if hasattr(data_manager, 'clear_lcms_eic_overlays'):
        data_manager.clear_lcms_eic_overlays(other_id)
    elif other_data:
        other_data.pop('eic_overlays', None)


def _render_eic_list(eic_list):
    if not eic_list:
        return [html.Span("No EICs extracted", style={'color': '#999', 'fontSize': '12px'})]
    return [
        html.Span(
            f"m/z {e['mz']:.1f} ±{e['tolerance']}",
            style={
                'display': 'inline-block', 'padding': '2px 8px',
                'backgroundColor': '#f0f0f0', 'borderRadius': '12px',
                'fontSize': '11px', 'marginRight': '4px', 'marginBottom': '4px',
            },
        )
        for e in eic_list
    ]


def _build_eic_figure(eic_list):
    if not eic_list:
        return _empty_eic("Extract an EIC to view it here")

    fig = go.Figure()
    colors = ['#0072B2', '#D55E00', '#009E73', '#CC79A7', '#E69F00', '#56B4E9']
    for idx, eic in enumerate(eic_list[-6:]):
        time = np.asarray(eic.get('time', []), dtype=float)
        intensity = np.asarray(eic.get('intensity', []), dtype=float)
        if time.size == 0 or intensity.size == 0:
            continue

        mz = float(eic.get('mz', 0.0))
        tolerance = float(eic.get('tolerance', 0.0))
        label = f"m/z {mz:.4g} +/- {tolerance:.3g}"
        color = colors[idx % len(colors)]
        fig.add_trace(go.Scatter(
            x=time,
            y=intensity,
            mode='lines',
            name=label,
            line=dict(color=color, width=1.6),
            hovertemplate=(
                f"{label}<br>Time: %{{x:.3f}} min"
                "<br>Intensity: %{y:.4g}<extra></extra>"
            ),
        ))

        apex_idx = int(np.argmax(intensity)) if intensity.size else 0
        if intensity.size and intensity[apex_idx] > 0:
            fig.add_trace(go.Scatter(
                x=[time[apex_idx]],
                y=[intensity[apex_idx]],
                mode='markers',
                name=f"{label} apex",
                marker=dict(color=color, size=7, symbol='x'),
                showlegend=False,
                hovertemplate=(
                    f"{label} apex<br>Time: %{{x:.3f}} min"
                    "<br>Intensity: %{y:.4g}<extra></extra>"
                ),
            ))

    if not fig.data:
        return _empty_eic("No EIC signal in the selected m/z window")

    fig.update_layout(
        template='plotly_white',
        margin=dict(l=50, r=20, t=28, b=36),
        xaxis_title='Retention Time (min)',
        yaxis_title='EIC Intensity',
        hovermode='closest',
        xaxis=dict(showgrid=False, showline=True, mirror=True, linecolor='#ccc', linewidth=1),
        yaxis=dict(showgrid=False, showline=True, mirror=True, linecolor='#ccc', linewidth=1),
        legend=dict(
            orientation='h',
            yanchor='bottom',
            y=1.02,
            xanchor='left',
            x=0,
            font=dict(size=10),
        ),
        uirevision='lcms-eic',
    )
    return fig


def _resolve_lcms_spectral_entry(data_manager, active_file, lcms_svc):
    """Resolve a signal while retaining the bundle's chosen MS analysis mode."""
    bundle = None
    if active_file:
        bundle = data_manager.get_bundle(active_file) if hasattr(data_manager, 'get_bundle') else None
        if not bundle and hasattr(data_manager, 'get_bundle_for_component'):
            bundle = data_manager.get_bundle_for_component(active_file)
        state = None
        if bundle and hasattr(data_manager, 'file_ui_state'):
            state = data_manager.file_ui_state.setdefault(bundle.bundle_id, {})
        entry = data_manager.get_data_by_id(active_file)
        role = (entry or {}).get('metadata', {}).get('component_role') or (entry or {}).get('record', {}).get('type')
        if state is not None and role in ('ms_positive', 'ms_negative'):
            state['ms_analysis_polarity'] = role
        if entry and lcms_svc.has_spectral_data(entry):
            record = entry.get('record') or {}
            return record.get('id', active_file), entry
        if bundle:
            preferred = (state or {}).get('ms_analysis_polarity')
            if preferred:
                selected = _polarity_spectral_entry(data_manager, active_file, preferred == 'ms_negative', lcms_svc)
                if selected:
                    return selected
            for component in bundle.component_list:
                entry = data_manager.get_data_by_id(component.component_id)
                if entry and lcms_svc.has_spectral_data(entry):
                    return component.component_id, entry

    for candidate_id, candidate in data_manager.loaded_data.items():
        if candidate and lcms_svc.has_spectral_data(candidate):
            record = candidate.get('record') or {}
            return record.get('id', candidate_id), candidate
    return None
