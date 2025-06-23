import numpy as np
import networkx as nx
from typing import List, Dict, Tuple, Any


def build_contact_network(residue_coords: Dict[str, Tuple[float, float, float]], threshold: float) -> nx.Graph:
    """
    Construct a residue contact network based on a distance threshold.

    Parameters:
    - residue_coords: dict mapping residue identifier to (x, y, z) coordinates
    - threshold: maximum distance (Å) for creating an edge

    Returns:
    - G: networkx.Graph with nodes=residue IDs and weighted edges (1/distance)
    """
    G = nx.Graph()
    # Add nodes
    for res_id in residue_coords:
        G.add_node(res_id)
    # Precompute pairs
    ids = list(residue_coords.keys())
    coords = np.array([residue_coords[r] for r in ids])
    # Compute pairwise distances
    diff = coords[:, None, :] - coords[None, :, :]
    dmat = np.linalg.norm(diff, axis=-1)
    n = len(ids)
    for i in range(n):
        for j in range(i+1, n):
            dist = dmat[i, j]
            if dist <= threshold:
                G.add_edge(ids[i], ids[j], weight=1.0/dist)
    return G


def compute_network_metrics(G: nx.Graph) -> Dict[str, Any]:
    """
    Compute basic network metrics.

    Returns a dict with:
    - nodes, edges, density, average_clustering, connected_components
    """
    metrics = {
        'nodes': G.number_of_nodes(),
        'edges': G.number_of_edges(),
        'density': nx.density(G),
        'average_clustering': nx.average_clustering(G),
        'connected_components': nx.number_connected_components(G)
    }
    return metrics


def degree_distribution(G: nx.Graph) -> List[int]:
    """
    Return the list of node degrees for the network.
    """
    return [deg for _, deg in G.degree()]


def compute_centrality_measures(G: nx.Graph) -> Dict[str, Dict[Any, float]]:
    """
    Compute degree, betweenness, and closeness centralities.

    Returns a dict with keys 'degree', 'betweenness', 'closeness'.
    """
    centralities = {
        'degree': nx.degree_centrality(G),
        'betweenness': nx.betweenness_centrality(G)
    }
    if nx.is_connected(G):
        centralities['closeness'] = nx.closeness_centrality(G)
    return centralities


def detect_communities(G: nx.Graph) -> Tuple[List[set], float]:
    """
    Detect communities using greedy modularity and compute modularity score.

    Returns:
    - communities: list of sets of node IDs
    - modularity: float
    """
    communities = list(nx.community.greedy_modularity_communities(G))
    modularity_score = nx.community.modularity(G, communities)
    return communities, modularity_score


def inter_community_matrix(G: nx.Graph, communities: List[set]) -> np.ndarray:
    """
    Build a matrix of inter-community edge counts.

    Parameters:
    - G: graph
    - communities: list of sets of node IDs

    Returns:
    - matrix: np.ndarray of shape (k, k) where k=len(communities)
    """
    k = len(communities)
    mat = np.zeros((k, k), dtype=int)
    # map node to community index
    node_comm = {node: i for i, comm in enumerate(communities) for node in comm}
    for u, v in G.edges():
        ci = node_comm.get(u)
        cj = node_comm.get(v)
        if ci is not None and cj is not None and ci != cj:
            mat[ci, cj] += 1
            mat[cj, ci] += 1
    return mat


def compute_shortest_path_stats(G: nx.Graph, samples: List[Any] = None) -> Dict[str, Any]:
    """
    Compute diameter and sample shortest-path distribution.

    Parameters:
    - G: graph
    - samples: optional list of node IDs to sample for path lengths

    Returns:
    - dict with 'diameter', 'max_paths', 'path_length_distribution'
    """
    result: Dict[str, Any] = {}
    if nx.is_connected(G):
        diam = nx.diameter(G)
        result['diameter'] = diam
        # find all pairs with max distance
        max_paths = []
        for u in G.nodes():
            for v in G.nodes():
                if u != v:
                    try:
                        path = nx.shortest_path(G, u, v)
                        if len(path)-1 == diam:
                            max_paths.append(path)
                    except nx.NetworkXNoPath:
                        pass
        result['max_paths'] = max_paths
    # path lengths distribution
    if samples is None:
        nodes = list(G.nodes())[:20]
    else:
        nodes = samples
    lengths = []
    for i, u in enumerate(nodes):
        for v in nodes[i+1:]:
            try:
                lengths.append(nx.shortest_path_length(G, u, v))
            except nx.NetworkXNoPath:
                pass
    result['path_length_distribution'] = lengths
    return result
