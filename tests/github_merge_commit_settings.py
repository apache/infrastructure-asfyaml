#!/usr/bin/env python3
"""Unit tests for .asf.yaml GitHub merge commits settings"""

from helpers import YamlTest
import asfyaml.asfyaml
import asfyaml.dataobjects

# Set .asf.yaml to debug mode
asfyaml.asfyaml.DEBUG = True


valid_github_merge_commit_setting = YamlTest(
    None,
    None,
    """
github:
    merge_commit_title: PR_TITLE
    merge_commit_message: PR_BODY
""",
)


def test_basic_yaml(test_repo: asfyaml.dataobjects.Repository):
    print("[github] Testing repository merge commit settings")

    tests_to_run = (
        valid_github_merge_commit_setting,
    )

    for test in tests_to_run:
        with test.ctx() as vs:
            a = asfyaml.asfyaml.ASFYamlInstance(test_repo, "humbedooh", test.yaml)
            a.environments_enabled.add("noop")
            a.no_cache = True
            a.run_parts()
