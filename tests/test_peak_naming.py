"""Peak names: one name everywhere (table and plot), kept when peaks are detected again."""
import numpy as np

from services.peak_service import PeakService


def _signal():
    x = np.linspace(0, 10, 2000)
    y = 100 * np.exp(-((x - 3) / .08) ** 2) + 60 * np.exp(-((x - 6) / .1) ** 2)
    return x, y


def test_peaks_are_numbered_from_one_in_retention_order():
    x, y = _signal()
    peaks = PeakService().detect_peaks('f', y, x)
    assert [p.name for p in peaks] == ['Peak 1', 'Peak 2']


def test_renaming_sets_the_name_and_the_label_shown_on_the_plot():
    service = PeakService()
    x, y = _signal()
    first = service.detect_peaks('f', y, x)[0]
    assert service.rename_peak('f', first.peak_id, 'Alanine')
    peak = service.get_peaks('f')[0]
    assert peak.name == 'Alanine' and peak.label == 'Alanine'


def test_a_name_survives_detecting_the_peaks_again():
    service = PeakService()
    x, y = _signal()
    first = service.detect_peaks('f', y, x)[0]
    service.rename_peak('f', first.peak_id, 'Alanine')
    again = service.detect_peaks('f', y, x, threshold=0.04)          # a setting changed: everything is detected again
    assert [p.name for p in again] == ['Alanine', 'Peak 2']
    assert again[0].label == 'Alanine'


def test_automatic_names_are_not_mistaken_for_custom_ones():
    service = PeakService()
    x, y = _signal()
    peaks = service.detect_peaks('f', y, x)
    assert not any(service.has_custom_name(p) for p in peaks)
    service.rename_peak('f', peaks[1].peak_id, 'Glycine')
    assert service.has_custom_name(service.get_peaks('f')[1])
