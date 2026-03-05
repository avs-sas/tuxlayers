import pytest
import os
import logging
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
    reverttobaseline
)
from unittest.mock import MagicMock, patch

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
        assert "Either specify all or provide a baseline name" in caplog.text
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
