"""Regression checks against actual imported package paths, including aliases."""
import os
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
CHECK = ROOT / "scripts/ci_install_check.py"


def check_location(expected, cwd):
    return subprocess.run(
        [sys.executable, str(CHECK), "cortex_vision", str(expected)],
        cwd=cwd, capture_output=True, text=True,
    )


def test_normalized_import_location(tmp_path):
    result = check_location(ROOT / "scripts" / "..", tmp_path)
    assert result.returncode == 0, result.stderr
    assert "PASS installed import" in result.stdout


def test_rejects_import_outside_expected_environment(tmp_path):
    result = check_location(tmp_path, tmp_path)
    assert result.returncode != 0
    assert "outside expected installation" in result.stderr


@pytest.mark.skipif(os.name == "nt", reason="Windows symlink creation requires additional privileges")
def test_symlinked_installation_root(tmp_path):
    alias = tmp_path / "installation-alias"
    alias.symlink_to(ROOT, target_is_directory=True)
    result = check_location(alias, tmp_path)
    assert result.returncode == 0, result.stderr
