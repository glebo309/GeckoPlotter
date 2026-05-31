import numpy as np
import pandas as pd

from src.services.lcms_service import LCMSService


def make_lcms_entry():
    return {
        "data": pd.DataFrame(
            {
                "Time (min)": [0.0, 0.5, 1.0],
                "Intensity": [100.0, 200.0, 300.0],
            }
        ),
        "metadata": {
            "mass_spectral_data": {
                "mass_values": np.array(
                    [99.9, 100.1, 101.0, 99.8, 100.2, 102.0, 50.0, 75.0, 100.0],
                    dtype=np.float32,
                ),
                "intensity_values": np.array(
                    [10.0, 20.0, 5.0, 3.0, 7.0, 11.0, 1.0, 2.0, 30.0],
                    dtype=np.float32,
                ),
                "scan_index": np.array([0, 3, 6], dtype=np.int32),
                "point_count": np.array([3, 3, 3], dtype=np.int32),
            }
        },
    }


def test_extract_eic_uses_point_counts_and_matches_scan_window_sum():
    service = LCMSService()
    time, intensity = service.extract_eic(make_lcms_entry(), 100.0, tolerance=0.25)

    assert time.tolist() == [0.0, 0.5, 1.0]
    assert intensity.tolist() == [30.0, 10.0, 30.0]


def test_extract_eic_caches_repeated_requests_for_same_arrays():
    service = LCMSService()
    entry = make_lcms_entry()

    first = service.extract_eic(entry, 100.0, tolerance=0.25)
    second = service.extract_eic(entry, 100.0, tolerance=0.25)

    assert second is first
    assert len(service._eic_cache) == 1
    assert len(service._sorted_scan_cache) == 1


def test_get_scan_index_at_time_returns_nearest_scan():
    service = LCMSService()

    assert service.get_scan_index_at_time(make_lcms_entry(), 0.6) == 1
