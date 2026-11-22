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

"""Unit tests for .asf.yaml GitHub features"""

from types import SimpleNamespace
from typing import Any

import pytest

import asfyaml.asfyaml
import asfyaml.dataobjects
from asfyaml.feature.github.features import config_features
from helpers import YamlTest
# Set .asf.yaml to debug mode
asfyaml.asfyaml.DEBUG = True


valid_github_features = YamlTest(
    None,
    None,
    """
github:
    features:
        issues: true
        wiki: false
        projects: true
        discussions: false
    labels:
        - a
        - b
        - c
    description: Apache Foo
    homepage: https://foo.apache.org/
""",
)

valid_github_features_pull_requests_disabled = YamlTest(
    None,
    None,
    """
github:
    features:
        issues: false
        pullrequests: false
""",
)

invalid_github_features_pull_requests_not_bool = YamlTest(
    asfyaml.asfyaml.ASFYAMLException,
    "expecting a boolean value",
    """
github:
    features:
        pullrequests: nope
""",
)

# Something isn't a bool
invalid_github_features_not_bool = YamlTest(
    asfyaml.asfyaml.ASFYAMLException,
    "expecting a boolean value",
    """
github:
    features:
        issues: maybe
        wiki: false
        projects: true
        discussions: false
""",
)

# Something isn't a valid directive
invalid_github_features_unknown_directive = YamlTest(
    asfyaml.asfyaml.ASFYAMLException,
    "unexpected key not in schema 'foobar'",
    """
github:
    features:
        foobar: true
        wiki: false
        projects: true
        discussions: false
""",
)


# Discussions enabled but no mailing list target set
invalid_github_features_no_disc_target = YamlTest(
    asfyaml.asfyaml.ASFYAMLException,
    "GitHub discussions can only be enabled if a mailing list target exists",
    """
github:
    features:
        issues: true
        wiki: false
        projects: true
        discussions: true
""",
)


def test_basic_yaml(test_repo: asfyaml.dataobjects.Repository):
    print("[github] Testing features")

    tests_to_run = (
        valid_github_features,
        valid_github_features_pull_requests_disabled,
        invalid_github_features_pull_requests_not_bool,
        invalid_github_features_not_bool,
        invalid_github_features_unknown_directive,
        invalid_github_features_no_disc_target
    )

    for test in tests_to_run:
        with test.ctx() as vs:
            a = asfyaml.asfyaml.ASFYamlInstance(
                repo=test_repo, committer="humbedooh", config_data=test.yaml, branch=asfyaml.dataobjects.DEFAULT_BRANCH
            )
            a.environments_enabled.add("noop")
            a.no_cache = True
            a.run_parts()


REPO_URL = "/repos/apache/infrastructure-asfyaml"


class FakeRequester:
    def __init__(self, status: int = 200, body: str = "{}"):
        self.calls: list[dict[str, Any]] = []
        self.status = status
        self.body = body

    def requestJson(self, method: str, url: str, input: dict[str, Any] | None = None):  # noqa: N802
        self.calls.append({"method": method, "url": url, "input": input})
        return self.status, {}, self.body


class FakeRepo:
    def __init__(self, requester: FakeRequester):
        self._requester = requester
        self.edits: list[dict[str, Any]] = []

    def edit(self, **kwargs):
        self.edits.append(kwargs)


class FakeFeature:
    def __init__(
        self,
        *,
        yaml: dict[str, Any],
        previous_yaml: dict[str, Any] | None = None,
        requester: FakeRequester | None = None,
        noop_enabled: bool = False,
    ):
        self.yaml = yaml
        self.previous_yaml = previous_yaml or {}
        self.repository = SimpleNamespace(org_id="apache", name="infrastructure-asfyaml")
        self.requester = requester or FakeRequester()
        self.ghrepo = FakeRepo(self.requester)
        self.instance = SimpleNamespace(features=SimpleNamespace(notifications=None))
        self._noop_enabled = noop_enabled

    def noop(self, directive: str) -> bool:
        if self._noop_enabled:
            print(f"[github::{directive}] Not applying changes, noop mode active.")
            return True
        return False


def pr_patches(feature: FakeFeature) -> list[Any]:
    return [c["input"] for c in feature.requester.calls if c["method"] == "PATCH" and c["url"] == REPO_URL]


@pytest.mark.parametrize("enabled", [True, False])
def test_pull_requests_set_explicitly(enabled: bool):
    feature = FakeFeature(yaml={"features": {"issues": True, "pullrequests": enabled}})
    config_features(feature)
    assert pr_patches(feature) == [{"has_pull_requests": enabled}]
    # The other features still go through PyGithub, without has_pull_requests.
    assert feature.ghrepo.edits == [
        {"has_issues": True, "has_wiki": False, "has_projects": False, "has_discussions": False}
    ]


def test_pull_requests_untouched_when_key_absent():
    # A features block without pullrequests must not switch pull requests off.
    feature = FakeFeature(yaml={"features": {"issues": True}})
    config_features(feature)
    assert feature.requester.calls == []


def test_pull_requests_untouched_without_features_block():
    feature = FakeFeature(yaml={"description": "Apache Foo"})
    config_features(feature)
    assert feature.requester.calls == []
    assert feature.ghrepo.edits == []


def test_pull_requests_reenabled_when_key_removed():
    feature = FakeFeature(
        yaml={"features": {"issues": True}},
        previous_yaml={"features": {"issues": True, "pullrequests": False}},
    )
    config_features(feature)
    assert pr_patches(feature) == [{"has_pull_requests": True}]


def test_pull_requests_reenabled_when_features_block_removed():
    feature = FakeFeature(
        yaml={"description": "Apache Foo"},
        previous_yaml={"features": {"pullrequests": False}},
    )
    config_features(feature)
    assert pr_patches(feature) == [{"has_pull_requests": True}]
    assert feature.ghrepo.edits == []


def test_pull_requests_not_touched_when_previously_enabled_and_removed():
    feature = FakeFeature(
        yaml={"features": {"issues": True}},
        previous_yaml={"features": {"pullrequests": True}},
    )
    config_features(feature)
    assert feature.requester.calls == []


def test_pull_requests_noop_mode_does_not_call_api(capsys):
    feature = FakeFeature(yaml={"features": {"pullrequests": False}}, noop_enabled=True)
    config_features(feature)
    assert feature.requester.calls == []
    assert feature.ghrepo.edits == []
    assert "Setting has_pull_requests to 'False'" in capsys.readouterr().out


def test_pull_requests_api_error_is_reported():
    feature = FakeFeature(
        yaml={"features": {"pullrequests": False}},
        requester=FakeRequester(status=422, body='{"message": "Validation Failed"}'),
    )
    with pytest.raises(Exception, match="Failed to disable pull requests on 'apache/infrastructure-asfyaml': HTTP 422"):
        config_features(feature)
