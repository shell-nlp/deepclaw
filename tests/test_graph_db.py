import pytest

from deepclaw.common.graph_db.base import GraphDatabaseBase
from deepclaw.common.graph_db.networkx import NetworkXGraph


class DummyGraph(GraphDatabaseBase):
    def add_node(self, label, properties=None, node_id=None):
        raise NotImplementedError

    def add_edge(self, from_node_id, to_node_id, relationship_type="LINK", properties=None):
        raise NotImplementedError

    def get_node(self, node_id):
        raise NotImplementedError

    def get_nodes_by_label(self, label):
        raise NotImplementedError

    def get_neighbors(self, node_id, relationship_type=None):
        raise NotImplementedError

    def delete_node(self, node_id):
        raise NotImplementedError

    def delete_edge(self, from_node_id, to_node_id, relationship_type):
        raise NotImplementedError

    def close(self):
        raise NotImplementedError


def test_abstract_class_cannot_be_instantiated():
    with pytest.raises(TypeError):
        GraphDatabaseBase()


def test_add_node_returns_id():
    g = NetworkXGraph()
    nid = g.add_node("Person", {"name": "Alice"})
    assert isinstance(nid, str)
    assert nid.startswith("Person_")
    g.close()


def test_add_node_with_custom_id():
    g = NetworkXGraph()
    nid = g.add_node("Person", {"name": "Bob"}, node_id="bob-001")
    assert nid == "bob-001"
    g.close()


def test_add_node_no_properties():
    g = NetworkXGraph()
    nid = g.add_node("Person")
    assert isinstance(nid, str)
    g.close()


def test_get_node_returns_correct_data():
    g = NetworkXGraph()
    nid = g.add_node("Person", {"name": "Alice", "age": 30})
    node = g.get_node(nid)
    assert node["id"] == nid
    assert node["labels"] == ["Person"]
    assert node["properties"]["name"] == "Alice"
    assert node["properties"]["age"] == 30
    g.close()


def test_get_node_returns_none_for_missing():
    g = NetworkXGraph()
    assert g.get_node("nonexistent") is None
    g.close()


def test_get_nodes_by_label():
    g = NetworkXGraph()
    id1 = g.add_node("Person", {"name": "Alice"})
    id2 = g.add_node("Person", {"name": "Bob"})
    g.add_node("Company", {"name": "Acme"})

    persons = g.get_nodes_by_label("Person")
    assert len(persons) == 2
    assert {n["id"] for n in persons} == {id1, id2}
    g.close()


def test_get_nodes_by_label_empty():
    g = NetworkXGraph()
    assert g.get_nodes_by_label("Nonexistent") == []
    g.close()


def test_add_edge_returns_true():
    g = NetworkXGraph()
    a = g.add_node("Person", {"name": "Alice"})
    b = g.add_node("Person", {"name": "Bob"})
    assert g.add_edge(a, b, "KNOWS", {"weight": 1.0})
    g.close()


def test_add_edge_returns_false_when_nodes_missing():
    g = NetworkXGraph()
    a = g.add_node("Person", {"name": "Alice"})
    assert not g.add_edge(a, "nonexistent", "KNOWS")
    assert not g.add_edge("nonexistent", a, "KNOWS")
    g.close()


def test_get_neighbors():
    g = NetworkXGraph()
    alice = g.add_node("Person", {"name": "Alice"})
    bob = g.add_node("Person", {"name": "Bob"})
    charlie = g.add_node("Person", {"name": "Charlie"})
    g.add_edge(alice, bob, "KNOWS")
    g.add_edge(alice, charlie, "FRIEND")

    neighbors = g.get_neighbors(alice)
    assert len(neighbors) == 2
    names = {n["node"]["properties"]["name"] for n in neighbors}
    rels = {n["relationship_type"] for n in neighbors}
    assert names == {"Bob", "Charlie"}
    assert rels == {"KNOWS", "FRIEND"}
    g.close()


def test_get_neighbors_filter_by_relationship():
    g = NetworkXGraph()
    alice = g.add_node("Person", {"name": "Alice"})
    bob = g.add_node("Person", {"name": "Bob"})
    g.add_edge(alice, bob, "KNOWS", {"weight": 1.0})

    neighbors = g.get_neighbors(alice, "KNOWS")
    assert len(neighbors) == 1
    assert neighbors[0]["node"]["properties"]["name"] == "Bob"

    neighbors = g.get_neighbors(alice, "NONEXISTENT")
    assert len(neighbors) == 0
    g.close()


def test_get_neighbors_returns_empty_for_missing_node():
    g = NetworkXGraph()
    assert g.get_neighbors("nonexistent") == []
    g.close()


def test_delete_node_returns_true():
    g = NetworkXGraph()
    nid = g.add_node("Person", {"name": "Alice"})
    assert g.delete_node(nid)
    assert g.get_node(nid) is None
    g.close()


def test_delete_node_returns_false_for_missing():
    g = NetworkXGraph()
    assert not g.delete_node("nonexistent")
    g.close()


def test_delete_node_removes_edges():
    g = NetworkXGraph()
    a = g.add_node("Person", {"name": "Alice"})
    b = g.add_node("Person", {"name": "Bob"})
    g.add_edge(a, b, "KNOWS")
    g.delete_node(a)
    assert g.get_node(a) is None
    assert g.get_node(b) is not None
    g.close()


def test_delete_edge_returns_true():
    g = NetworkXGraph()
    a = g.add_node("Person", {"name": "Alice"})
    b = g.add_node("Person", {"name": "Bob"})
    g.add_edge(a, b, "KNOWS")
    assert g.delete_edge(a, b, "KNOWS")

    neighbors = g.get_neighbors(a)
    assert len(neighbors) == 0
    g.close()


def test_delete_edge_returns_false_for_nonexistent():
    g = NetworkXGraph()
    a = g.add_node("Person", {"name": "Alice"})
    b = g.add_node("Person", {"name": "Bob"})
    assert not g.delete_edge(a, b, "KNOWS")
    g.close()


def test_clear_database():
    g = NetworkXGraph()
    g.add_node("Person", {"name": "Alice"})
    g.add_node("Person", {"name": "Bob"})
    g.clear_database()
    assert g.get_nodes_by_label("Person") == []
    g.close()


def test_close_releases_resources():
    g = NetworkXGraph()
    g.add_node("Person", {"name": "Alice"})
    g.close()
    assert g.get_nodes_by_label("Person") == []


def test_multiple_edge_types_between_same_nodes():
    g = NetworkXGraph()
    a = g.add_node("Person", {"name": "Alice"})
    b = g.add_node("Person", {"name": "Bob"})
    g.add_edge(a, b, "KNOWS")
    g.add_edge(a, b, "COLLEAGUE")

    neighbors = g.get_neighbors(a)
    assert len(neighbors) == 2
    assert {n["relationship_type"] for n in neighbors} == {"KNOWS", "COLLEAGUE"}
    g.close()


# ---- Neo4j 集成测试 ----
# 注意：Neo4j 测试共享同一个数据库实例，必须串行执行（不要用 -n auto）

def _neo4j_available():
    try:
        from neo4j import GraphDatabase

        driver = GraphDatabase.driver(
            "bolt://localhost:7687", auth=("neo4j", "neo4j@2025")
        )
        with driver.session(database="neo4j") as session:
            session.run("RETURN 1").single()
        driver.close()
        return True
    except Exception:
        return False


_skip_no_neo4j = pytest.mark.skipif(
    not _neo4j_available(),
    reason="需要本地 Neo4j 实例（bolt://localhost:7687）",
)


@pytest.fixture
def neo4j_graph():
    from deepclaw.common.graph_db.neo4j_db import Neo4jGraph

    g = Neo4jGraph(
        uri="bolt://localhost:7687",
        user="neo4j",
        password="neo4j@2025",
        database="neo4j",
    )
    g.clear_database()
    yield g
    g.clear_database()
    g.close()


@_skip_no_neo4j
def test_neo4j_add_node_and_get(neo4j_graph):
    nid = neo4j_graph.add_node("Person", {"name": "Alice", "age": 30})
    node = neo4j_graph.get_node(nid)
    assert node["id"] == nid
    assert "Person" in node["labels"]
    assert node["properties"]["name"] == "Alice"
    assert node["properties"]["age"] == 30


@_skip_no_neo4j
def test_neo4j_add_node_with_custom_id(neo4j_graph):
    nid = neo4j_graph.add_node("Person", {"name": "Bob"}, node_id="bob-001")
    assert nid == "bob-001"
    node = neo4j_graph.get_node(nid)
    assert node["id"] == "bob-001"


@_skip_no_neo4j
def test_neo4j_get_node_returns_none_for_missing(neo4j_graph):
    assert neo4j_graph.get_node("nonexistent") is None


@_skip_no_neo4j
def test_neo4j_get_nodes_by_label(neo4j_graph):
    a = neo4j_graph.add_node("Person", {"name": "Alice"})
    b = neo4j_graph.add_node("Person", {"name": "Bob"})
    neo4j_graph.add_node("Company", {"name": "Acme"})

    persons = neo4j_graph.get_nodes_by_label("Person")
    assert len(persons) == 2
    assert {n["id"] for n in persons} == {a, b}


@_skip_no_neo4j
def test_neo4j_get_nodes_by_label_empty(neo4j_graph):
    assert neo4j_graph.get_nodes_by_label("Nonexistent") == []


@_skip_no_neo4j
def test_neo4j_add_edge_and_get_neighbors(neo4j_graph):
    alice = neo4j_graph.add_node("Person", {"name": "Alice"})
    bob = neo4j_graph.add_node("Person", {"name": "Bob"})
    assert neo4j_graph.add_edge(alice, bob, "KNOWS", {"weight": 0.9})

    neighbors = neo4j_graph.get_neighbors(alice)
    assert len(neighbors) == 1
    assert neighbors[0]["node"]["id"] == bob
    assert neighbors[0]["relationship_type"] == "KNOWS"


@_skip_no_neo4j
def test_neo4j_add_edge_returns_false_when_nodes_missing(neo4j_graph):
    a = neo4j_graph.add_node("Person", {"name": "Alice"})
    assert not neo4j_graph.add_edge(a, "nonexistent", "KNOWS")
    assert not neo4j_graph.add_edge("nonexistent", a, "KNOWS")


@_skip_no_neo4j
def test_neo4j_get_neighbors_filter_by_relationship(neo4j_graph):
    alice = neo4j_graph.add_node("Person", {"name": "Alice"})
    bob = neo4j_graph.add_node("Person", {"name": "Bob"})
    charlie = neo4j_graph.add_node("Person", {"name": "Charlie"})
    neo4j_graph.add_edge(alice, bob, "KNOWS")
    neo4j_graph.add_edge(alice, charlie, "FRIEND")

    knows = neo4j_graph.get_neighbors(alice, "KNOWS")
    assert len(knows) == 1
    assert knows[0]["node"]["properties"]["name"] == "Bob"

    friend = neo4j_graph.get_neighbors(alice, "FRIEND")
    assert len(friend) == 1
    assert friend[0]["node"]["properties"]["name"] == "Charlie"


@_skip_no_neo4j
def test_neo4j_get_neighbors_returns_empty_for_missing_node(neo4j_graph):
    assert neo4j_graph.get_neighbors("nonexistent") == []


@_skip_no_neo4j
def test_neo4j_delete_node(neo4j_graph):
    nid = neo4j_graph.add_node("Person", {"name": "Alice"})
    assert neo4j_graph.delete_node(nid)
    assert neo4j_graph.get_node(nid) is None


@_skip_no_neo4j
def test_neo4j_delete_node_returns_false_for_missing(neo4j_graph):
    assert not neo4j_graph.delete_node("nonexistent")


@_skip_no_neo4j
def test_neo4j_delete_node_removes_edges(neo4j_graph):
    a = neo4j_graph.add_node("Person", {"name": "Alice"})
    b = neo4j_graph.add_node("Person", {"name": "Bob"})
    neo4j_graph.add_edge(a, b, "KNOWS")
    neo4j_graph.delete_node(a)
    assert neo4j_graph.get_node(a) is None
    assert neo4j_graph.get_node(b) is not None


@_skip_no_neo4j
def test_neo4j_delete_edge(neo4j_graph):
    a = neo4j_graph.add_node("Person", {"name": "Alice"})
    b = neo4j_graph.add_node("Person", {"name": "Bob"})
    neo4j_graph.add_edge(a, b, "KNOWS")
    assert neo4j_graph.delete_edge(a, b, "KNOWS")
    assert len(neo4j_graph.get_neighbors(a)) == 0


@_skip_no_neo4j
def test_neo4j_delete_edge_returns_false_for_nonexistent(neo4j_graph):
    a = neo4j_graph.add_node("Person", {"name": "Alice"})
    b = neo4j_graph.add_node("Person", {"name": "Bob"})
    assert not neo4j_graph.delete_edge(a, b, "KNOWS")


@_skip_no_neo4j
def test_neo4j_clear_database(neo4j_graph):
    neo4j_graph.add_node("Person", {"name": "Alice"})
    neo4j_graph.add_node("Person", {"name": "Bob"})
    neo4j_graph.clear_database()
    assert neo4j_graph.get_nodes_by_label("Person") == []


@_skip_no_neo4j
def test_neo4j_run_cypher_query(neo4j_graph):
    neo4j_graph.add_node("Person", {"name": "Alice"})
    results = neo4j_graph.run_cypher_query(
        "MATCH (n:Person) RETURN n.name AS name ORDER BY n.name"
    )
    assert len(results) == 1
    assert results[0]["name"] == "Alice"
