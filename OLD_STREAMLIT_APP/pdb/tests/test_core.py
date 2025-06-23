import pytest
import numpy as np
from parser import parse_pdb_extreme
from aa_conversion import three_to_one, convert_sequence
from sequence_analysis import compute_composition, compute_property_distribution, sequence_similarity
from md_analysis import compute_rmsd, compute_radius_of_gyration, compute_rmsf
from distance_utils import distance_matrix, pairwise_distances
from hbond_utils import detect_hydrogen_bonds
from geometry_utils import compute_dimensions, compute_volume, compute_aspect_ratio

# Sample minimal PDB content for testing
PDB_SAMPLE = """
HEADER    TEST PDB
ATOM      1  N   ALA A   1      11.104  13.207  12.011  1.00 20.00           N  
ATOM      2  CA  ALA A   1      12.567  13.000  12.000  1.00 20.00           C  
ATOM      3  C   ALA A   1      13.000  14.400  12.500  1.00 20.00           C  
END
"""

@ pytest.fixture
 def parsed():
     return parse_pdb_extreme(PDB_SAMPLE)

 def test_parse_pdb_extreme_keys(parsed):
     assert 'header_info' in parsed
     assert 'atoms' in parsed
     assert len(parsed['atoms']) == 3

 def test_three_to_one():
     assert three_to_one('ALA') == 'A'
     assert three_to_one('unknown') == 'X'

 def test_convert_sequence():
     assert convert_sequence(['ALA', 'CYS', 'ASP']) == 'ACD'

 def test_compute_composition():
     df = compute_composition('AABC')
     counts = dict(zip(df['Residue'], df['Count']))
     assert counts['A'] == 2
     assert counts['B'] == 1 or 'B' in counts

 def test_sequence_similarity():
     assert sequence_similarity('ABC', 'ABC') == 1.0
     assert sequence_similarity('ABC', 'ABD') == pytest.approx(2/3)

 def test_compute_rmsd_and_rg():
     coords = np.array([[[0,0,0], [1,0,0]], [[1,0,0], [2,0,0]]])
     rmsd = compute_rmsd(coords[0], coords)
     assert rmsd.shape == (2,)
     rg = compute_radius_of_gyration(coords)
     assert rg.shape == (2,)

 def test_compute_rmsf():
     coords = np.array([[[0,0,0],[1,1,1]], [[0,1,0],[1,2,1]], [[0,2,0],[1,3,1]]])
     rmsf = compute_rmsf(coords)
     assert rmsf.shape == (2,)

 def test_distance_utils():
     pts = np.array([[0,0,0],[1,0,0]])
     dm = distance_matrix(pts)
     assert dm[0,1] == pytest.approx(1.0)
     pdm = pairwise_distances(pts, pts)
     assert pdm.shape == (2,2)

 def test_detect_hydrogen_bonds_simple():
     donors = np.array([[0,0,0]])
     hydrogens = np.array([[0,0,1]])
     acceptors = np.array([[0,0,2]])
     hbonds = detect_hydrogen_bonds(donors, hydrogens, acceptors, distance_cutoff=3, angle_cutoff=45)
     assert isinstance(hbonds, list)

 def test_geometry_utils():
     pts = np.array([[0,0,0],[1,2,3]])
     dims = compute_dimensions(pts)
     assert np.allclose(dims, [1,2,3])
     assert compute_volume(dims) == pytest.approx(6)
     assert compute_aspect_ratio(dims) == pytest.approx(3/1)