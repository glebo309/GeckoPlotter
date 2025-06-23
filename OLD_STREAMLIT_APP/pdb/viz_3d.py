import py3Dmol
from typing import List, Optional


def view_structure(pdb_content: str,
                   selection: Optional[str] = 'all',
                   style: str = 'cartoon',
                   color: str = 'spectrum',
                   surface: bool = False,
                   surface_opacity: float = 0.8,
                   width: int = 800,
                   height: int = 600) -> py3Dmol.view:
    """
    Render a 3D view of a PDB structure using py3Dmol.

    Parameters:
    - pdb_content: raw PDB text
    - selection: atom selection (e.g. 'chain A', 'resn ASP', or 'all')
    - style: rendering style ('cartoon', 'stick', 'sphere', etc.)
    - color: coloring scheme (e.g. 'spectrum', 'chain', or any valid color)
    - surface: whether to show molecular surface
    - surface_opacity: opacity of the surface (0-1)
    - width, height: viewer dimensions in pixels

    Returns:
    - py3Dmol.view object
    """
    view = py3Dmol.view(width=width, height=height)
    view.addModel(pdb_content, 'pdb')
    view.setStyle({selection: {style: {}}}, {})
    view.setColorByProperty({'spectrum': {}}, {}) if color == 'spectrum' else view.setStyle({selection: {style: {'color': color}}}, {})
    if surface:
        view.addSurface(py3Dmol.VDW, {'opacity': surface_opacity, 'color': color}, {selection: {}})
    view.zoomTo({selection: {}})
    return view


def isolate_chain(pdb_content: str,
                  chain_id: str,
                  **kwargs) -> py3Dmol.view:
    """
    Render only the specified chain from a PDB structure.
    """
    selection = f'chain {chain_id}'
    return view_structure(pdb_content, selection=selection, **kwargs)


def highlight_residues(pdb_content: str,
                       residues: List[int],
                       chain: str = '',
                       color: str = 'red',
                       style: str = 'stick',
                       **kwargs) -> py3Dmol.view:
    """
    Highlight specific residues in the structure.
    """
    sel = {'chain': chain} if chain else {}
    for res in residues:
        sel.update({'resi': res})
        view = py3Dmol.view(width=kwargs.get('width',800), height=kwargs.get('height',600))
        view.addModel(pdb_content, 'pdb')
        view.setStyle(sel, {style: {'color': color}})
    view.zoomTo()
    return view


def display_multiple_views(pdb_content: str,
                           chain_ids: List[str],
                           cols: int = 2,
                           **kwargs) -> List[py3Dmol.view]:
    """
    Generate multiple synchronized views, one per chain.

    Returns a list of py3Dmol.view objects.
    """
    views = []
    for chain in chain_ids:
        v = isolate_chain(pdb_content, chain, **kwargs)
        views.append(v)
    return views

# Usage in Streamlit:
# import streamlit as st
# from viz_3d import view_structure
# 
# pdb_text = st.text_area('PDB')
# st.components.v1.html(view_structure(pdb_text).show(), height=650)
