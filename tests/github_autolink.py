#!/usr/bin/env python3
"""Unit tests for .asf.yaml github autolink features"""
import os
import sys
from helpers import YamlTest
sys.path.extend(
    (
        "./",
        "../",
    )
)
# If run locally inside the tests dir, we'll move one dir up for imports
if "tests" in os.getcwd():
    os.chdir("..")
import pytest
import asfyaml
import dataobjects
import contextlib
import strictyaml

# Set .asf.yaml to debug mode
asfyaml.DEBUG = True


valid_github_autolink = YamlTest(
    None,
    None,
    """
github:
    autolink_jira:
        - FOO
        - BAR
""",
)

valid_github_autolink_single = YamlTest(
    None,
    None,
    """
github:
    autolink_jira: INFRA
""",
)

# Something isn't uppercase alphabetical chars
invalid_github_autolink_not_upperalpha = YamlTest(
    strictyaml.exceptions.YAMLValidationError,
    "String must be uppercase only",
    """
github:
    autolink_jira:
        - FOO
        - bar
""",
)


# not even a list!
invalid_github_autolink_not_list = YamlTest(
    strictyaml.exceptions.YAMLValidationError,
    "when expecting a sequence",
    """
github:
    autolink_jira: foo
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

    print("[github] Testing jira autolink features")

    tests_to_run = (
        valid_github_autolink,
        valid_github_autolink_single,
        invalid_github_autolink_not_upperalpha,
        invalid_github_autolink_not_list
    )

    for test in tests_to_run:
        with test.ctx() as vs:
            a = asfyaml.ASFYamlInstance(testrepo, "humbedooh", test.yaml)
            a.environments_enabled.add("noop")
            a.no_cache = True
            a.run_parts()
