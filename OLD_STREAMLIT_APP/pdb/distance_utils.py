import numpy as np


def distance_matrix(coords: np.ndarray) -> np.ndarray:
    """
    Compute the full pairwise distance matrix for a set of points.

    Parameters:
    - coords: (N_points, 3) array of XYZ coordinates

    Returns:
    - dist_mat: (N_points, N_points) symmetric distance matrix
    """
    diff = coords[:, None, :] - coords[None, :, :]
    return np.sqrt(np.sum(diff**2, axis=-1))


def pairwise_distances(coords1: np.ndarray, coords2: np.ndarray) -> np.ndarray:
    """
    Compute distances between two sets of points.

    Parameters:
    - coords1: (N, 3)
    - coords2: (M, 3)

    Returns:
    - dists: (N, M) array of distances
    """
    diff = coords1[:, None, :] - coords2[None, :, :]
    return np.sqrt(np.sum(diff**2, axis=-1))


def find_contacts(coords: np.ndarray, cutoff: float = 4.5) -> list[tuple[int, int]]:
    """
    Identify pairs of atoms that are within a distance cutoff.

    Parameters:
    - coords: (N_atoms, 3)
    - cutoff: distance threshold in Å

    Returns:
    - contacts: list of (i, j) index pairs where distance <= cutoff
    """
    dist_mat = distance_matrix(coords)
    # get upper triangle indices
    idx_i, idx_j = np.where(np.triu(dist_mat <= cutoff, k=1))
    return list(zip(idx_i.tolist(), idx_j.tolist()))


def contact_map_frequency(traj_coords: np.ndarray, cutoff: float = 4.5) -> np.ndarray:
    """
    Compute the frequency of contacts over a trajectory.

    Parameters:
    - traj_coords: (N_frames, N_atoms, 3)
    - cutoff: distance threshold

    Returns:
    - freq_map: (N_atoms, N_atoms) array of contact frequencies (0-1)
    """
    n_frames, n_atoms, _ = traj_coords.shape
    freq = np.zeros((n_atoms, n_atoms), dtype=float)
    for frame in traj_coords:
        dm = distance_matrix(frame)
        contacts = dm <= cutoff
        freq += contacts.astype(float)
    # divide by number of frames
    return freq / n_frames
