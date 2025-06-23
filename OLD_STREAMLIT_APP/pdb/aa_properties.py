def get_aa_properties(aa: str) -> str:
    """Return the property category of a given amino acid single-letter code."""
    properties = {
        'A': 'Hydrophobic', 'V': 'Hydrophobic', 'L': 'Hydrophobic', 'I': 'Hydrophobic',
        'P': 'Hydrophobic', 'F': 'Hydrophobic', 'W': 'Hydrophobic', 'M': 'Hydrophobic',
        'S': 'Polar',       'T': 'Polar',       'Y': 'Polar',      'C': 'Polar',
        'N': 'Polar',       'Q': 'Polar',       'K': 'Positive',  'R': 'Positive',
        'H': 'Positive',    'D': 'Negative',    'E': 'Negative',  'G': 'Special'
    }
    return properties.get(aa, 'Unknown')
