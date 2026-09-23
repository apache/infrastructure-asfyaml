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

"""Unit tests for .asf.yaml GitHub pull request creation cap feature."""

import json
from types import SimpleNamespace
from typing import Any

import pytest

import asfyaml.asfyaml
import asfyaml.dataobjects
from asfyaml.feature.github.pr_creation_cap import pr_creation_cap
from helpers import YamlTest

# Set .asf.yaml to debug mode
asfyaml.asfyaml.DEBUG = True

CAP_URL = "/repos/apache/infrastructure-asfyaml/interaction-limits/pulls/creation-cap"
BYPASS_URL = "/repos/apache/infrastructure-asfyaml/interaction-limits/pulls/bypass-list"
BYPASS_LIST_URL = f"{BYPASS_URL}?per_page=100"


valid_creation_cap = YamlTest(
    None,
    None,
    """
github:
    pull_requests:
      creation_cap:
        enabled: true
        max_open_pull_requests: 5
""",
)

valid_creation_cap_disabled = YamlTest(
    None,
    None,
    """
github:
    pull_requests:
      creation_cap:
        enabled: false
""",
)

invalid_creation_cap_type = YamlTest(
    asfyaml.asfyaml.ASFYAMLException,
    "when expecting an integer",
    """
github:
    pull_requests:
      creation_cap:
        enabled: true
        max_open_pull_requests: lots
""",
)

valid_creation_cap_with_bypass_users = YamlTest(
    None,
    None,
    """
github:
    pull_requests:
      creation_cap:
        enabled: true
        max_open_pull_requests: 5
        bypass_users:
          - octocat
          - monalisa
""",
)

valid_creation_cap_with_empty_bypass_users = YamlTest(
    None,
    None,
    """
github:
    pull_requests:
      creation_cap:
        enabled: true
        bypass_users: ~
""",
)

invalid_bypass_users_type = YamlTest(
    asfyaml.asfyaml.ASFYAMLException,
    "when expecting a sequence",
    """
github:
    pull_requests:
      creation_cap:
        enabled: true
        bypass_users: octocat
""",
)


class FakeRequester:
    def __init__(
        self,
        status: int = 200,
        body: str = "{}",
        responses: dict[tuple[str, str], tuple[int, str]] | None = None,
    ):
        self.calls: list[dict[str, Any]] = []
        self.status = status
        self.body = body
        # Per (method, url) overrides; anything not listed gets the default status/body.
        self.responses = responses or {}

    def requestJson(self, method: str, url: str, input: dict[str, Any] | None = None):  # noqa: N802
        self.calls.append({"method": method, "url": url, "input": input})
        status, body = self.responses.get((method, url), (self.status, self.body))
        return status, {}, body


def bypass_list_body(*logins: str) -> str:
    return json.dumps([{"login": login, "id": index} for index, login in enumerate(logins, start=1)])


def bypass_list_responses(*on_github: str) -> dict[tuple[str, str], tuple[int, str]]:
    return {
        ("GET", BYPASS_LIST_URL): (200, bypass_list_body(*on_github)),
        ("PUT", BYPASS_URL): (204, ""),
        ("DELETE", BYPASS_URL): (204, ""),
    }


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
    print("[github] Testing pull request creation cap")

    tests_to_run = (
        valid_creation_cap,
        valid_creation_cap_disabled,
        invalid_creation_cap_type,
        valid_creation_cap_with_bypass_users,
        valid_creation_cap_with_empty_bypass_users,
        invalid_bypass_users_type,
    )

    for test in tests_to_run:
        with test.ctx():
            a = asfyaml.asfyaml.ASFYamlInstance(
                repo=test_repo, committer="humbedooh", config_data=test.yaml, branch=asfyaml.dataobjects.DEFAULT_BRANCH
            )
            a.environments_enabled.add("noop")
            a.no_cache = True
            a.run_parts()


def test_enable_creation_cap_with_max():
    requester = FakeRequester()
    feature = FakeFeature(
        yaml={"pull_requests": {"creation_cap": {"enabled": True, "max_open_pull_requests": 5}}},
        previous_yaml={},
        requester=requester,
    )

    pr_creation_cap(feature)

    assert requester.calls == [
        {"method": "PATCH", "url": CAP_URL, "input": {"enabled": True, "max_open_pull_requests": 5}}
    ]


def test_enable_creation_cap_without_max():
    requester = FakeRequester()
    feature = FakeFeature(
        yaml={"pull_requests": {"creation_cap": {"enabled": True}}},
        previous_yaml={},
        requester=requester,
    )

    pr_creation_cap(feature)

    assert requester.calls == [{"method": "PATCH", "url": CAP_URL, "input": {"enabled": True}}]


def test_disable_creation_cap():
    requester = FakeRequester()
    feature = FakeFeature(
        yaml={"pull_requests": {"creation_cap": {"enabled": False}}},
        previous_yaml={"pull_requests": {"creation_cap": {"enabled": True, "max_open_pull_requests": 5}}},
        requester=requester,
    )

    pr_creation_cap(feature)

    assert requester.calls == [{"method": "PATCH", "url": CAP_URL, "input": {"enabled": False}}]


def test_removed_section_disables_cap():
    requester = FakeRequester()
    feature = FakeFeature(
        yaml={"pull_requests": {"allow_auto_merge": True}},
        previous_yaml={"pull_requests": {"creation_cap": {"enabled": True, "max_open_pull_requests": 5}}},
        requester=requester,
    )

    pr_creation_cap(feature)

    assert requester.calls == [{"method": "PATCH", "url": CAP_URL, "input": {"enabled": False}}]


def test_disabled_without_previous_config_still_patches():
    # A cap can be on without .asf.yaml having put it there: set by hand in the
    # repository settings, or left from a run whose cached yaml has since been lost.
    # An explicit `enabled: false` has to turn it off in those cases too, so the
    # PATCH goes out whatever the previous yaml holds.
    requester = FakeRequester()
    feature = FakeFeature(
        yaml={"pull_requests": {"creation_cap": {"enabled": False}}},
        previous_yaml={},
        requester=requester,
    )

    pr_creation_cap(feature)

    assert requester.calls == [{"method": "PATCH", "url": CAP_URL, "input": {"enabled": False}}]


def test_no_creation_cap_section_is_noop():
    requester = FakeRequester()
    feature = FakeFeature(
        yaml={"pull_requests": {"allow_auto_merge": True}},
        previous_yaml={},
        requester=requester,
    )

    pr_creation_cap(feature)

    assert requester.calls == []


def test_out_of_range_max_raises():
    requester = FakeRequester()
    feature = FakeFeature(
        yaml={"pull_requests": {"creation_cap": {"enabled": True, "max_open_pull_requests": 5000}}},
        previous_yaml={},
        requester=requester,
    )

    with YamlTest(Exception, "must be between 1 and 1000", "").ctx():
        pr_creation_cap(feature)

    assert requester.calls == []


def test_204_response_is_accepted():
    requester = FakeRequester(status=204, body="")
    feature = FakeFeature(
        yaml={"pull_requests": {"creation_cap": {"enabled": True, "max_open_pull_requests": 5}}},
        previous_yaml={},
        requester=requester,
    )

    pr_creation_cap(feature)

    assert len(requester.calls) == 1


@pytest.mark.parametrize(
    "status, body, expected",
    [
        (403, '{"message": "Resource not accessible by integration"}', "Not allowed to set the pull request"),
        (404, '{"message": "Not Found"}', "not found or not accessible"),
        (422, '{"message": "Validation Failed"}', "Validation failed while setting"),
        (500, '{"message": "Server Error"}', "GitHub server error while setting"),
        (418, "not json at all", "Unexpected response while setting"),
    ],
)
def test_error_response_raises(status: int, body: str, expected: str):
    requester = FakeRequester(status=status, body=body)
    feature = FakeFeature(
        yaml={"pull_requests": {"creation_cap": {"enabled": True, "max_open_pull_requests": 5}}},
        previous_yaml={},
        requester=requester,
    )

    with YamlTest(Exception, expected, "").ctx():
        pr_creation_cap(feature)


def test_noop_mode_does_not_call_api(capsys):
    requester = FakeRequester()
    feature = FakeFeature(
        yaml={"pull_requests": {"creation_cap": {"enabled": True, "max_open_pull_requests": 5}}},
        previous_yaml={},
        requester=requester,
        noop_enabled=True,
    )

    pr_creation_cap(feature)

    captured = capsys.readouterr()
    assert "noop mode active" in captured.out
    assert requester.calls == []


def test_bypass_users_absent_leaves_list_untouched():
    requester = FakeRequester()
    feature = FakeFeature(
        yaml={"pull_requests": {"creation_cap": {"enabled": True, "max_open_pull_requests": 5}}},
        previous_yaml={},
        requester=requester,
    )

    pr_creation_cap(feature)

    assert [call["url"] for call in requester.calls] == [CAP_URL]


def test_removed_section_leaves_bypass_list_untouched():
    requester = FakeRequester()
    feature = FakeFeature(
        yaml={"pull_requests": {}},
        previous_yaml={"pull_requests": {"creation_cap": {"enabled": True, "bypass_users": ["octocat"]}}},
        requester=requester,
    )

    pr_creation_cap(feature)

    assert requester.calls == [{"method": "PATCH", "url": CAP_URL, "input": {"enabled": False}}]


@pytest.mark.parametrize(
    "configured, on_github, expected_calls",
    [
        pytest.param(
            ["octocat", "monalisa"],
            [],
            [{"method": "PUT", "input": {"users": ["octocat", "monalisa"]}}],
            id="adds-missing",
        ),
        pytest.param(
            ["octocat"],
            ["octocat", "hubot"],
            [{"method": "DELETE", "input": {"users": ["hubot"]}}],
            id="removes-extra",
        ),
        pytest.param(
            ["monalisa"],
            ["octocat"],
            [
                {"method": "PUT", "input": {"users": ["monalisa"]}},
                {"method": "DELETE", "input": {"users": ["octocat"]}},
            ],
            id="adds-and-removes",
        ),
        pytest.param(["octocat", "monalisa"], ["monalisa", "octocat"], [], id="in-sync"),
        pytest.param(
            None,
            ["octocat", "hubot"],
            [{"method": "DELETE", "input": {"users": ["octocat", "hubot"]}}],
            id="empty-clears",
        ),
        pytest.param(["OctoCat", "octocat"], ["octocat"], [], id="case-insensitive-and-deduplicated"),
    ],
)
def test_bypass_list_reconciliation(
    configured: list[str] | None, on_github: list[str], expected_calls: list[dict[str, Any]]
):
    requester = FakeRequester(responses=bypass_list_responses(*on_github))
    feature = FakeFeature(
        yaml={"pull_requests": {"creation_cap": {"enabled": True, "bypass_users": configured}}},
        previous_yaml={},
        requester=requester,
    )

    pr_creation_cap(feature)

    to_add = [c["input"]["users"] for c in expected_calls if c["method"] == "PUT"]
    lookups = [{"method": "GET", "url": f"/users/{login}", "input": None} for login in (to_add[0] if to_add else [])]
    assert requester.calls[0] == {"method": "GET", "url": BYPASS_LIST_URL, "input": None}
    assert requester.calls[1 : 1 + len(lookups)] == lookups
    assert requester.calls[1 + len(lookups)] == {"method": "PATCH", "url": CAP_URL, "input": {"enabled": True}}
    changes = requester.calls[2 + len(lookups) :]
    assert [{"method": c["method"], "input": c["input"]} for c in changes] == expected_calls
    assert all(c["url"] == BYPASS_URL for c in changes)  # PUT/DELETE carry no query string


def test_bypass_list_reconciled_even_when_cap_disabled():
    requester = FakeRequester(responses=bypass_list_responses())
    feature = FakeFeature(
        yaml={"pull_requests": {"creation_cap": {"enabled": False, "bypass_users": ["octocat"]}}},
        previous_yaml={},
        requester=requester,
    )

    pr_creation_cap(feature)

    assert [c["method"] for c in requester.calls] == ["GET", "GET", "PATCH", "PUT"]


@pytest.mark.parametrize(
    "bypass_users, expected",
    [
        ([f"user{i}" for i in range(101)], "may list at most 100 users, got 101"),
        (["octocat", ""], "entries must be non-empty GitHub logins"),
        (["octocat", 42], "entries must be non-empty GitHub logins"),
        (["octocat", "not a login!"], "'not a login!' is not a valid GitHub ID"),
        (["-leading-hyphen"], "'-leading-hyphen' is not a valid GitHub ID"),
        ("octocat", "must be a list of GitHub logins"),
    ],
)
def test_invalid_bypass_users_raise_before_any_call(bypass_users: Any, expected: str):
    requester = FakeRequester()
    feature = FakeFeature(
        yaml={"pull_requests": {"creation_cap": {"enabled": True, "bypass_users": bypass_users}}},
        previous_yaml={},
        requester=requester,
    )

    with YamlTest(Exception, expected, "").ctx():
        pr_creation_cap(feature)

    assert requester.calls == []


@pytest.mark.parametrize(
    "failing, expected, calls_made",
    [
        ("GET", "Failed reading the pull request creation cap bypass list", ["GET"]),
        ("PUT", "Failed adding users to the pull request creation cap bypass list", ["GET", "GET", "PATCH", "PUT"]),
    ],
)
def test_bypass_list_error_response_raises(failing: str, expected: str, calls_made: list[str]):
    responses = bypass_list_responses()
    failing_url = BYPASS_LIST_URL if failing == "GET" else BYPASS_URL
    responses[(failing, failing_url)] = (403, '{"message": "Resource not accessible by personal access token"}')
    requester = FakeRequester(responses=responses)
    feature = FakeFeature(
        yaml={"pull_requests": {"creation_cap": {"enabled": True, "bypass_users": ["octocat"]}}},
        previous_yaml={},
        requester=requester,
    )

    with YamlTest(Exception, expected, "").ctx():
        pr_creation_cap(feature)

    assert [c["method"] for c in requester.calls] == calls_made


def test_unknown_bypass_users_fail_before_cap_is_changed():
    responses = bypass_list_responses("hubot")
    responses[("GET", "/users/no-such-user")] = (404, '{"message": "Not Found"}')
    responses[("GET", "/users/also-missing")] = (404, '{"message": "Not Found"}')
    requester = FakeRequester(responses=responses)
    feature = FakeFeature(
        yaml={
            "pull_requests": {
                "creation_cap": {"enabled": True, "bypass_users": ["no-such-user", "octocat", "also-missing"]}
            }
        },
        previous_yaml={},
        requester=requester,
    )

    with YamlTest(Exception, "users that do not exist: no-such-user, also-missing", "").ctx():
        pr_creation_cap(feature)

    assert [c["method"] for c in requester.calls] == ["GET", "GET", "GET", "GET"]
    assert [c["url"] for c in requester.calls[1:]] == ["/users/no-such-user", "/users/octocat", "/users/also-missing"]


def test_bypass_user_lookup_error_raises():
    responses = bypass_list_responses()
    responses[("GET", "/users/octocat")] = (403, '{"message": "API rate limit exceeded"}')
    requester = FakeRequester(responses=responses)
    feature = FakeFeature(
        yaml={"pull_requests": {"creation_cap": {"enabled": True, "bypass_users": ["octocat"]}}},
        previous_yaml={},
        requester=requester,
    )

    with YamlTest(Exception, "Failed looking up 'octocat' for the pull request creation cap bypass list", "").ctx():
        pr_creation_cap(feature)

    assert [c["method"] for c in requester.calls] == ["GET", "GET"]


def test_bypass_list_noop_mode_does_not_call_api(capsys):
    requester = FakeRequester()
    feature = FakeFeature(
        yaml={"pull_requests": {"creation_cap": {"enabled": True, "bypass_users": ["octocat"]}}},
        previous_yaml={},
        requester=requester,
        noop_enabled=True,
    )

    pr_creation_cap(feature)

    captured = capsys.readouterr()
    assert "bypass list to: octocat" in captured.out
    assert requester.calls == []
