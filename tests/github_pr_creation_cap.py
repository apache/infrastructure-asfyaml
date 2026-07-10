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

from types import SimpleNamespace
from typing import Any

import asfyaml.asfyaml
import asfyaml.dataobjects
from asfyaml.feature.github.pr_creation_cap import pr_creation_cap
from helpers import YamlTest

# Set .asf.yaml to debug mode
asfyaml.asfyaml.DEBUG = True

CAP_URL = "/repos/apache/infrastructure-asfyaml/interaction-limits/pulls/creation-cap"


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


class FakeRequester:
    def __init__(self):
        self.calls: list[dict[str, Any]] = []

    def requestJson(self, method: str, url: str, input: dict[str, Any] | None = None):  # noqa: N802
        self.calls.append({"method": method, "url": url, "input": input})
        return 200, {}, "{}"


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


def test_disabled_and_never_configured_is_noop():
    requester = FakeRequester()
    feature = FakeFeature(
        yaml={"pull_requests": {"creation_cap": {"enabled": False}}},
        previous_yaml={},
        requester=requester,
    )

    pr_creation_cap(feature)

    assert requester.calls == []


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
