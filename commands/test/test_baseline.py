import pytest
import os
import logging
import treelib
import subprocess
import hashlib
from git import Repo
from click.testing import CliRunner
from commands.baseline import (
    normalize_workdir_path,
    get_baseline_prefix,
    get_baseline_seperator,
    get_hash,
    create_baseline_string,
    is_baseline,
    get_message_parts,
    is_baseline_patch,
    baselines_are_valid,
    addbaseline,
    showbaselines,
    clean_workdir,
    reverttobaseline,
    listsubmodules,
    get_baselines,
    get_baselines_from_path,
    createpatches,
    add_recursive_commit,
    reset_hard_to_baseline,
    extract_patches,
    extract_patches_for_repo
)
from unittest.mock import MagicMock, patch

@pytest.fixture
def temp_repo(tmp_path):
    repo_path = tmp_path / "test_repo"
    repo_path.mkdir()
    repo = Repo.init(repo_path)

    # Configure git user for commits
    repo.config_writer().set_value("user", "name", "Test User").release()
    repo.config_writer().set_value("user", "email", "test@example.com").release()

    # Create an initial commit
    file = repo_path / "README.md"
    file.write_text("Test repo")
    repo.index.add(["README.md"])
    repo.index.commit("Initial commit")

    return str(repo_path)

def test_reset_hard_to_baseline():
    with patch("commands.baseline.Repo") as mock_repo_class:
        mock_repo = mock_repo_class.return_value
        mock_repo.submodules = []

        mock_commit = MagicMock()
        mock_commit.parents = ["parent_commit"]

        baseline_set = [{"/path": mock_commit}]
        reset_hard_to_baseline("/path", baseline_set)

        mock_repo.git.reset.assert_called_with('--hard', "parent_commit")

def test_reverttobaseline_specific_baseline(caplog):
    caplog.set_level(logging.INFO)
    runner = CliRunner()
    baselines = {"v1.0": [{"/path": MagicMock()}]}
    with patch("commands.baseline.get_baselines_from_path", return_value=(baselines, ["v1.0"])):
        with patch("commands.baseline.reset_hard_to_baseline") as mock_reset:
            result = runner.invoke(reverttobaseline, ["--workdir", ".", "v1.0"])
            assert "Resetting all repos to the commit before baseline v1.0" in caplog.text
            mock_reset.assert_called_once()

def test_add_recursive_commit_no_submodules():
    with patch("commands.baseline.Repo") as mock_repo_class:
        mock_repo = mock_repo_class.return_value
        mock_repo.submodules = []
        mock_repo.working_tree_dir = "/path"

        add_recursive_commit("/path", "msg")
        mock_repo.git.commit.assert_called_with('--allow-empty', '-a', '-m', 'msg')

def test_add_recursive_commit_with_add_all():
    with patch("commands.baseline.Repo") as mock_repo_class:
        mock_repo = mock_repo_class.return_value
        mock_repo.submodules = []

        add_recursive_commit("/path", "msg", add_newly_created_too=True)
        mock_repo.git.add.assert_called_with('-A')
        mock_repo.git.commit.assert_called_with('--allow-empty', '-m', 'msg')

def test_get_baseline_seperator():
    assert get_baseline_seperator() == " ||| "

def test_get_hash():
    h = get_hash("test")
    assert len(h) == 128 # SHA-512

def test_baselines_are_valid_empty_keys(caplog):
    caplog.set_level(logging.INFO)
    assert baselines_are_valid({}) is True

def test_listsubmodules_command(temp_repo, caplog):
    caplog.set_level(logging.ERROR)
    runner = CliRunner()

    # Invalid baseline set scenario
    with patch("commands.baseline.get_baselines_from_path", return_value=({"repo1": ["b1"], "repo2": ["b1", "b2"]}, [])):
        result = runner.invoke(listsubmodules, ['--workdir', temp_repo])
        assert "Invalid baseline set!" in caplog.text

def test_get_baselines():
    mock_repo = MagicMock()
    mock_commit = MagicMock()
    mock_commit.message = create_baseline_string("v1.0")
    mock_repo.iter_commits.return_value = [mock_commit]
    mock_repo.working_tree_dir = "/repo"

    baselines, order = get_baselines(mock_repo)
    assert "v1.0" in baselines
    assert order == ["v1.0"]
    assert baselines["v1.0"][0] == {"/repo": mock_commit}

def test_get_baselines_from_path():
    with patch("commands.baseline.Repo") as mock_repo_class:
        mock_repo = mock_repo_class.return_value
        mock_repo.submodules = []
        mock_repo.working_tree_dir = "/path"

        # Mock get_baselines to return some data
        with patch("commands.baseline.get_baselines", return_value=({"v1": []}, ["v1"])):
            baselines, order = get_baselines_from_path("/path", 0, True)
            assert "v1" in baselines
            assert order == ["v1"]

def test_createpatches_outpath_exists(tmp_path):
    outpath = tmp_path / "already_exists"
    outpath.mkdir()
    runner = CliRunner()
    with patch("commands.baseline.exit_with_error") as mock_exit:
        runner.invoke(createpatches, ["--workdir", ".", str(outpath)])
        mock_exit.assert_called_once()
        assert "Outpath may not exist" in mock_exit.call_args[0][0]

def test_is_baseline_patch():
    # Correct baseline patch filename: <prefix> in name and ends with .patch
    prefix = get_baseline_prefix()
    assert is_baseline_patch(f"0001_some_patch_{prefix}.patch") is True
    # Does not end with .patch
    assert is_baseline_patch(f"0001_some_patch_{prefix}.txt") is False
    # Does not contain prefix
    assert is_baseline_patch("0001_some_patch.patch") is False
    # Starts with prefix (should be False according to current implementation)
    assert is_baseline_patch(f"{prefix}_0001_some_patch.patch") is False

def test_baselines_are_valid():
    # Empty baselines is valid
    assert baselines_are_valid({}) is True

    # Matching length
    baselines = {
        "repo1": ["b1", "b2"],
        "repo2": ["b1", "b2"]
    }
    assert baselines_are_valid(baselines) is True

    # Mismatch length
    baselines_mismatch = {
        "repo1": ["b1", "b2"],
        "repo2": ["b1"]
    }
    assert baselines_are_valid(baselines_mismatch) is False

def test_clean_workdir():
    with patch("commands.baseline.Repo") as mock_repo_class:
        mock_repo = mock_repo_class.return_value
        clean_workdir("/some/path")
        mock_repo.git.clean.assert_called_with(['-xfd'])
        mock_repo.git.submodule.assert_called()

def test_reverttobaseline_no_baseline_all_flag(caplog):
    caplog.set_level(logging.INFO)
    runner = CliRunner()
    with patch("commands.baseline.get_baselines_from_path", return_value=({}, [])):
        result = runner.invoke(reverttobaseline, ["--workdir", ".", "--all"])
        assert any("Repository contains no baselines" in record.message for record in caplog.records)
        assert result.exit_code == 0 # exit_application(0)

def test_reverttobaseline_missing_args(caplog):
    caplog.set_level(logging.ERROR)
    runner = CliRunner()
    with patch("commands.baseline.get_baselines_from_path", return_value=({"b1": []}, ["b1"])):
        result = runner.invoke(reverttobaseline, ["--workdir", "."])
        assert any("Either specify all or provide a baseline name" in record.message for record in caplog.records)
        assert result.exit_code != 0

def test_normalize_workdir_path():
    assert normalize_workdir_path("/path/to/workdir/") == "/path/to/workdir"
    assert normalize_workdir_path("/path/to/workdir") == "/path/to/workdir"
    with pytest.raises(SystemExit): # exit_with_error calls sys.exit(1)
        normalize_workdir_path(123)

def test_baseline_string_helpers():
    message = "test_baseline"
    expected_hash = get_hash(message)
    baseline_str = create_baseline_string(message)

    assert get_baseline_prefix() in baseline_str
    assert expected_hash in baseline_str
    assert message in baseline_str
    assert get_baseline_seperator() in baseline_str

    assert is_baseline(baseline_str) is True
    assert is_baseline("not a baseline") is False

    parts = get_message_parts(baseline_str)
    assert len(parts) == 3
    assert parts[0] == get_baseline_prefix()
    assert parts[1] == expected_hash
    assert parts[2] == message

def test_is_baseline_invalid_format():
    assert is_baseline(f"{get_baseline_prefix()} ||| wrong_hash ||| message") is False

def test_addbaseline_command(temp_repo, caplog):
    caplog.set_level(logging.INFO)
    runner = CliRunner()
    result = runner.invoke(addbaseline, ['--workdir', temp_repo, 'v1.0'])

    assert result.exit_code == 0
    assert "Adding baseline commit v1.0 to each repo under" in caplog.text

    # Verify the commit exists
    repo = Repo(temp_repo)
    latest_commit = next(repo.iter_commits())
    assert is_baseline(latest_commit.message)
    assert "v1.0" in latest_commit.message

def test_showbaselines_command(temp_repo, caplog):
    caplog.set_level(logging.INFO)
    runner = CliRunner()

    # Add a baseline first
    runner.invoke(addbaseline, ['--workdir', temp_repo, 'v1.0'])
    caplog.clear()

    result = runner.invoke(showbaselines, ['--workdir', temp_repo])
    assert result.exit_code == 0
    assert "Baselines are valid. Avaliable baselines are:" in caplog.text
    assert "- v1.0" in caplog.text

def test_reverttobaseline_all_flag_with_baselines(temp_repo, caplog):
    caplog.set_level(logging.INFO)
    runner = CliRunner()
    
    # Mocking baselines for --all flag
    mock_commit_1 = MagicMock()
    mock_commit_1.hexsha = "abc"
    mock_commit_1.message = "__tuxLayers_baseline__ ||| hash ||| b1"
    
    mock_commit_2 = MagicMock()
    mock_commit_2.hexsha = "def"
    mock_commit_2.message = "__tuxLayers_baseline__ ||| hash ||| b2"
    
    # Distance mocking: b2 is "further" from HEAD
    baselines = {
        "b1": [{temp_repo: mock_commit_1}],
        "b2": [{temp_repo: mock_commit_2}]
    }
    
    with patch("commands.baseline.get_baselines_from_path", return_value=(baselines, ["b1", "b2"])), \
         patch("commands.baseline.Repo") as mock_repo_class, \
         patch("commands.baseline.reset_hard_to_baseline") as mock_reset:
        
        mock_repo = mock_repo_class.return_value
        mock_repo.head.commit = "HEAD"
        # rev_list count mock: b2 is older (higher count)
        mock_repo.git.rev_list.side_effect = ["5", "10"] 
        
        result = runner.invoke(reverttobaseline, ["--workdir", temp_repo, "--all"])
        assert result.exit_code == 0
        assert "Oldest baseline in set: b2" in caplog.text
        mock_reset.assert_called_once()

def test_reverttobaseline_all_flag_full_path_lookup(temp_repo, caplog):
    caplog.set_level(logging.INFO)
    runner = CliRunner()
    
    mock_commit = MagicMock()
    mock_commit.message = "__tuxLayers_baseline__ ||| hash ||| b1"
    
    # Mocking a full path match (abspath)
    baselines = {
        "b1": [{os.path.abspath(temp_repo): mock_commit}]
    }
    
    with patch("commands.baseline.get_baselines_from_path", return_value=(baselines, ["b1"])), \
         patch("commands.baseline.Repo") as mock_repo_class, \
         patch("commands.baseline.reset_hard_to_baseline"):
        
        mock_repo = mock_repo_class.return_value
        mock_repo.git.rev_list.return_value = "5"
        
        result = runner.invoke(reverttobaseline, ["--workdir", temp_repo, "--all"])
        assert result.exit_code == 0
        assert "Oldest baseline in set: b1" in caplog.text

def test_get_baselines_from_path_recursive_mock(caplog):
    caplog.set_level(logging.INFO)
    # Mock Repo object and submodules
    mock_repo = MagicMock()
    mock_repo.working_tree_dir = "/path"
    
    mock_sub = MagicMock()
    mock_sub.module.return_value.working_tree_dir = "/subrepo"
    mock_repo.submodules = [mock_sub]
    
    # We need to make sure Repo(/subrepo) has no submodules to stop recursion
    mock_repo_sub = MagicMock()
    mock_repo_sub.working_tree_dir = "/subrepo"
    mock_repo_sub.submodules = []
    
    def side_effect(p):
        if p == "/path": return mock_repo
        return mock_repo_sub
    
    with patch("commands.baseline.Repo", side_effect=side_effect), \
         patch("commands.baseline.get_baselines") as mock_get_baselines:
        
        mock_get_baselines.side_effect = [
            ({"b1": [{"/path": "c1"}]}, ["b1"]),
            ({"b1": [{"/subrepo": "sc1"}]}, ["b1"])
        ]
        
        baselines, order = get_baselines_from_path("/path", 0, False)
        assert "b1" in baselines
        assert len(baselines["b1"]) == 2

def test_createpatches_invalid_set(tmp_path, caplog):
    caplog.set_level(logging.ERROR)
    runner = CliRunner()
    outpath = tmp_path / "out_createpatches_invalid"
    with patch("commands.baseline.baselines_are_valid", return_value=False), \
         patch("commands.baseline.get_baselines_from_path", return_value=({}, [])):
        with patch("commands.baseline.exit_with_error") as mock_exit:
            runner.invoke(createpatches, ["--workdir", ".", str(outpath)])
            mock_exit.assert_called_with("Invalid baseline configuration!")

def test_extract_patches_recursive(tmp_path):
    # Mock Repo and submodules
    mock_repo = MagicMock()
    mock_sub = MagicMock()
    mock_sub.module.return_value.working_tree_dir = "/subrepo"
    mock_repo.submodules = [mock_sub]
    
    # Prevent infinite recursion: ensure subrepo Repo mock has no submodules
    mock_repo_sub = MagicMock()
    mock_repo_sub.working_tree_dir = "/subrepo"
    mock_repo_sub.submodules = []
    
    def side_effect(p):
        if p == "/path": return mock_repo
        return mock_repo_sub
    
    with patch("commands.baseline.Repo", side_effect=side_effect), \
         patch("commands.baseline.extract_patches_for_repo") as mock_extract_repo:
        
        baseline_pair = {"name": "b1", "parent": "p1"}
        extract_patches("/path", "/base", "/patchdir", baseline_pair, False)
        
        # extract_patches_for_repo should be called for /path and /subrepo
        assert mock_extract_repo.call_count == 2

def test_extract_patches_for_repo_no_hashes(caplog):
    caplog.set_level(logging.WARNING)
    baseline_pair = {
        "name": "b1",
        "parent": "p1",
        "from": [{"/path": MagicMock()}]
    }
    
    with patch("commands.baseline.pydriller.Repository") as mock_pydriller:
        mock_pydriller.return_value.traverse_commits.return_value = []
        
        from commands.baseline import extract_patches_for_repo
        # We need to mock remove_empty_folders to avoid it exiting if path doesn't exist
        with patch("commands.baseline.remove_empty_folders"):
            result = extract_patches_for_repo("/path", "/base", "/patchdir", baseline_pair, False)
            assert "Missing at least one hash to export" in caplog.text
            assert result.id == "b1"

def test_extract_patches_for_repo_with_hashes(tmp_path):
    patchdir = tmp_path / "patches"
    patchdir.mkdir()
    
    m_from = MagicMock()
    m_from.hexsha = "abc"
    m_to = MagicMock()
    m_to.hexsha = "def"
    
    baseline_pair = {
        "name": "b1",
        "parent": "p1",
        "from": [{"/path": m_from}],
        "to": [{"/path": m_to}]
    }
    
    with patch("commands.baseline.pydriller.Repository") as mock_pydriller:
        c1 = MagicMock()
        c1.hash = "hash1"
        c2 = MagicMock()
        c2.hash = "hash2"
        mock_pydriller.return_value.traverse_commits.return_value = [c1, c2]
        
        with patch("commands.baseline.Repo") as mock_repo_class, \
             patch("commands.baseline.glob.glob") as mock_glob, \
             patch("commands.baseline.remove_empty_folders"):
            
            # format_patch should be called
            mock_glob.side_effect = [
                [], # first call for baseline removal (none found)
                [str(patchdir / "0001.patch")] # second call for patches list
            ]
            
            from commands.baseline import extract_patches_for_repo
            result = extract_patches_for_repo("/path", "/path", str(patchdir), baseline_pair, False)
            
            assert result.id == "b1"
            assert len(result.patches) == 1
            mock_repo_class.return_value.git.format_patch.assert_called()

def test_createpatches_basic_flow(tmp_path):
    runner = CliRunner()
    outpath = tmp_path / "out"
    
    m1 = MagicMock()
    m1.message = "__tuxLayers_baseline__ ||| h1 ||| b1"
    m2 = MagicMock()
    m2.message = "__tuxLayers_baseline__ ||| h2 ||| b2"
    
    baselines = {
        "b1": [{"/repo": m1}],
        "b2": [{"/repo": m2}]
    }
    order = ["b2", "b1"] # reversed newest to oldest
    
    with patch("commands.baseline.get_baselines_from_path", return_value=(baselines, order)), \
         patch("commands.baseline.extract_patches") as mock_extract:
        
        mock_layer = MagicMock()
        mock_layer.to_json.return_value = '{"id": "b1"}'
        mock_extract.return_value = mock_layer
        
        result = runner.invoke(createpatches, ["--workdir", ".", str(outpath)])
        assert result.exit_code == 0
        assert (outpath / "b1.json").exists()
        assert (outpath / "b2.json").exists()

def test_reset_hard_to_baseline_no_commit_error():
    with patch("commands.baseline.Repo") as mock_repo_class:
        mock_repo = mock_repo_class.return_value
        mock_repo.submodules = []
        
        with patch("commands.baseline.exit_with_error", side_effect=SystemExit(1)) as mock_exit:
            with pytest.raises(SystemExit):
                reset_hard_to_baseline("/path", [{"/other": "c1"}])
            mock_exit.assert_called_with("Could not find baseline commit in repo /path")

def test_is_baseline_patch_not_patch():
    assert is_baseline_patch("file.txt") is False

def test_reverttobaseline_all_flag_distance_lookup_error(temp_repo, caplog):
    caplog.set_level(logging.ERROR)
    runner = CliRunner()
    
    mock_commit = MagicMock()
    mock_commit.message = "__tuxLayers_baseline__ ||| hash ||| b1"
    
    # Path doesn't match workdir nor abspath
    baselines = {
        "b1": [{"/wrong/path": mock_commit}]
    }
    
    with patch("commands.baseline.get_baselines_from_path", return_value=(baselines, ["b1"])), \
         patch("commands.baseline.Repo"), \
         patch("commands.baseline.exit_with_error", side_effect=SystemExit(1)) as mock_exit:
        
        result = runner.invoke(reverttobaseline, ["--workdir", temp_repo, "--all"])
        assert result.exit_code == 1
        mock_exit.assert_called_with("Error during lookup!")

def test_listsubmodules_invalid_set_error(caplog):
    caplog.set_level(logging.ERROR)
    runner = CliRunner()
    with patch("commands.baseline.get_baselines_from_path", return_value=({"repo1": ["b1"], "repo2": ["b1", "b2"]}, [])):
        runner.invoke(listsubmodules, ['--workdir', '.'])
        assert "Invalid baseline set!" in caplog.text

def test_extract_patches_for_repo_single_commit(tmp_path):
    patchdir = tmp_path / "patches"
    patchdir.mkdir()
    
    m_from = MagicMock()
    m_from.hexsha = "abc"
    
    baseline_pair = {
        "name": "b1",
        "parent": "p1",
        "from": [{"/path": m_from}]
    }
    
    with patch("commands.baseline.pydriller.Repository") as mock_pydriller:
        c1 = MagicMock()
        c1.hash = "hash1"
        mock_pydriller.return_value.traverse_commits.return_value = [c1]
        
        with patch("commands.baseline.Repo") as mock_repo_class, \
             patch("commands.baseline.glob.glob", return_value=[]), \
             patch("commands.baseline.remove_empty_folders"):
            
            from commands.baseline import extract_patches_for_repo
            extract_patches_for_repo("/path", "/path", str(patchdir), baseline_pair, False)
            mock_repo_class.return_value.git.format_patch.assert_called_with('-o', os.path.join(str(patchdir), "b1", "."), "hash1")

def test_extract_patches_for_repo_delete_baseline_patches(tmp_path):
    patchdir = tmp_path / "patches"
    patchdir.mkdir()
    
    baseline_pair = {
        "name": "b1",
        "parent": "p1",
        "from": [{"/path": MagicMock()}]
    }
    
    with patch("commands.baseline.pydriller.Repository") as mock_pydriller:
        mock_pydriller.return_value.traverse_commits.return_value = [MagicMock()]
        
        with patch("commands.baseline.Repo"), \
             patch("commands.baseline.glob.glob") as mock_glob, \
             patch("commands.baseline.remove_empty_folders"), \
             patch("os.remove") as mock_remove:
            
            # First glob call for deletion logic
            mock_glob.side_effect = [
                [str(patchdir / f"0001_some_{get_baseline_prefix()}.patch")], # deletion loop
                [] # patches list loop
            ]
            
            from commands.baseline import extract_patches_for_repo
            extract_patches_for_repo("/path", "/path", str(patchdir), baseline_pair, False)
            mock_remove.assert_called_once()

def test_extract_patches_for_repo_from_equals_to(tmp_path):
    patchdir = tmp_path / "patches"
    patchdir.mkdir()
    
    m_commit = MagicMock()
    m_commit.hexsha = "abc"
    
    baseline_pair = {
        "name": "b1",
        "parent": "p1",
        "from": [{"/path": m_commit}],
        "to": [{"/path": m_commit}]
    }
    
    with patch("commands.baseline.pydriller.Repository") as mock_pydriller:
        mock_pydriller.return_value.traverse_commits.return_value = []
        
        with patch("commands.baseline.Repo"), \
             patch("commands.baseline.remove_empty_folders"):
            
            from commands.baseline import extract_patches_for_repo
            extract_patches_for_repo("/path", "/path", str(patchdir), baseline_pair, False)
            # Check pydriller called with single=...
            mock_pydriller.assert_called_with("/path", single="abc")

def test_showbaselines_invalid_error(caplog):
    caplog.set_level(logging.ERROR)
    runner = CliRunner()
    with patch("commands.baseline.get_baselines_from_path", return_value=({"r1": [1], "r2": [1, 2]}, [])):
        runner.invoke(showbaselines, ['--workdir', '.'])
        assert "Invalid baseline set!" in caplog.text

def test_reverttobaseline_no_baselines_clean(temp_repo, caplog):
    caplog.set_level(logging.INFO)
    runner = CliRunner()
    with patch("commands.baseline.get_baselines_from_path", return_value=({}, [])):
        with patch("commands.baseline.clean_workdir") as mock_clean:
            runner.invoke(reverttobaseline, ["--workdir", temp_repo, "--all", "--clean"])
            mock_clean.assert_called_once()

def test_add_recursive_commit_git_error():
    with patch("commands.baseline.Repo") as mock_repo_class:
        mock_repo = mock_repo_class.return_value
        mock_repo.submodules = []
        import git
        mock_repo.git.commit.side_effect = git.exc.GitError("error")
        # add_recursive_commit doesn't catch GitError, it will bubble up
        with pytest.raises(git.exc.GitError):
            add_recursive_commit("/path", "msg")

def test_clean_workdir_error(caplog):
    caplog.set_level(logging.ERROR)
    with patch("commands.baseline.Repo") as mock_repo_class:
        mock_repo = mock_repo_class.return_value
        import git
        mock_repo.git.clean.side_effect = git.exc.GitError("clean error")
        with patch("commands.baseline.exit_with_error") as mock_exit:
            clean_workdir("/path")
            mock_exit.assert_called()
