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
    addbaseline,
    showbaselines
)

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
