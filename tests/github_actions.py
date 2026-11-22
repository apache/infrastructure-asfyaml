# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.

"""Unit tests for .asf.yaml GitHub Actions settings feature."""

from types import SimpleNamespace
from typing import Any

import pytest

import asfyaml.asfyaml
import asfyaml.dataobjects
from asfyaml.feature.github.actions import fork_pr_contributor_approval
from helpers import YamlTest

# Set .asf.yaml to debug mode
asfyaml.asfyaml.DEBUG = True

APPROVAL_URL = "/repos/apache/infrastructure-asfyaml/actions/permissions/fork-pr-contributor-approval"


valid_all_external = YamlTest(
    None,
    None,
    """
github:
    actions:
      fork_pr_contributor_approval: all_external_contributors
""",
)

valid_first_time = YamlTest(
    None,
    None,
    """
github:
    actions:
      fork_pr_contributor_approval: first_time_contributors
""",
)

valid_first_time_new_to_github = YamlTest(
    None,
    None,
    """
github:
    actions:
      fork_pr_contributor_approval: first_time_contributors_new_to_github
""",
)

invalid_approval_policy_value = YamlTest(
    asfyaml.asfyaml.ASFYAMLException,
    "when expecting one of: first_time_contributors_new_to_github, first_time_contributors, all_external_contributors",
    """
github:
    actions:
      fork_pr_contributor_approval: nobody
""",
)

invalid_approval_policy_type = YamlTest(
    asfyaml.asfyaml.ASFYAMLException,
    "when expecting a enum",
    """
github:
    actions:
      fork_pr_contributor_approval:
        - all_external_contributors
""",
)

invalid_unknown_actions_key = YamlTest(
    asfyaml.asfyaml.ASFYAMLException,
    "unexpected key not in schema",
    """
github:
    actions:
      unknown_setting: true
""",
)


class FakeRequester:
    def __init__(self, status: int = 204, body: str = ""):
        self.calls: list[dict[str, Any]] = []
        self.status = status
        self.body = body

    def requestJson(self, method: str, url: str, input: dict[str, Any] | None = None):  # noqa: N802
        self.calls.append({"method": method, "url": url, "input": input})
        return self.status, {}, self.body


class FakeFeature:
    def __init__(
        self,
        *,
        yaml: dict[str, Any],
        previous_yaml: dict[str, Any],
        requester: FakeRequester,
        noop_enabled: bool = False,
    ):
        self.yaml = yaml
        self.previous_yaml = previous_yaml
        self.repository = SimpleNamespace(org_id="apache", name="infrastructure-asfyaml")
        self.ghrepo = SimpleNamespace(_requester=requester)
        self._noop_enabled = noop_enabled

    def noop(self, directive: str) -> bool:
        if self._noop_enabled:
            print(f"[github::{directive}] Not applying changes, noop mode active.")
            return True
        return False


def test_basic_yaml(test_repo: asfyaml.dataobjects.Repository):
    print("[github] Testing GitHub Actions fork PR contributor approval")

    tests_to_run = (
        valid_all_external,
        valid_first_time,
        valid_first_time_new_to_github,
        invalid_approval_policy_value,
        invalid_approval_policy_type,
        invalid_unknown_actions_key,
    )

    for test in tests_to_run:
        with test.ctx():
            a = asfyaml.asfyaml.ASFYamlInstance(
                repo=test_repo, committer="humbedooh", config_data=test.yaml, branch=asfyaml.dataobjects.DEFAULT_BRANCH
            )
            a.environments_enabled.add("noop")
            a.no_cache = True
            a.run_parts()


@pytest.mark.parametrize(
    "policy",
    [
        "first_time_contributors_new_to_github",
        "first_time_contributors",
        "all_external_contributors",
    ],
)
def test_set_fork_pr_contributor_approval(policy: str):
    # Explicit policy values always send PUT, even with an empty previous_yaml cache.
    requester = FakeRequester()
    feature = FakeFeature(
        yaml={"actions": {"fork_pr_contributor_approval": policy}},
        previous_yaml={},
        requester=requester,
    )

    fork_pr_contributor_approval(feature)

    assert requester.calls == [
        {"method": "PUT", "url": APPROVAL_URL, "input": {"approval_policy": policy}}
    ]


def test_update_fork_pr_contributor_approval():
    requester = FakeRequester()
    feature = FakeFeature(
        yaml={"actions": {"fork_pr_contributor_approval": "all_external_contributors"}},
        previous_yaml={"actions": {"fork_pr_contributor_approval": "first_time_contributors"}},
        requester=requester,
    )

    fork_pr_contributor_approval(feature)

    assert requester.calls == [
        {"method": "PUT", "url": APPROVAL_URL, "input": {"approval_policy": "all_external_contributors"}}
    ]


def test_removed_actions_section_reverts_to_default():
    requester = FakeRequester()
    feature = FakeFeature(
        yaml={"description": "Apache Example"},
        previous_yaml={"actions": {"fork_pr_contributor_approval": "first_time_contributors"}},
        requester=requester,
    )

    fork_pr_contributor_approval(feature)

    assert requester.calls == [
        {"method": "PUT", "url": APPROVAL_URL, "input": {"approval_policy": "all_external_contributors"}}
    ]


def test_removed_approval_key_reverts_to_default():
    requester = FakeRequester()
    feature = FakeFeature(
        yaml={"actions": {}},
        previous_yaml={"actions": {"fork_pr_contributor_approval": "first_time_contributors_new_to_github"}},
        requester=requester,
    )

    fork_pr_contributor_approval(feature)

    assert requester.calls == [
        {"method": "PUT", "url": APPROVAL_URL, "input": {"approval_policy": "all_external_contributors"}}
    ]


def test_no_actions_section_is_noop():
    requester = FakeRequester()
    feature = FakeFeature(
        yaml={"description": "Apache Example"},
        previous_yaml={},
        requester=requester,
    )

    fork_pr_contributor_approval(feature)

    assert requester.calls == []


def test_invalid_policy_raises_before_api_call():
    requester = FakeRequester()
    feature = FakeFeature(
        yaml={"actions": {"fork_pr_contributor_approval": "everyone"}},
        previous_yaml={},
        requester=requester,
    )

    with YamlTest(Exception, "must be one of", "").ctx():
        fork_pr_contributor_approval(feature)

    assert requester.calls == []


def test_200_response_is_accepted():
    requester = FakeRequester(status=200, body="{}")
    feature = FakeFeature(
        yaml={"actions": {"fork_pr_contributor_approval": "all_external_contributors"}},
        previous_yaml={},
        requester=requester,
    )

    fork_pr_contributor_approval(feature)

    assert len(requester.calls) == 1


@pytest.mark.parametrize(
    "status, body, expected",
    [
        (
            403,
            '{"message": "Resource not accessible by integration"}',
            "Not allowed to set the fork PR contributor approval policy",
        ),
        (404, '{"message": "Not Found"}', "not found or not accessible"),
        (422, '{"message": "Validation Failed"}', "Validation failed while setting"),
        (500, '{"message": "Server Error"}', "GitHub server error while setting"),
        (418, "not json at all", "Unexpected response while setting"),
    ],
)
def test_error_response_raises(status: int, body: str, expected: str):
    requester = FakeRequester(status=status, body=body)
    feature = FakeFeature(
        yaml={"actions": {"fork_pr_contributor_approval": "all_external_contributors"}},
        previous_yaml={},
        requester=requester,
    )

    with YamlTest(Exception, expected, "").ctx():
        fork_pr_contributor_approval(feature)


def test_noop_mode_does_not_call_api(capsys):
    requester = FakeRequester()
    feature = FakeFeature(
        yaml={"actions": {"fork_pr_contributor_approval": "all_external_contributors"}},
        previous_yaml={},
        requester=requester,
        noop_enabled=True,
    )

    fork_pr_contributor_approval(feature)

    captured = capsys.readouterr()
    assert "noop mode active" in captured.out
    assert requester.calls == []
