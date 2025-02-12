import os
import pytest
from pathlib import Path

import asfyaml.dataobjects


@pytest.fixture
def base_path() -> Path:
    """Get the current folder of the test"""
    return Path(__file__).parent

@pytest.fixture
def test_repo(base_path: Path) -> asfyaml.dataobjects.Repository:
    repo_path = str(base_path.joinpath("../repos/private/whimsy/whimsy-private.git"))
    os.environ["PATH_INFO"] = "whimsy-site.git/git-receive-pack"
    os.environ["GIT_PROJECT_ROOT"] = str(base_path.joinpath("../repos/private"))
    if not os.path.isdir(repo_path):  # Make test repo dir
        os.makedirs(repo_path, exist_ok=True)
    return asfyaml.dataobjects.Repository(repo_path)
