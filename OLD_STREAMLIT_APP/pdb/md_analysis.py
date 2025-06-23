import numpy as np
from scipy.spatial.distance import cdist
from sklearn.decomposition import PCA
from sklearn.cluster import KMeans, DBSCAN


def compute_rmsd(reference_coords: np.ndarray, traj_coords: np.ndarray) -> np.ndarray:
    """
    Compute RMSD of each frame in a trajectory relative to a reference.

    Parameters:
    - reference_coords: (N_atoms, 3) array for reference structure
    - traj_coords: (N_frames, N_atoms, 3) trajectory coordinates

    Returns:
    - rmsd: (N_frames,) array of RMSD values
    """
    ref = reference_coords.reshape(-1, 3)
    num_frames = traj_coords.shape[0]
    rmsd = np.zeros(num_frames)
    for i in range(num_frames):
        diff = traj_coords[i].reshape(-1, 3) - ref
        rmsd[i] = np.sqrt((diff**2).sum(axis=1).mean())
    return rmsd


def compute_radius_of_gyration(traj_coords: np.ndarray, masses: np.ndarray = None) -> np.ndarray:
    """
    Compute radius of gyration for each frame.

    Parameters:
    - traj_coords: (N_frames, N_atoms, 3)
    - masses: (N_atoms,) optional array of atomic masses

    Returns:
    - rg: (N_frames,) array of Rg values
    """
    if masses is None:
        masses = np.ones(traj_coords.shape[1])
    total_mass = masses.sum()
    rg = np.zeros(traj_coords.shape[0])
    for i, frame in enumerate(traj_coords):
        com = np.average(frame, axis=0, weights=masses)
        diff = frame - com
        rg[i] = np.sqrt(np.average((diff**2).sum(axis=1), weights=masses))
    return rg


def compute_rmsf(traj_coords: np.ndarray) -> np.ndarray:
    """
    Compute RMSF for each atom across a trajectory.

    Parameters:
    - traj_coords: (N_frames, N_atoms, 3)

    Returns:
    - rmsf: (N_atoms,) array of fluctuations
    """
    mean_coords = traj_coords.mean(axis=0)
    diff = traj_coords - mean_coords
    sq = (diff**2).sum(axis=2)
    msf = sq.mean(axis=0)
    return np.sqrt(msf)


def perform_pca(traj_coords: np.ndarray, n_components: int = 3) -> tuple[np.ndarray, np.ndarray]:
    """
    Perform PCA on concatenated trajectory coordinates.

    Parameters:
    - traj_coords: (N_frames, N_atoms, 3)
    - n_components: number of PCs

    Returns:
    - coords_pc: (N_frames, n_components) projected coordinates
    - variance_ratio: (n_components,) explained variance ratios
    """
    frames, atoms, _ = traj_coords.shape
    data = traj_coords.reshape(frames, atoms * 3)
    pca = PCA(n_components=n_components)
    coords_pc = pca.fit_transform(data)
    return coords_pc, pca.explained_variance_ratio_


def cluster_kmeans(coords: np.ndarray, n_clusters: int = 3) -> tuple[np.ndarray, np.ndarray]:
    """
    Apply KMeans clustering.

    Returns labels and cluster centers.
    """
    kmeans = KMeans(n_clusters=n_clusters)
    labels = kmeans.fit_predict(coords)
    return labels, kmeans.cluster_centers_


def cluster_dbscan(coords: np.ndarray, eps: float = 1.0, min_samples: int = 5) -> np.ndarray:
    """
    Apply DBSCAN clustering.

    Returns labels (with -1 for noise).
    """
    db = DBSCAN(eps=eps, min_samples=min_samples)
    return db.fit_predict(coords)


def compute_ramachandran_angles(phi_atoms: np.ndarray, psi_atoms: np.ndarray) -> tuple[list, list]:
    """
    Compute torsion angles (phi, psi) for each residue.

    Parameters:
    - phi_atoms: (N_residues, 4, 3) coordinates of [C_{i-1}, N_i, CA_i, C_i]
    - psi_atoms: (N_residues, 4, 3) coordinates of [N_i, CA_i, C_i, N_{i+1}]

    Returns:
    - phi: list of phi angles in degrees
    - psi: list of psi angles in degrees
    """
    def torsion(p):
        b1 = p[1] - p[0]
        b2 = p[2] - p[1]
        b3 = p[3] - p[2]
        # normal vectors
        n1 = np.cross(b1, b2)
        n2 = np.cross(b2, b3)
        # normalize
        n1 /= np.linalg.norm(n1, axis=1)[:, None] if n1.ndim>1 else np.linalg.norm(n1)
        n2 /= np.linalg.norm(n2, axis=1)[:, None] if n2.ndim>1 else np.linalg.norm(n2)
        m1 = np.cross(n1, b2/np.linalg.norm(b2, axis=1)[:, None]) if b2.ndim>1 else np.cross(n1, b2/np.linalg.norm(b2))
        x = (n1 * n2).sum(axis=1) if n1.ndim>1 else np.dot(n1, n2)
        y = (m1 * n2).sum(axis=1) if m1.ndim>1 else np.dot(m1, n2)
        return np.degrees(np.arctan2(y, x))
    phi = torsion(phi_atoms)
    psi = torsion(psi_atoms)
    return list(phi), list(psi)
