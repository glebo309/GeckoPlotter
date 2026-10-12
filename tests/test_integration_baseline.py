import numpy as np
from services.integration_service import IntegrationService
from services.peak_service import PeakService


def test_snip_roundtrip_preserves_flat_baselines_in_absorbance_and_count_units():
    for level in (0., .05, .4, 1000.):
        baseline=IntegrationService._snip_baseline(np.full(101,level))
        np.testing.assert_allclose(baseline,level,atol=2e-10)


def test_absorbance_peak_below_one_survives_full_detection_pipeline():
    x=np.linspace(380,950,2000)
    raw=.02+.43*np.exp(-.5*((x-516)/45)**2)
    integration=IntegrationService()
    integration.update_settings('uv',smooth_window=101)
    processed=integration.process_signal('uv',x,raw)
    peaks=PeakService().detect_peaks('uv',processed.corrected,x,threshold=.001,
        display_signal=raw,integration_baseline='linear')
    assert any(abs(p.rt-516)<3 and p.area>0 and p.rt_start<500<p.rt_end for p in peaks)
    np.testing.assert_array_equal(processed.raw,raw)
