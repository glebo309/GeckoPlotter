from __future__ import annotations
from typing import List
from ..stage_2_registry import FormatPreset


def load_all_presets() -> List[FormatPreset]:
    from .shimadzu_ascii import ShimadzuASCIIPreset
    from .shimadzu_lcd import ShimadzuLCDPreset
    from .cary_kinetics import CaryKineticsPreset
    from .chromeleon_txt import ChromeleonTxtPreset
    from .plate_reader_csv import PlateReaderCSVPreset
    from .agilent_lcms_csv import AgilentLCMSCSVPreset
    from .lcms_cdf import LCMSCDFPreset
    from .lcms_vwd_cdf import LCMSVWDCDFPreset
    from .excel_xlsx import ExcelPreset

    return [
        ShimadzuASCIIPreset(),
        ShimadzuLCDPreset(),
        CaryKineticsPreset(),
        ChromeleonTxtPreset(),
        AgilentLCMSCSVPreset(),
        PlateReaderCSVPreset(),
        LCMSCDFPreset(),
        LCMSVWDCDFPreset(),
        ExcelPreset(),
    ]
