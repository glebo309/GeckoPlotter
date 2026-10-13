"""Shimadzu LabSolutions ``.lcd`` data files, read directly (no ASCII export needed).

Produces the same structure as the ASCII export preset: one chromatogram per exported channel, the PDA 3D matrix and
the sample record. The instrument status traces (pump pressure, temperatures) are read as well. LabSolutions' own peak tables are
not read from the binary file yet, so ``instrument_peaks`` is empty.
"""
from __future__ import annotations

import hashlib

import numpy as np
import pandas as pd

from ..stage_2_registry import FormatPreset
from ..types import ColumnRole, PlotHint, SourceCategory
from .shimadzu_ascii import _ROLES, _acquisition_extent, _pda_summary

_OLE_MAGIC = b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1'
UAU_TO_MAU = .001
_SCALING = {'factor_to_mau': UAU_TO_MAU, 'declared_unit': 'uAU', 'declared_multiplier': 1.0, 'output_unit': 'mAU',
            'basis': 'integers of the .lcd PDA frames (micro-AU); identical to the values of the ASCII export'}


def _curated(sample: dict, instrument, version_fallback=None) -> dict:
    keys = ('sample_name', 'sample_id', 'sample_type', 'level', 'vial', 'injection_volume_ul', 'sample_amount',
            'dilution_factor', 'operator', 'acquired', 'data_file', 'method_file', 'batch_file',
            'file_generated', 'file_modified')
    metadata = {'file_type_detail': 'shimadzu_labsolutions_lcd', 'manufacturer': 'Shimadzu', 'software': 'LabSolutions',
                'software_version': sample.get('software_version') or version_fallback,
                'instrument': instrument, 'detector': 'PDA'}
    metadata.update({k: sample[k] for k in keys if k in sample})
    if isinstance(metadata.get('vial'), str) and metadata['vial'].isdigit():
        metadata['vial'] = int(metadata['vial'])        # the ASCII export gives a plain number here
    return {k: v for k, v in metadata.items() if v is not None}


class ShimadzuLCDPreset(FormatPreset):
    name = 'shimadzu_lcd'
    extensions = {'lcd'}
    priority = 95
    strict = True    # a recognised but unreadable data file must not fall back to a heuristic table

    @staticmethod
    def sniff(path: str, head_bytes: bytes, head_lines: list[str]) -> bool:
        if not head_bytes.startswith(_OLE_MAGIC):
            return False
        try:
            import olefile
            with olefile.OleFileIO(path) as ole:
                return ole.exists('PDA 3D Raw Data/3D Raw Data')
        except Exception:
            return False

    def parse(self, path: str) -> dict:
        from services.lcd_reader import read_lcd, channel_trace
        lcd = read_lcd(path)
        time, wavelength = lcd['time_min'], lcd['wavelength_nm']
        absorbance = lcd['matrix_uau'].astype(float) * UAU_TO_MAU
        start, end = lcd['scan_range_nm']
        source = {'Interval(msec)': str(lcd['interval_ms']), 'Start Time(min)': '0',
                  'End Time(min)': f'{time[-1]:.3f}', 'Start Wavelength(nm)': f'{start:g}',
                  'End Wavelength(nm)': f'{end:g}', '# of Wavelength Axis Points': str(len(wavelength)),
                  '# of Time Axis Points': str(len(time))}
        arrays = {'time_min': time.copy(), 'wavelength_nm': wavelength.copy(), 'absorbance_mau': absorbance}
        digest = hashlib.sha256()
        for values in arrays.values():
            digest.update(values.astype('<f8', copy=False).tobytes())
            values.setflags(write=False)
        pda = {**arrays, 'data_sha256': digest.hexdigest(), 'intensity_scaling': dict(_SCALING),
               'wavelength_scaling': {'factor_to_nm': 1.0, 'basis': 'wavelength table of the .lcd 3D data item'},
               'source_metadata': source, 'source_section': 'PDA 3D Raw Data'}

        sample = lcd['sample']
        metadata = _curated(sample, lcd['instrument'])
        metadata.update(instrument_peaks={}, instrument_status=lcd.get('status_traces') or {})
        channels = []
        for channel in lcd['channels']:
            trace = channel_trace(lcd['matrix_uau'], wavelength, channel['wavelength_nm'], channel['bandwidth_nm'])
            channel_meta = {'detector_channel': channel['channel'], 'wavelength_nm': channel['wavelength_nm'],
                            'bandwidth_nm': channel['bandwidth_nm'], **_acquisition_extent(source, time),
                            'intensity_scaling': dict(_SCALING),
                            'source_section': f"channel {channel['number']} computed from the PDA 3D data"}
            channels.append({'name': f"PDA {channel['wavelength_nm']:g} nm ({channel['channel']})",
                             'data': pd.DataFrame({'Time (min)': time, 'Absorbance (mAU)': trace * UAU_TO_MAU}),
                             'column_roles': dict(_ROLES), 'metadata': channel_meta})
        metadata['pda'] = pda
        if not channels:
            index = int(np.argmin(abs(wavelength - 254)))
            channels.append({'name': f'PDA {wavelength[index]:g} nm',
                             'data': pd.DataFrame({'Time (min)': time, 'Absorbance (mAU)': absorbance[:, index]}),
                             'column_roles': dict(_ROLES),
                             'metadata': {'detector_channel': 'PDA', 'wavelength_nm': float(wavelength[index]),
                                          **_acquisition_extent(source, time), 'derived_from': 'PDA 3D',
                                          'intensity_scaling': dict(_SCALING)}})
        metadata.update(channels[0]['metadata'])
        metadata.update(_pda_summary(pda))
        metadata['channels'] = [
            {k: v for k, v in (('channel', c['metadata']['detector_channel']),
                               ('wavelength_nm', float(c['metadata']['wavelength_nm'])),
                               ('bandwidth_nm', c['metadata'].get('bandwidth_nm'))) if v is not None}
            for c in channels]
        metadata['chromatogram_channels'] = channels
        return {'data': channels[0]['data'], 'column_roles': dict(_ROLES), 'plot_hint': PlotHint.LINE,
                'source_category': SourceCategory.CHROMATOGRAM,
                'sample_name': sample.get('sample_name') or None, 'metadata': metadata}
