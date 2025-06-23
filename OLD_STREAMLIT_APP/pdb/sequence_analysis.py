from collections import Counter
import pandas as pd
from aa_conversion import three_to_one
from aa_properties import get_aa_properties



def seq_list_to_single(residue_list: list[str]) -> str:
    """Convert a list of three-letter residues to its single-letter sequence string."""
    return ''.join(three_to_one(res) for res in residue_list)


def compute_composition(sequence: str) -> pd.DataFrame:
    """Return a DataFrame of residue counts and percentages for a given sequence."""
    counts = Counter(sequence)
    total = sum(counts.values())
    data = [
        {'Residue': aa, 'Count': cnt, 'Percentage': cnt / total * 100}
        for aa, cnt in counts.items()
    ]
    df = pd.DataFrame(data)
    return df.sort_values(by='Count', ascending=False)


def compute_property_distribution(sequence: str) -> pd.DataFrame:
    """Return a DataFrame of amino acid property counts and percentages for a sequence."""
    props = [get_aa_properties(aa) for aa in sequence]
    prop_counts = Counter(props)
    total = sum(prop_counts.values())
    data = [
        {'Property': prop, 'Count': cnt, 'Percentage': cnt / total * 100}
        for prop, cnt in prop_counts.items()
    ]
    df = pd.DataFrame(data)
    return df.sort_values(by='Count', ascending=False)


def sequence_similarity(seq1: str, seq2: str) -> float:
    """Compute a simple similarity score between two sequences (fraction of matches)."""
    min_len = min(len(seq1), len(seq2))
    if min_len == 0:
        return 0.0
    matches = sum(a == b for a, b in zip(seq1[:min_len], seq2[:min_len]))
    return matches / min_len
