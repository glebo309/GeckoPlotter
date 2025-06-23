import os
import requests
from typing import Dict, Any


def fetch_pdb(pdb_id: str, save_dir: str = './pdb') -> str:
    """
    Download a PDB file by its ID from RCSB and save it locally.

    Parameters:
    - pdb_id: 4-character PDB accession (e.g. '1CRN')
    - save_dir: directory to save PDB files

    Returns:
    - Path to the saved PDB file
    """
    pdb_id = pdb_id.strip().upper()
    url = f'https://files.rcsb.org/download/{pdb_id}.pdb'
    response = requests.get(url)
    if response.status_code != 200:
        raise ValueError(f'Failed to download PDB {pdb_id}: HTTP {response.status_code}')
    os.makedirs(save_dir, exist_ok=True)
    path = os.path.join(save_dir, f'{pdb_id}.pdb')
    with open(path, 'w') as f:
        f.write(response.text)
    return path


def fetch_pdb_metadata(pdb_id: str) -> Dict[str, Any]:
    """
    Retrieve PDB entry metadata from RCSB REST API.

    Parameters:
    - pdb_id: 4-character PDB accession

    Returns:
    - JSON dict of metadata
    """
    pdb_id = pdb_id.strip().upper()
    url = f'https://data.rcsb.org/rest/v1/core/entry/{pdb_id}'
    response = requests.get(url)
    if response.status_code != 200:
        raise ValueError(f'Failed to fetch metadata for {pdb_id}: HTTP {response.status_code}')
    return response.json()
