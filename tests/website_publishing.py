#!/usr/bin/env python3
"""Unit tests for .asf.yaml website publishing"""
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
import pytest
import asfyaml.asfyaml
import asfyaml.dataobjects
import contextlib
import strictyaml
from helpers import YamlTest
# Set .asf.yaml to debug mode
asfyaml.DEBUG = True

valid_staging = YamlTest(
    None,
    None,
    """
staging:
  subdir: foo
  profile: foo
  autostage: foo/*
""",
)

# Valid staging section, but invalid subdir directive
invalid_staging_subdir_slash = YamlTest(
    asfyaml.asfyaml.ASFYAMLException,
    "cannot start with a forward slash",
    """
staging:
  subdir: /foo
  autostage: foo/*
""",
)

# Valid staging section, but invalid profile directive
invalid_staging_bad_profile = YamlTest(
    asfyaml.asfyaml.ASFYAMLException,
    "Must only contain permitted DNS characters",
    """
staging:
  profile: a+b+c
  autostage: foo/*
""",
)

# Valid staging section, but invalid autostage directive
invalid_staging_bad_autostage = YamlTest(
    asfyaml.asfyaml.ASFYAMLException,
    "autostage parameter must be",
    """
staging:
  profile: a+b+c
  autostage: foo/bar
""",
)

# Valid staging section, but invalid unknown directive
invalid_staging_unknown_directive = YamlTest(
    asfyaml.asfyaml.ASFYAMLException,
    "key not in schema",
    """
staging:
  blorp: foo
  autostage: foo/bar
""",
)

# Valid publish section
valid_publish = YamlTest(
    None,
    None,
    """
publish:
  whoami: main
  subdir: foobar
  type: website
""",
)

# Valid publish, but invalid hostname
invalid_publish_hostname = YamlTest(
    asfyaml.asfyaml.ASFYAMLException,
    "you cannot specify .*?apache.org hostnames, they must be inferred!",
    """
publish:
  whoami: main
  subdir: foobar
  type: website
  hostname: foo.apache.org
""",
)


def test_basic_yaml():
    repo_path = "./repos/private/whimsy/whimsy-private.git"
    os.environ["PATH_INFO"] = "whimsy-site.git/git-receive-pack"
    os.environ["GIT_PROJECT_ROOT"] = "./repos/private"
    if not os.path.isdir(repo_path):  # Make test repo dir
        os.makedirs(repo_path, exist_ok=True)
    testrepo = asfyaml.dataobjects.Repository(repo_path)

    print("STAGING TESTS")
    tests_to_run = (
        valid_staging,
        invalid_staging_subdir_slash,
        invalid_staging_bad_profile,
        invalid_staging_bad_autostage,
        invalid_staging_unknown_directive,
    )

    for test in tests_to_run:
        with test.ctx() as vs:
            a = asfyaml.asfyaml.ASFYamlInstance(testrepo, "humbedooh", test.yaml)
            a.environments_enabled.add("noop")
            a.run_parts()

    print("PUBLISHING TESTS")
    tests_to_run = (valid_publish, invalid_publish_hostname,)

    for test in tests_to_run:
        with test.ctx() as vs:
            a = asfyaml.asfyaml.ASFYamlInstance(testrepo, "humbedooh", test.yaml)
            a.environments_enabled.add("noop")
            a.run_parts()
