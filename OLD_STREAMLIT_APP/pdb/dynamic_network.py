import networkx as nx
import numpy as np


def simulate_network_evolution(G_initial: nx.Graph,
                               perturbations: list[dict],
                               steps: int = 10) -> list[nx.Graph]:
    """
    Simulate network evolution by applying perturbations over discrete time steps.

    Parameters:
    - G_initial: starting networkx graph
    - perturbations: list of dicts describing changes, e.g. {'add_edges': [(u,v)], 'remove_nodes': [n]}
    - steps: number of evolution steps to simulate

    Returns:
    - List of Graph snapshots at each step (including initial)
    """
    snapshots = [G_initial.copy()]
    G = G_initial.copy()
    for i in range(min(steps, len(perturbations))):
        p = perturbations[i]
        if 'add_edges' in p:
            G.add_edges_from(p['add_edges'])
        if 'remove_edges' in p:
            G.remove_edges_from(p['remove_edges'])
        if 'add_nodes' in p:
            G.add_nodes_from(p['add_nodes'])
        if 'remove_nodes' in p:
            G.remove_nodes_from(p['remove_nodes'])
        snapshots.append(G.copy())
    return snapshots


def compute_evolution_metrics(snapshots: list[nx.Graph]) -> dict:
    """
    Compute time series of network metrics over evolution snapshots.

    Returns a dict containing lists of metrics: density, clustering, components.
    """
    densities = []
    clusterings = []
    components = []
    for G in snapshots:
        densities.append(nx.density(G))
        clusterings.append(nx.average_clustering(G))
        components.append(nx.number_connected_components(G))
    return {
        'density': np.array(densities),
        'avg_clustering': np.array(clusterings),
        'n_components': np.array(components)
    }
