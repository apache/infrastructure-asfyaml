#!/usr/bin/env python3
"""Simple unit test for .asf.yaml"""
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
import asfyaml
asfyaml.DEBUG = True

@pytest.mark.validator
def test_basic_yaml():
    EXPECTED_ENVS = {"production", "dev"}  # We expect these two envs enabled
    EXPECTED_FEATURES_MIN = {"test"}
    basic_yaml = open("tests/basic-dev-env.yaml", "r").read()
    a = asfyaml.ASFYamlInstance(basic_yaml)
    a.run_parts()

    # We should have both prod+dev envs enabled here
    assert a.environments_enabled == EXPECTED_ENVS
    # We should have at least our 'test' feature in the set
    assert EXPECTED_FEATURES_MIN.issubset(a.enabled_features.keys())

