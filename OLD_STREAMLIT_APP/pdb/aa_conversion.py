def three_to_one(residue: str) -> str:
    """Convert a three-letter amino acid code to its single-letter code."""
    aa_map = {
        'ALA': 'A', 'ARG': 'R', 'ASN': 'N', 'ASP': 'D', 'CYS': 'C',
        'GLU': 'E', 'GLN': 'Q', 'GLY': 'G', 'HIS': 'H', 'ILE': 'I',
        'LEU': 'L', 'LYS': 'K', 'MET': 'M', 'PHE': 'F', 'PRO': 'P',
        'SER': 'S', 'THR': 'T', 'TRP': 'W', 'TYR': 'Y', 'VAL': 'V'
    }
    return aa_map.get(residue.upper(), 'X')


def convert_sequence(residue_list: list[str]) -> str:
    """Convert a list of three-letter residues to a single-letter sequence string."""
    return ''.join(three_to_one(res) for res in residue_list)
