#!/usr/bin/env python3
"""Unit tests for .asf.yaml GitHub autolink features"""

from helpers import YamlTest
import asfyaml.asfyaml
import asfyaml.dataobjects

# Set .asf.yaml to debug mode
asfyaml.asfyaml.DEBUG = True


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
    asfyaml.asfyaml.ASFYAMLException,
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
    asfyaml.asfyaml.ASFYAMLException,
    "when expecting a sequence",
    """
github:
    autolink_jira: foo
""",
)


def test_basic_yaml(test_repo: asfyaml.dataobjects.Repository):
    print("[github] Testing jira autolink features")

    tests_to_run = (
        valid_github_autolink,
        valid_github_autolink_single,
        invalid_github_autolink_not_upperalpha,
        invalid_github_autolink_not_list
    )

    for test in tests_to_run:
        with test.ctx() as vs:
            a = asfyaml.asfyaml.ASFYamlInstance(test_repo, "humbedooh", test.yaml)
            a.environments_enabled.add("noop")
            a.no_cache = True
            a.run_parts()
