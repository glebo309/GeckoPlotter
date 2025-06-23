import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from sklearn.preprocessing import MinMaxScaler


def get_pockets_data(parsed_pdb: dict) -> pd.DataFrame:
    """
    Identify and return binding pocket metrics as a DataFrame.

    Currently simulates pocket identification as per single-file version.

    Columns: ['pocket_id', 'volume', 'hydrophobicity', 'druggability', 'type']
    """
    pockets = [
        {"pocket_id": "P1", "volume": 856.3, "hydrophobicity": 0.65, "druggability": 0.92, "type": "Active Site"},
        {"pocket_id": "P2", "volume": 432.7, "hydrophobicity": 0.45, "druggability": 0.78, "type": "Allosteric"},
        {"pocket_id": "P3", "volume": 298.1, "hydrophobicity": 0.72, "druggability": 0.84, "type": "Allosteric"},
        {"pocket_id": "P4", "volume": 156.9, "hydrophobicity": 0.38, "druggability": 0.56, "type": "Cryptic"}
    ]
    return pd.DataFrame(pockets)


def plot_pocket_scatter(pockets_df: pd.DataFrame) -> go.Figure:
    """
    Scatter plot of pocket volume vs druggability, colored by type.
    """
    fig = px.scatter(
        pockets_df,
        x='volume',
        y='druggability',
        color='type',
        text='pocket_id',
        title='Binding Pocket Druggability Analysis',
        labels={'volume': 'Pocket Volume (Å³)', 'druggability': 'Druggability Score'}
    )
    fig.update_traces(textposition='top center')
    return fig


def plot_pocket_heatmap(pockets_df: pd.DataFrame) -> go.Figure:
    """
    Heatmap of normalized pocket properties (volume, hydrophobicity, druggability).
    """
    props = pockets_df[['volume', 'hydrophobicity', 'druggability']]
    scaler = MinMaxScaler()
    norm = scaler.fit_transform(props)
    fig = go.Figure(
        go.Heatmap(
            z=norm,
            x=props.columns,
            y=pockets_df['pocket_id'],
            text=np.round(props.values, 3),
            texttemplate='%{text}'
        )
    )
    fig.update_layout(
        title='Pocket Properties Heatmap',
        xaxis_title='Property',
        yaxis_title='Pocket ID',
        height=400
    )
    return fig














