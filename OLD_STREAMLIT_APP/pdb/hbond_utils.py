import numpy as np


def detect_hydrogen_bonds(donor_coords: np.ndarray,
                          hydrogen_coords: np.ndarray,
                          acceptor_coords: np.ndarray,
                          distance_cutoff: float = 3.5,
                          angle_cutoff: float = 30.0) -> list[tuple[int, int, int]]:
    """
    Detect potential hydrogen bonds based on geometric criteria.

    Parameters:
    - donor_coords: (N_donors, 3) array of donor atom coordinates (e.g., N or O atoms)
    - hydrogen_coords: (N_hydrogens, 3) array of hydrogen atom coordinates bonded to donors
    - acceptor_coords: (N_acceptors, 3) array of acceptor atom coordinates (e.g., O or N atoms)
    - distance_cutoff: maximal D-A distance to consider (Å)
    - angle_cutoff: maximal deviation from linear D-H-A angle (°; so angle must be >= 180° - cutoff)

    Returns:
    - List of tuples (donor_index, hydrogen_index, acceptor_index) indicating detected H-bonds.
    """
    hbonds = []
    # Precompute donor-acceptor pairs within distance
    for i, d in enumerate(donor_coords):
        # distances from donor to all acceptors
        da_vecs = acceptor_coords - d
        da_dists = np.linalg.norm(da_vecs, axis=1)
        close_acceptors = np.where(da_dists <= distance_cutoff)[0]
        if close_acceptors.size == 0:
            continue
        # hydrogen attached to donor: find H that is closest to this donor
        # assume hydrogen_coords and donor_coords are aligned lists (same indexing)
        # if not, user must align externally
        h = hydrogen_coords[i]
        dh_vec = h - d
        dh_len = np.linalg.norm(dh_vec)
        if dh_len == 0:
            continue
        dh_unit = dh_vec / dh_len
        for j in close_acceptors:
            # compute D-H-A angle
            da_vec = acceptor_coords[j] - h
            da_len = np.linalg.norm(da_vec)
            if da_len == 0:
                continue
            da_unit = da_vec / da_len
            angle = np.degrees(np.arccos(np.clip(np.dot(dh_unit, da_unit), -1.0, 1.0)))
            # bond is linear if angle close to 180; here angle is H-D-A deviation
            if angle <= angle_cutoff:
                hbonds.append((i, i, j))  # (donor_idx, hydrogen_idx, acceptor_idx)
    return hbonds


def hydrogen_bond_frequency(traj_donors: np.ndarray,
                             traj_hydrogens: np.ndarray,
                             traj_acceptors: np.ndarray,
                             distance_cutoff: float = 3.5,
                             angle_cutoff: float = 30.0) -> np.ndarray:
    """
    Compute hydrogen-bond occupancy (frequency) over a trajectory.

    Returns:
    - freq_map: (N_donors, N_acceptors) array of frequencies (0-1)
    """
    n_frames = traj_donors.shape[0]
    n_donors = traj_donors.shape[1]
    n_acceptors = traj_acceptors.shape[1]
    freq = np.zeros((n_donors, n_acceptors), dtype=float)
    for frame in range(n_frames):
        donors = traj_donors[frame]
        hydrogens = traj_hydrogens[frame]
        acceptors = traj_acceptors[frame]
        hbonds = detect_hydrogen_bonds(donors, hydrogens, acceptors, distance_cutoff, angle_cutoff)
        for donor_idx, _, acc_idx in hbonds:
            freq[donor_idx, acc_idx] += 1
    return freq / n_frames
