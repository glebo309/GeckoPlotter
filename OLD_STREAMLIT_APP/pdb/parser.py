import numpy as np
from collections import defaultdict


def parse_pdb_extreme(pdb_content: str) -> dict:
    """The most comprehensive PDB parser ever created"""
    lines = pdb_content.split('\n')
    
    header_info = {}
    atoms = []
    residues = defaultdict(list)
    chains = set()
    secondary_structure = {}
    crystallographic_info = {}
    experimental_data = {}
    
    for line in lines:
        # Header information
        if line.startswith('HEADER'):
            header_info['title'] = line[10:50].strip()
            header_info['date'] = line[50:59].strip()
            header_info['pdb_id'] = line[62:66].strip()
            header_info['classification'] = line[10:50].strip()
        elif line.startswith('TITLE'):
            header_info.setdefault('full_title', []).append(line[10:].strip())
        elif line.startswith('COMPND'):
            header_info.setdefault('compound', []).append(line[10:].strip())
        elif line.startswith('SOURCE'):
            header_info.setdefault('source', []).append(line[10:].strip())
        elif line.startswith('KEYWDS'):
            header_info['keywords'] = line[10:].strip()
        elif line.startswith('EXPDTA'):
            experimental_data['method'] = line[10:].strip()
        elif line.startswith('REMARK   2') and 'RESOLUTION' in line:
            try:
                experimental_data['resolution'] = float(line.split()[-2])
            except ValueError:
                pass
        elif line.startswith('REMARK   3') and 'R VALUE' in line:
            try:
                experimental_data['r_factor'] = float(line.split()[-1])
            except ValueError:
                pass
        # Secondary structure
        elif line.startswith('HELIX'):
            secondary_structure.setdefault('helices', []).append({
                'id': line[11:14].strip(),
                'chain': line[19:20].strip(),
                'start': int(line[21:25].strip()),
                'end': int(line[33:37].strip())
            })
        elif line.startswith('SHEET'):
            secondary_structure.setdefault('sheets', []).append({
                'strand': line[7:10].strip(),
                'chain': line[21:22].strip(),
                'start': int(line[22:26].strip()),
                'end': int(line[33:37].strip())
            })
        # Crystallographic data
        elif line.startswith('CRYST1'):
            crystallographic_info = {
                'a': float(line[6:15].strip()),
                'b': float(line[15:24].strip()),
                'c': float(line[24:33].strip()),
                'alpha': float(line[33:40].strip()),
                'beta': float(line[40:47].strip()),
                'gamma': float(line[47:54].strip()),
                'space_group': line[55:66].strip()
            }
        # Atom information
        elif line.startswith('ATOM'):
            atom_data = {
                'serial': int(line[6:11].strip()),
                'name': line[12:16].strip(),
                'residue': line[17:20].strip(),
                'chain': line[21:22].strip(),
                'residue_num': int(line[22:26].strip()),
                'x': float(line[30:38].strip()),
                'y': float(line[38:46].strip()),
                'z': float(line[46:54].strip()),
                'occupancy': float(line[54:60].strip()) if len(line) > 54 else 1.0,
                'b_factor': float(line[60:66].strip()) if len(line) > 60 else 0.0,
                'element': line[76:78].strip() if len(line) > 76 else line[12:14].strip(),
                'charge': line[78:80].strip() if len(line) > 78 else ''
            }
            atoms.append(atom_data)
            residues[atom_data['chain']].append(atom_data)
            chains.add(atom_data['chain'])
    
    return {
        'header_info': header_info,
        'atoms': atoms,
        'residues': residues,
        'chains': chains,
        'secondary_structure': secondary_structure,
        'crystallographic_info': crystallographic_info,
        'experimental_data': experimental_data
    }
