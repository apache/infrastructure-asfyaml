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

"""Unit tests for .asf.yaml GitHub Actions OIDC subject claim feature."""

from types import SimpleNamespace
from typing import Any

import pytest

import asfyaml.asfyaml
import asfyaml.dataobjects
from asfyaml.feature.github.oidc_subject import oidc_subject
from helpers import YamlTest

# Set .asf.yaml to debug mode
asfyaml.asfyaml.DEBUG = True

OIDC_URL = "/repos/apache/infrastructure-asfyaml/actions/oidc/customization/sub"


valid_immutable = YamlTest(
    None,
    None,
    """
github:
    oidc_subject:
      use_immutable_subject: true
""",
)

valid_claim_keys = YamlTest(
    None,
    None,
    """
github:
    oidc_subject:
      use_immutable_subject: true
      include_claim_keys:
        - repo
        - context
""",
)

invalid_immutable_type = YamlTest(
    asfyaml.asfyaml.ASFYAMLException,
    "when expecting a boolean value",
    """
github:
    oidc_subject:
      use_immutable_subject: maybe
""",
)

invalid_unknown_key = YamlTest(
    asfyaml.asfyaml.ASFYAMLException,
    "unexpected key not in schema",
    """
github:
    oidc_subject:
      use_default: true
""",
)


class FakeRequester:
    def __init__(self, status: int = 201, body: str = ""):
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


def run(yaml: dict[str, Any], previous_yaml: dict[str, Any] | None = None, **kwargs) -> FakeRequester:
    requester = FakeRequester(**kwargs)
    oidc_subject(FakeFeature(yaml=yaml, previous_yaml=previous_yaml or {}, requester=requester))
    return requester


def test_basic_yaml(test_repo: asfyaml.dataobjects.Repository):
    print("[github] Testing OIDC subject claim")

    tests_to_run = (
        valid_immutable,
        valid_claim_keys,
        invalid_immutable_type,
        invalid_unknown_key,
    )

    for test in tests_to_run:
        with test.ctx():
            a = asfyaml.asfyaml.ASFYamlInstance(
                repo=test_repo, committer="humbedooh", config_data=test.yaml, branch=asfyaml.dataobjects.DEFAULT_BRANCH
            )
            a.environments_enabled.add("noop")
            a.no_cache = True
            a.run_parts()


def test_enable_immutable_subject():
    requester = run({"oidc_subject": {"use_immutable_subject": True}})

    assert requester.calls == [
        {"method": "PUT", "url": OIDC_URL, "input": {"use_default": True, "use_immutable_subject": True}}
    ]


def test_explicit_false_disables_immutable_subject():
    # Sent even with a cold cache, so an explicit false also turns off a format set by hand.
    requester = run({"oidc_subject": {"use_immutable_subject": False}})

    assert requester.calls == [
        {"method": "PUT", "url": OIDC_URL, "input": {"use_default": True, "use_immutable_subject": False}}
    ]


def test_custom_claim_keys():
    requester = run({"oidc_subject": {"include_claim_keys": ["repo", "context", "job_workflow_ref"]}})

    assert requester.calls == [
        {
            "method": "PUT",
            "url": OIDC_URL,
            "input": {"use_default": False, "include_claim_keys": ["repo", "context", "job_workflow_ref"]},
        }
    ]


def test_removed_claim_keys_restore_default_template():
    requester = run(
        {"oidc_subject": {"use_immutable_subject": True}},
        {"oidc_subject": {"use_immutable_subject": True, "include_claim_keys": ["repo", "context"]}},
    )

    assert requester.calls == [
        {"method": "PUT", "url": OIDC_URL, "input": {"use_default": True, "use_immutable_subject": True}}
    ]


def test_removed_immutable_key_leaves_format_alone():
    requester = run(
        {"oidc_subject": {"include_claim_keys": ["repo"]}},
        {"oidc_subject": {"use_immutable_subject": True, "include_claim_keys": ["repo"]}},
    )

    assert requester.calls == [
        {"method": "PUT", "url": OIDC_URL, "input": {"use_default": False, "include_claim_keys": ["repo"]}}
    ]


def test_removed_section_restores_default_template_only():
    requester = run(
        {"description": "unrelated"},
        {"oidc_subject": {"use_immutable_subject": True, "include_claim_keys": ["repo"]}},
    )

    assert requester.calls == [{"method": "PUT", "url": OIDC_URL, "input": {"use_default": True}}]


def test_no_section_is_noop():
    requester = run({"description": "unrelated"})

    assert requester.calls == []


@pytest.mark.parametrize(
    "keys, expected",
    [
        ([], "must list at least one claim key"),
        (["repo", "job-workflow"], "letters, digits and underscores, got job-workflow"),
        (["repo", "repo"], "must not repeat a claim key"),
    ],
)
def test_invalid_claim_keys_raise(keys: list[str], expected: str):
    requester = FakeRequester()
    feature = FakeFeature(yaml={"oidc_subject": {"include_claim_keys": keys}}, previous_yaml={}, requester=requester)

    with YamlTest(Exception, expected, "").ctx():
        oidc_subject(feature)

    assert requester.calls == []


@pytest.mark.parametrize(
    "status, body, expected",
    [
        (400, '{"message": "Bad Request"}', "GitHub rejected the OIDC subject claim settings"),
        (403, '{"message": "Resource not accessible by integration"}', "Not allowed to set the OIDC subject"),
        (404, '{"message": "Not Found"}', "not found or not accessible"),
        (422, '{"message": "Validation Failed"}', "Validation failed while setting"),
        (418, "not json at all", "Unexpected response while setting"),
    ],
)
def test_error_response_raises(status: int, body: str, expected: str):
    with YamlTest(Exception, expected, "").ctx():
        run({"oidc_subject": {"use_immutable_subject": True}}, status=status, body=body)


def test_noop_mode_does_not_call_api(capsys):
    requester = FakeRequester()
    feature = FakeFeature(
        yaml={"oidc_subject": {"use_immutable_subject": True}},
        previous_yaml={},
        requester=requester,
        noop_enabled=True,
    )

    oidc_subject(feature)

    captured = capsys.readouterr()
    assert "noop mode active" in captured.out
    assert requester.calls == []
