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

"""Unit tests for .asf.yaml GitHub autolink features"""

from types import SimpleNamespace
from typing import Any

from helpers import YamlTest
import asfyaml.asfyaml
import asfyaml.dataobjects
from asfyaml.feature.github.autolink import autolink as configure_autolinks

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
    "String must be uppercase or digits only, e.g. INFRA or LOG4J2.",
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
        invalid_github_autolink_not_list,
    )

    for test in tests_to_run:
        with test.ctx() as _:
            a = asfyaml.asfyaml.ASFYamlInstance(
                repo=test_repo, committer="humbedooh", config_data=test.yaml, branch=asfyaml.dataobjects.DEFAULT_BRANCH
            )
            a.environments_enabled.add("noop")
            a.no_cache = True
            a.run_parts()


def make_autolink(autolink_id: int, jira_space: str, is_alphanumeric: bool = False) -> SimpleNamespace:
    return SimpleNamespace(
        id=autolink_id,
        key_prefix=f"{jira_space}-",
        url_template=f"https://issues.apache.org/jira/browse/{jira_space}-<num>",
        is_alphanumeric=is_alphanumeric,
    )


def expected_create(jira_space: str) -> dict:
    return {
        "key_prefix": f"{jira_space}-",
        "url_template": f"https://issues.apache.org/jira/browse/{jira_space}-<num>",
        "is_alphanumeric": False,
    }


class FakeGHRepo:
    def __init__(self, existing_autolinks: list[SimpleNamespace] | None = None):
        self.existing_autolinks = existing_autolinks or []
        self.created: list[dict] = []
        self.removed: list[SimpleNamespace] = []

    def get_autolinks(self):
        return list(self.existing_autolinks)

    def create_autolink(self, key_prefix: str, url_template: str, is_alphanumeric: bool):
        self.created.append(
            {"key_prefix": key_prefix, "url_template": url_template, "is_alphanumeric": is_alphanumeric}
        )

    def remove_autolink(self, autolink: SimpleNamespace) -> bool:
        self.removed.append(autolink)
        return True


class FakeFeature:
    def __init__(
        self,
        *,
        yaml: dict[str, Any],
        previous_yaml: dict[str, Any],
        ghrepo: FakeGHRepo,
        noop_enabled: bool = False,
    ):
        self.yaml = yaml
        self.previous_yaml = previous_yaml
        self.ghrepo = ghrepo
        self.instance = SimpleNamespace(no_cache=False)
        self._noop_enabled = noop_enabled

    def noop(self, directive: str) -> bool:
        if self._noop_enabled:
            print(f"[github::{directive}] Not applying changes, noop mode active.")
            return True
        return False


def test_autolink_create_new():
    ghrepo = FakeGHRepo()
    feature = FakeFeature(yaml={"autolink_jira": ["FOO", "BAR"]}, previous_yaml={}, ghrepo=ghrepo)

    configure_autolinks(feature)

    assert ghrepo.created == [expected_create("FOO"), expected_create("BAR")]
    assert ghrepo.removed == []


def test_autolink_existing_not_recreated():
    ghrepo = FakeGHRepo(existing_autolinks=[make_autolink(1, "FOO")])
    feature = FakeFeature(yaml={"autolink_jira": ["FOO"]}, previous_yaml={"autolink_jira": ["FOO"]}, ghrepo=ghrepo)

    configure_autolinks(feature)

    assert ghrepo.created == []
    assert ghrepo.removed == []


def test_autolink_section_removed_removes_all():
    foo = make_autolink(1, "FOO")
    bar = make_autolink(2, "BAR")
    ghrepo = FakeGHRepo(existing_autolinks=[foo, bar])
    feature = FakeFeature(yaml={}, previous_yaml={"autolink_jira": ["FOO", "BAR"]}, ghrepo=ghrepo)

    configure_autolinks(feature)

    assert ghrepo.created == []
    assert ghrepo.removed == [foo, bar]


def test_autolink_entry_removed_removes_only_that_autolink():
    foo = make_autolink(1, "FOO")
    bar = make_autolink(2, "BAR")
    ghrepo = FakeGHRepo(existing_autolinks=[foo, bar])
    feature = FakeFeature(
        yaml={"autolink_jira": ["FOO"]}, previous_yaml={"autolink_jira": ["FOO", "BAR"]}, ghrepo=ghrepo
    )

    configure_autolinks(feature)

    assert ghrepo.created == []
    assert ghrepo.removed == [bar]


def test_autolink_single_string_previous_removed():
    infra = make_autolink(1, "INFRA")
    ghrepo = FakeGHRepo(existing_autolinks=[infra])
    feature = FakeFeature(yaml={}, previous_yaml={"autolink_jira": "INFRA"}, ghrepo=ghrepo)

    configure_autolinks(feature)

    assert ghrepo.created == []
    assert ghrepo.removed == [infra]


def test_autolink_config_is_authoritative_for_jira_autolinks():
    # A Jira autolink set up outside .asf.yaml (e.g. via INFRA ticket) is removed once
    # autolink_jira is configured and doesn't list it
    manual = make_autolink(1, "OTHER")
    foo = make_autolink(2, "FOO")
    ghrepo = FakeGHRepo(existing_autolinks=[manual, foo])
    feature = FakeFeature(yaml={"autolink_jira": ["FOO"]}, previous_yaml={"autolink_jira": ["FOO"]}, ghrepo=ghrepo)

    configure_autolinks(feature)

    assert ghrepo.created == []
    assert ghrepo.removed == [manual]


def test_autolink_non_jira_autolinks_untouched():
    # Autolinks pointing anywhere else than the ASF Jira are never touched
    other = SimpleNamespace(
        id=1, key_prefix="GH-", url_template="https://github.com/apache/foo/issues/<num>", is_alphanumeric=False
    )
    ghrepo = FakeGHRepo(existing_autolinks=[other])
    feature = FakeFeature(yaml={}, previous_yaml={"autolink_jira": ["FOO"]}, ghrepo=ghrepo)

    configure_autolinks(feature)

    assert ghrepo.created == []
    assert ghrepo.removed == []


def test_autolink_alphanumeric_autolink_recreated():
    # Autolinks created with is_alphanumeric=true (matching e.g. SOLR-FOO) are recreated
    # with is_alphanumeric=false so they only match numeric ticket ids
    foo = make_autolink(1, "FOO", is_alphanumeric=True)
    ghrepo = FakeGHRepo(existing_autolinks=[foo])
    feature = FakeFeature(yaml={"autolink_jira": ["FOO"]}, previous_yaml={"autolink_jira": ["FOO"]}, ghrepo=ghrepo)

    configure_autolinks(feature)

    assert ghrepo.removed == [foo]
    assert ghrepo.created == [expected_create("FOO")]


def test_autolink_never_configured_does_nothing():
    ghrepo = FakeGHRepo(existing_autolinks=[make_autolink(1, "FOO")])
    feature = FakeFeature(yaml={}, previous_yaml={}, ghrepo=ghrepo)

    configure_autolinks(feature)

    assert ghrepo.created == []
    assert ghrepo.removed == []


def test_autolink_noop_mode_makes_no_changes():
    bar = make_autolink(1, "BAR")
    ghrepo = FakeGHRepo(existing_autolinks=[bar])
    feature = FakeFeature(
        yaml={"autolink_jira": ["FOO"]},
        previous_yaml={"autolink_jira": ["BAR"]},
        ghrepo=ghrepo,
        noop_enabled=True,
    )

    configure_autolinks(feature)

    assert ghrepo.created == []
    assert ghrepo.removed == []
