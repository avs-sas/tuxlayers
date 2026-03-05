import pytest
import datetime
from configuration.data import (
    PatchConfig,
    PatchSet,
    PatchLayer,
    PatchInfo,
    LayerInfo,
    Documentation
)

def test_patch_config_valid():
    # Only patch
    p = PatchConfig(basePath=".", patch="p1.patch")
    assert p.valid() is True
    assert p.is_patch() is True
    assert p.is_baseline() is False
    assert p.is_script() is False
    assert p.is_copy() is False

    # Only baseline
    p = PatchConfig(basePath=".", patch="", baseline="b1")
    assert p.valid() is True
    assert p.is_baseline() is True
    assert p.is_patch() is False

    # Only script
    p = PatchConfig(basePath=".", patch="", script="s1.sh")
    assert p.valid() is True
    assert p.is_script() is True
    assert p.is_patch() is False

    # Only copy
    p = PatchConfig(basePath=".", patch="", copyPattern="*")
    assert p.valid() is True
    assert p.is_copy() is True
    assert p.is_patch() is False

    # Invalid: patch and baseline
    p = PatchConfig(basePath=".", patch="p1.patch", baseline="b1")
    assert p.valid() is False

    # Invalid: none
    p = PatchConfig(basePath=".", patch="")
    assert p.valid() is False

def test_patch_config_has_tags():
    p = PatchConfig(basePath=".", patch="p1.patch", tags="tag1")
    assert p.has_tags() is True
    p.tags = ""
    assert p.has_tags() is False

def test_patch_layer_tree_ids_valid():
    # No parents, no tree_ids
    pl = PatchLayer(id="L1")
    assert pl.tree_ids_valid() is True

    # Parents, matching tree_ids
    pl = PatchLayer(id="L1", parents=["P1", "P2"], tree_ids=["T1", "T2"])
    assert pl.tree_ids_valid() is True

    # Parents, no tree_ids
    pl = PatchLayer(id="L1", parents=["P1", "P2"])
    assert pl.tree_ids_valid() is True

    # Parents, mismatch length tree_ids
    pl = PatchLayer(id="L1", parents=["P1", "P2"], tree_ids=["T1"])
    assert pl.tree_ids_valid() is False

    # Parents, empty tree_id in list
    pl = PatchLayer(id="L1", parents=["P1", "P2"], tree_ids=["T1", ""])
    assert pl.tree_ids_valid() is False

def test_patch_layer_have_parent():
    pl = PatchLayer(id="L1", parent="P1")
    assert pl.have_parent() is True

    pl = PatchLayer(id="L1", parents=["P1"])
    assert pl.have_parent() is True

    pl = PatchLayer(id="L1")
    assert pl.have_parent() is False

def test_patch_layer_is_multi_parent():
    pl = PatchLayer(id="L1", parents=["P1", "P2"])
    assert pl.is_multi_parent() is True

    pl = PatchLayer(id="L1", parent="P1", parents=["P1", "P2"])
    assert pl.is_multi_parent() is False

    pl = PatchLayer(id="L1", parent="P1")
    assert pl.is_multi_parent() is False

def test_patch_layer_get_id_from_index():
    pl = PatchLayer(id="L1", parents=["P1", "P2"], tree_ids=["T1", "T2"])
    assert pl.get_id_from_index(0) == "T1"
    assert pl.get_id_from_index(1) == "T2"

    pl = PatchLayer(id="L1", parents=["P1", "P2"])
    assert pl.get_id_from_index(0) == "L1_1"
    assert pl.get_id_from_index(1) == "L1_2"

    pl = PatchLayer(id="L1", parents=["P1", "P2"], tree_ids=["T1"])
    assert pl.get_id_from_index(0) == ""

def test_patch_set():
    ps = PatchSet(patches=[PatchConfig(basePath=".", patch="p1.patch")])
    assert len(ps.patches) == 1

def test_patch_info():
    pi = PatchInfo(patchfile="p1.patch", comments=["comment 1"])
    assert pi.patchfile == "p1.patch"
    assert pi.comments == ["comment 1"]

def test_layer_info():
    li = LayerInfo(id="L1", title="Title", description="Desc")
    assert li.id == "L1"
    assert li.title == "Title"
    assert li.description == "Desc"

def test_documentation():
    now = datetime.datetime.now()
    li = LayerInfo(id="L1", title="Title", description="Desc")
    doc = Documentation(timestamp=now, primaryLayer=li)
    assert doc.timestamp == now
    assert doc.primaryLayer == li
    assert isinstance(doc.primaryLayer, LayerInfo)
    assert len(doc.patches) == 0
    assert len(doc.layers) == 0
    assert isinstance(doc.misc, dict)

def test_documentation_default_primary_layer():
    doc = Documentation()
    # If the trailing comma exists, this will be a tuple.
    assert isinstance(doc.primaryLayer, LayerInfo)
    assert isinstance(doc.timestamp, datetime.datetime)
