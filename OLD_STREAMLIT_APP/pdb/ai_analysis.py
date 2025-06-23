import numpy as np
import pandas as pd
from typing import Dict, List, Tuple, Any


def predict_active_sites(parsed_pdb: dict,
                         method: str = 'geometry') -> List[Tuple[str, int]]:
    """
    Predict potential active site residues from parsed PDB data.

    Parameters:
    - parsed_pdb: output dict from parse_pdb_extreme
    - method: 'geometry' (pocket geometry), 'conservation', or 'ml'

    Returns:
    - List of tuples (chain_id, residue_number)
    """
    # Placeholder: simple pocket by low B-factor
    active = []
    for atom in parsed_pdb['atoms']:
        if atom['b_factor'] < np.percentile([a['b_factor'] for a in parsed_pdb['atoms']], 20):
            active.append((atom['chain'], atom['residue_num']))
    # unique
    return sorted(set(active))


def evaluate_drug_binding_sites(parsed_pdb: dict,
                                docking_scores: Dict[str, float]) -> pd.DataFrame:
    """
    Combine docking scores with site predictions to rank binding sites.

    Parameters:
    - parsed_pdb: output dict from parse_pdb_extreme
    - docking_scores: mapping 'chain:resnum' -> docking score

    Returns:
    - DataFrame with columns ['Chain','Residue','DockingScore','Ranking']
    """
    data = []
    for key, score in docking_scores.items():
        chain, res = key.split(':')
        resnum = int(res)
        data.append({'Chain': chain, 'Residue': resnum, 'DockingScore': score})
    df = pd.DataFrame(data)
    df['Ranking'] = df['DockingScore'].rank(ascending=True)
    return df.sort_values('Ranking')


def analyze_flexibility(md_metrics: Dict[str, Any],
                        threshold: float = 1.5) -> Dict[str, Any]:
    """
    Identify flexible regions from RMSF or PCA metrics.

    Parameters:
    - md_metrics: dict containing 'rmsf': list or array of RMSF values
    - threshold: RMSF threshold to classify flexibility

    Returns:
    - Dict with keys 'flexible_residues', 'rmsf_values'
    """
    rmsf = np.array(md_metrics.get('rmsf', []))
    flexible_idx = np.where(rmsf > threshold)[0]
    return {
        'flexible_residues': flexible_idx.tolist(),
        'rmsf_values': rmsf.tolist()
    }


def suggest_mutations(active_sites: List[Tuple[str, int]],
                      conservation_scores: Dict[Tuple[str, int], float],
                      top_n: int = 5) -> List[Tuple[str, int, float]]:
    """
    Recommend mutations at active sites based on conservation.

    Parameters:
    - active_sites: list of (chain, residue_num)
    - conservation_scores: mapping (chain, resnum) -> conservation score (0-1)
    - top_n: number of recommendations

    Returns:
    - List of (chain, residue, score) sorted by lowest conservation first
    """
    data = []
    for site in active_sites:
        score = conservation_scores.get(site, 0.0)
        data.append((site[0], site[1], score))
    # low conservation => good candidate
    data.sort(key=lambda x: x[2])
    return data[:top_n]


def ai_recommend_experiments(parsed_pdb: dict,
                             md_metrics: Dict[str, Any],
                             sequence: str) -> List[str]:
    """
    Provide AI-driven experiment suggestions based on structure and dynamics.

    Returns a list of human-readable suggestions.
    """
    suggestions = []
    # Example rules
    active = predict_active_sites(parsed_pdb)
    if active:
        suggestions.append(f"Validate predicted active site at {active[0][0]} chain, residue {active[0][1]} by site-directed mutagenesis.")
    if md_metrics.get('rmsf') is not None and max(md_metrics['rmsf']) > 2.0:
        suggestions.append("Perform hydrogen-deuterium exchange MS to probe flexible regions.")
    if len(sequence) > 100:
        suggestions.append("Consider truncation constructs to improve crystallization.")
    return suggestions
