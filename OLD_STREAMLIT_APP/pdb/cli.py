import argparse
import sys
from file_io import load_pdb_content, load_trajectory_npz, export_results
from parser import parse_pdb_extreme
from md_analysis import compute_rmsd, compute_radius_of_gyration, compute_rmsf, perform_pca
from sequence_analysis import seq_list_to_single, compute_composition


def main():
    parser = argparse.ArgumentParser(description='MD & Sequence Analysis CLI')
    parser.add_argument('--pdb', required=True, help='Path to PDB file')
    parser.add_argument('--traj', help='Path to .npz trajectory file')
    parser.add_argument('--out', default='results.npz', help='Output .npz file')
    args = parser.parse_args()

    # Load inputs
    pdb_content = load_pdb_content(args.pdb)
    parsed = parse_pdb_extreme(pdb_content)

    results = {}
    # Sequence
    for chain, atoms in parsed['residues'].items():
        seq3 = [atom['residue'] for atom in atoms]
        seq1 = seq_list_to_single(seq3)
        comp = compute_composition(seq1)
        results[f'comp_chain_{chain}'] = comp.to_dict(orient='list')

    # Dynamics
    if args.traj:
        traj = load_trajectory_npz(args.traj)
        coords = traj['coords']
        results['rmsd'] = compute_rmsd(coords[0], coords).tolist()
        results['rg'] = compute_radius_of_gyration(coords).tolist()
        results['rmsf'] = compute_rmsf(coords).tolist()
        pca_coords, var = perform_pca(coords)
        results['pca_coords'] = pca_coords.tolist()
        results['pca_variance'] = var.tolist()

    # Export
    export_results(results, args.out)
    print(f"Results saved to {args.out}")


if __name__ == '__main__':
    main()
