import os

import pickle
import tempfile
import unittest

import backend as F

import dgl
import dgl.graphbolt as gb
import gb_test_utils as gbt
import pytest
import torch
import torch.multiprocessing as mp
from scipy import sparse as spsp

torch.manual_seed(3407)
mp.set_sharing_strategy("file_system")


@unittest.skipIf(
    F._default_context_str == "gpu",
    reason="Graph is CPU only at present.",
)
@pytest.mark.parametrize("num_nodes", [0, 1, 10, 100, 1000])
def test_empty_graph(num_nodes):
    csc_indptr = torch.zeros((num_nodes + 1,), dtype=int)
    indices = torch.tensor([])
    graph = gb.from_csc(csc_indptr, indices)
    assert graph.num_edges == 0
    assert graph.num_nodes == num_nodes
    assert torch.equal(graph.csc_indptr, csc_indptr)
    assert torch.equal(graph.indices, indices)


@unittest.skipIf(
    F._default_context_str == "gpu",
    reason="Graph is CPU only at present.",
)
@pytest.mark.parametrize("num_nodes", [0, 1, 10, 100, 1000])
def test_hetero_empty_graph(num_nodes):
    csc_indptr = torch.zeros((num_nodes + 1,), dtype=int)
    indices = torch.tensor([])
    metadata = gbt.get_metadata(num_ntypes=3, num_etypes=5)
    # Some node types have no nodes.
    if num_nodes == 0:
        node_type_offset = torch.zeros((4,), dtype=int)
    else:
        node_type_offset = torch.sort(torch.randint(0, num_nodes, (4,)))[0]
        node_type_offset[0] = 0
        node_type_offset[-1] = num_nodes
    type_per_edge = torch.tensor([])
    graph = gb.from_csc(
        csc_indptr,
        indices,
        node_type_offset,
        type_per_edge,
        None,
        metadata,
    )
    assert graph.num_edges == 0
    assert graph.num_nodes == num_nodes
    assert torch.equal(graph.csc_indptr, csc_indptr)
    assert torch.equal(graph.indices, indices)
    assert graph.metadata.node_type_to_id == metadata.node_type_to_id
    assert graph.metadata.edge_type_to_id == metadata.edge_type_to_id
    assert torch.equal(graph.node_type_offset, node_type_offset)
    assert torch.equal(graph.type_per_edge, type_per_edge)


@unittest.skipIf(
    F._default_context_str == "gpu",
    reason="Graph is CPU only at present.",
)
@pytest.mark.parametrize(
    "ntypes", [{"n1": 1, "n2": 1}, {5: 1, "n2": 2}, {"n1": 1.5, "n2": 2.0}]
)
def test_metadata_with_ntype_exception(ntypes):
    with pytest.raises(Exception):
        gb.GraphMetadata(ntypes, {"n1:e1:n2": 1})


@unittest.skipIf(
    F._default_context_str == "gpu",
    reason="Graph is CPU only at present.",
)
@pytest.mark.parametrize(
    "etypes",
    [
        {("n1", 5, "n12"): 1},
        {"e1": 1},
        {("n1", "e1"): 1},
        {("n1", "e1", 10): 1},
        {"n1:e1:n2": 1, ("n1", "e2", "n3"): 1},
        {("n1", "e1", "n10"): 1},
        {"n1:e1:n2": 1.5},
    ],
)
def test_metadata_with_etype_exception(etypes):
    with pytest.raises(Exception):
        gb.GraphMetadata({"n1": 0, "n2": 1, "n3": 2}, etypes)


@unittest.skipIf(
    F._default_context_str == "gpu",
    reason="Graph is CPU only at present.",
)
@pytest.mark.parametrize(
    "num_nodes, num_edges", [(1, 1), (100, 1), (10, 50), (1000, 50000)]
)
def test_homo_graph(num_nodes, num_edges):
    csc_indptr, indices = gbt.random_homo_graph(num_nodes, num_edges)
    edge_attributes = {
        "A1": torch.randn(num_edges),
        "A2": torch.randn(num_edges),
    }
    graph = gb.from_csc(csc_indptr, indices, edge_attributes=edge_attributes)

    assert graph.num_nodes == num_nodes
    assert graph.num_edges == num_edges

    assert torch.equal(csc_indptr, graph.csc_indptr)
    assert torch.equal(indices, graph.indices)

    assert graph.edge_attributes == edge_attributes
    assert graph.metadata is None
    assert graph.node_type_offset is None
    assert graph.type_per_edge is None


@unittest.skipIf(
    F._default_context_str == "gpu",
    reason="Graph is CPU only at present.",
)
@pytest.mark.parametrize(
    "num_nodes, num_edges", [(1, 1), (100, 1), (10, 50), (1000, 50000)]
)
@pytest.mark.parametrize("num_ntypes, num_etypes", [(1, 1), (3, 5), (100, 1)])
def test_hetero_graph(num_nodes, num_edges, num_ntypes, num_etypes):
    (
        csc_indptr,
        indices,
        node_type_offset,
        type_per_edge,
        metadata,
    ) = gbt.random_hetero_graph(num_nodes, num_edges, num_ntypes, num_etypes)
    edge_attributes = {
        "A1": torch.randn(num_edges),
        "A2": torch.randn(num_edges),
    }
    graph = gb.from_csc(
        csc_indptr,
        indices,
        node_type_offset,
        type_per_edge,
        edge_attributes,
        metadata,
    )

    assert graph.num_nodes == num_nodes
    assert graph.num_edges == num_edges

    assert torch.equal(csc_indptr, graph.csc_indptr)
    assert torch.equal(indices, graph.indices)
    assert torch.equal(node_type_offset, graph.node_type_offset)
    assert torch.equal(type_per_edge, graph.type_per_edge)
    assert graph.edge_attributes == edge_attributes
    assert metadata.node_type_to_id == graph.metadata.node_type_to_id
    assert metadata.edge_type_to_id == graph.metadata.edge_type_to_id


@unittest.skipIf(
    F._default_context_str == "gpu",
    reason="Graph is CPU only at present.",
)
@pytest.mark.parametrize(
    "node_type_offset",
    [
        torch.tensor([0, 1]),
        torch.tensor([0, 1, 5, 6, 10]),
        torch.tensor([0, 1, 10]),
    ],
)
def test_node_type_offset_wrong_legnth(node_type_offset):
    num_ntypes = 3
    csc_indptr, indices, _, type_per_edge, metadata = gbt.random_hetero_graph(
        10, 50, num_ntypes, 5
    )
    with pytest.raises(Exception):
        gb.from_csc(
            csc_indptr, indices, node_type_offset, type_per_edge, None, metadata
        )


@unittest.skipIf(
    F._default_context_str == "gpu",
    reason="Graph is CPU only at present.",
)
@pytest.mark.parametrize(
    "num_nodes, num_edges", [(1, 1), (100, 1), (10, 50), (1000, 50000)]
)
def test_load_save_homo_graph(num_nodes, num_edges):
    csc_indptr, indices = gbt.random_homo_graph(num_nodes, num_edges)
    graph = gb.from_csc(csc_indptr, indices)

    with tempfile.TemporaryDirectory() as test_dir:
        filename = os.path.join(test_dir, "csc_sampling_graph.tar")
        gb.save_csc_sampling_graph(graph, filename)
        graph2 = gb.load_csc_sampling_graph(filename)

    assert graph.num_nodes == graph2.num_nodes
    assert graph.num_edges == graph2.num_edges

    assert torch.equal(graph.csc_indptr, graph2.csc_indptr)
    assert torch.equal(graph.indices, graph2.indices)

    assert graph.metadata is None and graph2.metadata is None
    assert graph.node_type_offset is None and graph2.node_type_offset is None
    assert graph.type_per_edge is None and graph2.type_per_edge is None


@unittest.skipIf(
    F._default_context_str == "gpu",
    reason="Graph is CPU only at present.",
)
@pytest.mark.parametrize(
    "num_nodes, num_edges", [(1, 1), (100, 1), (10, 50), (1000, 50000)]
)
@pytest.mark.parametrize("num_ntypes, num_etypes", [(1, 1), (3, 5), (100, 1)])
def test_load_save_hetero_graph(num_nodes, num_edges, num_ntypes, num_etypes):
    (
        csc_indptr,
        indices,
        node_type_offset,
        type_per_edge,
        metadata,
    ) = gbt.random_hetero_graph(num_nodes, num_edges, num_ntypes, num_etypes)
    graph = gb.from_csc(
        csc_indptr, indices, node_type_offset, type_per_edge, None, metadata
    )

    with tempfile.TemporaryDirectory() as test_dir:
        filename = os.path.join(test_dir, "csc_sampling_graph.tar")
        gb.save_csc_sampling_graph(graph, filename)
        graph2 = gb.load_csc_sampling_graph(filename)

    assert graph.num_nodes == graph2.num_nodes
    assert graph.num_edges == graph2.num_edges

    assert torch.equal(graph.csc_indptr, graph2.csc_indptr)
    assert torch.equal(graph.indices, graph2.indices)
    assert torch.equal(graph.node_type_offset, graph2.node_type_offset)
    assert torch.equal(graph.type_per_edge, graph2.type_per_edge)
    assert graph.metadata.node_type_to_id == graph2.metadata.node_type_to_id
    assert graph.metadata.edge_type_to_id == graph2.metadata.edge_type_to_id


@unittest.skipIf(
    F._default_context_str == "gpu",
    reason="Graph is CPU only at present.",
)
@pytest.mark.parametrize(
    "num_nodes, num_edges", [(1, 1), (100, 1), (10, 50), (1000, 50000)]
)
def test_pickle_homo_graph(num_nodes, num_edges):
    csc_indptr, indices = gbt.random_homo_graph(num_nodes, num_edges)
    graph = gb.from_csc(csc_indptr, indices)

    serialized = pickle.dumps(graph)
    graph2 = pickle.loads(serialized)

    assert graph.num_nodes == graph2.num_nodes
    assert graph.num_edges == graph2.num_edges

    assert torch.equal(graph.csc_indptr, graph2.csc_indptr)
    assert torch.equal(graph.indices, graph2.indices)

    assert graph.metadata is None and graph2.metadata is None
    assert graph.node_type_offset is None and graph2.node_type_offset is None
    assert graph.type_per_edge is None and graph2.type_per_edge is None


@unittest.skipIf(
    F._default_context_str == "gpu",
    reason="Graph is CPU only at present.",
)
@pytest.mark.parametrize(
    "num_nodes, num_edges", [(1, 1), (100, 1), (10, 50), (1000, 50000)]
)
@pytest.mark.parametrize("num_ntypes, num_etypes", [(1, 1), (3, 5), (100, 1)])
def test_pickle_hetero_graph(num_nodes, num_edges, num_ntypes, num_etypes):
    (
        csc_indptr,
        indices,
        node_type_offset,
        type_per_edge,
        metadata,
    ) = gbt.random_hetero_graph(num_nodes, num_edges, num_ntypes, num_etypes)
    edge_attributes = {
        "a": torch.randn((num_edges,)),
        "b": torch.randint(1, 10, (num_edges,)),
    }
    graph = gb.from_csc(
        csc_indptr,
        indices,
        node_type_offset,
        type_per_edge,
        edge_attributes,
        metadata,
    )

    serialized = pickle.dumps(graph)
    graph2 = pickle.loads(serialized)

    assert graph.num_nodes == graph2.num_nodes
    assert graph.num_edges == graph2.num_edges

    assert torch.equal(graph.csc_indptr, graph2.csc_indptr)
    assert torch.equal(graph.indices, graph2.indices)
    assert torch.equal(graph.node_type_offset, graph2.node_type_offset)
    assert torch.equal(graph.type_per_edge, graph2.type_per_edge)
    assert graph.metadata.node_type_to_id == graph2.metadata.node_type_to_id
    assert graph.metadata.edge_type_to_id == graph2.metadata.edge_type_to_id
    assert graph.edge_attributes.keys() == graph2.edge_attributes.keys()
    for i in graph.edge_attributes.keys():
        assert torch.equal(graph.edge_attributes[i], graph2.edge_attributes[i])


def process_csc_sampling_graph_multiprocessing(graph):
    return graph.num_nodes


@unittest.skipIf(
    F._default_context_str == "gpu",
    reason="Graph is CPU only at present.",
)
def test_multiprocessing():
    num_nodes = 5
    num_edges = 10
    num_ntypes = 2
    num_etypes = 3
    (
        csc_indptr,
        indices,
        node_type_offset,
        type_per_edge,
        metadata,
    ) = gbt.random_hetero_graph(num_nodes, num_edges, num_ntypes, num_etypes)
    edge_attributes = {
        "a": torch.randn((num_edges,)),
    }
    graph = gb.from_csc(
        csc_indptr,
        indices,
        node_type_offset,
        type_per_edge,
        edge_attributes,
        metadata,
    )

    p = mp.Process(
        target=process_csc_sampling_graph_multiprocessing, args=(graph,)
    )
    p.start()
    p.join()


@unittest.skipIf(
    F._default_context_str == "gpu",
    reason="Graph is CPU only at present.",
)
def test_in_subgraph_homogeneous():
    """Original graph in COO:
    1   0   1   0   1
    1   0   1   1   0
    0   1   0   1   0
    0   1   0   0   1
    1   0   0   0   1
    """
    # Initialize data.
    num_nodes = 5
    num_edges = 12
    indptr = torch.LongTensor([0, 3, 5, 7, 9, 12])
    indices = torch.LongTensor([0, 1, 4, 2, 3, 0, 1, 1, 2, 0, 3, 4])
    assert indptr[-1] == num_edges
    assert indptr[-1] == len(indices)

    # Construct CSCSamplingGraph.
    graph = gb.from_csc(indptr, indices)

    # Extract in subgraph.
    nodes = torch.LongTensor([1, 3, 4])
    in_subgraph = graph.in_subgraph(nodes)

    # Verify in subgraph.
    assert torch.equal(in_subgraph.indptr, torch.LongTensor([0, 2, 4, 7]))
    assert torch.equal(
        in_subgraph.indices, torch.LongTensor([2, 3, 1, 2, 0, 3, 4])
    )
    assert torch.equal(in_subgraph.reverse_column_node_ids, nodes)
    assert torch.equal(
        in_subgraph.reverse_row_node_ids, torch.arange(0, num_nodes)
    )
    assert torch.equal(
        in_subgraph.reverse_edge_ids, torch.LongTensor([3, 4, 7, 8, 9, 10, 11])
    )
    assert in_subgraph.type_per_edge is None


@unittest.skipIf(
    F._default_context_str == "gpu",
    reason="Graph is CPU only at present.",
)
def test_in_subgraph_heterogeneous():
    """Original graph in COO:
    1   0   1   0   1
    1   0   1   1   0
    0   1   0   1   0
    0   1   0   0   1
    1   0   0   0   1

    node_type_0: [0, 1]
    node_type_1: [2, 3, 4]
    edge_type_0: node_type_0 -> node_type_0
    edge_type_1: node_type_0 -> node_type_1
    edge_type_2: node_type_1 -> node_type_0
    edge_type_3: node_type_1 -> node_type_1
    """
    # Initialize data.
    num_nodes = 5
    num_edges = 12
    ntypes = {
        "N0": 0,
        "N1": 1,
    }
    etypes = {
        "N0:R0:N0": 0,
        "N0:R1:N1": 1,
        "N1:R2:N0": 2,
        "N1:R3:N1": 3,
    }
    indptr = torch.LongTensor([0, 3, 5, 7, 9, 12])
    indices = torch.LongTensor([0, 1, 4, 2, 3, 0, 1, 1, 2, 0, 3, 4])
    node_type_offset = torch.LongTensor([0, 2, 5])
    type_per_edge = torch.LongTensor([0, 0, 2, 2, 2, 1, 1, 1, 3, 1, 3, 3])
    assert indptr[-1] == num_edges
    assert indptr[-1] == len(indices)
    assert node_type_offset[-1] == num_nodes
    assert all(type_per_edge < len(etypes))

    # Construct CSCSamplingGraph.
    metadata = gb.GraphMetadata(ntypes, etypes)
    graph = gb.from_csc(
        indptr, indices, node_type_offset, type_per_edge, None, metadata
    )

    # Extract in subgraph.
    nodes = torch.LongTensor([1, 3, 4])
    in_subgraph = graph.in_subgraph(nodes)

    # Verify in subgraph.
    assert torch.equal(in_subgraph.indptr, torch.LongTensor([0, 2, 4, 7]))
    assert torch.equal(
        in_subgraph.indices, torch.LongTensor([2, 3, 1, 2, 0, 3, 4])
    )
    assert torch.equal(in_subgraph.reverse_column_node_ids, nodes)
    assert torch.equal(
        in_subgraph.reverse_row_node_ids, torch.arange(0, num_nodes)
    )
    assert torch.equal(
        in_subgraph.reverse_edge_ids, torch.LongTensor([3, 4, 7, 8, 9, 10, 11])
    )
    assert torch.equal(
        in_subgraph.type_per_edge, torch.LongTensor([2, 2, 1, 3, 1, 3, 3])
    )


@unittest.skipIf(
    F._default_context_str == "gpu",
    reason="Graph is CPU only at present.",
)
def test_sample_neighbors_homo():
    """Original graph in COO:
    1   0   1   0   1
    1   0   1   1   0
    0   1   0   1   0
    0   1   0   0   1
    1   0   0   0   1
    """
    # Initialize data.
    num_nodes = 5
    num_edges = 12
    indptr = torch.LongTensor([0, 3, 5, 7, 9, 12])
    indices = torch.LongTensor([0, 1, 4, 2, 3, 0, 1, 1, 2, 0, 3, 4])
    assert indptr[-1] == num_edges
    assert indptr[-1] == len(indices)

    # Construct CSCSamplingGraph.
    graph = gb.from_csc(indptr, indices)

    # Generate subgraph via sample neighbors.
    nodes = torch.LongTensor([1, 3, 4])
    subgraph = graph.sample_neighbors(nodes, fanouts=torch.LongTensor([2]))

    # Verify in subgraph.
    sampled_num = subgraph.node_pairs[0].size(0)
    assert sampled_num == 6
    assert subgraph.reverse_column_node_ids is None
    assert subgraph.reverse_row_node_ids is None
    assert subgraph.reverse_edge_ids is None


@unittest.skipIf(
    F._default_context_str == "gpu",
    reason="Graph is CPU only at present.",
)
@pytest.mark.parametrize("labor", [False, True])
def test_sample_neighbors_hetero(labor):
    """Original graph in COO:
    "n1:e1:n2":[0, 0, 1, 1, 1], [0, 2, 0, 1, 2]
    "n2:e2:n1":[0, 0, 1, 2], [0, 1, 1 ,0]
    0   0   1   0   1
    0   0   1   1   1
    1   1   0   0   0
    0   1   0   0   0
    1   0   0   0   0
    """
    # Initialize data.
    ntypes = {"n1": 0, "n2": 1}
    etypes = {"n1:e1:n2": 0, "n2:e2:n1": 1}
    metadata = gb.GraphMetadata(ntypes, etypes)
    num_nodes = 5
    num_edges = 9
    indptr = torch.LongTensor([0, 2, 4, 6, 7, 9])
    indices = torch.LongTensor([2, 4, 2, 3, 0, 1, 1, 0, 1])
    type_per_edge = torch.LongTensor([1, 1, 1, 1, 0, 0, 0, 0, 0])
    node_type_offset = torch.LongTensor([0, 2, 5])
    assert indptr[-1] == num_edges
    assert indptr[-1] == len(indices)

    # Construct CSCSamplingGraph.
    graph = gb.from_csc(
        indptr,
        indices,
        node_type_offset=node_type_offset,
        type_per_edge=type_per_edge,
        metadata=metadata,
    )

    # Generate subgraph via sample neighbors.
    nodes = {"n1": torch.LongTensor([0]), "n2": torch.LongTensor([0])}
    fanouts = torch.tensor([-1, -1])
    sampler = graph.sample_layer_neighbors if labor else graph.sample_neighbors
    subgraph = sampler(nodes, fanouts)

    # Verify in subgraph.
    expected_node_pairs = {
        "n1:e1:n2": (
            torch.LongTensor([0, 1]),
            torch.LongTensor([0, 0]),
        ),
        "n2:e2:n1": (
            torch.LongTensor([0, 2]),
            torch.LongTensor([0, 0]),
        ),
    }
    assert len(subgraph.node_pairs) == 2
    for etype, pairs in expected_node_pairs.items():
        assert torch.equal(subgraph.node_pairs[etype][0], pairs[0])
        assert torch.equal(subgraph.node_pairs[etype][1], pairs[1])
    assert subgraph.reverse_column_node_ids is None
    assert subgraph.reverse_row_node_ids is None
    assert subgraph.reverse_edge_ids is None


@unittest.skipIf(
    F._default_context_str == "gpu",
    reason="Graph is CPU only at present.",
)
@pytest.mark.parametrize(
    "fanouts, expected_sampled_num1, expected_sampled_num2",
    [
        ([0], 0, 0),
        ([1], 1, 1),
        ([2], 2, 2),
        ([4], 2, 2),
        ([-1], 2, 2),
        ([0, 0], 0, 0),
        ([1, 0], 1, 0),
        ([0, 1], 0, 1),
        ([1, 1], 1, 1),
        ([2, 1], 2, 1),
        ([-1, -1], 2, 2),
    ],
)
@pytest.mark.parametrize("labor", [False, True])
def test_sample_neighbors_fanouts(
    fanouts, expected_sampled_num1, expected_sampled_num2, labor
):
    """Original graph in COO:
    "n1:e1:n2":[0, 0, 1, 1, 1], [0, 2, 0, 1, 2]
    "n2:e2:n1":[0, 0, 1, 2], [0, 1, 1 ,0]
    0   0   1   0   1
    0   0   1   1   1
    1   1   0   0   0
    0   1   0   0   0
    1   0   0   0   0
    """
    # Initialize data.
    ntypes = {"n1": 0, "n2": 1}
    etypes = {"n1:e1:n2": 0, "n2:e2:n1": 1}
    metadata = gb.GraphMetadata(ntypes, etypes)
    num_nodes = 5
    num_edges = 9
    indptr = torch.LongTensor([0, 2, 4, 6, 7, 9])
    indices = torch.LongTensor([2, 4, 2, 3, 0, 1, 1, 0, 1])
    type_per_edge = torch.LongTensor([1, 1, 1, 1, 0, 0, 0, 0, 0])
    node_type_offset = torch.LongTensor([0, 2, 5])
    assert indptr[-1] == num_edges
    assert indptr[-1] == len(indices)

    # Construct CSCSamplingGraph.
    graph = gb.from_csc(
        indptr,
        indices,
        node_type_offset=node_type_offset,
        type_per_edge=type_per_edge,
        metadata=metadata,
    )

    nodes = {"n1": torch.LongTensor([0]), "n2": torch.LongTensor([0])}
    fanouts = torch.LongTensor(fanouts)
    sampler = graph.sample_layer_neighbors if labor else graph.sample_neighbors
    subgraph = sampler(nodes, fanouts)

    # Verify in subgraph.
    assert subgraph.node_pairs["n1:e1:n2"][0].numel() == expected_sampled_num1
    assert subgraph.node_pairs["n2:e2:n1"][0].numel() == expected_sampled_num2


@unittest.skipIf(
    F._default_context_str == "gpu",
    reason="Graph is CPU only at present.",
)
@pytest.mark.parametrize(
    "replace, expected_sampled_num1, expected_sampled_num2",
    [(False, 2, 2), (True, 4, 4)],
)
def test_sample_neighbors_replace(
    replace, expected_sampled_num1, expected_sampled_num2
):
    """Original graph in COO:
    "n1:e1:n2":[0, 0, 1, 1, 1], [0, 2, 0, 1, 2]
    "n2:e2:n1":[0, 0, 1, 2], [0, 1, 1 ,0]
    0   0   1   0   1
    0   0   1   1   1
    1   1   0   0   0
    0   1   0   0   0
    1   0   0   0   0
    """
    # Initialize data.
    ntypes = {"n1": 0, "n2": 1}
    etypes = {"n1:e1:n2": 0, "n2:e2:n1": 1}
    metadata = gb.GraphMetadata(ntypes, etypes)
    num_nodes = 5
    num_edges = 9
    indptr = torch.LongTensor([0, 2, 4, 6, 7, 9])
    indices = torch.LongTensor([2, 4, 2, 3, 0, 1, 1, 0, 1])
    type_per_edge = torch.LongTensor([1, 1, 1, 1, 0, 0, 0, 0, 0])
    node_type_offset = torch.LongTensor([0, 2, 5])
    assert indptr[-1] == num_edges
    assert indptr[-1] == len(indices)

    # Construct CSCSamplingGraph.
    graph = gb.from_csc(
        indptr,
        indices,
        node_type_offset=node_type_offset,
        type_per_edge=type_per_edge,
        metadata=metadata,
    )

    nodes = {"n1": torch.LongTensor([0]), "n2": torch.LongTensor([0])}
    subgraph = graph.sample_neighbors(
        nodes, torch.LongTensor([4]), replace=replace
    )

    # Verify in subgraph.
    assert subgraph.node_pairs["n1:e1:n2"][0].numel() == expected_sampled_num1
    assert subgraph.node_pairs["n2:e2:n1"][0].numel() == expected_sampled_num2


@unittest.skipIf(
    F._default_context_str == "gpu",
    reason="Graph is CPU only at present.",
)
@pytest.mark.parametrize("replace", [True, False])
@pytest.mark.parametrize("labor", [False, True])
@pytest.mark.parametrize("probs_name", ["weight", "mask"])
def test_sample_neighbors_probs(replace, labor, probs_name):
    """Original graph in COO:
    1   0   1   0   1
    1   0   1   1   0
    0   1   0   1   0
    0   1   0   0   1
    1   0   0   0   1
    """
    # Initialize data.
    num_nodes = 5
    num_edges = 12
    indptr = torch.LongTensor([0, 3, 5, 7, 9, 12])
    indices = torch.LongTensor([0, 1, 4, 2, 3, 0, 1, 1, 2, 0, 3, 4])
    assert indptr[-1] == num_edges
    assert indptr[-1] == len(indices)

    edge_attributes = {
        "weight": torch.FloatTensor(
            [2.5, 0, 8.4, 0, 0.4, 1.2, 2.5, 0, 8.4, 0.5, 0.4, 1.2]
        ),
        "mask": torch.BoolTensor([1, 0, 1, 0, 1, 1, 1, 0, 1, 1, 1, 1]),
    }

    # Construct CSCSamplingGraph.
    graph = gb.from_csc(indptr, indices, edge_attributes=edge_attributes)

    # Generate subgraph via sample neighbors.
    nodes = torch.LongTensor([1, 3, 4])

    sampler = graph.sample_layer_neighbors if labor else graph.sample_neighbors
    subgraph = sampler(
        nodes,
        fanouts=torch.tensor([2]),
        replace=replace,
        probs_name=probs_name,
    )

    # Verify in subgraph.
    sampled_num = subgraph.node_pairs[0].size(0)
    if replace:
        assert sampled_num == 6
    else:
        assert sampled_num == 4


@unittest.skipIf(
    F._default_context_str == "gpu",
    reason="Graph is CPU only at present.",
)
@pytest.mark.parametrize("replace", [True, False])
@pytest.mark.parametrize("labor", [False, True])
@pytest.mark.parametrize(
    "probs_or_mask",
    [
        torch.zeros(12, dtype=torch.float32),
        torch.zeros(12, dtype=torch.bool),
    ],
)
def test_sample_neighbors_zero_probs(replace, labor, probs_or_mask):
    # Initialize data.
    num_nodes = 5
    num_edges = 12
    indptr = torch.LongTensor([0, 3, 5, 7, 9, 12])
    indices = torch.LongTensor([0, 1, 4, 2, 3, 0, 1, 1, 2, 0, 3, 4])
    assert indptr[-1] == num_edges
    assert indptr[-1] == len(indices)

    edge_attributes = {"probs_or_mask": probs_or_mask}

    # Construct CSCSamplingGraph.
    graph = gb.from_csc(indptr, indices, edge_attributes=edge_attributes)

    # Generate subgraph via sample neighbors.
    nodes = torch.LongTensor([1, 3, 4])
    sampler = graph.sample_layer_neighbors if labor else graph.sample_neighbors
    subgraph = sampler(
        nodes,
        fanouts=torch.tensor([5]),
        replace=replace,
        probs_name="probs_or_mask",
    )

    # Verify in subgraph.
    sampled_num = subgraph.node_pairs[0].size(0)
    assert sampled_num == 0


def check_tensors_on_the_same_shared_memory(t1: torch.Tensor, t2: torch.Tensor):
    """Check if two tensors are on the same shared memory.

    This function copies a random tensor value to `t1` and checks whether `t2`
    holds the same random value and checks whether t2 is a distinct tensor
    object from `t1`. Their equality confirms that they are separate tensors
    that rely on the shared memory for their tensor value.
    """
    assert t1.data_ptr() != t2.data_ptr()
    old_t1 = t1.clone()
    v = torch.randint_like(t1, 100)
    t1[:] = v
    assert torch.equal(t1, t2)
    t1[:] = old_t1


@unittest.skipIf(
    F._default_context_str == "gpu",
    reason="CSCSamplingGraph is only supported on CPU.",
)
@pytest.mark.parametrize(
    "num_nodes, num_edges", [(1, 1), (100, 1), (10, 50), (1000, 50000)]
)
@pytest.mark.parametrize("test_edge_attrs", [True, False])
def test_homo_graph_on_shared_memory(num_nodes, num_edges, test_edge_attrs):
    csc_indptr, indices = gbt.random_homo_graph(num_nodes, num_edges)
    if test_edge_attrs:
        edge_attributes = {
            "A1": torch.randn(num_edges),
            "A2": torch.randn(num_edges),
        }
    else:
        edge_attributes = None
    graph = gb.from_csc(csc_indptr, indices, edge_attributes=edge_attributes)

    shm_name = "test_homo_g"
    graph1 = graph.copy_to_shared_memory(shm_name)
    graph2 = gb.load_from_shared_memory(shm_name, graph.metadata)

    assert graph1.num_nodes == num_nodes
    assert graph1.num_nodes == num_nodes
    assert graph2.num_edges == num_edges
    assert graph2.num_edges == num_edges

    # Test the value of graph1 is correct
    assert torch.equal(graph1.csc_indptr, csc_indptr)
    assert torch.equal(graph1.indices, indices)

    # Test the value of graph2 is correct
    assert torch.equal(graph2.csc_indptr, csc_indptr)
    assert torch.equal(graph2.indices, indices)

    # Test the memory of graph1 and graph2 is on shared memory
    check_tensors_on_the_same_shared_memory(
        graph1.csc_indptr, graph2.csc_indptr
    )
    check_tensors_on_the_same_shared_memory(graph1.indices, graph2.indices)

    if test_edge_attrs:
        for name, edge_attr in edge_attributes.items():
            assert name in graph1.edge_attributes
            assert name in graph2.edge_attributes
            assert torch.equal(graph1.edge_attributes[name], edge_attr)
            check_tensors_on_the_same_shared_memory(
                graph1.edge_attributes[name], graph2.edge_attributes[name]
            )

    assert graph1.metadata is None and graph2.metadata is None
    assert graph1.node_type_offset is None and graph2.node_type_offset is None
    assert graph1.type_per_edge is None and graph2.type_per_edge is None


@unittest.skipIf(
    F._default_context_str == "gpu",
    reason="CSCSamplingGraph is only supported on CPU.",
)
@pytest.mark.parametrize(
    "num_nodes, num_edges", [(1, 1), (100, 1), (10, 50), (1000, 50000)]
)
@pytest.mark.parametrize("num_ntypes, num_etypes", [(1, 1), (3, 5), (100, 1)])
@pytest.mark.parametrize("test_edge_attrs", [True, False])
def test_hetero_graph_on_shared_memory(
    num_nodes, num_edges, num_ntypes, num_etypes, test_edge_attrs
):
    (
        csc_indptr,
        indices,
        node_type_offset,
        type_per_edge,
        metadata,
    ) = gbt.random_hetero_graph(num_nodes, num_edges, num_ntypes, num_etypes)

    if test_edge_attrs:
        edge_attributes = {
            "A1": torch.randn(num_edges),
            "A2": torch.randn(num_edges),
        }
    else:
        edge_attributes = None
    graph = gb.from_csc(
        csc_indptr,
        indices,
        node_type_offset,
        type_per_edge,
        edge_attributes,
        metadata,
    )

    shm_name = "test_hetero_g"
    graph1 = graph.copy_to_shared_memory(shm_name)
    graph2 = gb.load_from_shared_memory(shm_name, graph.metadata)

    assert graph1.num_nodes == num_nodes
    assert graph1.num_nodes == num_nodes
    assert graph2.num_edges == num_edges
    assert graph2.num_edges == num_edges

    # Test the value of graph1 is correct
    assert torch.equal(graph1.csc_indptr, csc_indptr)
    assert torch.equal(graph1.indices, indices)
    assert torch.equal(graph1.node_type_offset, node_type_offset)
    assert torch.equal(graph1.type_per_edge, type_per_edge)

    # Test the value of graph2 is correct
    assert torch.equal(graph2.csc_indptr, csc_indptr)
    assert torch.equal(graph2.indices, indices)
    assert torch.equal(graph2.node_type_offset, node_type_offset)
    assert torch.equal(graph2.type_per_edge, type_per_edge)

    # Test the memory of graph1 and graph2 is on shared memory
    check_tensors_on_the_same_shared_memory(
        graph1.csc_indptr, graph2.csc_indptr
    )
    check_tensors_on_the_same_shared_memory(graph1.indices, graph2.indices)
    check_tensors_on_the_same_shared_memory(
        graph1.node_type_offset, graph2.node_type_offset
    )
    check_tensors_on_the_same_shared_memory(
        graph1.type_per_edge, graph2.type_per_edge
    )

    if test_edge_attrs:
        for name, edge_attr in edge_attributes.items():
            assert name in graph1.edge_attributes
            assert name in graph2.edge_attributes
            assert torch.equal(graph1.edge_attributes[name], edge_attr)
            check_tensors_on_the_same_shared_memory(
                graph1.edge_attributes[name], graph2.edge_attributes[name]
            )

    assert metadata.node_type_to_id == graph1.metadata.node_type_to_id
    assert metadata.edge_type_to_id == graph1.metadata.edge_type_to_id
    assert metadata.node_type_to_id == graph2.metadata.node_type_to_id
    assert metadata.edge_type_to_id == graph2.metadata.edge_type_to_id


def process_csc_sampling_graph_on_shared_memory(graph, data_queue, flag_queue):
    # Backup the attributes.
    csc_indptr = graph.csc_indptr.clone()
    indices = graph.indices.clone()
    node_type_offset = graph.node_type_offset.clone()
    type_per_edge = graph.type_per_edge.clone()

    # Change the value to random integers. Send the new value to the main
    # process.
    v = torch.randint_like(graph.csc_indptr, 100)
    graph.csc_indptr[:] = v
    data_queue.put(v.clone())

    v = torch.randint_like(graph.indices, 100)
    graph.indices[:] = v
    data_queue.put(v.clone())

    v = torch.randint_like(graph.node_type_offset, 100)
    graph.node_type_offset[:] = v
    data_queue.put(v.clone())

    v = torch.randint_like(graph.type_per_edge, 100)
    graph.type_per_edge[:] = v
    data_queue.put(v.clone())

    # Wait for the main process to finish.
    flag_queue.get()

    graph.csc_indptr[:] = csc_indptr
    graph.indices[:] = indices
    graph.node_type_offset[:] = node_type_offset
    graph.type_per_edge[:] = type_per_edge


@unittest.skipIf(
    F._default_context_str == "gpu",
    reason="Graph is CPU only at present.",
)
def test_multiprocessing_with_shared_memory():
    """Test if two CSCSamplingGraphs are on the same shared memory after
    spawning.

    For now this code only works when the sharing strategy of
    torch.multiprocessing is set to `file_system` at the beginning.
    The cause is still yet to be found.
    """

    num_nodes = 5
    num_edges = 10
    num_ntypes = 2
    num_etypes = 3
    (
        csc_indptr,
        indices,
        node_type_offset,
        type_per_edge,
        metadata,
    ) = gbt.random_hetero_graph(num_nodes, num_edges, num_ntypes, num_etypes)

    csc_indptr.share_memory_()
    indices.share_memory_()
    node_type_offset.share_memory_()
    type_per_edge.share_memory_()

    graph = gb.from_csc(
        csc_indptr,
        indices,
        node_type_offset,
        type_per_edge,
        None,
        metadata,
    )

    ctx = mp.get_context("spawn")  # Use spawn method.

    data_queue = ctx.Queue()  # Used for sending graph.
    flag_queue = ctx.Queue()  # Used for sending finish signal.

    p = ctx.Process(
        target=process_csc_sampling_graph_on_shared_memory,
        args=(graph, data_queue, flag_queue),
    )
    p.start()
    try:
        # Get data from the other process. Then check if the tensors here have
        # the same data.
        csc_indptr2 = data_queue.get()
        assert torch.equal(graph.csc_indptr, csc_indptr2)
        indices2 = data_queue.get()
        assert torch.equal(graph.indices, indices2)
        node_type_offset2 = data_queue.get()
        assert torch.equal(graph.node_type_offset, node_type_offset2)
        type_per_edge2 = data_queue.get()
        assert torch.equal(graph.type_per_edge, type_per_edge2)
    except:
        raise
    finally:
        # Send a finish signal to end sub-process.
        flag_queue.put(None)
    p.join()


@unittest.skipIf(
    F._default_context_str == "gpu",
    reason="Graph on GPU is not supported yet.",
)
def test_from_dglgraph_homogeneous():
    dgl_g = dgl.rand_graph(1000, 10 * 1000)
    gb_g = gb.from_dglgraph(dgl_g, is_homogeneous=True)

    assert gb_g.num_nodes == dgl_g.num_nodes()
    assert gb_g.num_edges == dgl_g.num_edges()
    assert torch.equal(gb_g.node_type_offset, torch.tensor([0, 1000]))
    assert gb_g.type_per_edge is None
    assert gb_g.metadata.node_type_to_id == {"_N": 0}
    assert gb_g.metadata.edge_type_to_id == {"_N:_E:_N": 0}


@unittest.skipIf(
    F._default_context_str == "gpu",
    reason="Graph on GPU is not supported yet.",
)
def test_from_dglgraph_heterogeneous():
    dgl_g = dgl.heterograph(
        {
            ("author", "writes", "paper"): (
                [1, 2, 3, 4, 5, 2],
                [1, 2, 3, 4, 5, 4],
            ),
            ("author", "affiliated_with", "institution"): (
                [1, 2, 3, 4, 5],
                [1, 2, 3, 4, 5],
            ),
            ("paper", "has_topic", "field"): ([1, 2, 3, 4, 5], [1, 2, 3, 4, 5]),
            ("paper", "cites", "paper"): (
                [2, 3, 4, 5, 6, 1],
                [1, 2, 3, 4, 5, 4],
            ),
        }
    )
    gb_g = gb.from_dglgraph(dgl_g, is_homogeneous=False)

    assert gb_g.num_nodes == dgl_g.num_nodes()
    assert gb_g.num_edges == dgl_g.num_edges()
    assert torch.equal(gb_g.node_type_offset, torch.tensor([0, 6, 12, 18, 25]))
    assert torch.equal(
        gb_g.type_per_edge,
        torch.tensor(
            [3, 3, 3, 3, 3, 0, 0, 0, 0, 0, 1, 2, 1, 2, 1, 2, 1, 1, 2, 2, 1, 2]
        ),
    )
    assert gb_g.metadata.node_type_to_id == {
        "author": 0,
        "field": 1,
        "institution": 2,
        "paper": 3,
    }
    assert gb_g.metadata.edge_type_to_id == {
        "author:affiliated_with:institution": 0,
        "author:writes:paper": 1,
        "paper:cites:paper": 2,
        "paper:has_topic:field": 3,
    }


@unittest.skipIf(
    F._default_context_str == "gpu",
    reason="Graph is CPU only at present.",
)
@pytest.mark.parametrize("replace", [False, True])
@pytest.mark.parametrize("labor", [False, True])
@pytest.mark.parametrize(
    "fanouts, probs_name",
    [
        ([2], "mask"),
        ([3], "mask"),
        ([4], "mask"),
        ([-1], "mask"),
        ([7], "mask"),
        ([3], "all"),
        ([-1], "all"),
        ([7], "all"),
        ([3], "zero"),
        ([-1], "zero"),
        ([3], "none"),
        ([-1], "none"),
    ],
)
def test_sample_neighbors_homo_pick_number(fanouts, replace, labor, probs_name):
    """Original graph in COO:
    1   1   1   1   1   1
    0   0   0   0   0   0
    0   0   0   0   0   0
    0   0   0   0   0   0
    0   0   0   0   0   0
    0   0   0   0   0   0
    """
    # Initialize data.
    num_nodes = 6
    num_edges = 6
    indptr = torch.LongTensor([0, 6, 6, 6, 6, 6, 6])
    indices = torch.LongTensor([0, 1, 2, 3, 4, 5])
    assert indptr[-1] == num_edges
    assert indptr[-1] == len(indices)

    edge_attributes = {
        "mask": torch.BoolTensor([1, 0, 0, 1, 0, 1]),
        "all": torch.BoolTensor([1, 1, 1, 1, 1, 1]),
        "zero": torch.BoolTensor([0, 0, 0, 0, 0, 0]),
    }

    # Construct CSCSamplingGraph.
    graph = gb.from_csc(indptr, indices, edge_attributes=edge_attributes)

    # Generate subgraph via sample neighbors.
    nodes = torch.LongTensor([0, 1])

    sampler = graph.sample_layer_neighbors if labor else graph.sample_neighbors

    # Make sure no exception will be thrown.
    subgraph = sampler(
        nodes,
        fanouts=torch.LongTensor(fanouts),
        replace=replace,
        probs_name=probs_name if probs_name != "none" else None,
    )
    sampled_num = subgraph.node_pairs[0].size(0)

    # Verify in subgraph.
    if probs_name == "mask":
        if fanouts[0] == -1:
            assert sampled_num == 3
        else:
            if replace:
                assert sampled_num == fanouts[0]
            else:
                assert sampled_num == min(fanouts[0], 3)
    elif probs_name == "zero":
        assert sampled_num == 0
    else:
        if fanouts[0] == -1:
            assert sampled_num == 6
        else:
            if replace:
                assert sampled_num == fanouts[0]
            else:
                assert sampled_num == min(fanouts[0], 6)


@unittest.skipIf(
    F._default_context_str == "gpu",
    reason="Graph is CPU only at present.",
)
@pytest.mark.parametrize("replace", [False, True])
@pytest.mark.parametrize("labor", [False, True])
@pytest.mark.parametrize(
    "fanouts, probs_name",
    [
        ([-1, -1, -1], "mask"),
        ([1, 1, 1], "mask"),
        ([2, 2, 2], "mask"),
        ([3, 3, 3], "mask"),
        ([4, 4, 4], "mask"),
        ([-1, 1, 3], "none"),
        ([2, -1, 4], "none"),
    ],
)
def test_sample_neighbors_hetero_pick_number(
    fanouts, replace, labor, probs_name
):
    # Initialize data.
    num_nodes = 10
    num_edges = 9
    ntypes = {"N0": 0, "N1": 1, "N2": 2, "N3": 3}
    etypes = {
        "N0:R0:N1": 0,
        "N0:R1:N2": 1,
        "N0:R2:N3": 2,
    }
    metadata = gb.GraphMetadata(ntypes, etypes)
    indptr = torch.LongTensor([0, 9, 9, 9, 9, 9, 9, 9, 9, 9, 9])
    indices = torch.LongTensor([1, 2, 3, 4, 5, 6, 7, 8, 9])
    node_type_offset = torch.LongTensor([0, 1, 4, 7, 10])
    type_per_edge = torch.LongTensor([0, 0, 0, 1, 1, 1, 2, 2, 2])
    assert indptr[-1] == num_edges
    assert indptr[-1] == len(indices)
    assert node_type_offset[-1] == num_nodes
    assert all(type_per_edge < len(etypes))

    edge_attributes = {
        "mask": torch.BoolTensor([1, 1, 0, 1, 1, 1, 0, 0, 0]),
        "all": torch.BoolTensor([1, 1, 1, 1, 1, 1, 1, 1, 1]),
        "zero": torch.BoolTensor([0, 0, 0, 0, 0, 0, 0, 0, 0]),
    }

    # Construct CSCSamplingGraph.
    graph = gb.from_csc(
        indptr,
        indices,
        edge_attributes=edge_attributes,
        node_type_offset=node_type_offset,
        type_per_edge=type_per_edge,
        metadata=metadata,
    )

    # Generate subgraph via sample neighbors.
    nodes = torch.LongTensor([0, 1])

    sampler = graph.sample_layer_neighbors if labor else graph.sample_neighbors

    # Make sure no exception will be thrown.
    subgraph = sampler(
        nodes,
        fanouts=torch.LongTensor(fanouts),
        replace=replace,
        probs_name=probs_name if probs_name != "none" else None,
    )

    if probs_name == "none":
        for etype, pairs in subgraph.node_pairs.items():
            fanout = fanouts[etypes[etype]]
            if fanout == -1:
                assert pairs[0].size(0) == 3
            else:
                if replace:
                    assert pairs[0].size(0) == fanout
                else:
                    assert pairs[0].size(0) == min(fanout, 3)
    else:
        fanout = fanouts[0]  # Here fanout is the same for all etypes.
        for etype, pairs in subgraph.node_pairs.items():
            if etypes[etype] == 0:
                # Etype 0: 2 valid neighbors.
                if fanout == -1:
                    assert pairs[0].size(0) == 2
                else:
                    if replace:
                        assert pairs[0].size(0) == fanout
                    else:
                        assert pairs[0].size(0) == min(fanout, 2)
            elif etypes[etype] == 1:
                # Etype 1: 3 valid neighbors.
                if fanout == -1:
                    assert pairs[0].size(0) == 3
                else:
                    if replace:
                        assert pairs[0].size(0) == fanout
                    else:
                        assert pairs[0].size(0) == min(fanout, 3)
            else:
                # Etype 2: 0 valid neighbors.
                assert pairs[0].size(0) == 0
