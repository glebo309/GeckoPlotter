from __future__ import annotations
from typing import List
from ..stage_2_registry import FormatPreset


def load_all_presets() -> List[FormatPreset]:
    from .cary_kinetics import CaryKineticsPreset
    from .chromeleon_txt import ChromeleonTxtPreset
    from .plate_reader_csv import PlateReaderCSVPreset
    from .lcms_cdf import LCMSCDFPreset
    from .lcms_vwd_cdf import LCMSVWDCDFPreset
    from .excel_xlsx import ExcelPreset

    return [
        CaryKineticsPreset(),
        ChromeleonTxtPreset(),
        PlateReaderCSVPreset(),
        LCMSCDFPreset(),
        LCMSVWDCDFPreset(),
        ExcelPreset(),
    ]
