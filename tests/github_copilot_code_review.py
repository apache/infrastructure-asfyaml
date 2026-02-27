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

"""Unit tests for .asf.yaml GitHub Copilot code review feature."""

from types import SimpleNamespace
from typing import Any

import asfyaml.asfyaml
import asfyaml.dataobjects
from asfyaml.feature.github.copilot_code_review import (
    RULESET_NAME,
    _build_copilot_ruleset_payload,
    copilot_code_review,
)
from helpers import YamlTest

# Set .asf.yaml to debug mode
asfyaml.asfyaml.DEBUG = True


valid_copilot_code_review = YamlTest(
    None,
    None,
    """
github:
    copilot_code_review:
      enabled: true
      review_drafts: false
      review_on_push: true
""",
)

invalid_copilot_code_review = YamlTest(
    asfyaml.asfyaml.ASFYAMLException,
    "when expecting a bool",
    """
github:
    copilot_code_review:
      enabled:
        - true
""",
)


class FakeRequester:
    def __init__(self, rulesets: list[dict[str, Any]] | None = None):
        self.rulesets = rulesets or []
        self.calls: list[dict[str, Any]] = []

    def requestJson(self, method: str, url: str, input: dict[str, Any] | None = None):  # noqa: N802
        self.calls.append({"method": method, "url": url, "input": input})
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
    print("[github] Testing copilot code review")

    tests_to_run = (
        valid_copilot_code_review,
        invalid_copilot_code_review,
    )

    for test in tests_to_run:
        with test.ctx():
            a = asfyaml.asfyaml.ASFYamlInstance(
                repo=test_repo, committer="humbedooh", config_data=test.yaml, branch=asfyaml.dataobjects.DEFAULT_BRANCH
            )
            a.environments_enabled.add("noop")
            a.no_cache = True
            a.run_parts()


def test_enable_copilot_code_review_creates_ruleset():
    requester = FakeRequester()
    feature = FakeFeature(
        yaml={"copilot_code_review": {"enabled": True, "review_drafts": False, "review_on_push": True}},
        previous_yaml={},
        requester=requester,
    )

    copilot_code_review(feature)

    assert [call["method"] for call in requester.calls] == ["GET", "POST"]
    assert requester.calls[1]["url"] == "/repos/apache/infrastructure-asfyaml/rulesets"
    assert requester.calls[1]["input"] == _build_copilot_ruleset_payload(False, True)


def test_enable_copilot_code_review_updates_existing_ruleset():
    existing_rulesets = [
        {
            "id": 73,
            "name": RULESET_NAME,
            "rules": [{"type": "copilot_code_review", "parameters": {}}],
        }
    ]
    requester = FakeRequester(rulesets=existing_rulesets)
    feature = FakeFeature(
        yaml={"copilot_code_review": {"enabled": True, "review_drafts": True, "review_on_push": False}},
        previous_yaml={"copilot_code_review": {"enabled": True, "review_drafts": False, "review_on_push": False}},
        requester=requester,
    )

    copilot_code_review(feature)

    assert [call["method"] for call in requester.calls] == ["GET", "PUT"]
    assert requester.calls[1]["url"] == "/repos/apache/infrastructure-asfyaml/rulesets/73"
    assert requester.calls[1]["input"] == _build_copilot_ruleset_payload(True, False)


def test_disable_copilot_code_review_deletes_existing_ruleset():
    existing_rulesets = [
        {
            "id": 89,
            "name": RULESET_NAME,
            "rules": [{"type": "copilot_code_review", "parameters": {}}],
        }
    ]
    requester = FakeRequester(rulesets=existing_rulesets)
    feature = FakeFeature(
        yaml={"copilot_code_review": {"enabled": False}},
        previous_yaml={"copilot_code_review": {"enabled": True}},
        requester=requester,
    )

    copilot_code_review(feature)

    assert [call["method"] for call in requester.calls] == ["GET", "DELETE"]
    assert requester.calls[1]["url"] == "/repos/apache/infrastructure-asfyaml/rulesets/89"


def test_removed_copilot_code_review_section_deletes_existing_ruleset():
    existing_rulesets = [
        {
            "id": 101,
            "name": RULESET_NAME,
            "rules": [{"type": "copilot_code_review", "parameters": {}}],
        }
    ]
    requester = FakeRequester(rulesets=existing_rulesets)
    feature = FakeFeature(
        yaml={},
        previous_yaml={"copilot_code_review": {"enabled": True}},
        requester=requester,
    )

    copilot_code_review(feature)

    assert [call["method"] for call in requester.calls] == ["GET", "DELETE"]
    assert requester.calls[1]["url"] == "/repos/apache/infrastructure-asfyaml/rulesets/101"


def test_noop_mode_does_not_call_api(capsys):
    requester = FakeRequester()
    feature = FakeFeature(
        yaml={"copilot_code_review": {"enabled": True}},
        previous_yaml={},
        requester=requester,
        noop_enabled=True,
    )

    copilot_code_review(feature)

    captured = capsys.readouterr()
    assert "noop mode active" in captured.out
    assert requester.calls == []
