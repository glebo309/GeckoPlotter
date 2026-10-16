"""Peak-first calibration editor and portable model workflow."""
import base64
import copy
import json
import math
import uuid

import dash
from dash import Input, Output, State, dcc
from services.calibration_service import empty_calibration_figure


def _number(value, label):
    try:
        number = float(value)
    except (ValueError, TypeError):
        raise ValueError(f'{label} must be a number.') from None
    if not math.isfinite(number):
        raise ValueError(f'{label} must be finite.')
    return number


from services.calibration_workflow import add_peak_rows, fit_calibration_form  # noqa: E402,F401  (shared with the agent)


def _form_signature(form):
    rows, included, values = form
    # Labels are saved independently; browser echoes may still contain untrimmed text.
    fit_values = {k:v for k,v in values.items() if k not in ('name','units')}
    return ([{k:r.get(k) for k in ('id','sample_name','position','concentration','area','signal_key','x_units','response_units')} for r in rows], included, fit_values)


def register_calibration_callbacks(app: dash.Dash, data_manager) -> None:
    from services.calibration_workflow import peak_candidates, apply_calibrations
    from services.workspaces import scoped, service_of
    service = service_of(data_manager, 'calibration_service')
    drafts = scoped(data_manager, 'calibration_drafts', dict)       # unsaved calibration edits, per workspace
    field_ids = [('cal-analyte-name','value'), ('cal-units','value'), ('cal-fit-type','value'),
                 ('cal-force-zero','checked'), ('cal-response-type','value'),
                 ('cal-match-position','value'), ('cal-match-tolerance','value'), ('cal-auto-apply','checked')]
    field_names = ['name','units','fit_type','force_zero','response_type','position','tolerance','auto_apply']

    @app.callback(Output('cal-peak-picker','data'),
        Input('peak-change-trigger','data'), Input('loaded-files','data'), Input('active-tab','data'),
        Input('cal-response-type','value'))
    def available_peaks(_peaks, _files, _tab, response_type):
        options = []
        for peak in peak_candidates(data_manager):
            position = (f"{peak['position']:.4g} {peak['x_units']}" if peak['position'] is not None
                        else 'Position unavailable')
            options.append({'value': peak['id'], 'label': f"{peak['sample']} / {peak['peak_name']} / {position}"})
        return options

    @app.callback(Output('cal-standards-table','columns'),Input('cal-response-type','value'),Input('cal-units','value'))
    def standard_columns(response_type,units):
        return [dict(name='Sample / peak',id='sample_name',type='text'),
                dict(name='Peak position',id='position',type='numeric',editable=False,format=dict(specifier='.5~g')),
                dict(name='Concentration'+(f' ({units})' if units else ''),id='concentration',type='numeric',format=dict(specifier='.5~g')),
                dict(name='Peak height' if response_type == 'height' else 'Peak area',id='area',type='numeric',format=dict(specifier='.5~g'))]

    outputs = [Output('cal-active-model','data'),Output('cal-active-model','value'),
        Output('cal-standards-table','data'),Output('cal-standards-table','selected_rows')]
    outputs += [Output(cid, prop) for cid, prop in field_ids]
    outputs += [Output('cal-curve-graph','figure'),Output('cal-feedback','children'),
        Output('cal-match-label','children'),Output('cal-revision','data'),Output('cal-save-btn','disabled')]
    inputs = [Input('cal-new-btn','n_clicks'),Input('cal-add-peaks-btn','n_clicks'),
        Input('cal-add-manual-btn','n_clicks'),Input('cal-fit-btn','n_clicks'),
        Input('cal-load-upload','contents'),Input('cal-active-model','value'),
        Input('cal-standards-table','data_timestamp'),Input('cal-standards-table','selected_rows'),
        Input('cal-link-peak-btn','n_clicks')]
    inputs += [Input(cid,prop) for cid,prop in field_ids]
    inputs += [Input('cal-import-peaks','data')]
    states = [State('cal-standards-table','data'),State('cal-peak-picker','value'),State('cal-revision','data')]

    @app.callback(
        [Output('cal-active-model', 'data', allow_duplicate=True),
         Output('cal-active-model', 'value', allow_duplicate=True)],
        Input('loaded-files', 'data'), State('cal-active-model', 'value'), prevent_initial_call=True)
    def list_calibrations(_files, current):
        """The calibrations of the workspace in the editor's list: after opening a project, after the agent made one, after
        removing data. The first is shown when none was chosen."""
        options = [{'value': m.model_id, 'label': m.analyte_name} for m in service.get_all_models().values()]
        ids = [o['value'] for o in options]
        value = current if current in ids else (ids[0] if ids else None)
        return options, (value if value != current else dash.no_update)

    @app.callback(outputs, inputs, states, prevent_initial_call=True)
    def edit_calibration(_new, _add, _manual, _fit, upload, model_id, _timestamp, included, _link, *args):
        values = dict(zip(field_names, args[:len(field_names)]))
        imported_peaks, rows, picked, revision = args[len(field_names):]
        rows = copy.deepcopy(rows or [])
        included = list(included or [])
        trigger = dash.ctx.triggered_id
        result = [dash.no_update] * len(outputs)
        model = service.get_model(model_id)
        feedback = ''
        hydrate = False
        changed = False
        labels_only = False
        try:
            if trigger == 'cal-new-btn':
                model = service.create_model('New calibration', '')
                hydrate = True
            elif trigger == 'cal-load-upload':
                if not upload:
                    return result
                encoded = upload.split(',',1)[1]
                if len(encoded) > 14_000_000:
                    raise ValueError('Calibration file is too large (maximum 10 MB).')
                payload = json.loads(base64.b64decode(encoded, validate=True).decode('utf-8-sig'))
                imported = service.import_calibrations(payload)
                model = imported[0]
                hydrate = changed = True
                feedback = f'Loaded {len(imported)} calibration(s).'
                if not model.signal_key:
                    feedback += ' Select a matching measured peak to link this older model to a signal.'
            elif trigger == 'cal-active-model':
                if not model:
                    return result
                hydrate = True
            elif trigger in ('cal-analyte-name', 'cal-units') and model:
                # Labels do not change the regression. In particular, replace_model
                # imports/refits standards, which could resurrect a pending fit.
                field, attribute = ('name', 'analyte_name') if trigger == 'cal-analyte-name' else ('units', 'units')
                label = str(values[field] or '').strip()
                if field == 'name' and not label:
                    raise ValueError('Give the calibration an analyte name.')
                if label == getattr(model, attribute):
                    return result
                setattr(model, attribute, label)
                if model_id in drafts:
                    drafts[model_id][2][field] = label
                labels_only = changed = True
                feedback = 'Calibration label updated.'
            elif trigger in ('cal-match-position', 'cal-match-tolerance', 'cal-auto-apply') and model and model.coefficients is not None:
                # Matching does not alter the fitted response curve.
                proposed_position = None if values['position'] in (None,'') else _number(values['position'],'Peak position')
                proposed_tolerance = _number(values['tolerance'],'Matching tolerance')
                if proposed_tolerance <= 0:
                    raise ValueError('Matching tolerance must be greater than zero.')
                if (proposed_position,proposed_tolerance,bool(values['auto_apply'])) == (model.match_position,model.match_tolerance,model.auto_apply):
                    return result
                updated = copy.deepcopy(model)
                updated.match_position, updated.match_tolerance = proposed_position, proposed_tolerance
                updated.auto_apply = bool(values['auto_apply'] and updated.signal_key and proposed_position is not None)
                model = service.replace_model(updated)
                hydrate = changed = True
                feedback = 'Peak matching updated.'
            elif trigger == 'cal-link-peak-btn':
                if not model or model.coefficients is None:
                    raise ValueError('Load or fit a calibration first, then select one reference peak.')
                if len(picked or []) != 1:
                    raise ValueError('Select exactly one peak to identify the matching signal.')
                reference = next((p for p in peak_candidates(data_manager) if p['id'] == picked[0]), None)
                if reference is None:
                    raise ValueError('The selected peak is no longer available.')
                model = copy.deepcopy(model)
                model.signal_key = reference['signal_key']
                model.x_units = reference['x_units']
                model.response_units = reference['height_units'] if model.response_type == 'height' else reference['response_units']
                model.match_position = reference['position']
                model.match_tolerance = _number(values['tolerance'], 'Matching tolerance')
                if model.match_tolerance <= 0:
                    raise ValueError('Matching tolerance must be greater than zero.')
                model.auto_apply = True
                model = service.replace_model(model)
                drafts.pop(model.model_id, None)
                hydrate = changed = True
                feedback = 'Saved calibration linked to this signal and peak position. Matching peaks are now quantified.'
            elif trigger == 'cal-import-peaks':
                selected = (imported_peaks or {}).get('ids', [])
                if not selected:
                    return result
                rows = add_peak_rows([],selected,peak_candidates(data_manager),'area')
                positions = [r['position'] for r in rows if r.get('position') is not None]
                included = list(range(len(rows)))
                first = next((p for p in peak_candidates(data_manager) if p['id'] == selected[0]),None)
                values = dict(name=first['peak_name'] if first else 'Calibration',units='',fit_type='linear',
                    force_zero=False,response_type='area',position=sum(positions)/len(positions) if positions else None,
                    tolerance=.2,auto_apply=True)
                model = service.create_model(values['name'],'')
                model_id = model.model_id
                feedback = 'Selected peaks added. Enter their known concentrations, then fit calibration.'
            elif trigger == 'cal-add-peaks-btn':
                if not picked:
                    raise ValueError('Select the measured peaks to add first.')
                previous_count = len(rows)
                rows = add_peak_rows(rows, picked, peak_candidates(data_manager), values['response_type'])
                included += list(range(previous_count,len(rows)))
                if values['position'] in (None,''):
                    positions = [r['position'] for r in rows if r.get('position') is not None]
                    if positions:
                        values['position'] = sum(positions)/len(positions)
                if not values['name'] or values['name'] == 'New calibration':
                    first = next((p for p in peak_candidates(data_manager) if p['id'] == picked[0]), None)
                    values['name'] = first['peak_name'] if first else 'Calibration'
                feedback = 'Enter known concentrations, then fit. Uncheck rows you do not want to use as standards.'
            elif trigger == 'cal-add-manual-btn':
                rows.append(dict(id='manual:'+str(uuid.uuid4()), sample_name=f'Standard {len(rows)+1}',
                                 concentration=None, area=None, position=None))
                included.append(len(rows)-1)
                feedback = 'Enter concentration and response for the new standard.'
            elif trigger == 'cal-fit-btn':
                model = fit_calibration_form(service, model_id, rows, included, **values)
                drafts.pop(model.model_id, None)
                hydrate = changed = True
                predictions = apply_calibrations(data_manager)
                count = sum(r.get('concentration') is not None for r in predictions.values())
                feedback = f'Calibration fitted. {count} matching peak(s) quantified in Peaks.'
                if not model.auto_apply:
                    feedback += ' Automatic matching is off; add a reference peak to identify the signal.'
            elif trigger == 'cal-response-type':
                for row in rows:
                    field = 'measured_height' if values['response_type']=='height' else 'measured_area'
                    if field in row:
                        row['area'] = row[field]
                        row['response_units'] = row.get('height_units' if values['response_type']=='height' else 'area_units','')
                    elif model and values['response_type'] != model.response_type:
                        row['area'] = None
                feedback = 'Response changed. Check the standards and fit again.'

            if hydrate:
                model_id = model.model_id
                if model_id in drafts and trigger == 'cal-active-model':
                    rows, included, values = copy.deepcopy(drafts[model_id])
                else:
                    rows = [dict(id=s.source_id or 'saved:'+str(i), sample_name=s.sample_name,
                        position=s.position, concentration=s.concentration, area=s.area,
                        signal_key=model.signal_key,x_units=model.x_units,response_units=model.response_units)
                        for i,s in enumerate(model.standards)]
                    known = {p['id']: p for p in peak_candidates(data_manager)}
                    for row in rows:
                        peak = known.get(row['id'])
                        if peak:
                            row.update(measured_area=peak['response'],measured_height=peak['height'],
                                       area_units=peak['response_units'],height_units=peak['height_units'])
                    included = [i for i,s in enumerate(model.standards) if s.included]
                    values = dict(name=model.analyte_name, units=model.units, fit_type=model.fit_type,
                        force_zero=model.force_zero,response_type=model.response_type,
                        position=model.match_position,tolerance=model.match_tolerance,auto_apply=model.auto_apply)
                    if not model.standards and not model.signal_key:
                        values['auto_apply'] = True
            elif not labels_only:
                new_model = model is None
                if model is None:
                    model = service.create_model(values['name'] or 'New calibration','')
                    model_id = model.model_id
                # A draft disables stale predictions immediately. Fitting is explicit.
                signature = (rows,included,values)
                previous = drafts.get(model_id)
                baseline_rows = [dict(id=s.source_id or 'saved:'+str(i),sample_name=s.sample_name,
                    position=s.position,concentration=s.concentration,area=s.area,
                    signal_key=model.signal_key,x_units=model.x_units,response_units=model.response_units)
                    for i,s in enumerate(model.standards)]
                baseline_values = dict(name=model.analyte_name,units=model.units,fit_type=model.fit_type,
                    force_zero=model.force_zero,response_type=model.response_type,position=model.match_position,
                    tolerance=model.match_tolerance,auto_apply=model.auto_apply)
                baseline = (baseline_rows,[i for i,s in enumerate(model.standards) if s.included],baseline_values)
                if not new_model and _form_signature(signature) == _form_signature(previous if previous is not None else baseline):
                    return result
                drafts[model_id] = copy.deepcopy(signature)
                service._invalidate_fit(model)
                changed = True
                feedback = feedback or 'Changes pending. Fit calibration to update the curve and calculated concentrations.'

            if changed:
                apply_calibrations(data_manager)
            options = [{'value':m.model_id,'label':m.analyte_name} for m in service.get_all_models().values()]
            figure = service.create_calibration_figure(model_id) if model.coefficients is not None else empty_calibration_figure('Select standards and fit calibration')
            figure.update_layout(margin=dict(l=65,r=24,t=48,b=50),autosize=True)
            signal_rows = [r for r in rows if r.get('signal_key')]
            matching_signal = bool(signal_rows or model.signal_key)
            matching_units = signal_rows[0].get('x_units', '') if signal_rows else model.x_units
            match_text = 'Select a measured reference peak to identify the peak to find in other samples.'
            if matching_signal and values['position'] not in (None,''):
                center, tolerance = float(values['position']), float(values['tolerance'])
                match_text = (f"Find a peak between {center-tolerance:.4g} and {center+tolerance:.4g} {matching_units} "
                              'in other samples, using the same signal; a peak with the calibrated peak\'s name is taken first, and two '
                              'other peaks there are ambiguous. Peaks in the standards are not unknowns. Its response is converted to concentration using this curve.')
            result = [options,model_id,rows,included] + [values[n] for n in field_names]
            result += [figure,feedback,match_text,(revision or 0)+1 if changed else dash.no_update,model.coefficients is None]
            if not hydrate and trigger in {'cal-standards-table', *(cid for cid, _ in field_ids)} and trigger != 'cal-response-type':
                # Preserve the browser's active cell and newer keystrokes while saving the draft.
                result[2:12] = [dash.no_update] * 10
            return result
        except (ValueError,TypeError,KeyError,IndexError,UnicodeError) as exc:
            result[-4] = str(exc)
            return result

    @app.callback(Output('cal-download','data'),Input('cal-save-btn','n_clicks'),
                  State('cal-active-model','value'),prevent_initial_call=True)
    def save_calibration(clicks,model_id):
        model = service.get_model(model_id)
        if not clicks or not model or model.coefficients is None:
            return dash.no_update
        import re
        name = re.sub(r'[^\w.-]+','_',model.analyte_name).strip('_') or 'calibration'
        return dcc.send_string(json.dumps(service.export_calibrations([model_id]),indent=2,allow_nan=False),name+'_calibration.json')
