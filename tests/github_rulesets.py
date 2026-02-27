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

"""Unit tests for .asf.yaml GitHub rulesets feature."""

from types import SimpleNamespace
from typing import Any

import asfyaml.asfyaml
import asfyaml.dataobjects
import pytest
from asfyaml.feature.github.rulesets import COPILOT_RULESET_NAME, rulesets as configure_rulesets
from helpers import YamlTest

# Set .asf.yaml to debug mode
asfyaml.asfyaml.DEBUG = True


valid_rulesets = YamlTest(
    None,
    None,
    """
github:
    rulesets:
      - name: "Default branch checks"
        target: branch
        enforcement: active
        conditions:
          ref_name:
            include:
              - "~DEFAULT_BRANCH"
            exclude: []
        rules:
          - type: required_status_checks
            parameters:
              strict_required_status_checks_policy: true
              required_status_checks: []
""",
)

valid_rulesets_friendly = YamlTest(
    None,
    None,
    """
github:
    rulesets:
      - name: "Branch Protection"
        type: branch
        branches:
          includes:
            - "main"
          excludes: []
        required_signatures: true
        required_linear_history: true
        required_conversation_resolution: true
        required_pull_request_reviews:
          dismiss_stale_reviews: true
          require_last_push_approval: false
          require_code_owner_reviews: true
          required_approving_review_count: 2
        required_status_checks:
          - name: "gh-infra/jenkins"
            app_slug: -1
""",
)

invalid_rulesets_not_sequence = YamlTest(
    asfyaml.asfyaml.ASFYAMLException,
    "when expecting a sequence",
    """
github:
    rulesets:
      name: "Not a list"
""",
)

invalid_rulesets_friendly_bad_bool = YamlTest(
    asfyaml.asfyaml.ASFYAMLException,
    "required_signatures must be a boolean",
    """
github:
    rulesets:
      - name: "Branch Protection"
        required_signatures: "yes"
""",
)


def _build_ruleset_payload(name: str) -> dict[str, Any]:
    return {
        "name": name,
        "target": "branch",
        "enforcement": "active",
        "conditions": {
            "ref_name": {
                "include": ["~DEFAULT_BRANCH"],
                "exclude": [],
            }
        },
        "rules": [
            {
                "type": "required_status_checks",
                "parameters": {
                    "strict_required_status_checks_policy": True,
                    "required_status_checks": [],
                },
            }
        ],
    }


class FakeRequester:
    def __init__(self, rulesets: list[dict[str, Any]] | None = None, apps: dict[str, int] | None = None):
        self.rulesets = rulesets or []
        self.apps = apps or {}
        self.calls: list[dict[str, Any]] = []

    def requestJson(self, method: str, url: str, input: dict[str, Any] | None = None):  # noqa: N802
        self.calls.append({"method": method, "url": url, "input": input})
        if method == "GET" and url.startswith("/apps/"):
            app_slug = url.rsplit("/", 1)[-1]
            app_id = self.apps.get(app_slug)
            if app_id is None:
                return 404, {}, {}
            return 200, {}, {"id": app_id}
        if method == "GET":
            return 200, {}, self.rulesets
        return 200, {}, {}


class FakeFeature:
    def __init__(
        self,
        *,
        yaml: dict[str, Any],
        previous_yaml: dict[str, Any],
        requester: FakeRequester,
        gh: Any | None = None,
        noop_enabled: bool = False,
    ):
        self.yaml = yaml
        self.previous_yaml = previous_yaml
        self.repository = SimpleNamespace(org_id="apache", name="infrastructure-asfyaml")
        self.ghrepo = SimpleNamespace(_requester=requester)
        self.gh = gh
        self._noop_enabled = noop_enabled

    def noop(self, directive: str) -> bool:
        if self._noop_enabled:
            print(f"[github::{directive}] Not applying changes, noop mode active.")
            return True
        return False


def test_basic_yaml(test_repo: asfyaml.dataobjects.Repository):
    print("[github] Testing rulesets")

    tests_to_run = (
        valid_rulesets,
        valid_rulesets_friendly,
        invalid_rulesets_not_sequence,
        invalid_rulesets_friendly_bad_bool,
    )

    for test in tests_to_run:
        with test.ctx():
            a = asfyaml.asfyaml.ASFYamlInstance(
                repo=test_repo, committer="humbedooh", config_data=test.yaml, branch=asfyaml.dataobjects.DEFAULT_BRANCH
            )
            a.environments_enabled.add("noop")
            a.no_cache = True
            a.run_parts()


def test_rulesets_create_new_ruleset():
    payload = _build_ruleset_payload("Default branch checks")
    requester = FakeRequester()
    feature = FakeFeature(
        yaml={"rulesets": [payload]},
        previous_yaml={},
        requester=requester,
    )

    configure_rulesets(feature)

    assert [call["method"] for call in requester.calls] == ["GET", "POST"]
    assert requester.calls[1]["url"] == "/repos/apache/infrastructure-asfyaml/rulesets"
    assert requester.calls[1]["input"] == payload


def test_rulesets_friendly_syntax_creates_ruleset():
    requester = FakeRequester()
    feature = FakeFeature(
        yaml={
            "rulesets": [
                {
                    "name": "Branch Protection",
                    "type": "branch",
                    "branches": {"includes": ["main"], "excludes": []},
                    "required_signatures": True,
                    "required_linear_history": True,
                    "required_conversation_resolution": True,
                    "required_pull_request_reviews": {
                        "dismiss_stale_reviews": True,
                        "require_last_push_approval": False,
                        "require_code_owner_reviews": True,
                        "required_approving_review_count": 2,
                    },
                    "required_status_checks": [{"name": "gh-infra/jenkins", "app_slug": -1}],
                }
            ]
        },
        previous_yaml={},
        requester=requester,
    )

    configure_rulesets(feature)

    assert [call["method"] for call in requester.calls] == ["GET", "POST"]
    payload = requester.calls[1]["input"]
    assert payload["name"] == "Branch Protection"
    assert payload["target"] == "branch"
    assert payload["enforcement"] == "active"
    assert payload["conditions"]["ref_name"]["include"] == ["main"]
    assert payload["conditions"]["ref_name"]["exclude"] == []

    rule_types = [rule["type"] for rule in payload["rules"]]
    assert "required_signatures" in rule_types
    assert "required_linear_history" in rule_types
    assert "pull_request" in rule_types
    assert "required_status_checks" in rule_types

    status_rule = next(rule for rule in payload["rules"] if rule["type"] == "required_status_checks")
    assert status_rule["parameters"]["strict_required_status_checks_policy"] is False


def test_rulesets_friendly_resolves_bypass_and_app_slug():
    fake_gh = SimpleNamespace(
        get_user=lambda username: SimpleNamespace(id={"alice": 101}[username]),
        get_organization=lambda _org: SimpleNamespace(
            get_team_by_slug=lambda slug: SimpleNamespace(id={"infra": 202}[slug])
        ),
    )
    requester = FakeRequester(apps={"jenkins": 303})
    feature = FakeFeature(
        yaml={
            "rulesets": [
                {
                    "name": "Branch Protection",
                    "type": "branch",
                    "required_signatures": True,
                    "bypass_users": ["alice"],
                    "bypass_teams": ["infra"],
                    "required_status_checks": [{"name": "gh-infra/jenkins", "app_slug": "jenkins"}],
                }
            ]
        },
        previous_yaml={},
        requester=requester,
        gh=fake_gh,
    )

    configure_rulesets(feature)

    post_call = next(call for call in requester.calls if call["method"] == "POST")
    payload = post_call["input"]
    assert payload["bypass_actors"] == [
        {"actor_id": 101, "actor_type": "User", "bypass_mode": "always"},
        {"actor_id": 202, "actor_type": "Team", "bypass_mode": "always"},
    ]
    status_rule = next(rule for rule in payload["rules"] if rule["type"] == "required_status_checks")
    assert status_rule["parameters"]["required_status_checks"] == [
        {"context": "gh-infra/jenkins", "integration_id": 303}
    ]


def test_rulesets_friendly_tag_non_fast_forward_rule():
    requester = FakeRequester()
    feature = FakeFeature(
        yaml={
            "rulesets": [
                {
                    "name": "Release tags",
                    "type": "tag",
                    "branches": {"includes": ["v*.*.*"], "excludes": []},
                    "non_fast_forward": True,
                }
            ]
        },
        previous_yaml={},
        requester=requester,
    )

    configure_rulesets(feature)

    payload = requester.calls[1]["input"]
    assert payload["target"] == "tag"
    rule_types = [rule["type"] for rule in payload["rules"]]
    assert "non_fast_forward" in rule_types


def test_rulesets_friendly_conversation_resolution_false_does_not_add_pull_request_rule():
    requester = FakeRequester()
    feature = FakeFeature(
        yaml={
            "rulesets": [
                {
                    "name": "Branch Protection",
                    "type": "branch",
                    "required_signatures": True,
                    "required_conversation_resolution": False,
                }
            ]
        },
        previous_yaml={},
        requester=requester,
    )

    configure_rulesets(feature)

    payload = requester.calls[1]["input"]
    rule_types = [rule["type"] for rule in payload["rules"]]
    assert "required_signatures" in rule_types
    assert "pull_request" not in rule_types


def test_rulesets_update_existing_ruleset():
    payload = _build_ruleset_payload("Default branch checks")
    requester = FakeRequester(rulesets=[{"id": 22, "name": payload["name"], "rules": []}])
    feature = FakeFeature(
        yaml={"rulesets": [payload]},
        previous_yaml={"rulesets": [payload]},
        requester=requester,
    )

    configure_rulesets(feature)

    assert [call["method"] for call in requester.calls] == ["GET", "PUT"]
    assert requester.calls[1]["url"] == "/repos/apache/infrastructure-asfyaml/rulesets/22"
    assert requester.calls[1]["input"] == payload


def test_rulesets_removed_section_deletes_previously_managed_rulesets():
    existing = [{"id": 31, "name": "Default branch checks", "rules": []}]
    requester = FakeRequester(rulesets=existing)
    feature = FakeFeature(
        yaml={},
        previous_yaml={"rulesets": [_build_ruleset_payload("Default branch checks")]},
        requester=requester,
    )

    configure_rulesets(feature)

    assert [call["method"] for call in requester.calls] == ["GET", "DELETE"]
    assert requester.calls[1]["url"] == "/repos/apache/infrastructure-asfyaml/rulesets/31"


def test_rulesets_noop_mode_does_not_call_api(capsys):
    payload = _build_ruleset_payload("Default branch checks")
    requester = FakeRequester()
    feature = FakeFeature(
        yaml={"rulesets": [payload]},
        previous_yaml={},
        requester=requester,
        noop_enabled=True,
    )

    configure_rulesets(feature)

    captured = capsys.readouterr()
    assert "noop mode active" in captured.out
    assert requester.calls == []


def test_rulesets_conflict_with_copilot_convenience_block():
    payload = _build_ruleset_payload(COPILOT_RULESET_NAME)
    requester = FakeRequester()
    feature = FakeFeature(
        yaml={"rulesets": [payload], "copilot_code_review": {"enabled": True}},
        previous_yaml={},
        requester=requester,
    )

    with pytest.raises(Exception, match="Cannot configure Copilot Code Review via both"):
        configure_rulesets(feature)

    assert requester.calls == []


def test_rulesets_conflict_with_copilot_when_ruleset_contains_copilot_rule():
    payload = {
        "name": "Custom copilot ruleset",
        "target": "branch",
        "enforcement": "active",
        "conditions": {"ref_name": {"include": ["~DEFAULT_BRANCH"], "exclude": []}},
        "rules": [{"type": "copilot_code_review", "parameters": {"review_draft_pull_requests": False}}],
    }
    requester = FakeRequester()
    feature = FakeFeature(
        yaml={"rulesets": [payload], "copilot_code_review": {"enabled": True}},
        previous_yaml={},
        requester=requester,
    )

    with pytest.raises(Exception, match="Cannot configure Copilot Code Review via both"):
        configure_rulesets(feature)

    assert requester.calls == []


def test_rulesets_duplicate_names_raise():
    payload = _build_ruleset_payload("Duplicate name")
    requester = FakeRequester()
    feature = FakeFeature(
        yaml={"rulesets": [payload, payload]},
        previous_yaml={},
        requester=requester,
    )

    with pytest.raises(Exception, match=r"Duplicate ruleset name in github\.rulesets"):
        configure_rulesets(feature)


def test_rulesets_mixed_raw_and_friendly_keys_raise():
    requester = FakeRequester()
    feature = FakeFeature(
        yaml={
            "rulesets": [
                {
                    "name": "Branch Protection",
                    "target": "branch",
                    "rules": [{"type": "required_signatures"}],
                    "required_signatures": True,
                }
            ]
        },
        previous_yaml={},
        requester=requester,
    )

    with pytest.raises(Exception, match="Raw ruleset payload cannot mix friendly keys"):
        configure_rulesets(feature)
