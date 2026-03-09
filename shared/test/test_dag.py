import pytest
import os
import json
import logging
from unittest.mock import MagicMock, patch
from shared.dag import (Node, LayerDAG, validate_path, parse_path_configs_and_add_dummy_nodes,
                       load_layer_config, parse_dag_from_layers)
from configuration.data import PatchLayer, LayerPath, LayerPathSet
from graphlib import TopologicalSorter

def test_node_init():
    data = {"key": "value"}
    path_data = LayerPath(id="p1", target_layer="L1", layers=["root", "L1"])
    node = Node(identifier="test_id", data=data, tag="test_tag", path_data=path_data)
    
    assert node.identifier == "test_id"
    assert node.data == data
    assert node.tag == "test_tag"
    assert node.path_data == path_data

def test_layer_dag_init():
    dag = LayerDAG()
    assert dag.nodes == {}
    assert dag.edges == {}
    assert dag.root is None

def test_layer_dag_create_node():
    dag = LayerDAG()
    dag.create_node("root", data="root_data")
    assert "root" in dag.nodes
    assert dag.root == "root"
    assert dag.nodes["root"].data == "root_data"
    
    dag.create_node("child", parent="root", data="child_data")
    assert "child" in dag.nodes
    assert "root" in dag.edges["child"]

def test_layer_dag_create_node_invalid_parent():
    dag = LayerDAG()
    with pytest.raises(ValueError, match="Parent nonexistent does not exist"):
        dag.create_node("child", parent="nonexistent")

def test_layer_dag_get_node():
    dag = LayerDAG()
    dag.create_node("root")
    assert dag.get_node("root").identifier == "root"
    assert dag.get_node("nonexistent") is None

def test_layer_dag_parents():
    dag = LayerDAG()
    dag.create_node("root")
    dag.create_node("p1", parent="root")
    dag.create_node("p2", parent="root")
    dag.create_node("child", parent="p1")
    dag.edges["child"].add("p2")
    
    parents = dag.parents("child")
    assert len(parents) == 2
    assert "p1" in parents
    assert "p2" in parents

def test_layer_dag_leaves():
    dag = LayerDAG()
    dag.create_node("root")
    dag.create_node("child1", parent="root")
    dag.create_node("child2", parent="root")
    dag.create_node("grandchild", parent="child1")
    
    leaves = dag.leaves()
    leaf_ids = [n.identifier for n in leaves]
    assert len(leaf_ids) == 2
    assert "child2" in leaf_ids
    assert "grandchild" in leaf_ids

def test_layer_dag_get_all_ancestors():
    dag = LayerDAG()
    dag.create_node("root")
    dag.create_node("a", parent="root")
    dag.create_node("b", parent="a")
    
    ancestors = dag.get_all_ancestors("b")
    assert [n.identifier for n in ancestors] == ["root", "a", "b"]

def test_layer_dag_get_all_paths():
    dag = LayerDAG()
    dag.create_node("root")
    dag.create_node("a", parent="root")
    dag.create_node("b", parent="root")
    dag.create_node("target", parent="a")
    dag.edges["target"].add("b")
    
    paths = dag.get_all_paths("target")
    assert len(paths) == 2
    assert ["root", "a", "target"] in paths
    assert ["root", "b", "target"] in paths

def test_layer_dag_show(capsys):
    dag = LayerDAG()
    dag.create_node("root")
    dag.create_node("child", parent="root")
    dag.show()
    captured = capsys.readouterr()
    assert "Layer DAG Structure:" in captured.out
    assert "root" in captured.out
    assert "└── child" in captured.out

def test_layer_dag_show_failure(caplog):
    dag = LayerDAG()
    dag.create_node("root")
    with patch("shared.dag.TopologicalSorter", side_effect=Exception("TopologicalSorter failed")):
        with caplog.at_level(logging.ERROR):
            dag.show()
            assert "Could not show DAG: TopologicalSorter failed" in caplog.text

def test_layer_dag_show_recursive_invalid_id(capsys):
    dag = LayerDAG()
    dag.create_node("root")
    # Calling _show_recursive with invalid id should return early
    dag._show_recursive("nonexistent", 0, set())
    captured = capsys.readouterr()
    assert captured.out == ""

def test_layer_dag_to_networkx():
    dag = LayerDAG()
    dag.create_node("root")
    dag.create_node("child", parent="root")
    dg = dag.to_networkx()
    assert dg.has_node("root")
    assert dg.has_node("child")
    assert dg.has_edge("root", "child")

def test_layer_dag_to_dot(tmp_path):
    dag = LayerDAG()
    dag.create_node("root")
    dot_file = tmp_path / "graph.dot"
    dag.to_dot(str(dot_file))
    assert dot_file.exists()

def test_layer_dag_to_graphml(tmp_path):
    dag = LayerDAG()
    dag.create_node("root")
    graphml_file = tmp_path / "graph.graphml"
    dag.to_graphml(str(graphml_file))
    assert graphml_file.exists()

def test_validate_path_success():
    dag = LayerDAG()
    dag.create_node("root")
    dag.create_node("mid", parent="root")
    dag.create_node("leaf", parent="mid")
    
    path = LayerPath(id="p1", target_layer="leaf", layers=["root", "mid", "leaf"])
    assert validate_path(path, dag) is True

def test_validate_path_missing_layer():
    dag = LayerDAG()
    dag.create_node("root")
    path = LayerPath(id="p1", target_layer="leaf", layers=["root", "nonexistent"])
    assert validate_path(path, dag) is False

def test_validate_path_broken_connectivity():
    dag = LayerDAG()
    dag.create_node("root")
    dag.create_node("a") # No parent
    dag.root = "root"
    path = LayerPath(id="p1", target_layer="a", layers=["root", "a"])
    assert validate_path(path, dag) is False

def test_validate_path_mismatch_target():
    dag = LayerDAG()
    dag.create_node("root")
    dag.create_node("leaf", parent="root")
    path = LayerPath(id="p1", target_layer="other", layers=["root", "leaf"])
    assert validate_path(path, dag) is False

def test_parse_path_configs_and_add_dummy_nodes(tmp_path):
    dag = LayerDAG()
    dag.create_node("root")
    dag.create_node("target", parent="root")
    
    paths_dir = tmp_path / "paths"
    paths_dir.mkdir()
    path_file = paths_dir / "my_paths.json"
    
    path_data = LayerPathSet(paths=[
        LayerPath(id="dummy-path", target_layer="target", layers=["root", "target"])
    ])
    path_file.write_text(path_data.to_json())
    
    parse_path_configs_and_add_dummy_nodes(str(paths_dir), dag)
    
    assert "dummy-path" in dag.nodes
    assert dag.nodes["dummy-path"].data.layers == ["root", "target"]
    assert "target" in dag.edges["dummy-path"]

def test_load_layer_config_success(tmp_path):
    layer_file = tmp_path / "layer.json"
    layer_data = PatchLayer(id="test_id", title="Test Title")
    layer_file.write_text(layer_data.to_json())
    
    config = load_layer_config(str(tmp_path), "layer.json")
    assert config.id == "test_id"
    assert config.title == "Test Title"

def test_load_layer_config_not_found():
    with pytest.raises(SystemExit):
        load_layer_config("/nonexistent", "config.json")

def test_load_layer_config_invalid_json(tmp_path):
    layer_file = tmp_path / "invalid.json"
    layer_file.write_text("{invalid_json:}")
    with pytest.raises(SystemExit):
        load_layer_config(str(tmp_path), "invalid.json")

def test_load_layer_config_value_error(tmp_path):
    # PatchLayer.from_json is mocked to raise ValueError
    layer_file = tmp_path / "layer.json"
    layer_file.write_text("{}")
    with patch("configuration.data.PatchLayer.from_json", side_effect=ValueError("Bad data")):
        with pytest.raises(SystemExit):
            load_layer_config(str(tmp_path), "layer.json")

def test_parse_dag_from_layers_success(tmp_path):
    layers_dir = tmp_path / "layers"
    layers_dir.mkdir()
    
    base_layer = PatchLayer(id="base", title="Base Layer")
    (layers_dir / "base.json").write_text(base_layer.to_json())
    
    child_layer = PatchLayer(id="child", parent="base", title="Child Layer")
    (layers_dir / "child.json").write_text(child_layer.to_json())
    
    dag, files = parse_dag_from_layers(str(layers_dir), None)
    assert "base" in dag.nodes
    assert "child" in dag.nodes
    assert "base" in dag.edges["child"]
    assert "base.json" in files
    assert "child.json" in files

def test_parse_dag_from_layers_multi_parents(tmp_path):
    layers_dir = tmp_path / "layers"
    layers_dir.mkdir()
    
    base_layer = PatchLayer(id="base", title="Base Layer")
    (layers_dir / "base.json").write_text(base_layer.to_json())
    
    mid1_layer = PatchLayer(id="mid1", parent="base", title="Mid 1")
    (layers_dir / "mid1.json").write_text(mid1_layer.to_json())
    
    mid2_layer = PatchLayer(id="mid2", parent="base", title="Mid 2")
    (layers_dir / "mid2.json").write_text(mid2_layer.to_json())
    
    child_layer = PatchLayer(id="child", parents=["mid1", "mid2"], title="Child Layer")
    (layers_dir / "child.json").write_text(child_layer.to_json())
    
    dag, _ = parse_dag_from_layers(str(layers_dir), None)
    assert "child" in dag.nodes
    assert "mid1" in dag.edges["child"]
    assert "mid2" in dag.edges["child"]

def test_parse_dag_from_layers_duplicate_base(tmp_path):
    layers_dir = tmp_path / "layers"
    layers_dir.mkdir()
    
    base1 = PatchLayer(id="base1", title="Base 1")
    (layers_dir / "base1.json").write_text(base1.to_json())
    
    base2 = PatchLayer(id="base2", title="Base 2")
    (layers_dir / "base2.json").write_text(base2.to_json())
    
    with pytest.raises(SystemExit):
        parse_dag_from_layers(str(layers_dir), None)

def test_parse_dag_from_layers_duplicate_id(tmp_path):
    layers_dir = tmp_path / "layers"
    layers_dir.mkdir()
    
    base = PatchLayer(id="base", title="Base")
    (layers_dir / "base.json").write_text(base.to_json())
    
    child1 = PatchLayer(id="child", parent="base", title="Child 1")
    (layers_dir / "child1.json").write_text(child1.to_json())
    
    child2 = PatchLayer(id="child", parent="base", title="Child 2")
    (layers_dir / "child2.json").write_text(child2.to_json())
    
    with pytest.raises(SystemExit):
        parse_dag_from_layers(str(layers_dir), None)

def test_layer_dag_get_all_ancestors_invalid_node():
    dag = LayerDAG()
    assert dag.get_all_ancestors("nonexistent") == []

def test_layer_dag_get_all_ancestors_failure():
    dag = LayerDAG()
    dag.create_node("root")
    dag.create_node("child", parent="root")
    with patch("shared.dag.TopologicalSorter", side_effect=Exception("TopologicalSorter failed")):
        ancestors = dag.get_all_ancestors("child")
        assert len(ancestors) == 1
        assert ancestors[0].identifier == "child"

def test_layer_dag_get_all_paths_invalid_target():
    dag = LayerDAG()
    # No root
    assert dag.get_all_paths("target") == []
    
    dag.create_node("root")
    # target not in dg
    assert dag.get_all_paths("target") == []

def test_layer_dag_create_node_already_root():
    dag = LayerDAG()
    dag.create_node("root")
    dag.create_node("other") # root is already set to "root", so "other" won't be root
    assert dag.root == "root"

def test_parse_path_configs_invalid_json(tmp_path):
    dag = LayerDAG()
    dag.create_node("root")
    paths_dir = tmp_path / "paths"
    paths_dir.mkdir()
    (paths_dir / "bad.json").write_text("{not json}")
    
    # Should not raise exception because of try-except block
    parse_path_configs_and_add_dummy_nodes(str(paths_dir), dag)
    assert len(dag.nodes) == 1

def test_parse_dag_from_layers_with_paths(tmp_path):
    layers_dir = tmp_path / "layers"
    layers_dir.mkdir()
    (layers_dir / "base.json").write_text(PatchLayer(id="base", title="Base").to_json())
    
    paths_dir = tmp_path / "paths"
    paths_dir.mkdir()
    path_data = LayerPathSet(paths=[
        LayerPath(id="p1", target_layer="base", layers=["base"])
    ])
    (paths_dir / "p1.json").write_text(path_data.to_json())
    
    dag, _ = parse_dag_from_layers(str(layers_dir), str(paths_dir))
    assert "p1" in dag.nodes

def test_validate_path_warnings(caplog):
    dag = LayerDAG()
    dag.create_node("root")
    
    # Connectivity broken
    dag.create_node("leaf") # Not child of root
    path = LayerPath(id="p1", target_layer="leaf", layers=["root", "leaf"])
    with caplog.at_level(logging.WARNING):
        assert validate_path(path, dag) is False
        assert "Connectivity broken" in caplog.text

    # Target layer mismatch
    caplog.clear()
    dag.edges["leaf"] = {"root"} # Fix connectivity
    path = LayerPath(id="p2", target_layer="other", layers=["root", "leaf"])
    with caplog.at_level(logging.WARNING):
        assert validate_path(path, dag) is False
        assert "Target layer other does not match the end of path" in caplog.text

def test_parse_dag_from_layers_no_layers(tmp_path):
    # Test when layersdir is provided but empty
    layers_dir = tmp_path / "empty_layers"
    layers_dir.mkdir()
    
    dag, files = parse_dag_from_layers(str(layers_dir), None)
    assert dag.root is None
    assert files == []

def test_parse_dag_from_layers_invalid_dir():
    with pytest.raises(SystemExit):
        parse_dag_from_layers("/nonexistent_dir_random_name_123", None)

def test_parse_dag_from_layers_add_existing_parent(tmp_path):
    layers_dir = tmp_path / "layers"
    layers_dir.mkdir()
    
    # base1 is the root
    base1 = PatchLayer(id="base1", title="B1")
    (layers_dir / "base1.json").write_text(base1.to_json())
    
    # base2 depends on base1
    base2 = PatchLayer(id="base2", parent="base1", title="B2")
    # Named so it comes AFTER child in glob
    (layers_dir / "z_base2.json").write_text(base2.to_json())
    
    # child has parent base2 (single) AND parents [base1] (multi)
    child_mixed = PatchLayer(id="child", parent="base2", parents=["base1"], title="Mixed")
    # Named so it comes BEFORE base2 in glob
    (layers_dir / "a_child.json").write_text(child_mixed.to_json())
    
    dag, _ = parse_dag_from_layers(str(layers_dir), None)
    assert "base1" in dag.edges["child"]
    assert "base2" in dag.edges["child"]

def test_parse_dag_from_layers_multi_parent_elif(tmp_path):
    layers_dir = tmp_path / "layers"
    layers_dir.mkdir()
    
    base1 = PatchLayer(id="base1", title="B1")
    (layers_dir / "base1.json").write_text(base1.to_json())
    
    base2 = PatchLayer(id="base2", parent="base1", title="B2")
    (layers_dir / "base2.json").write_text(base2.to_json())
    
    # child has parents [base1, base2]
    # In one iteration, it might be added via base1.
    # In next iteration, base2 is added, then child adds base2 via parents elif.
    child = PatchLayer(id="child", parents=["base1", "base2"], title="Child")
    (layers_dir / "child.json").write_text(child.to_json())
    
    dag, _ = parse_dag_from_layers(str(layers_dir), None)
    assert "base1" in dag.edges["child"]
    assert "base2" in dag.edges["child"]
