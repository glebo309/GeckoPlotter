import numpy as np


def compute_dimensions(coords: np.ndarray) -> np.ndarray:
    """
    Compute the bounding box dimensions of a set of 3D points.

    Parameters:
    - coords: (N_points, 3) array of XYZ coordinates

    Returns:
    - dimensions: (3,) array of extents along X, Y, Z
    """
    mins = coords.min(axis=0)
    maxs = coords.max(axis=0)
    return maxs - mins


def compute_volume(dimensions: np.ndarray) -> float:
    """
    Compute the approximate volume of the bounding box.

    Parameters:
    - dimensions: (3,) array of box side lengths

    Returns:
    - volume: product of the three dimensions
    """
    return float(np.prod(dimensions))


def compute_aspect_ratio(dimensions: np.ndarray) -> float:
    """
    Compute the aspect ratio of the bounding box (max_side / min_side).

    Parameters:
    - dimensions: (3,) array of box side lengths

    Returns:
    - aspect_ratio: ratio of longest to shortest dimension
    """
    sorted_dims = np.sort(dimensions)
    # Avoid division by zero
    if sorted_dims[0] == 0:
        return float('inf')
    return float(sorted_dims[-1] / sorted_dims[0])


def sample_coordinates(coords: np.ndarray, max_points: int = 1000) -> np.ndarray:
    """
    Uniformly sample up to max_points from a larger coordinate set.

    Parameters:
    - coords: (N_points, 3) array of XYZ coordinates
    - max_points: maximum number of points to return

    Returns:
    - sampled_coords: (<=max_points, 3) array
    """
    n = coords.shape[0]
    step = max(1, n // max_points)
    return coords[::step]
