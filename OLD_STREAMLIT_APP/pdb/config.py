# config.py
# Centralized configuration and default parameters for the MD & Sequence Analysis package

# Hydrogen-bond detection defaults
HBOND_DISTANCE_CUTOFF: float = 3.5  # Ångstroms
HBOND_ANGLE_CUTOFF: float = 30.0    # Degrees of deviation from linear

# Contact map defaults
CONTACT_DISTANCE_CUTOFF: float = 4.5  # Ångstroms

# RMSF thresholds for visualization
RMSF_MEDIUM_THRESHOLD: float = 1.0  # Å
RMSF_HIGH_THRESHOLD: float = 2.0    # Å

# Clustering defaults
KMEANS_N_CLUSTERS: int = 3
DBSCAN_EPS: float = 1.0
DBSCAN_MIN_SAMPLES: int = 5

# PCA defaults
PCA_N_COMPONENTS: int = 3

# Filenames / paths
DEFAULT_RESULTS_PATH: str = 'results.npz'

# Logging
LOGGING_LEVEL: str = 'INFO'

# Plot settings
PLOT_HEIGHT_SMALL: int = 400
PLOT_HEIGHT_LARGE: int = 600

# End of config.py
