import pytest
import os
import treelib
import subprocess
import logging
import git
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

def test_collect_patch_not_found(tmp_path):
    target_path = tmp_path / "target"
    target_path.mkdir()
    patch = PatchConfig(basePath=".", patch="nonexistent.patch")
    with pytest.raises(SystemExit):
        collect_patch(str(tmp_path), str(target_path), 1, patch)

def test_load_patches_invalid_json(tmp_path):
    ps_file = tmp_path / "patches.json"
    ps_file.write_text("invalid json")
    with pytest.raises(SystemExit):
        load_patches(str(tmp_path))

def test_create_patchset_tags_none():
    tree = treelib.Tree()
    p1 = PatchConfig(basePath=".", patch="p1.patch", tags=None)
    layer1 = PatchLayer(id="root", title="Root", patches=[p1])
    tree.create_node(layer1.id, layer1.id, data=layer1)
    ctx = MagicMock()
    ctx.obj = {'LAYER_TREE': tree}
    # Should not crash and include patch if no filters
    patchset = create_patchset(ctx, "root", [], [])
    assert len(patchset.patches) == 2

def test_document_command_no_template(tmp_path):
    runner = CliRunner()
    tree = treelib.Tree()
    layer1 = PatchLayer(id="root", title="Root", description="Desc")
    tree.create_node(layer1.id, layer1.id, data=layer1)
    ctx_obj = {'LAYER_TREE': tree}
    with patch("shared.helpers.layer_config_exists", return_value=True), \
         patch("commands.patchset.create_patchset", return_value=PatchSet(patches=[])), \
         patch("commands.patchset.get_all_referred_layers", return_value=[layer1]):
        outdir = tmp_path / "docs"
        outdir.mkdir()
        result = runner.invoke(document, ["-l", "root", str(outdir)], obj=ctx_obj)
        assert result.exit_code == 0
        assert len(list(outdir.glob("*_default.md"))) == 1

def test_add_patches_fixwhitespace_retry_commit(tmp_path):
    # This specifically targets the "Retrying to commit patch" branch
    patchset_dir = tmp_path / "patchset"
    patchset_dir.mkdir()
    (patchset_dir / "test.patch").write_text("patch")
    patch_config = PatchConfig(basePath=".", patch="test.patch")
    with patch("git.Repo") as mock_repo_class:
        mock_repo = mock_repo_class.return_value
        # First commit fails, second succeeds
        mock_repo.git.commit.side_effect = [git.exc.GitError("err"), None]
        add_patches(True, str(patchset_dir), str(tmp_path), patch_config)
        assert mock_repo.git.commit.call_count == 2

def test_add_patches_git_error(tmp_path):
    patch_config = PatchConfig(basePath=".", patch="test.patch")
    with patch("git.Repo") as mock_repo_class:
        mock_repo = mock_repo_class.return_value
        mock_repo.git.apply.side_effect = git.exc.GitError("err")
        with pytest.raises(SystemExit):
            add_patches(False, str(tmp_path), str(tmp_path), patch_config)

def test_extract_patch_commente_complex_file(tmp_path):
    patch_file = tmp_path / "test.patch"
    # Mix of comments, blank lines, and content
    patch_file.write_text("# Comment 1\n\n# Comment 2\n---\nPatch content")
    comments = extract_patch_commente(str(patch_file))
    assert comments == ["Comment 1", "Comment 2"]

def test_patchset_command_single_layer(tmp_path):
    runner = CliRunner()
    tree = treelib.Tree()
    tree.create_node("root", "root", data=PatchLayer(id="root"))
    ctx_obj = {'LAYER_TREE': tree}
    
    # We need real patchdir, scriptdir, filedir
    patchdir = tmp_path / "patches"
    patchdir.mkdir()
    scriptdir = tmp_path / "scripts"
    scriptdir.mkdir()
    filedir = tmp_path / "files"
    filedir.mkdir()
    
    with patch("shared.helpers.layer_config_exists", return_value=True), \
         patch("shared.helpers.need_layer_config"):
        from commands.patchset import patchset
        result = runner.invoke(patchset, ["-l", "root", "-p", str(patchdir), "-s", str(scriptdir), "-f", str(filedir), str(tmp_path / "out")], obj=ctx_obj)
        assert result.exit_code == 0
        assert os.path.exists(tmp_path / "out" / "patches.json")

def test_document_command_with_patches(tmp_path):
    runner = CliRunner()
    tree = treelib.Tree()
    layer1 = PatchLayer(id="root", title="Root")
    tree.create_node(layer1.id, layer1.id, data=layer1)
    ctx_obj = {'LAYER_TREE': tree}
    
    # Create a patch file with comments
    patchdir = tmp_path / "patches"
    patchdir.mkdir()
    p1_file = patchdir / "p1.patch"
    p1_file.write_text("# P1 Comment\n---\nContent")
    
    ps = PatchSet(patches=[PatchConfig(basePath=".", patch="p1.patch")])
    
    with patch("shared.helpers.layer_config_exists", return_value=True), \
         patch("commands.patchset.create_patchset", return_value=ps), \
         patch("commands.patchset.get_all_referred_layers", return_value=[layer1]):
        outdir = tmp_path / "docs"
        outdir.mkdir()
        result = runner.invoke(document, ["-l", "root", "-p", str(patchdir), str(outdir)], obj=ctx_obj)
        assert result.exit_code == 0
        assert len(list(outdir.glob("*_default.md"))) == 1

def test_apply_command_inconsistent_args(tmp_path):
    runner = CliRunner()
    from commands.patchset import apply
    with patch("shared.helpers.layer_config_exists", return_value=True):
        # fromLayer without addBaselines
        result = runner.invoke(apply, ["-p", str(tmp_path), "-w", str(tmp_path), "-f", "layer1"])
        assert result.exit_code != 0

def test_apply_command_with_baseline_and_script(tmp_path):
    runner = CliRunner()
    patchset_dir = tmp_path / "patchset"
    patchset_dir.mkdir()
    (patchset_dir / "scripts").mkdir()
    (patchset_dir / "scripts" / "s1.sh").write_text("echo s1")
    
    ps = PatchSet(patches=[
        PatchConfig(basePath=".", patch="", baseline="b1"),
        PatchConfig(basePath=".", patch="", script="s1.sh", comment="Script comment")
    ])
    (patchset_dir / "patches.json").write_text(ps.to_json())
    
    workdir = tmp_path / "work"
    workdir.mkdir()
    
    with patch("git.Repo"), \
         patch("commands.baseline.add_baseline_internal") as mock_add_baseline, \
         patch("subprocess.run") as mock_run, \
         patch("commands.baseline.add_recursive_commit") as mock_commit, \
         patch("shared.helpers.layer_config_exists", return_value=True):
        mock_run.return_value = MagicMock(stdout="out", stderr="err", returncode=0)
        from commands.patchset import apply
        result = runner.invoke(apply, ["-p", str(patchset_dir), "-w", str(workdir), "-b"])
        assert result.exit_code == 0
        mock_add_baseline.assert_called_once()
        mock_run.assert_called_once()
        mock_commit.assert_called()

def test_collect_patches_invalid_paths(tmp_path):
    with pytest.raises(SystemExit):
        collect_patches(str(tmp_path / "nonexistent"), PatchSet(), str(tmp_path), "", "")
    
    with pytest.raises(SystemExit):
        collect_patches(str(tmp_path), PatchSet(), str(tmp_path / "nonexistent"), "", "")

def test_create_all_sets_outpath_exists(tmp_path):
    outdir = tmp_path / "out"
    outdir.mkdir()
    from commands.patchset import create_all_sets
    with pytest.raises(SystemExit):
        create_all_sets(MagicMock(), "", "", "", str(outdir), [], [])

def test_add_scripted_scripts_dir_missing(tmp_path):
    with pytest.raises(SystemExit):
        add_scripted(str(tmp_path), str(tmp_path / "nonexistent"), PatchConfig(basePath=".", patch="", script="s.sh"))

def test_document_command_template_not_found(tmp_path):
    runner = CliRunner()
    tree = treelib.Tree()
    tree.create_node("root", "root", data=PatchLayer(id="root"))
    ctx_obj = {'LAYER_TREE': tree}
    with patch("shared.helpers.layer_config_exists", return_value=True), \
         patch("commands.patchset.create_patchset", return_value=PatchSet(patches=[])):
        result = runner.invoke(document, ["-l", "root", "-t", str(tmp_path / "nonexistent"), "."], obj=ctx_obj)
        assert result.exit_code != 0

def test_apply_command_invalid_workdir(tmp_path):
    runner = CliRunner()
    patchset_dir = tmp_path / "patchset"
    patchset_dir.mkdir()
    (patchset_dir / "patches.json").write_text(PatchSet().to_json())
    from commands.patchset import apply
    with patch("shared.helpers.layer_config_exists", return_value=True):
        result = runner.invoke(apply, ["-p", str(patchset_dir), "-w", str(tmp_path / "nonexistent")])
        assert result.exit_code != 0

def test_add_patches_invalid_config(tmp_path):
    from commands.patchset import apply
    # basePath and patch are both empty -> invalid
    patch_cfg = PatchConfig(basePath="", patch="")
    # We need to trigger the loop in apply
    ps = PatchSet(patches=[patch_cfg])
    (tmp_path / "patches.json").write_text(ps.to_json())
    runner = CliRunner()
    with patch("shared.helpers.layer_config_exists", return_value=True):
        result = runner.invoke(apply, ["-p", str(tmp_path), "-w", str(tmp_path)])
        assert result.exit_code != 0

def test_print_script_results_with_stderr():
    from commands.patchset import print_script_results
    patch_cfg = PatchConfig(basePath=".", patch="", script="s.sh")
    with patch("commands.patchset.logger.info") as mock_info:
        print_script_results(patch_cfg, "out", "err")
        # Check if any call contains "wrote this to stderr" in its first argument
        assert any("wrote this to stderr" in str(call[0][0]) for call in mock_info.call_args_list)

def test__patchset_internal_outpath_exists(tmp_path):
    outdir = tmp_path / "out"
    outdir.mkdir()
    from commands.patchset import _patchset_internal
    with pytest.raises(SystemExit):
        _patchset_internal(MagicMock(), "root", "", "", "", str(outdir), [], [])

def test_document_command_with_template(tmp_path):
    runner = CliRunner()
    tree = treelib.Tree()
    layer1 = PatchLayer(id="root", title="Root")
    tree.create_node(layer1.id, layer1.id, data=layer1)
    ctx_obj = {'LAYER_TREE': tree}
    
    template = tmp_path / "template.jinja2"
    template.write_text("Template content for {{ data.primaryLayer }}")
    
    with patch("shared.helpers.layer_config_exists", return_value=True), \
         patch("commands.patchset.create_patchset", return_value=PatchSet(patches=[])), \
         patch("commands.patchset.get_all_referred_layers", return_value=[layer1]):
        outdir = tmp_path / "docs"
        outdir.mkdir()
        result = runner.invoke(document, ["-l", "root", "-t", str(template), str(outdir)], obj=ctx_obj)
        assert result.exit_code == 0
        
        # Check if file with template name (sans .jinja2) was created
        files = list(outdir.glob("*template"))
        assert len(files) == 1

def test_create_patchset_complex_filtering():
    tree = treelib.Tree()
    p1 = PatchConfig(basePath=".", patch="p1.patch", tags="tag1, tag2")
    p2 = PatchConfig(basePath=".", patch="p2.patch", tags="tag2, tag3")
    p3 = PatchConfig(basePath=".", patch="p3.patch", tags="tag4")
    
    layer1 = PatchLayer(id="root", title="Root", patches=[p1, p2, p3])
    tree.create_node(layer1.id, layer1.id, data=layer1)
    
    ctx = MagicMock()
    ctx.obj = {'LAYER_TREE': tree}
    
    # Include tag1, exclude tag3 -> only p1
    ps = create_patchset(ctx, "root", ["tag1"], ["tag3"])
    # 2 entries (baseline + p1)
    assert len(ps.patches) == 2
    assert ps.patches[1].patch == "p1.patch"
    
    # Include tag2, exclude tag1 -> only p2
    ps = create_patchset(ctx, "root", ["tag2"], ["tag1"])
    assert len(ps.patches) == 2
    assert ps.patches[1].patch == "p2.patch"
def test_apply_command_basic(tmp_path):
    runner = CliRunner()
    
    # Create a mock patchset directory
    patchset_dir = tmp_path / "patchset"
    patchset_dir.mkdir()
    ps = PatchSet(patches=[
        PatchConfig(basePath="repo1", patch="00001_p1.patch")
    ])
    (patchset_dir / "patches.json").write_text(ps.to_json())
    (patchset_dir / "00001_p1.patch").write_text("patch content")
    
    # Create a mock workdir
    workdir = tmp_path / "work"
    workdir.mkdir()
    (workdir / "repo1").mkdir()
    
    with patch("git.Repo") as mock_repo_class, \
         patch("shared.helpers.layer_config_exists", return_value=True):
        from commands.patchset import apply
        result = runner.invoke(apply, ["-p", str(patchset_dir), "-w", str(workdir)])
        assert result.exit_code == 0
        mock_repo_class.assert_called()

def test_apply_command_invalid_patchset(tmp_path):
    runner = CliRunner()
    from commands.patchset import apply
    with patch("shared.helpers.layer_config_exists", return_value=True):
        result = runner.invoke(apply, ["-p", str(tmp_path / "nonexistent"), "-w", str(tmp_path)])
        assert result.exit_code != 0

def test_add_patches_with_fixwhitespace(tmp_path):
    patchset_dir = tmp_path / "patchset"
    patchset_dir.mkdir()
    patch_file = patchset_dir / "test.patch"
    patch_file.write_text("patch content")
    
    patch_config = PatchConfig(basePath=".", patch="test.patch")
    
    with patch("git.Repo") as mock_repo_class:
        mock_repo = mock_repo_class.return_value
        # Simulate GitError on first apply, but success on retry
        mock_repo.git.apply.side_effect = [git.exc.GitError("err"), None]
        
        add_patches(True, str(patchset_dir), str(tmp_path), patch_config)
        
        assert mock_repo.git.apply.call_count == 2
        mock_repo.git.restore.assert_called()

def test_add_patches_with_fixwhitespace_and_empty_commit(tmp_path):
    patchset_dir = tmp_path / "patchset"
    patchset_dir.mkdir()
    patch_file = patchset_dir / "test.patch"
    patch_file.write_text("patch content")
    
    patch_config = PatchConfig(basePath=".", patch="test.patch")
    
    with patch("git.Repo") as mock_repo_class:
        mock_repo = mock_repo_class.return_value
        # Simulate GitError on first commit, but success on retry with --allow-empty
        mock_repo.git.commit.side_effect = [git.exc.GitError("err"), None]
        
        add_patches(True, str(patchset_dir), str(tmp_path), patch_config)
        
        assert mock_repo.git.commit.call_count == 2
        # Check if --allow-empty was used in the second call
        args = mock_repo.git.commit.call_args_list[1][0][0]
        assert "--allow-empty" in args

def test_add_scripted_error(tmp_path, caplog):
    scripts_dir = tmp_path / "scripts"
    scripts_dir.mkdir()
    (scripts_dir / "fail.sh").write_text("exit 1")
    
    patch_config = PatchConfig(basePath=".", patch="", script="fail.sh")
    
    with patch("subprocess.run") as mock_run:
        mock_run.side_effect = subprocess.CalledProcessError(1, "fail.sh", stderr="error msg")
        
        with pytest.raises(SystemExit):
            add_scripted(str(tmp_path), str(scripts_dir), patch_config)
        assert "Script fail.sh returned 1 when running" in caplog.text

def test_create_all_sets(tmp_path):
    tree = treelib.Tree()
    layer1 = PatchLayer(id="root", title="Root")
    layer2 = PatchLayer(id="leaf1", parent="root", title="Leaf 1")
    layer3 = PatchLayer(id="leaf2", parent="root", title="Leaf 2")
    
    tree.create_node(layer1.id, layer1.id, data=layer1)
    tree.create_node(layer2.id, layer2.id, parent=layer1.id, data=layer2)
    tree.create_node(layer3.id, layer3.id, parent=layer1.id, data=layer3)
    
    ctx = MagicMock()
    ctx.obj = {'LAYER_TREE': tree}
    
    outpath = tmp_path / "out"
    # Note: create_all_sets expects outpath to NOT exist
    
    with patch("commands.patchset._patchset_internal") as mock_internal:
        from commands.patchset import create_all_sets
        create_all_sets(ctx, "patchdir", "scriptdir", "filedir", str(outpath), [], [])
        
        assert mock_internal.call_count == 2

def test_document_command_with_misc(tmp_path):
    runner = CliRunner()
    
    tree = treelib.Tree()
    layer1 = PatchLayer(id="root", title="Root", description="Desc")
    tree.create_node(layer1.id, layer1.id, data=layer1)
    
    ctx_obj = {'LAYER_TREE': tree}
    
    with patch("shared.helpers.layer_config_exists", return_value=True), \
         patch("shared.helpers.need_layer_config"), \
         patch("commands.patchset.create_patchset", return_value=PatchSet(patches=[])), \
         patch("commands.patchset.get_all_referred_layers", return_value=[layer1]):
        
        from commands.patchset import document
        # Need to provide outpath that exists
        outdir = tmp_path / "docs"
        outdir.mkdir()
        
        result = runner.invoke(document, ["-l", "root", "-m", "mykey", "myval", str(outdir)], obj=ctx_obj)
        assert result.exit_code == 0
        
        # Check if file was created
        files = list(outdir.glob("*_default.md"))
        assert len(files) == 1
        content = files[0].read_text()
        assert "Documentation for layer root" in content

def test_patchset_command_all(tmp_path):
    runner = CliRunner()
    tree = treelib.Tree()
    tree.create_node("root", "root", data=PatchLayer(id="root"))
    ctx_obj = {'LAYER_TREE': tree}
    
    with patch("shared.helpers.layer_config_exists", return_value=True), \
         patch("commands.patchset.create_all_sets") as mock_create_all:
        from commands.patchset import patchset
        result = runner.invoke(patchset, ["-a", str(tmp_path / "out")], obj=ctx_obj)
        assert result.exit_code == 0
        mock_create_all.assert_called_once()
