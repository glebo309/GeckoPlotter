"""Source-scoped capabilities for the mounted analysis workspace."""
from services.data_store import BundleType
from services.lcms_service import LCMSService

MS_ANALYSIS_TABS = ('ms-scan', 'ms-eic', 'ms-peak-mass')


def has_lcms_scans(data_manager, active_file):
    """Require scan arrays in this LC-MS bundle, never another loaded file.

    A TIC export or standalone m/z plot is insufficient for scan selection,
    extraction of ion chromatograms, or averaging scans over a peak.
    """
    if not active_file:
        return False
    bundle = (data_manager.get_bundle(active_file)
              or data_manager.get_bundle_for_component(active_file))
    if not bundle or bundle.bundle_type != BundleType.LCMS:
        return False
    for component in bundle.component_list:
        entry = data_manager.get_data_by_id(component.component_id)
        arrays = LCMSService._get_spectral_arrays(entry or {})
        if arrays is None:
            continue
        try:
            if all(len(arrays.get(key, [])) > 0 for key in
                   ('mass_values', 'intensity_values', 'scan_index')):
                return True
        except TypeError:
            continue
    return False
