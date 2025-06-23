# app.py
import streamlit as st
import pandas as pd
import numpy as np

from parser import parse_pdb_extreme
from aa_conversion import convert_sequence
from sequence_analysis import compute_composition, compute_property_distribution
from md_analysis import compute_rmsd, compute_radius_of_gyration, compute_rmsf, perform_pca
from distance_utils import distance_matrix
from hbond_utils import detect_hydrogen_bonds
from geometry_utils import compute_dimensions
from pocket_utils import get_pockets_data, plot_pocket_scatter, plot_pocket_heatmap
from network_analysis import build_contact_network, compute_network_metrics
from dynamic_network import simulate_network_evolution, compute_evolution_metrics
from ai_analysis import ai_recommend_experiments
from fetch_utils import fetch_pdb, fetch_pdb_metadata
from viz_3d import view_structure, isolate_chain, display_multiple_views
from palette_utils import list_palettes, apply_palette
from css_utils import set_page_style, inject_google_font

st.set_page_config(page_title="Molecular Universe Explorer", layout="wide")
inject_google_font("Roboto")

st.title("Molecular Universe Explorer")

pdb_file = st.sidebar.file_uploader("Upload PDB", type="pdb")
traj_file = st.sidebar.file_uploader("Upload trajectory (.npz)", type="npz")
palette = st.sidebar.selectbox("Color palette", list_palettes(), index=0)

tabs = st.tabs([
    "🧬 3D MOLECULAR THEATER",
    "📊 DEEP STRUCTURAL ANALYSIS",
    "🔬 SEQUENCE INTELLIGENCE",
    "🎨 CUSTOM VISUALIZATION STUDIO",
    "📈 INTERACTIVE SCIENTIFIC PLOTS",
    "🤖 AI MOLECULAR INSIGHTS",
    "⚡ MOLECULAR DYNAMICS",
    "💊 DRUG DISCOVERY SUITE",
    "🌌 NETWORK ANALYSIS"
])

if pdb_file:
    pdb_text = pdb_file.read().decode("utf-8")
    parsed = parse_pdb_extreme(pdb_text)
    chains = sorted(parsed["chains"])

    with tabs[0]:
        st.header("🧬 3D MOLECULAR THEATER")
        v = view_structure(pdb_text, style="cartoon", color=palette)
        st.components.v1.html(v.show(), height=600)
        if chains:
            cols = st.columns(len(chains))
            views = display_multiple_views(pdb_text, chains, style="cartoon", color=palette)
            for col, view in zip(cols, views):

                import streamlit.components.v1 as components  # make sure this is at the top

                col.write("")  # optional spacer
                components.html(view.show(), height=400)


    with tabs[1]:
        st.header("📊 DEEP STRUCTURAL ANALYSIS")
        st.json(parsed["header_info"])
        df_cryst = pd.DataFrame([parsed["crystallographic_info"]])
        st.dataframe(df_cryst)
        st.write("Experimental:", parsed["experimental_data"])

    with tabs[2]:
        st.header("🔬 SEQUENCE INTELLIGENCE")
        seq3 = [a["residue"] for a in parsed["atoms"] if a["chain"] == chains[0]]
        seq1 = convert_sequence(seq3)
        st.text(seq1)
        comp_df = compute_composition(seq1)
        prop_df = compute_property_distribution(seq1)
        st.dataframe(comp_df)
        st.dataframe(prop_df)

    with tabs[3]:
        st.header("🎨 CUSTOM VISUALIZATION STUDIO")
        df_pockets = get_pockets_data(parsed)
        fig1 = plot_pocket_scatter(df_pockets)
        apply_palette(fig1, palette)
        st.plotly_chart(fig1, use_container_width=True)
        fig2 = plot_pocket_heatmap(df_pockets)
        apply_palette(fig2, palette)
        st.plotly_chart(fig2, use_container_width=True)

    with tabs[4]:
        st.header("📈 INTERACTIVE SCIENTIFIC PLOTS")
        rmsf_vals = np.array(parsed["experimental_data"].get("rmsf", []))
        if traj_file:
            coords = np.load(traj_file)["coords"]
            dm = distance_matrix(coords[0])
            st.write("Distance matrix shape:", dm.shape)
            hbonds = detect_hydrogen_bonds(coords[0], coords[0], coords[0])
            st.write("Example H-bonds:", hbonds)

    with tabs[5]:
        st.header("🤖 AI MOLECULAR INSIGHTS")
        md_metrics = {}
        if traj_file:
            data = np.load(traj_file)
            md_metrics = {"rmsf": compute_rmsf(data["coords"])}
        suggestions = ai_recommend_experiments(parsed, md_metrics, seq1)
        for s in suggestions:
            st.info(s)

    with tabs[6]:
        st.header("⚡ MOLECULAR DYNAMICS")
        if traj_file:
            coords = np.load(traj_file)["coords"]
            rmsd = compute_rmsd(coords[0], coords)
            rg = compute_radius_of_gyration(coords)
            st.line_chart({"RMSD": rmsd, "Rg": rg})

    with tabs[7]:
        st.header("💊 DRUG DISCOVERY SUITE")
        # placeholder for screening UI

    with tabs[8]:
        st.header("🌌 NETWORK ANALYSIS")
        residue_coords = {f"{c}{i}": (0,0,0) for c in chains for i in range(1,6)}  # example
        G = build_contact_network(residue_coords, threshold=5.0)
        metrics = compute_network_metrics(G)
        st.json(metrics)
