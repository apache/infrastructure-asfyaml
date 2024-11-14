#!/usr/bin/env python3
"""Unit tests for .asf.yaml github features"""
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



valid_github_features = YamlTest(
    None,
    None,
    """
github:
    features:
        issues: true
        wiki: false
        projects: true
        discussions: false
    labels:
        - a
        - b
        - c
""",
)

# Something isn't a bool
invalid_github_features_not_bool = YamlTest(
    strictyaml.exceptions.YAMLValidationError,
    "expecting a boolean value",
    """
github:
    features:
        issues: maybe
        wiki: false
        projects: true
        discussions: false
""",
)

# Something isn't a valid directive
invalid_github_features_unknown_directive = YamlTest(
    strictyaml.exceptions.YAMLValidationError,
    "unexpected key not in schema 'foobar'",
    """
github:
    features:
        foobar: true
        wiki: false
        projects: true
        discussions: false
""",
)


# Discussions enabled but no mailing list target set
invalid_github_features_no_disc_target = YamlTest(
    Exception,
    "GitHub discussions can only be enabled if a mailing list target exists",
    """
github:
    features:
        issues: true
        wiki: false
        projects: true
        discussions: true
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
        valid_github_features,
        invalid_github_features_not_bool,
        invalid_github_features_unknown_directive,
        invalid_github_features_no_disc_target
    )

    for test in tests_to_run:
        with test.ctx() as vs:
            a = asfyaml.ASFYamlInstance(testrepo, "humbedooh", test.yaml)
            a.environments_enabled.add("noop")
            a.no_cache = True
            a.run_parts()
