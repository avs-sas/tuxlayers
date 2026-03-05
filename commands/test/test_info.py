import pytest
import logging
from click.testing import CliRunner
from commands.info import info
from configuration.data import PatchLayer
import treelib

@pytest.fixture
def mock_ctx_obj():
    tree = treelib.Tree()
    layer1 = PatchLayer(id="base", title="Base Layer")
    layer2 = PatchLayer(id="child", parent="base", title="Child Layer")
    tree.create_node(layer1.id, layer1.id, data=layer1)
    tree.create_node(layer2.id, layer2.id, parent=layer1.id, data=layer2)

    return {
        'LEAVES': tree.leaves(),
        'LAYER_SOURCE': '/mock/path',
        'LAYER_FILES': ['base.json', 'child.json'],
        'LAYER_TREE': tree
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
    result = runner.invoke(info, ['--tree', '-f', 'display'], obj=mock_ctx_obj)
    assert result.exit_code == 0
    assert "base" in result.output
    assert "└── child" in result.output

def test_info_tree_json(mock_ctx_obj):
    runner = CliRunner()
    result = runner.invoke(info, ['--tree', '-f', 'json'], obj=mock_ctx_obj)
    assert result.exit_code == 0
    assert '"base"' in result.output
    assert '"child"' in result.output
