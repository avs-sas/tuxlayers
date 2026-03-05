import pytest
import os
import treelib
from commands.patchset import (
    extract_patch_commente,
    get_all_referred_layers,
    create_patchset
)
from configuration.data import PatchLayer, PatchConfig

def test_extract_patch_commente(tmp_path):
    patch_file = tmp_path / "test.patch"
    patch_file.write_text("# This is a comment\n# Another line\n---\nPatch content starts here")
    
    comments = extract_patch_commente(str(patch_file))
    assert comments == ["This is a comment", "Another line"]

def test_extract_patch_commente_no_comments(tmp_path):
    patch_file = tmp_path / "test.patch"
    patch_file.write_text("---\nPatch content starts here")
    
    comments = extract_patch_commente(str(patch_file))
    assert comments == []

def test_get_all_referred_layers():
    tree = treelib.Tree()
    layer1 = PatchLayer(id="root", title="Root Layer")
    layer2 = PatchLayer(id="mid", parent="root", title="Mid Layer")
    layer3 = PatchLayer(id="leaf", parent="mid", title="Leaf Layer")
    
    tree.create_node(layer1.id, layer1.id, data=layer1)
    tree.create_node(layer2.id, layer2.id, parent=layer1.id, data=layer2)
    tree.create_node(layer3.id, layer3.id, parent=layer2.id, data=layer3)
    
    layers = list(get_all_referred_layers("leaf", tree))
    assert len(layers) == 3
    assert layers[0].id == "root"
    assert layers[1].id == "mid"
    assert layers[2].id == "leaf"

def test_create_patchset():
    tree = treelib.Tree()
    p1 = PatchConfig(basePath=".", patch="p1.patch")
    p2 = PatchConfig(basePath=".", patch="p2.patch")
    
    layer1 = PatchLayer(id="root", title="Root", patches=[p1])
    layer2 = PatchLayer(id="leaf", parent="root", title="Leaf", patches=[p2])
    
    tree.create_node(layer1.id, layer1.id, data=layer1)
    tree.create_node(layer2.id, layer2.id, parent=layer1.id, data=layer2)
    
    ctx = type('obj', (object,), {'obj': {'LAYER_TREE': tree}})
    
    patchset = create_patchset(ctx, "leaf", [], [])
    
    # Expectations:
    # 1. Baseline for root
    # 2. Patches for root (p1)
    # 3. Baseline for leaf
    # 4. Patches for leaf (p2)
    
    assert len(patchset.patches) == 4
    assert patchset.patches[0].baseline == "root"
    assert patchset.patches[1].patch == "p1.patch"
    assert patchset.patches[2].baseline == "leaf"
    assert patchset.patches[3].patch == "p2.patch"

def test_create_patchset_with_filters():
    tree = treelib.Tree()
    p1 = PatchConfig(basePath=".", patch="p1.patch", tags="tag1")
    p2 = PatchConfig(basePath=".", patch="p2.patch", tags="tag2")
    
    layer1 = PatchLayer(id="root", title="Root", patches=[p1, p2])
    tree.create_node(layer1.id, layer1.id, data=layer1)
    
    ctx = type('obj', (object,), {'obj': {'LAYER_TREE': tree}})
    
    # Include only tag1
    patchset = create_patchset(ctx, "root", ["tag1"], [])
    # 1 baseline + 1 patch
    assert len(patchset.patches) == 2
    assert patchset.patches[1].patch == "p1.patch"
    
    # Exclude tag1
    patchset = create_patchset(ctx, "root", [], ["tag1"])
    assert len(patchset.patches) == 2
    assert patchset.patches[1].patch == "p2.patch"
