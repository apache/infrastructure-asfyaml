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

"""Unit tests for .asf.yaml GitHub code scanning (CodeQL default setup) feature."""

import json
from types import SimpleNamespace
from typing import Any

import asfyaml.asfyaml
import asfyaml.dataobjects
from asfyaml.feature.github.code_scanning import code_scanning
from helpers import YamlTest

# Set .asf.yaml to debug mode
asfyaml.asfyaml.DEBUG = True


valid_code_scanning_simple = YamlTest(
    None,
    None,
    """
github:
    code_scanning: true
""",
)

valid_code_scanning_disabled = YamlTest(
    None,
    None,
    """
github:
    code_scanning: false
""",
)

valid_code_scanning_all_settings = YamlTest(
    None,
    None,
    """
github:
    code_scanning:
      query_suite: extended
      threat_model: remote_and_local
      languages:
        - java-kotlin
        - python
        - some-future-language
""",
)

invalid_code_scanning_query_suite = YamlTest(
    asfyaml.asfyaml.ASFYAMLException,
    "when expecting one of",
    """
github:
    code_scanning:
      query_suite: paranoid
""",
)

invalid_code_scanning_threat_model = YamlTest(
    asfyaml.asfyaml.ASFYAMLException,
    "when expecting one of",
    """
github:
    code_scanning:
      threat_model: local
""",
)

invalid_code_scanning_duplicate_language = YamlTest(
    asfyaml.asfyaml.ASFYAMLException,
    "duplicate found",
    """
github:
    code_scanning:
      languages:
        - python
        - python
""",
)

invalid_code_scanning_unknown_key = YamlTest(
    asfyaml.asfyaml.ASFYAMLException,
    "unexpected key not in schema",
    """
github:
    code_scanning:
      enabled: true
""",
)


class FakeRequester:
    def __init__(
        self,
        *,
        state: str = "not-configured",
        query_suite: str | None = None,
        threat_model: str | None = None,
        languages: list[str] | None = None,
        patch_status: int = 200,
        patch_body: str = "{}",
        get_body: str | None = None,
    ):
        self.state = state
        self.query_suite = query_suite
        self.threat_model = threat_model
        self.languages = languages or []
        self.patch_status = patch_status
        self.patch_body = patch_body
        self.get_body = get_body
        self.calls: list[dict[str, Any]] = []

    def requestJson(self, method: str, url: str, input: dict[str, Any] | None = None):  # noqa: N802
        self.calls.append({"method": method, "url": url, "input": input})
        if method == "GET":
            if self.get_body is not None:
                return 200, {}, self.get_body
            return (
                200,
                {},
                json.dumps(
                    {
                        "state": self.state,
                        "query_suite": self.query_suite,
                        "threat_model": self.threat_model,
                        "languages": self.languages,
                        "updated_at": None,
                        "schedule": None,
                    }
                ),
            )
        return self.patch_status, {}, self.patch_body


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


DEFAULT_SETUP_URL = "/repos/apache/infrastructure-asfyaml/code-scanning/default-setup"


def test_basic_yaml(test_repo: asfyaml.dataobjects.Repository):
    print("[github] Testing code scanning")

    tests_to_run = (
        valid_code_scanning_simple,
        valid_code_scanning_disabled,
        valid_code_scanning_all_settings,
        invalid_code_scanning_query_suite,
        invalid_code_scanning_threat_model,
        invalid_code_scanning_duplicate_language,
        invalid_code_scanning_unknown_key,
    )

    for test in tests_to_run:
        with test.ctx():
            a = asfyaml.asfyaml.ASFYamlInstance(
                repo=test_repo, committer="humbedooh", config_data=test.yaml, branch=asfyaml.dataobjects.DEFAULT_BRANCH
            )
            a.environments_enabled.add("noop")
            a.no_cache = True
            a.run_parts()


def test_enable_configures_default_setup():
    requester = FakeRequester()
    feature = FakeFeature(
        yaml={"code_scanning": True},
        previous_yaml={},
        requester=requester,
    )

    code_scanning(feature)

    assert [call["method"] for call in requester.calls] == ["GET", "PATCH"]
    assert requester.calls[1]["url"] == DEFAULT_SETUP_URL
    assert requester.calls[1]["input"] == {"state": "configured"}


def test_enable_with_all_settings():
    requester = FakeRequester()
    feature = FakeFeature(
        yaml={
            "code_scanning": {
                "query_suite": "extended",
                "threat_model": "remote_and_local",
                "languages": ["java-kotlin", "python"],
            }
        },
        previous_yaml={},
        requester=requester,
    )

    code_scanning(feature)

    assert [call["method"] for call in requester.calls] == ["GET", "PATCH"]
    assert requester.calls[1]["input"] == {
        "state": "configured",
        "query_suite": "extended",
        "threat_model": "remote_and_local",
        "languages": ["java-kotlin", "python"],
    }


def test_enable_skips_when_already_configured():
    requester = FakeRequester(state="configured", query_suite="default")
    feature = FakeFeature(
        yaml={"code_scanning": True},
        previous_yaml={},
        requester=requester,
    )

    code_scanning(feature)

    assert [call["method"] for call in requester.calls] == ["GET"]


def test_enable_skips_ignores_unspecified_fields():
    # GET reports auto-detected languages and a threat model; the yaml does not manage them.
    requester = FakeRequester(
        state="configured", query_suite="default", threat_model="remote", languages=["go", "python"]
    )
    feature = FakeFeature(
        yaml={"code_scanning": True},
        previous_yaml={},
        requester=requester,
    )

    code_scanning(feature)

    assert [call["method"] for call in requester.calls] == ["GET"]


def test_enable_skips_when_languages_match_in_different_order():
    requester = FakeRequester(state="configured", query_suite="default", languages=["python", "go"])
    feature = FakeFeature(
        yaml={"code_scanning": {"query_suite": "default", "languages": ["go", "python"]}},
        previous_yaml={},
        requester=requester,
    )

    code_scanning(feature)

    assert [call["method"] for call in requester.calls] == ["GET"]


def test_query_suite_change_repatches():
    requester = FakeRequester(state="configured", query_suite="default")
    feature = FakeFeature(
        yaml={"code_scanning": {"query_suite": "extended"}},
        previous_yaml={"code_scanning": True},
        requester=requester,
    )

    code_scanning(feature)

    assert [call["method"] for call in requester.calls] == ["GET", "PATCH"]
    assert requester.calls[1]["input"] == {"state": "configured", "query_suite": "extended"}


def test_languages_change_repatches():
    requester = FakeRequester(state="configured", query_suite="default", languages=["python"])
    feature = FakeFeature(
        yaml={"code_scanning": {"query_suite": "default", "languages": ["python", "go"]}},
        previous_yaml={},
        requester=requester,
    )

    code_scanning(feature)

    assert [call["method"] for call in requester.calls] == ["GET", "PATCH"]
    assert requester.calls[1]["input"]["languages"] == ["python", "go"]


def test_patch_202_accepted_is_success():
    requester = FakeRequester(patch_status=202, patch_body='{"run_id": 42, "run_url": "https://example.invalid"}')
    feature = FakeFeature(
        yaml={"code_scanning": True},
        previous_yaml={},
        requester=requester,
    )

    code_scanning(feature)

    assert [call["method"] for call in requester.calls] == ["GET", "PATCH"]


def test_patch_other_2xx_is_success():
    requester = FakeRequester(patch_status=204, patch_body="")
    feature = FakeFeature(
        yaml={"code_scanning": True},
        previous_yaml={},
        requester=requester,
    )

    code_scanning(feature)

    assert [call["method"] for call in requester.calls] == ["GET", "PATCH"]


def test_get_non_json_raises_helpful_error():
    requester = FakeRequester(get_body="<html>Service unavailable</html>")
    feature = FakeFeature(
        yaml={"code_scanning": True},
        previous_yaml={},
        requester=requester,
    )

    with YamlTest(Exception, "expected JSON", "").ctx():
        code_scanning(feature)


def test_disable_patches_not_configured():
    requester = FakeRequester(state="configured", query_suite="default")
    feature = FakeFeature(
        yaml={"code_scanning": False},
        previous_yaml={"code_scanning": True},
        requester=requester,
    )

    code_scanning(feature)

    assert [call["method"] for call in requester.calls] == ["GET", "PATCH"]
    assert requester.calls[1]["input"] == {"state": "not-configured"}


def test_disable_skips_when_never_managed():
    requester = FakeRequester(state="configured", query_suite="default")
    feature = FakeFeature(
        # Never managed by .asf.yaml: a setup enabled by INFRA is left untouched.
        yaml={"code_scanning": False},
        previous_yaml={},
        requester=requester,
    )

    code_scanning(feature)

    assert requester.calls == []


def test_disable_skips_when_not_configured():
    requester = FakeRequester(state="not-configured")
    feature = FakeFeature(
        yaml={"code_scanning": False},
        previous_yaml={"code_scanning": True},
        requester=requester,
    )

    code_scanning(feature)

    assert [call["method"] for call in requester.calls] == ["GET"]


def test_removed_section_disables_when_previously_managed():
    requester = FakeRequester(state="configured", query_suite="default")
    feature = FakeFeature(
        yaml={},
        previous_yaml={"code_scanning": True},
        requester=requester,
    )

    code_scanning(feature)

    assert [call["method"] for call in requester.calls] == ["GET", "PATCH"]
    assert requester.calls[1]["input"] == {"state": "not-configured"}


def test_absent_section_untouched_when_never_managed():
    requester = FakeRequester(state="configured", query_suite="default")
    feature = FakeFeature(
        yaml={},
        previous_yaml={},
        requester=requester,
    )

    code_scanning(feature)

    assert requester.calls == []


def test_noop_mode_does_not_call_api(capsys):
    requester = FakeRequester()
    feature = FakeFeature(
        yaml={"code_scanning": True},
        previous_yaml={},
        requester=requester,
        noop_enabled=True,
    )

    code_scanning(feature)

    captured = capsys.readouterr()
    assert "noop mode active" in captured.out
    assert requester.calls == []


def test_patch_403_raises_helpful_error():
    requester = FakeRequester(patch_status=403, patch_body='{"message": "Advanced Security is not enabled"}')
    feature = FakeFeature(
        yaml={"code_scanning": True},
        previous_yaml={},
        requester=requester,
    )

    with YamlTest(Exception, "not permitted", "").ctx():
        code_scanning(feature)


def test_patch_409_raises_helpful_error():
    requester = FakeRequester(patch_status=409, patch_body='{"message": "default setup is already being enabled"}')
    feature = FakeFeature(
        yaml={"code_scanning": True},
        previous_yaml={},
        requester=requester,
    )

    with YamlTest(Exception, "already in progress", "").ctx():
        code_scanning(feature)


def test_patch_422_raises_helpful_error():
    requester = FakeRequester(patch_status=422, patch_body='{"message": "no CodeQL supported languages found"}')
    feature = FakeFeature(
        yaml={"code_scanning": True},
        previous_yaml={},
        requester=requester,
    )

    with YamlTest(Exception, "Validation failed", "").ctx():
        code_scanning(feature)
