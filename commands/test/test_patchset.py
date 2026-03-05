import pytest
import os
import treelib
import subprocess
import logging
from unittest.mock import MagicMock, patch
from click.testing import CliRunner
from commands.patchset import (
    extract_patch_commente,
    get_all_referred_layers,
    create_patchset,
    load_patches,
    collect_patch,
    collect_files,
    collect_script,
    collect_patches,
    create_run_patches,
    add_scripted,
    add_files,
    add_patches,
    patchset,
    document
)
from configuration.data import PatchLayer, PatchConfig, PatchSet

def test_patchset_command_no_args(caplog):
    runner = CliRunner()
    caplog.set_level(logging.ERROR)
    # Mocking layer_config_exists to return True so we pass need_layer_config
    with patch("shared.helpers.layer_config_exists", return_value=True):
        result = runner.invoke(patchset, ["out"])
        assert any("You need to specify either a layer" in record.message for record in caplog.records)
        assert result.exit_code != 0

def test_document_command_invalid_outpath(caplog):
    runner = CliRunner()
    caplog.set_level(logging.ERROR)
    with patch("shared.helpers.layer_config_exists", return_value=True):
        result = runner.invoke(document, ["-l", "root", "nonexistent_dir"])
        assert any("Outpath must exist" in record.message for record in caplog.records)
        assert result.exit_code != 0

def test_add_scripted(tmp_path):
    scripts_dir = tmp_path / "scripts"
    scripts_dir.mkdir()
    (scripts_dir / "test.sh").write_text("echo test")
    
    patch_config = PatchConfig(basePath=".", patch="", script="test.sh", scriptArgs=["arg1"])
    
    with patch("subprocess.run") as mock_run, \
         patch("commands.baseline.add_recursive_commit") as mock_commit:
        mock_run.return_value = MagicMock(stdout="out", stderr="err", returncode=0)
        
        add_scripted(str(tmp_path), str(scripts_dir), patch_config)
        
        mock_run.assert_called_once()
        assert "test.sh arg1" in mock_run.call_args[0][0]
        mock_commit.assert_called_once()

def test_add_files(tmp_path):
    files_dir = tmp_path / "files"
    files_dir.mkdir()
    (files_dir / "source").mkdir()
    (files_dir / "source" / "data.txt").write_text("data")
    
    work_dir = tmp_path / "work"
    work_dir.mkdir()
    
    patch_config = PatchConfig(basePath=".", patch="", copyPattern="data.txt", copySourceDir="source")
    
    # We need to use real os.chdir to affect relative path operations in add_files
    original_cwd = os.getcwd()
    try:
        os.chdir(str(work_dir))
        with patch("commands.baseline.add_recursive_commit") as mock_commit:
            add_files(str(work_dir), str(files_dir), patch_config)
            
            assert os.path.exists("data.txt")
            mock_commit.assert_called_once()
    finally:
        os.chdir(original_cwd)

def test_add_patches(tmp_path):
    patchset_dir = tmp_path / "patchset"
    patchset_dir.mkdir()
    (patchset_dir / "test.patch").write_text("patch content")
    
    patch_config = PatchConfig(basePath=".", patch="test.patch")
    
    with patch("git.Repo") as mock_repo_class:
        mock_repo = mock_repo_class.return_value
        add_patches(False, str(patchset_dir), str(tmp_path), patch_config)
        
        mock_repo.git.apply.assert_called_with(['-3', os.path.abspath(os.path.join(str(patchset_dir), "test.patch"))])
        mock_repo.git.commit.assert_called()

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

def test_get_all_referred_layers_unknown(capsys):
    tree = treelib.Tree()
    with pytest.raises(SystemExit):
        get_all_referred_layers("unknown", tree)

def test_create_patchset():
    tree = treelib.Tree()
    p1 = PatchConfig(basePath=".", patch="p1.patch")
    p2 = PatchConfig(basePath=".", patch="p2.patch")
    
    layer1 = PatchLayer(id="root", title="Root", patches=[p1])
    layer2 = PatchLayer(id="leaf", parent="root", title="Leaf", patches=[p2])
    
    tree.create_node(layer1.id, layer1.id, data=layer1)
    tree.create_node(layer2.id, layer2.id, parent=layer1.id, data=layer2)
    
    ctx = MagicMock()
    ctx.obj = {'LAYER_TREE': tree}
    
    patchset = create_patchset(ctx, "leaf", [], [])
    
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
    
    ctx = MagicMock()
    ctx.obj = {'LAYER_TREE': tree}
    
    # Include only tag1
    patchset = create_patchset(ctx, "root", ["tag1"], [])
    assert len(patchset.patches) == 2
    assert patchset.patches[1].patch == "p1.patch"
    
    # Exclude tag1
    patchset = create_patchset(ctx, "root", [], ["tag1"])
    assert len(patchset.patches) == 2
    assert patchset.patches[1].patch == "p2.patch"

def test_load_patches(tmp_path):
    ps = PatchSet(patches=[PatchConfig(basePath=".", patch="test.patch")])
    ps_file = tmp_path / "patches.json"
    ps_file.write_text(ps.to_json())
    
    loaded = load_patches(str(tmp_path))
    assert len(loaded.patches) == 1
    assert loaded.patches[0].patch == "test.patch"

def test_load_patches_not_found(tmp_path):
    with pytest.raises(SystemExit):
        load_patches(str(tmp_path / "nonexistent"))

def test_collect_patch(tmp_path):
    patchdir = tmp_path / "patches"
    patchdir.mkdir()
    (patchdir / "test.patch").write_text("patch content")
    
    target_path = tmp_path / "target"
    target_path.mkdir()
    
    patch = PatchConfig(basePath="subdir", patch="test.patch")
    collect_patch(str(patchdir), str(target_path), 1, patch)
    
    assert patch.patch == os.path.join("subdir", "00001_test.patch")
    assert os.path.exists(target_path / "subdir" / "00001_test.patch")

def test_collect_files(tmp_path):
    file_dir = tmp_path / "files"
    file_dir.mkdir()
    (file_dir / "src").mkdir()
    (file_dir / "src" / "file.txt").write_text("content")
    
    target_path = tmp_path / "target"
    target_path.mkdir()
    
    patch = PatchConfig(basePath=".", patch="", copyPattern="**/*", copySourceDir="src")
    collect_files(str(target_path), str(file_dir), patch)
    
    assert os.path.exists(target_path / "files" / "src" / "file.txt")

def test_collect_script(tmp_path):
    script_dir = tmp_path / "scripts"
    script_dir.mkdir()
    (script_dir / "script.sh").write_text("echo hello")
    (script_dir / "resource.txt").write_text("resource")
    
    target_path = tmp_path / "target"
    target_path.mkdir()
    
    patch = PatchConfig(basePath=".", patch="", script="script.sh", scriptResources=["resource.txt"])
    collect_script(str(target_path), str(script_dir), patch)
    
    assert os.path.exists(target_path / "scripts" / "script.sh")
    assert os.path.exists(target_path / "scripts" / "resource.txt")

def test_collect_patches(tmp_path):
    patchdir = tmp_path / "patches"
    patchdir.mkdir()
    (patchdir / "p1.patch").write_text("p1")
    
    scriptdir = tmp_path / "scripts"
    scriptdir.mkdir()
    (scriptdir / "s1.sh").write_text("s1")
    
    filedir = tmp_path / "files"
    filedir.mkdir()
    (filedir / "f1.txt").write_text("f1")
    
    target_path = tmp_path / "target"
    target_path.mkdir()
    
    ps = PatchSet(patches=[
        PatchConfig(basePath="", patch="", baseline="b1"),
        PatchConfig(basePath="p", patch="p1.patch"),
        PatchConfig(basePath="s", patch="", script="s1.sh"),
        PatchConfig(basePath="f", patch="", copyPattern="f1.txt", copySourceDir="")
    ])
    
    new_ps = collect_patches(str(patchdir), ps, str(target_path), str(filedir), str(scriptdir))
    
    assert len(new_ps.patches) == 4
    assert new_ps.patches[1].patch.endswith("p1.patch")
    assert os.path.exists(target_path / "scripts" / "s1.sh")
    assert os.path.exists(target_path / "files" / "f1.txt")

def test_create_run_patches(tmp_path):
    ps = PatchSet(patches=[
        PatchConfig(basePath="sub", patch="00001_p1.patch", updateModulesAfterPatch=True)
    ])
    create_run_patches(ps, str(tmp_path))
    
    run_script = tmp_path / "runPatches.sh"
    assert run_script.exists()
    content = run_script.read_text()
    assert "pushd sub" in content
    assert "git submodule update" in content
