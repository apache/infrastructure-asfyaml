#!/usr/bin/env python3
"""Simple unit test for .asf.yaml"""

from pathlib import Path

import asfyaml.asfyaml
import asfyaml.dataobjects


def test_basic_yaml(base_path: Path, test_repo: asfyaml.dataobjects.Repository):
    # Rewire the notifications path, so we can test with a mock json file
    import asfyaml.feature.notifications
    asfyaml.feature.notifications.VALID_LISTS_FILE = str(base_path.joinpath("data/mailinglists.json"))

    # Set .asf.yaml to debug mode
    asfyaml.asfyaml.DEBUG = True

    expected_envs = {"production", "quietmode"}  # We expect these two envs enabled
    expected_minimum_features = {"test"}
    basic_yaml = open(base_path.joinpath("data/basic-dev-env.yaml"), "r").read()
    a = asfyaml.asfyaml.ASFYamlInstance(test_repo, "humbedooh", basic_yaml)
    a.run_parts()

    # We should have both prod+dev envs enabled here
    assert a.environments_enabled == expected_envs
    # We should have at least our 'test' feature in the set
    assert expected_minimum_features.issubset(a.enabled_features.keys())

    # The repo should be marked as private by asfyaml
    assert test_repo.is_private is True, "Expected testrepo.private to be True, but wasn't!"

    # Assert that we know the project name and the hostname
    assert test_repo.project == "whimsy", f"Expected project name whimsy, but got {test_repo.project}"
    assert test_repo.hostname == "whimsical", f"Expected project hostname whimsical, but got {test_repo.hostname}"

