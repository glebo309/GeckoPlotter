import numpy as np
from typing import Tuple, Optional, Dict, Any


def load_pdb_content(pdb_file) -> str:
    """
    Read and return the content of an uploaded PDB file (Streamlit file-like or path).
    """
    if hasattr(pdb_file, 'read'):
        raw = pdb_file.read()
        # if bytes, decode
        return raw.decode('utf-8') if isinstance(raw, (bytes, bytearray)) else raw
    else:
        with open(pdb_file, 'r') as f:
            return f.read()


def load_trajectory_npz(npz_file) -> Dict[str, Any]:
    """
    Load trajectory data from a .npz archive.

    Expects arrays:
    - 'coords': (N_frames, N_atoms, 3)
    - optionally 'phi_atoms', 'psi_atoms', 'ss_types'

    Returns a dict with keys for each array present.
    """
    if hasattr(npz_file, 'read'):
        # Streamlit uploads have no filename, so save to temp
        import io
        buf = io.BytesIO(npz_file.read())
        data = np.load(buf, allow_pickle=True)
    else:
        data = np.load(npz_file, allow_pickle=True)

    result: Dict[str, Any] = {}
    for key in ['coords', 'phi_atoms', 'psi_atoms', 'ss_types']:
        if key in data:
            result[key] = data[key]
    return result


def save_dataframe(df, path: str) -> None:
    """
    Save a pandas DataFrame to CSV.
    """
    df.to_csv(path, index=False)


def save_plotly_figure(fig, path: str) -> None:
    """
    Save a Plotly figure to an HTML file.
    """
    fig.write_html(path)


def export_results(results: Dict[str, Any], path: str) -> None:
    """
    Export multiple arrays and metrics to a compressed .npz file.

    'results' can include numpy arrays and scalars.
    """
    np.savez_compressed(path, **results)
