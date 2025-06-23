import numpy as np
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots


def plot_rmsd_rg(time_ns: np.ndarray, rmsd: np.ndarray, rg: np.ndarray) -> go.Figure:
    """Plot RMSD and Radius of Gyration over time."""
    fig = make_subplots(rows=2, cols=1,
                        subplot_titles=['RMSD Over Time', 'Radius of Gyration Over Time'],
                        vertical_spacing=0.15)
    fig.add_trace(go.Scatter(x=time_ns, y=rmsd, mode='lines', name='RMSD'), row=1, col=1)
    fig.add_trace(go.Scatter(x=time_ns, y=rg, mode='lines', name='Rg'), row=2, col=1)
    fig.update_xaxes(title_text='Time (ns)', row=2, col=1)
    fig.update_yaxes(title_text='RMSD (Å)', row=1, col=1)
    fig.update_yaxes(title_text='Rg (Å)', row=2, col=1)
    fig.update_layout(height=600, showlegend=False)
    return fig


def plot_rmsf(res_nums: np.ndarray, rmsf_vals: np.ndarray) -> go.Figure:
    """Plot per-residue RMSF values."""
    fig = go.Figure()
    colors = ['red' if v>2.0 else 'orange' if v>1.0 else 'blue' for v in rmsf_vals]
    fig.add_trace(go.Scatter(x=res_nums, y=rmsf_vals, mode='lines+markers', marker=dict(color=colors, size=4)))
    fig.add_hline(y=1.0, line_dash='dash', annotation_text='Medium')
    fig.add_hline(y=2.0, line_dash='dash', annotation_text='High')
    fig.update_layout(title='Per-Residue RMSF', xaxis_title='Residue', yaxis_title='RMSF (Å)', height=400)
    return fig


def plot_rmsf_distribution(rmsf_vals: np.ndarray) -> go.Figure:
    """Plot histogram of RMSF distribution."""
    fig = go.Figure(go.Histogram(x=rmsf_vals, nbinsx=30, name='RMSF Dist'))
    fig.add_vline(x=np.mean(rmsf_vals), line_dash='dash', annotation_text='Mean')
    fig.update_layout(title='RMSF Distribution', xaxis_title='RMSF', yaxis_title='Frequency', height=400)
    return fig


def plot_free_energy(rmsd: np.ndarray, rg: np.ndarray, bins: int=20) -> go.Figure:
    """Plot free energy landscape (RMSD vs Rg)."""
    rmsd_bins = np.linspace(rmsd.min(), rmsd.max(), bins)
    rg_bins = np.linspace(rg.min(), rg.max(), bins)
    H, xedges, yedges = np.histogram2d(rmsd, rg, bins=[rmsd_bins, rg_bins])
    H[H==0] = 1
    fe = -np.log(H)
    fe -= fe.min()
    return go.Figure(data=go.Contour(z=fe.T, x=rmsd_bins[:-1], y=rg_bins[:-1], colorscale='viridis'))


def plot_kmeans(coords: np.ndarray, labels: np.ndarray, centers: np.ndarray) -> go.Figure:
    """3D scatter of KMeans clusters with centers."""
    fig = go.Figure()
    unique = np.unique(labels)
    for u in unique:
        mask = labels==u
        fig.add_trace(go.Scatter3d(x=coords[mask,0], y=coords[mask,1], z=coords[mask,2], mode='markers', name=f'Cluster {u}'))
    fig.add_trace(go.Scatter3d(x=centers[:,0], y=centers[:,1], z=centers[:,2], mode='markers', marker=dict(symbol='diamond', size=8), name='Centers'))
    fig.update_layout(scene=dict(xaxis_title='X',yaxis_title='Y',zaxis_title='Z'), title='KMeans Clustering')
    return fig


def plot_dbscan(coords: np.ndarray, labels: np.ndarray) -> go.Figure:
    """3D scatter of DBSCAN clustering."""
    fig = go.Figure()
    for label in np.unique(labels):
        mask = labels==label
        name = 'Noise' if label==-1 else f'Cluster {label}'
        fig.add_trace(go.Scatter3d(x=coords[mask,0], y=coords[mask,1], z=coords[mask,2], mode='markers', name=name))
    fig.update_layout(scene=dict(xaxis_title='X',yaxis_title='Y',zaxis_title='Z'), title='DBSCAN Clustering')
    return fig


def plot_pca_3d(coords: np.ndarray, variance: np.ndarray) -> go.Figure:
    """3D PCA projection colored by PC3."""
    fig = go.Figure(go.Scatter3d(x=coords[:,0], y=coords[:,1], z=coords[:,2], mode='markers', marker=dict(color=coords[:,2], colorscale='Viridis'))) 
    fig.update_layout(scene=dict(
        xaxis_title=f'PC1 ({variance[0]:.1%})',
        yaxis_title=f'PC2 ({variance[1]:.1%})',
        zaxis_title=f'PC3 ({variance[2]:.1%})'
    ), title='3D PCA')
    return fig


def plot_pca_2d(coords: np.ndarray) -> go.Figure:
    """2D PCA pairwise scatter subplots."""
    fig = make_subplots(rows=1, cols=3, subplot_titles=['PC1 vs PC2','PC1 vs PC3','PC2 vs PC3'])
    fig.add_trace(go.Scatter(x=coords[:,0], y=coords[:,1], mode='markers'), row=1, col=1)
    fig.add_trace(go.Scatter(x=coords[:,0], y=coords[:,2], mode='markers'), row=1, col=2)
    fig.add_trace(go.Scatter(x=coords[:,1], y=coords[:,2], mode='markers'), row=1, col=3)
    fig.update_layout(title='2D PCA Projections')
    return fig


def plot_ramachandran(phi: list, psi: list, ss_types: list) -> go.Figure:
    """Ramachandran scatter with SS coloring."""
    fig = go.Figure()
    colors = {'α-helix':'blue','β-sheet':'green','Random coil':'red','Left-handed':'orange'}
    for ss in set(ss_types):
        idx = [i for i,s in enumerate(ss_types) if s==ss]
        fig.add_trace(go.Scatter(x=[phi[i] for i in idx], y=[psi[i] for i in idx], mode='markers', name=ss, marker=dict(color=colors.get(ss,'gray'))))
    fig.update_layout(xaxis=dict(range=[-180,180],dtick=60), yaxis=dict(range=[-180,180],dtick=60), title='Ramachandran Plot')
    return fig


def plot_ramachandran_density(phi: list, psi: list) -> go.Figure:
    """Density contour Ramachandran."""
    from scipy.stats import gaussian_kde
    data = np.vstack([phi,psi])
    kde = gaussian_kde(data)
    grid_phi = np.linspace(-180,180,50)
    grid_psi = np.linspace(-180,180,50)
    mesh_phi, mesh_psi = np.meshgrid(grid_phi,grid_psi)
    density = kde(np.vstack([mesh_phi.ravel(), mesh_psi.ravel()])).reshape(mesh_phi.shape)
    return go.Figure(go.Contour(z=density, x=grid_phi, y=grid_psi))


def plot_compound_screening(df: pd.DataFrame) -> go.Figure:
    """Scatter of compounds by docking vs admet, size by novelty."""
    fig = go.Figure(go.Scatter(x=df['docking_score'], y=df['admet_score'], mode='markers+text', text=df['compound_id'], marker=dict(size=df['novelty']*30, color=df['lipinski_violations'], colorscale='RdYlGn_r', showscale=True)))
    fig.update_layout(xaxis_title='Docking Score', yaxis_title='ADMET', title='Virtual Screening')
    return fig


def plot_similarity_matrix(mat: np.ndarray, labels: list) -> go.Figure:
    """Heatmap of sequence similarity."""
    fig = go.Figure(go.Heatmap(z=mat, x=labels, y=labels, text=np.round(mat,3), texttemplate='%{text}'))
    fig.update_layout(title='Sequence Similarity')
    return fig
