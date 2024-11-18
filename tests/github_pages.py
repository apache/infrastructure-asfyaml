#!/usr/bin/env python3
"""Unit tests for .asf.yaml github pages feature"""
import os
import sys

sys.path.extend(
    (
        "./",
        "../",
    )
)
# If run locally inside the tests dir, we'll move one dir up for imports
if "tests" in os.getcwd():
    os.chdir("..")
import asfyaml
import dataobjects
import strictyaml
from helpers import YamlTest
# Set .asf.yaml to debug mode
asfyaml.DEBUG = True



valid_github_pages = YamlTest(
    None,
    None,
    """
github:
    ghp_branch: main
    ghp_path: /docs
""",
)

# Something isn't a string
invalid_github_pages_garbage = YamlTest(
    strictyaml.exceptions.YAMLValidationError,
    "when expecting a str",
    """
github:
    ghp_branch:
     - 1
     - 2
    ghp_path: /docs
""",
)

# branch isn't a valid setting
invalid_github_pages_bad_branch = YamlTest(
    Exception,
    "Invalid GitHub Pages branch",
    """
github:
    ghp_branch: foo
    ghp_path: /docs
""",
)

os.makedirs("/x1/asfyaml", exist_ok=True)

def test_basic_yaml():
    repo_path = "./repos/private/whimsy/whimsy-private.git"
    os.environ["PATH_INFO"] = "whimsy-site.git/git-receive-pack"
    os.environ["GIT_PROJECT_ROOT"] = "./repos/private"
    if not os.path.isdir(repo_path):  # Make test repo dir
        os.makedirs(repo_path, exist_ok=True)
    testrepo = dataobjects.Repository(repo_path)

    print("[github] Testing features")

    tests_to_run = (
        valid_github_pages,
        invalid_github_pages_garbage,
        invalid_github_pages_bad_branch,

    )

    for test in tests_to_run:
        with test.ctx() as _vs:
            a = asfyaml.ASFYamlInstance(testrepo, "humbedooh", test.yaml)
            a.environments_enabled.add("noop")
            a.no_cache = True
            a.run_parts()
