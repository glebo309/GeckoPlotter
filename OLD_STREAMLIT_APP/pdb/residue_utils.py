from typing import List, Dict


def filter_by_residue_name(atoms: List[Dict], names: List[str]) -> List[Dict]:
    """
    Return a list of atom dicts whose residue name matches any in names (three-letter codes).
    """
    names_set = set(n.upper() for n in names)
    return [atom for atom in atoms if atom['residue'].upper() in names_set]


def filter_by_chain(atoms: List[Dict], chain_id: str) -> List[Dict]:
    """
    Return atoms belonging to the specified chain.
    """
    return [atom for atom in atoms if atom['chain'] == chain_id]


def filter_by_bfactor(atoms: List[Dict], min_b: float = None, max_b: float = None) -> List[Dict]:
    """
    Filter atoms by B-factor range.

    Parameters:
    - min_b: minimum inclusive B-factor
    - max_b: maximum inclusive B-factor
    """
    result = atoms
    if min_b is not None:
        result = [atom for atom in result if atom.get('b_factor', 0.0) >= min_b]
    if max_b is not None:
        result = [atom for atom in result if atom.get('b_factor', 0.0) <= max_b]
    return result


def filter_by_residue_number(atoms: List[Dict], start: int = None, end: int = None) -> List[Dict]:
    """
    Filter atoms by residue sequence number range.
    """
    result = atoms
    if start is not None:
        result = [atom for atom in result if atom.get('residue_num', 0) >= start]
    if end is not None:
        result = [atom for atom in result if atom.get('residue_num', 0) <= end]
    return result


def group_atoms_by_residue(atoms: List[Dict]) -> Dict[int, List[Dict]]:
    """
    Group atom dicts by residue sequence number.

    Returns a dict mapping residue_num -> list of atom dicts.
    """
    grouped: Dict[int, List[Dict]] = {}
    for atom in atoms:
        resnum = atom.get('residue_num')
        if resnum is None:
            continue
        grouped.setdefault(resnum, []).append(atom)
    return grouped


def get_unique_residues(atoms: List[Dict]) -> List[int]:
    """
    Return sorted list of unique residue numbers present in the atom list.
    """
    resnums = {atom.get('residue_num') for atom in atoms if atom.get('residue_num') is not None}
    return sorted(resnums)
