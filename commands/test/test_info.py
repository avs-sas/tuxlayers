import pytest
import logging
from click.testing import CliRunner
from commands.info import info
from configuration.data import PatchLayer
from shared.dag import LayerDAG

@pytest.fixture
def mock_ctx_obj():
    dag = LayerDAG()
    layer1 = PatchLayer(id="base", title="Base Layer")
    layer2 = PatchLayer(id="child", parent="base", title="Child Layer")
    dag.create_node(layer1.id, tag=layer1.id, data=layer1)
    dag.create_node(layer2.id, tag=layer2.id, parent=layer1.id, data=layer2)

    return {
        'LEAVES': dag.leaves(),
        'LAYER_SOURCE': '/mock/path',
        'LAYER_FILES': ['base.json', 'child.json'],
        'LAYER_DAG': dag
    }

def test_info_no_args(mock_ctx_obj, caplog):
    caplog.set_level(logging.INFO)
    runner = CliRunner()
    result = runner.invoke(info, obj=mock_ctx_obj)
    assert result.exit_code == 0
    assert "Available leafs:" in caplog.text
    assert "- child: Child Layer" in caplog.text
    assert "Layer source in use:" in caplog.text
    assert "Path: /mock/path" in caplog.text
    # Tree display goes to stdout
    assert "base" in result.output
    assert "└── child" in result.output

def test_info_layers(mock_ctx_obj, caplog):
    caplog.set_level(logging.INFO)
    runner = CliRunner()
    result = runner.invoke(info, ['--layers'], obj=mock_ctx_obj)
    assert result.exit_code == 0
    assert "Available leafs:" in caplog.text
    assert "Layer source in use:" not in caplog.text

def test_info_config(mock_ctx_obj, caplog):
    caplog.set_level(logging.INFO)
    runner = CliRunner()
    result = runner.invoke(info, ['--config'], obj=mock_ctx_obj)
    assert result.exit_code == 0
    assert "Layer source in use:" in caplog.text
    assert "Available leafs:" not in caplog.text

def test_info_tree_display(mock_ctx_obj):
    runner = CliRunner()
    result = runner.invoke(info, ['--tree'], obj=mock_ctx_obj)
    assert result.exit_code == 0
    assert "base" in result.output
    assert "└── child" in result.output

def test_info_paths(mock_ctx_obj, caplog):
    caplog.set_level(logging.INFO)
    runner = CliRunner()
    # Test path to a specific node
    result = runner.invoke(info, ['--paths', 'child'], obj=mock_ctx_obj)
    assert result.exit_code == 0
    assert "Found 1 unique path(s) to layer 'child':" in caplog.text
    assert "Path 1: base -> child" in caplog.text
    assert "Use: -l base,child" in caplog.text

def test_info_paths_all(mock_ctx_obj, caplog):
    caplog.set_level(logging.INFO)
    runner = CliRunner()
    # Test paths for all nodes
    result = runner.invoke(info, ['--paths'], obj=mock_ctx_obj)
    assert result.exit_code == 0
    assert "Printing paths for all nodes in the DAG:" in caplog.text
    assert "Found 1 unique path(s) to layer 'base':" in caplog.text
    assert "Found 1 unique path(s) to layer 'child':" in caplog.text

def test_info_dot(mock_ctx_obj, tmp_path):
    runner = CliRunner()
    dot_file = tmp_path / "test.dot"
    result = runner.invoke(info, ['--dot', str(dot_file)], obj=mock_ctx_obj)
    assert result.exit_code == 0
    assert dot_file.exists()
    content = dot_file.read_text()
    assert "strict digraph" in content
    assert 'base -> child' in content
