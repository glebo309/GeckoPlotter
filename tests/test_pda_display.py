import numpy as np
from services.pda_service import display_matrix


def test_display_matrix_is_screen_sized_and_keeps_narrow_peaks_and_dips():
    t = np.linspace(0, 3.5, 8401)
    w = np.linspace(190, 700, 412)
    z = np.zeros((8401, 412))
    z[4200, 100] = 2500.   # one-sample spike
    z[1000, 50] = -300.    # negative dip
    dt, dw, dz = display_matrix(t, w, z)
    assert dz.shape[0] <= 700 and dz.shape[1] <= 512 and dz.dtype == np.float32
    assert len(dt) == dz.shape[0] and len(dw) == dz.shape[1]
    assert dz.max() == 2500. and dz.min() == -300.
    assert dt.min() >= 0 and dt.max() <= 3.5 and np.all(np.diff(dt) > 0)


def test_small_matrices_are_not_resampled():
    t, w, z = np.array([0., 1., 2.]), np.array([200., 220.]), np.arange(6.).reshape(3, 2)
    dt, dw, dz = display_matrix(t, w, z)
    assert dz.shape == (3, 2) and list(dt) == [0., 1., 2.] and list(dw) == [200., 220.]
