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

"""Unit tests for the .asf.yaml `project` (ATR metadata) feature"""

import json

import pytest

import asfyaml.asfyaml
import asfyaml.dataobjects
from asfyaml.feature.project import (
    _doap_metadata,
    _exchange_token_for_jwt,
    _is_transient,
    _parse_doap,
    _post_with_retry,
    _validate_doap_url,
)
from helpers import YamlTest

# The ATR project's own description, reused across the DOAP fixture and assertions.
ATR_DESCRIPTION = (
    "ATR is a platform through which committees of Apache Software Foundation (ASF) projects can make "
    'official ASF software releases. Official ASF releases are endorsed as an "act of the Foundation". '
    "It is therefore important that the foundation - its board, members, committees, and contributors - "
    "and the general public can have confidence in the releases."
)

# A DOAP file for the ATR project, covering every field we map. DOAP has no
# equivalent of lifecycle_page or committee, so those are not represented here.
SAMPLE_DOAP = f"""<?xml version="1.0"?>
<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
         xmlns="http://usefulinc.com/ns/doap#"
         xmlns:asfext="http://projects.apache.org/ns/asfext#">
  <Project rdf:about="https://tooling.apache.org/trusted-releases.html">
    <name>Apache Trusted Releases</name>
    <shortdesc>A platform for making official ASF software releases.</shortdesc>
    <description>{ATR_DESCRIPTION}</description>
    <homepage rdf:resource="https://tooling.apache.org/trusted-releases.html"/>
    <bug-database rdf:resource="https://github.com/apache/tooling-trusted-releases/issues"/>
    <download-page rdf:resource="https://github.com/apache/tooling-trusted-releases"/>
    <mailing-list rdf:resource="https://tooling.apache.org/volunteer.html"/>
    <programming-language>python</programming-language>
    <category rdf:resource="http://projects.apache.org/category/build-management"/>
    <repository>
      <GitRepository>
        <location rdf:resource="git+ssh://git@github.com:apache/tooling-trusted-releases.git"/>
        <browse rdf:resource="https://github.com/apache/tooling-trusted-releases"/>
      </GitRepository>
    </repository>
    <asfext:implements>
      <asfext:Standard>
        <asfext:title>OWASP ASVS</asfext:title>
        <asfext:url rdf:resource="https://owasp.org/www-project-application-security-verification-standard/"/>
      </asfext:Standard>
    </asfext:implements>
  </Project>
</rdf:RDF>""".encode()


valid_metadata = YamlTest(
    None,
    None,
    """
project:
    metadata:
        key: tooling-trusted-releases
        committee: tooling
        name: Apache Trusted Releases
        short_description: A platform for making official ASF software releases.
        homepage: https://tooling.apache.org/trusted-releases.html
        lifecycle_page: https://tooling.apache.org/trusted-releases.html
        download_page: https://github.com/apache/tooling-trusted-releases
        bug_database: https://github.com/apache/tooling-trusted-releases/issues
        mailing_lists: https://tooling.apache.org/volunteer.html
        repositories:
            - git+ssh://git@github.com:apache/tooling-trusted-releases.git
        standards:
            - https://owasp.org/www-project-application-security-verification-standard/
        categories:
            - build-management
        programming_languages:
            - python
""",
)

valid_metadata_with_policy = YamlTest(
    None,
    None,
    """
project:
    metadata:
        key: tooling-trusted-releases
        committee: tooling
        name: Apache Trusted Releases
    policy:
        vote_recipients:
            to: private@tooling.apache.org
            cc:
                - dev@tooling.apache.org
        announce_recipients:
            to: announce@apache.org
""",
)

valid_metadata_with_doap = YamlTest(
    None,
    None,
    """
project:
    metadata:
        key: tooling-trusted-releases
        committee: tooling
        doap: https://tooling.apache.org/doap.rdf
""",
)

# The security fields and the download path suffix, as added to ATR.
valid_security_and_download_suffix = YamlTest(
    None,
    None,
    """
project:
    metadata:
        key: tooling
        committee: tooling
        name: Apache Tooling
        homepage: https://github.com/test
        security_contact: security@apache.org
        threat_model_link: http://test/
        threat_model_src_link: http://test/
    policy:
        download_path_suffix: tesettest
""",
)

# metadata is a required key
invalid_missing_metadata = YamlTest(
    asfyaml.asfyaml.ASFYAMLException,
    "required key",
    """
project:
    features:
        atr_sync: true
""",
)

# key and committee are required inside metadata
invalid_missing_key = YamlTest(
    asfyaml.asfyaml.ASFYAMLException,
    "required key",
    """
project:
    metadata:
        committee: tooling
        name: Apache Trusted Releases
""",
)

# unexpected key inside metadata
invalid_unknown_metadata_key = YamlTest(
    asfyaml.asfyaml.ASFYAMLException,
    "unexpected key not in schema 'foobar'",
    """
project:
    metadata:
        key: tooling-trusted-releases
        committee: tooling
        name: Apache Trusted Releases
        foobar: nope
""",
)

valid_full_policy = YamlTest(
    None,
    None,
    """
project:
    metadata:
        key: tooling-trusted-releases
        committee: tooling
        name: Apache Trusted Releases
    policy:
        announce_release_subject: "[ANNOUNCE] Apache Foo released"
        binary_artifact_paths:
            - dist/*.jar
        file_tag_mappings:
            sources:
                - "*.tar.gz"
            binaries:
                - "*.jar"
        github_repository_branch: main
        github_vote_workflow_path:
            - .github/workflows/vote.yml
        license_check_mode: RAT
        rat_excludes_url: https://raw.githubusercontent.com/apache/example/main/.rat-excludes
        vote_recipients:
            to: private@tooling.apache.org
        min_hours: 72
        vote_mode: email
""",
)

# Each email template can be given as a URL instead of inline text
valid_template_urls = YamlTest(
    None,
    None,
    """
project:
    metadata:
        key: tooling-trusted-releases
        committee: tooling
        name: Apache Trusted Releases
    policy:
        announce_release_template_url: https://raw.githubusercontent.com/apache/example/main/.atr/announce.txt
        start_vote_template_url: https://raw.githubusercontent.com/apache/example/main/.atr/start-vote.txt
        finish_vote_template_url: https://raw.githubusercontent.com/apache/example/main/.atr/finish-vote.txt
        vote_comment_template_url: https://raw.githubusercontent.com/apache/example/main/.atr/vote-comment.txt
""",
)

# A calver project describes its cycles with a date format under metadata.
valid_calver_metadata = YamlTest(
    None,
    None,
    """
project:
    metadata:
        key: tooling-trusted-releases
        committee: tooling
        name: Apache Trusted Releases
        version_method: calver
        calver_format: "(YY.MM).N"
""",
)

# vote_mode only accepts manual/email/trusted
invalid_bad_vote_mode = YamlTest(
    asfyaml.asfyaml.ASFYAMLException,
    "when expecting one of: manual, email, trusted",
    """
project:
    metadata:
        key: tooling-trusted-releases
        committee: tooling
        name: Apache Trusted Releases
    policy:
        vote_mode: telepathy
""",
)

# unexpected key inside policy
invalid_unknown_policy_key = YamlTest(
    asfyaml.asfyaml.ASFYAMLException,
    "unexpected key not in schema 'reviewers'",
    """
project:
    metadata:
        key: tooling-trusted-releases
        committee: tooling
        name: Apache Trusted Releases
    policy:
        reviewers:
            to: someone@tooling.apache.org
""",
)


def test_schema_validation(test_repo: asfyaml.dataobjects.Repository):
    print("[project] Testing schema validation")
    tests_to_run = (
        valid_metadata,
        valid_metadata_with_policy,
        valid_full_policy,
        valid_calver_metadata,
        valid_template_urls,
        valid_metadata_with_doap,
        valid_security_and_download_suffix,
        invalid_missing_metadata,
        invalid_missing_key,
        invalid_unknown_metadata_key,
        invalid_bad_vote_mode,
        invalid_unknown_policy_key,
    )
    for test in tests_to_run:
        with test.ctx():
            a = asfyaml.asfyaml.ASFYamlInstance(
                repo=test_repo, committer="arm", config_data=test.yaml, branch=asfyaml.dataobjects.DEFAULT_BRANCH
            )
            a.environments_enabled.add("noop")
            a.no_cache = True
            a.run_parts(validate_only=True)


def test_doap_full_mapping():
    metadata = _doap_metadata(SAMPLE_DOAP)
    assert metadata == {
        "name": "Apache Trusted Releases",
        "description": ATR_DESCRIPTION,
        "short_description": "A platform for making official ASF software releases.",
        "homepage": "https://tooling.apache.org/trusted-releases.html",
        "download_page": "https://github.com/apache/tooling-trusted-releases",
        "bug_database": "https://github.com/apache/tooling-trusted-releases/issues",
        "mailing_lists": "https://tooling.apache.org/volunteer.html",
        "programming_languages": ["python"],
        "categories": ["build-management"],
        "repositories": ["git+ssh://git@github.com:apache/tooling-trusted-releases.git"],
        "standards": ["https://owasp.org/www-project-application-security-verification-standard/"],
    }


def test_doap_partial_only_includes_present_fields():
    doap = b"""<?xml version="1.0"?>
<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
         xmlns="http://usefulinc.com/ns/doap#">
  <Project>
    <name>Apache Trusted Releases</name>
    <homepage rdf:resource="https://tooling.apache.org/trusted-releases.html"/>
  </Project>
</rdf:RDF>"""
    assert _doap_metadata(doap) == {
        "name": "Apache Trusted Releases",
        "homepage": "https://tooling.apache.org/trusted-releases.html",
    }


def test_doap_collects_multiple_repos_and_standards():
    # Mirrors real DOAP files (e.g. Maven's two repos, FOP's SVN repo and many standards):
    # repositories may be Git or SVN and appear more than once, and each Standard carries
    # body/id we ignore in favour of the url.
    doap = b"""<?xml version="1.0"?>
<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
         xmlns="http://usefulinc.com/ns/doap#"
         xmlns:asfext="http://projects.apache.org/ns/asfext#">
  <Project>
    <name>Apache Example</name>
    <repository>
      <SVNRepository>
        <location rdf:resource="https://svn.apache.org/repos/asf/example/trunk/"/>
        <browse rdf:resource="https://svn.apache.org/viewvc/example/trunk/"/>
      </SVNRepository>
    </repository>
    <repository>
      <GitRepository>
        <location rdf:resource="https://gitbox.apache.org/repos/asf/example.git"/>
        <browse rdf:resource="https://github.com/apache/example"/>
      </GitRepository>
    </repository>
    <asfext:implements>
      <asfext:Standard>
        <asfext:title>Extensible Stylesheet Language (XSL-FO 1.1)</asfext:title>
        <asfext:body>W3C</asfext:body>
        <asfext:id>XSL 1.1</asfext:id>
        <asfext:url rdf:resource="http://www.w3.org/TR/xsl11/"/>
      </asfext:Standard>
    </asfext:implements>
    <asfext:implements>
      <asfext:Standard>
        <asfext:title>Portable Document Format (PDF 1.4)</asfext:title>
        <asfext:body>Adobe Systems Incorporated</asfext:body>
        <asfext:id>PDF 1.4</asfext:id>
        <asfext:url rdf:resource="https://www.adobe.com/pdf/1.4"/>
      </asfext:Standard>
    </asfext:implements>
  </Project>
</rdf:RDF>"""
    assert _doap_metadata(doap) == {
        "name": "Apache Example",
        "repositories": [
            "https://svn.apache.org/repos/asf/example/trunk/",
            "https://gitbox.apache.org/repos/asf/example.git",
        ],
        "standards": ["http://www.w3.org/TR/xsl11/", "https://www.adobe.com/pdf/1.4"],
    }


def test_doap_missing_project_element_raises():
    doap = b"""<?xml version="1.0"?>
<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
         xmlns="http://usefulinc.com/ns/doap#"></rdf:RDF>"""
    with pytest.raises(Exception, match="No doap:Project element found"):
        _doap_metadata(doap)


def test_doap_malformed_xml_raises():
    with pytest.raises(Exception, match="Could not parse DOAP file"):
        _doap_metadata(b"<rdf:RDF><not closed")


def test_validate_doap_url_allows_apache_and_raw_github_apache():
    # apache.org and its subdomains, plus raw.githubusercontent.com/apache, are permitted.
    _validate_doap_url("https://tooling.apache.org/doap.rdf")
    _validate_doap_url("https://apache.org/doap.rdf")
    _validate_doap_url("https://raw.githubusercontent.com/apache/tooling-trusted-releases/main/doap.rdf")


def test_validate_doap_url_rejects_github_com():
    # github.com itself redirects to raw.githubusercontent.com, and we don't follow redirects.
    with pytest.raises(Exception, match="host not allowed"):
        _validate_doap_url("https://github.com/apache/tooling-trusted-releases/raw/main/doap.rdf")


def test_validate_doap_url_rejects_http_scheme():
    with pytest.raises(Exception, match="must use https"):
        _validate_doap_url("http://tooling.apache.org/doap.rdf")


def test_validate_doap_url_rejects_foreign_host():
    with pytest.raises(Exception, match="host not allowed"):
        _validate_doap_url("https://evil.example.com/doap.rdf")


def test_validate_doap_url_rejects_internal_metadata_endpoint():
    with pytest.raises(Exception, match="host not allowed"):
        _validate_doap_url("https://169.254.169.254/latest/meta-data/")


def test_validate_doap_url_rejects_raw_github_non_apache_org():
    with pytest.raises(Exception, match="host not allowed"):
        _validate_doap_url("https://raw.githubusercontent.com/someoneelse/project/main/doap.rdf")


def test_validate_doap_url_rejects_lookalike_host():
    # A host that merely contains apache.org must not slip through.
    with pytest.raises(Exception, match="host not allowed"):
        _validate_doap_url("https://apache.org.evil.com/doap.rdf")


def test_parse_doap_downloads_then_maps(monkeypatch):
    class FakeResponse:
        ok = True
        is_redirect = False
        content = SAMPLE_DOAP

    captured = {}

    def fake_get(url, timeout=None, allow_redirects=True):
        captured["url"] = url
        captured["timeout"] = timeout
        captured["allow_redirects"] = allow_redirects
        return FakeResponse()

    monkeypatch.setattr("asfyaml.feature.project.requests.get", fake_get)
    metadata = _parse_doap("https://tooling.apache.org/doap.rdf")
    assert captured["url"] == "https://tooling.apache.org/doap.rdf"
    assert captured["allow_redirects"] is False
    assert metadata["name"] == "Apache Trusted Releases"


def test_parse_doap_download_failure_raises(monkeypatch):
    class FakeResponse:
        ok = False
        is_redirect = False
        status_code = 404

    monkeypatch.setattr(
        "asfyaml.feature.project.requests.get", lambda url, timeout=None, allow_redirects=True: FakeResponse()
    )
    with pytest.raises(Exception, match="Could not download DOAP file"):
        _parse_doap("https://tooling.apache.org/missing.rdf")


def test_parse_doap_redirect_rejected(monkeypatch):
    class FakeResponse:
        ok = True
        is_redirect = True
        status_code = 302

    monkeypatch.setattr(
        "asfyaml.feature.project.requests.get", lambda url, timeout=None, allow_redirects=True: FakeResponse()
    )
    with pytest.raises(Exception, match="returned a redirect"):
        _parse_doap("https://tooling.apache.org/moved.rdf")


def test_parse_doap_rejects_disallowed_host_before_fetching(monkeypatch):
    def explode(*args, **kwargs):
        raise AssertionError("requests.get must not be called for a disallowed host")

    monkeypatch.setattr("asfyaml.feature.project.requests.get", explode)
    with pytest.raises(Exception, match="host not allowed"):
        _parse_doap("https://evil.example.com/doap.rdf")


def test_noop_payload_shape(atr_repo: asfyaml.dataobjects.Repository, capsys):
    yaml = """
project:
    metadata:
        key: tooling-trusted-releases
        committee: tooling
        name: Apache Trusted Releases
        homepage: https://tooling.apache.org/trusted-releases.html
    policy:
        vote_recipients:
            to: private@tooling.apache.org
"""
    a = asfyaml.asfyaml.ASFYamlInstance(
        repo=atr_repo, committer="arm", config_data=yaml, branch=asfyaml.dataobjects.DEFAULT_BRANCH
    )
    a.environments_enabled.add("noop")
    a.no_cache = True
    a.run_parts()

    out = capsys.readouterr().out
    payload = json.loads(out[out.index("{") : out.rindex("}") + 1])
    assert payload["project_key"] == "tooling-trusted-releases"
    assert payload["committee_key"] == "tooling"
    assert "key" not in payload["project"]
    assert "committee" not in payload["project"]
    assert payload["project"]["name"] == "Apache Trusted Releases"
    assert payload["policy"]["vote_recipients"]["to"] == "private@tooling.apache.org"


def test_noop_payload_omits_sync_mode_unless_authored(atr_repo: asfyaml.dataobjects.Repository, capsys):
    yaml = """
project:
    metadata:
        key: tooling-trusted-releases
        committee: tooling
    features:
        atr_sync: true
"""
    a = asfyaml.asfyaml.ASFYamlInstance(
        repo=atr_repo, committer="arm", config_data=yaml, branch=asfyaml.dataobjects.DEFAULT_BRANCH
    )
    a.environments_enabled.add("noop")
    a.no_cache = True
    a.run_parts()

    out = capsys.readouterr().out
    payload = json.loads(out[out.index("{") : out.rindex("}") + 1])
    assert "sync_mode" not in payload


def test_noop_payload_carries_sync_mode(atr_repo: asfyaml.dataobjects.Repository, capsys):
    yaml = """
project:
    metadata:
        key: tooling-trusted-releases
        committee: tooling
    features:
        atr_sync_mode: full
"""
    a = asfyaml.asfyaml.ASFYamlInstance(
        repo=atr_repo, committer="arm", config_data=yaml, branch=asfyaml.dataobjects.DEFAULT_BRANCH
    )
    a.environments_enabled.add("noop")
    a.no_cache = True
    a.run_parts()

    out = capsys.readouterr().out
    payload = json.loads(out[out.index("{") : out.rindex("}") + 1])
    assert payload["sync_mode"] == "full"


def test_noop_payload_policy_types(atr_repo: asfyaml.dataobjects.Repository, capsys):
    yaml = """
project:
    metadata:
        key: tooling-trusted-releases
        committee: tooling
        name: Apache Trusted Releases
    policy:
        min_hours: 72
        manual_vote: true
        license_check_mode: RAT
        binary_artifact_paths:
            - dist/*.jar
        file_tag_mappings:
            sources:
                - "*.tar.gz"
"""
    a = asfyaml.asfyaml.ASFYamlInstance(
        repo=atr_repo, committer="arm", config_data=yaml, branch=asfyaml.dataobjects.DEFAULT_BRANCH
    )
    a.environments_enabled.add("noop")
    a.no_cache = True
    a.run_parts()

    out = capsys.readouterr().out
    policy = json.loads(out[out.index("{") : out.rindex("}") + 1])["policy"]
    assert policy["min_hours"] == 72  # int, not "72"
    assert policy["manual_vote"] is True  # bool, not "true"
    assert policy["license_check_mode"] == "RAT"
    assert policy["binary_artifact_paths"] == ["dist/*.jar"]
    assert policy["file_tag_mappings"] == {"sources": ["*.tar.gz"]}


def test_noop_payload_carries_security_and_download_suffix(atr_repo: asfyaml.dataobjects.Repository, capsys):
    yaml = """
project:
    metadata:
        key: tooling
        committee: tooling
        name: Apache Tooling
        security_contact: security@apache.org
        threat_model_link: http://test/
        threat_model_src_link: http://test/
    policy:
        download_path_suffix: tesettest
"""
    a = asfyaml.asfyaml.ASFYamlInstance(
        repo=atr_repo, committer="arm", config_data=yaml, branch=asfyaml.dataobjects.DEFAULT_BRANCH
    )
    a.environments_enabled.add("noop")
    a.no_cache = True
    a.run_parts()

    out = capsys.readouterr().out
    payload = json.loads(out[out.index("{") : out.rindex("}") + 1])
    # Security fields ride along in the project block; the suffix is a policy field.
    assert payload["project"]["security_contact"] == "security@apache.org"
    assert payload["project"]["threat_model_link"] == "http://test/"
    assert payload["project"]["threat_model_src_link"] == "http://test/"
    assert payload["policy"]["download_path_suffix"] == "tesettest"


def test_noop_payload_carries_template_urls(atr_repo: asfyaml.dataobjects.Repository, capsys):
    url = "https://raw.githubusercontent.com/apache/example/main/.atr/start-vote.txt"
    yaml = f"""
project:
    metadata:
        key: tooling
        committee: tooling
        name: Apache Tooling
    policy:
        start_vote_template_url: {url}
"""
    a = asfyaml.asfyaml.ASFYamlInstance(
        repo=atr_repo, committer="arm", config_data=yaml, branch=asfyaml.dataobjects.DEFAULT_BRANCH
    )
    a.environments_enabled.add("noop")
    a.no_cache = True
    a.run_parts()

    out = capsys.readouterr().out
    policy = json.loads(out[out.index("{") : out.rindex("}") + 1])["policy"]
    assert policy["start_vote_template_url"] == url


def test_noop_payload_carries_version_scheme(atr_repo: asfyaml.dataobjects.Repository, capsys):
    yaml = """
project:
    metadata:
        key: tooling
        committee: tooling
        name: Apache Tooling
        version_method: calver
        calver_format: "(YY.MM).N"
"""
    a = asfyaml.asfyaml.ASFYamlInstance(
        repo=atr_repo, committer="arm", config_data=yaml, branch=asfyaml.dataobjects.DEFAULT_BRANCH
    )
    a.environments_enabled.add("noop")
    a.no_cache = True
    a.run_parts()

    out = capsys.readouterr().out
    project = json.loads(out[out.index("{") : out.rindex("}") + 1])["project"]
    # The version scheme rides along in the project block, alongside the DOAP-style fields.
    assert project["version_method"] == "calver"
    assert project["calver_format"] == "(YY.MM).N"


def test_noop_payload_doap_keeps_atr_only_fields(atr_repo: asfyaml.dataobjects.Repository, capsys, monkeypatch):
    class FakeResponse:
        ok = True
        is_redirect = False
        content = SAMPLE_DOAP

    monkeypatch.setattr(
        "asfyaml.feature.project.requests.get", lambda url, timeout=None, allow_redirects=True: FakeResponse()
    )
    yaml = """
project:
    metadata:
        key: tooling
        committee: tooling
        doap: https://tooling.apache.org/doap.rdf
        security_contact: security@apache.org
        version_method: calver
        calver_format: "(YY.MM).N"
"""
    a = asfyaml.asfyaml.ASFYamlInstance(
        repo=atr_repo, committer="arm", config_data=yaml, branch=asfyaml.dataobjects.DEFAULT_BRANCH
    )
    a.environments_enabled.add("noop")
    a.no_cache = True
    a.run_parts()

    out = capsys.readouterr().out
    project = json.loads(out[out.index("{") : out.rindex("}") + 1])["project"]
    # DOAP supplies the fields it can express...
    assert project["name"] == "Apache Trusted Releases"
    # ...while the ATR-only fields, which DOAP has no vocabulary for, survive from .asf.yaml.
    assert project["security_contact"] == "security@apache.org"
    assert project["version_method"] == "calver"
    assert project["calver_format"] == "(YY.MM).N"


def test_committee_matching_repo_prefix_is_accepted(atr_repo: asfyaml.dataobjects.Repository, capsys):
    # Repo "tooling-trusted-releases" accepts committee "tooling" (prefix before the hyphen).
    yaml = """
project:
    metadata:
        key: tooling-test
        committee: tooling
        name: Apache Trusted Releases
"""
    a = asfyaml.asfyaml.ASFYamlInstance(
        repo=atr_repo, committer="arm", config_data=yaml, branch=asfyaml.dataobjects.DEFAULT_BRANCH
    )
    a.environments_enabled.add("noop")
    a.no_cache = True
    a.run_parts()

    out = capsys.readouterr().out
    payload = json.loads(out[out.index("{") : out.rindex("}") + 1])
    assert payload["project_key"] == "tooling-test"
    assert payload["committee_key"] == "tooling"


def test_exchange_token_for_jwt_posts_system_pat(monkeypatch):
    # The config holds a system PAT; ATR swaps it for a JWT at /api/jwt/create.
    captured = {}

    class FakeResponse:
        ok = True
        status_code = 200

        @staticmethod
        def json():
            return {"asfuid": "system", "jwt": "a-short-lived-jwt"}

    def fake_post(url, json=None, timeout=None):
        captured["url"] = url
        captured["json"] = json
        return FakeResponse()

    monkeypatch.setattr("asfyaml.feature.project.requests.post", fake_post)
    jwt = _exchange_token_for_jwt("https://atr.example", "the-system-pat")
    assert jwt == "a-short-lived-jwt"
    assert captured["url"] == "https://atr.example/api/jwt/create"
    assert captured["json"] == {"asfuid": "system", "pat": "the-system-pat"}


def test_exchange_token_for_jwt_failure_raises(monkeypatch):
    class FakeResponse:
        ok = False
        status_code = 401
        text = "unauthorized"

    monkeypatch.setattr("asfyaml.feature.project.requests.post", lambda url, json=None, timeout=None: FakeResponse())
    with pytest.raises(Exception, match="ATR token exchange failed"):
        _exchange_token_for_jwt("https://atr.example", "bad-pat")


def test_exchange_token_for_jwt_missing_jwt_raises(monkeypatch):
    class FakeResponse:
        ok = True
        status_code = 200
        text = '{"asfuid": "system"}'

        @staticmethod
        def json():
            return {"asfuid": "system"}

    monkeypatch.setattr("asfyaml.feature.project.requests.post", lambda url, json=None, timeout=None: FakeResponse())
    with pytest.raises(Exception, match="returned no JWT"):
        _exchange_token_for_jwt("https://atr.example", "the-system-pat")


class _FakeResp:
    """Minimal stand-in for a requests.Response, enough for the retry helpers."""

    def __init__(self, status_code, *, text="", content_type=""):
        self.status_code = status_code
        self.text = text
        self.headers = {"Content-Type": content_type} if content_type else {}
        self.ok = status_code < 400


# A redeploy's proxy 500: httpd's SSL-handshake error page while the backend has no TLS listener.
_PROXY_500 = _FakeResp(
    500,
    text=(
        "<html><head><title>500 Proxy Error</title></head>"
        "<body><h1>Proxy Error</h1>Error during SSL Handshake with remote server</body></html>"
    ),
    content_type="text/html; charset=iso-8859-1",
)


def test_is_transient_classification():
    # The 5xx codes ATR emits while restarting, plus the proxy's SSL-handshake 500, are transient.
    assert _is_transient(_FakeResp(503, text="unavailable")) is True
    assert _is_transient(_FakeResp(502, text="bad gateway")) is True
    assert _is_transient(_PROXY_500) is True
    # A genuine ATR 500 comes back as JSON, and a 4xx is a real rejection — neither is retried.
    assert _is_transient(_FakeResp(500, text='{"error": "boom"}', content_type="application/json")) is False
    assert _is_transient(_FakeResp(500, text="mystery html", content_type="text/html")) is False
    assert _is_transient(_FakeResp(400, text="bad request")) is False


def _sequence_poster(monkeypatch, responses):
    """Wire requests.post to hand back `responses` in order, and skip the real backoff sleeps."""
    calls = {"n": 0}

    def fake_post(url, **kwargs):
        resp = responses[calls["n"]]
        calls["n"] += 1
        return resp

    monkeypatch.setattr("asfyaml.feature.project.requests.post", fake_post)
    monkeypatch.setattr("asfyaml.feature.project.time.sleep", lambda _s: None)
    return calls


def test_post_with_retry_recovers_from_proxy_500(monkeypatch):
    # The redeploy's proxy 500 clears once the backend is back, so the retry gets through.
    ok = _FakeResp(200, text='{"success": true}', content_type="application/json")
    calls = _sequence_poster(monkeypatch, [_PROXY_500, ok])
    resp = _post_with_retry("https://atr.example/api/jwt/create")
    assert resp.status_code == 200
    assert calls["n"] == 2  # bounced off the proxy 500, then succeeded


def test_post_with_retry_recovers_from_503(monkeypatch):
    ok = _FakeResp(200, text="ok", content_type="application/json")
    calls = _sequence_poster(monkeypatch, [_FakeResp(503, text="unavailable"), ok])
    resp = _post_with_retry("https://atr.example/api/jwt/create")
    assert resp.status_code == 200
    assert calls["n"] == 2


def test_post_with_retry_bounces_atr_json_500_immediately(monkeypatch):
    # A real ATR 500 isn't a restart blip; it should fail on the first try, not burn the budget.
    calls = _sequence_poster(
        monkeypatch,
        [_FakeResp(500, text='{"error": "boom"}', content_type="application/json")],
    )
    resp = _post_with_retry("https://atr.example/api/project/config")
    assert resp.status_code == 500
    assert calls["n"] == 1  # no retry


def test_committee_not_matching_repo_is_rejected(atr_repo: asfyaml.dataobjects.Repository):
    yaml = """
project:
    metadata:
        key: tooling-trusted-releases
        committee: whimsy
        name: Apache Trusted Releases
"""
    a = asfyaml.asfyaml.ASFYamlInstance(
        repo=atr_repo, committer="arm", config_data=yaml, branch=asfyaml.dataobjects.DEFAULT_BRANCH
    )
    a.environments_enabled.add("noop")
    a.no_cache = True
    with pytest.raises(asfyaml.asfyaml.ASFYAMLException, match="does not match repository name"):
        a.run_parts()


# --- Trusted publishing gate -------------------------------------------------------------
#
# A policy block carrying any of the trusted publishing fields makes the feature check how
# the default branch was protected for the push that landed this .asf.yaml. These tests fake
# the GitHub client at the point the feature would build one, so nothing here hits the network.

import os
from types import SimpleNamespace

import yaml as pyyaml

import asfyaml.feature.project
from asfyaml.feature.project import _RULE_SUITE_ATTEMPTS, ASFATRFeature

PUSH_SHA = "a" * 40
OTHER_SHA = "b" * 40
MAIN_REFLOG = f"{'0' * 40} {PUSH_SHA} refs/heads/main\n"

TP_YAML = """
project:
    metadata:
        key: tooling-trusted-releases
        committee: tooling
        name: Apache Trusted Releases
    policy:
        github_vote_workflow_path:
            - .github/workflows/vote.yml
"""

TP_YAML_WITH_NAME = """
project:
    metadata:
        key: tooling-trusted-releases
        committee: tooling
        name: Apache Trusted Releases
    policy:
        github_repository_name: tooling-trusted-releases
        github_vote_workflow_path:
            - .github/workflows/vote.yml
"""

TP_YAML_WRONG_NAME = """
project:
    metadata:
        key: tooling-trusted-releases
        committee: tooling
        name: Apache Trusted Releases
    policy:
        github_repository_name: tooling-something-else
        github_vote_workflow_path:
            - .github/workflows/vote.yml
"""

# Same trusted publishing fields as TP_YAML, different metadata.
TP_YAML_NEW_METADATA = """
project:
    metadata:
        key: tooling-trusted-releases
        committee: tooling
        name: Apache Trusted Releases
        homepage: https://tooling.apache.org/trusted-releases.html
    policy:
        github_vote_workflow_path:
            - .github/workflows/vote.yml
"""

TP_YAML_NEW_WORKFLOW = """
project:
    metadata:
        key: tooling-trusted-releases
        committee: tooling
        name: Apache Trusted Releases
    policy:
        github_vote_workflow_path:
            - .github/workflows/vote-v2.yml
"""

NO_TP_YAML = """
project:
    metadata:
        key: tooling-trusted-releases
        committee: tooling
        name: Apache Trusted Releases
    policy:
        min_hours: 72
"""


def _rule(rule_type, enforcement="active", result="pass", source="ruleset"):
    return {
        "rule_type": rule_type,
        "enforcement": enforcement,
        "result": result,
        "rule_source": {"type": source, "id": 7, "name": "Default branch"},
    }


PASSING_RULES = [_rule("pull_request"), _rule("non_fast_forward")]


def _suite(*, sha=PUSH_SHA, result="pass", rules=None, suite_id=42):
    """A (list entry, detail) pair as the two rule-suite endpoints hand them back."""
    summary = {"id": suite_id, "after_sha": sha, "before_sha": "0" * 40, "ref": "refs/heads/main", "result": result}
    detail = {**summary, "rule_evaluations": PASSING_RULES if rules is None else rules}
    return summary, detail


class FakeSuiteRequester:
    """Stands in for ghrepo._requester, serving the two rule-suite endpoints.

    `page_size` is how many summaries a list page carries (GitHub honours per_page, this
    ignores it so a test can force a second page). `hidden_for` is how many list calls come
    back empty before the suites appear, to mimic GitHub still indexing the push.
    """

    def __init__(self, *suites, list_status=200, page_size=100, hidden_for=0):
        self.summaries = [summary for summary, _detail in suites]
        self.details = {detail["id"]: detail for _summary, detail in suites}
        self.list_status = list_status
        self.page_size = page_size
        self.hidden_for = hidden_for
        self.calls = []

    def requestJson(self, method, url, parameters=None, headers=None, input=None):
        self.calls.append((method, url, parameters))
        if url.endswith("/rule-suites"):
            if len(self.list_calls) <= self.hidden_for:
                return self.list_status, {}, "[]"
            page = (parameters or {}).get("page", 1)
            start = (page - 1) * self.page_size
            return self.list_status, {}, json.dumps(self.summaries[start : start + self.page_size])
        suite_id = int(url.rsplit("/", 1)[-1])
        return 200, {}, json.dumps(self.details[suite_id])

    @property
    def list_calls(self):
        return [call for call in self.calls if call[1].endswith("/rule-suites")]


@pytest.fixture
def cache_dir(tmp_path, monkeypatch):
    """Point the shared settings cache at a scratch directory."""
    monkeypatch.setattr("asfyaml.asfyaml.BASE_CACHE_PATH", str(tmp_path))
    return tmp_path


def _cache_file(cache_dir, repo):
    return cache_dir / f"projectsettings.{repo.name}.yml"


def _write_cache(cache_dir, repo, yaml_text):
    block = pyyaml.safe_load(yaml_text)["project"]
    _cache_file(cache_dir, repo).write_text(pyyaml.dump(block, default_flow_style=False))


def _wire_github(monkeypatch, requester):
    """Hand the feature a fake GitHub client, a token from the environment, and no real sleeps."""

    def connect(self, token):
        self._ghrepo = SimpleNamespace(_requester=requester)

    monkeypatch.setattr(ASFATRFeature, "_connect_github", connect)
    monkeypatch.setenv("GH_TOKEN", "test-token")
    monkeypatch.setattr("asfyaml.feature.project.time.sleep", lambda _s: None)


def _forbid_github(monkeypatch):
    """Make any attempt to read a token or build a client fail the test."""

    def explode(*args, **kwargs):
        raise AssertionError("the feature must not touch GitHub here")

    monkeypatch.setattr(ASFATRFeature, "_connect_github", explode)
    monkeypatch.setattr("asfyaml.feature.project._github_token", explode)


def _wire_atr(monkeypatch, *, ok=True):
    """Fake the ATR side of a live run: config, token exchange and the final POST."""
    posted = {}

    def fake_post(url, **kwargs):
        posted["url"] = url
        posted["json"] = kwargs.get("json")
        return _FakeResp(200 if ok else 422, text='{"success": true}' if ok else '{"error": "nope"}')

    monkeypatch.setattr("asfyaml.feature.project._load_config", lambda path: {"url": "x", "token": "pat"})
    monkeypatch.setattr("asfyaml.feature.project._exchange_token_for_jwt", lambda base_url, token: "jwt")
    monkeypatch.setattr("asfyaml.feature.project._post_with_retry", fake_post)
    return posted


def _tp_repo(atr_repo, reflog=MAIN_REFLOG):
    return asfyaml.dataobjects.Repository(str(atr_repo.path), reflog=reflog)


def _run(repo, yaml_text, *, noop=True, no_cache=False):
    a = asfyaml.asfyaml.ASFYamlInstance(
        repo=repo, committer="arm", config_data=yaml_text, branch=asfyaml.dataobjects.DEFAULT_BRANCH
    )
    if noop:
        a.environments_enabled.add("noop")
    a.no_cache = no_cache
    a.run_parts()


def _payload(out):
    return json.loads(out[out.index("{") : out.rindex("}") + 1])


def test_tp_no_fields_never_touches_github(atr_repo, cache_dir, capsys, monkeypatch):
    _forbid_github(monkeypatch)
    _run(_tp_repo(atr_repo), NO_TP_YAML)
    payload = _payload(capsys.readouterr().out)
    assert payload["policy"] == {"min_hours": 72}


def test_tp_passing_suite_sends_payload_with_repository_name(atr_repo, cache_dir, capsys, monkeypatch):
    requester = FakeSuiteRequester(_suite())
    _wire_github(monkeypatch, requester)
    _run(_tp_repo(atr_repo), TP_YAML)
    out = capsys.readouterr().out
    payload = _payload(out)
    # The repository name is pinned to this repo when workflow paths are given without one.
    assert payload["policy"]["github_repository_name"] == "tooling-trusted-releases"
    assert payload["policy"]["github_vote_workflow_path"] == [".github/workflows/vote.yml"]
    assert "[project] default branch 'main' passed the protection check" in out
    assert "pull_request" in out and "non_fast_forward" in out
    # One list call scoped to the default branch over the widest window, then the detail.
    method, url, parameters = requester.list_calls[0]
    assert method == "GET"
    assert url == "/repos/apache/tooling-trusted-releases/rulesets/rule-suites"
    assert parameters == {"ref": "refs/heads/main", "time_period": "month", "per_page": 100, "page": 1}
    assert requester.calls[-1][1] == "/repos/apache/tooling-trusted-releases/rulesets/rule-suites/42"


def test_tp_authored_repository_name_matching_is_accepted(atr_repo, cache_dir, capsys, monkeypatch):
    _wire_github(monkeypatch, FakeSuiteRequester(_suite()))
    _run(_tp_repo(atr_repo), TP_YAML_WITH_NAME)
    payload = _payload(capsys.readouterr().out)
    assert payload["policy"]["github_repository_name"] == "tooling-trusted-releases"


def test_tp_authored_repository_name_mismatch_raises_before_github(atr_repo, cache_dir, monkeypatch):
    _forbid_github(monkeypatch)
    with pytest.raises(asfyaml.asfyaml.ASFYAMLException) as excinfo:
        _run(_tp_repo(atr_repo), TP_YAML_WRONG_NAME)
    message = str(excinfo.value)
    assert "tooling-something-else" in message
    assert "tooling-trusted-releases" in message


def test_tp_bypass_result_raises(atr_repo, cache_dir, monkeypatch):
    _wire_github(monkeypatch, FakeSuiteRequester(_suite(result="bypass")))
    with pytest.raises(asfyaml.asfyaml.ASFYAMLException, match="bypass"):
        _run(_tp_repo(atr_repo), TP_YAML)


def test_tp_missing_non_fast_forward_rule_raises(atr_repo, cache_dir, monkeypatch):
    _wire_github(monkeypatch, FakeSuiteRequester(_suite(rules=[_rule("pull_request")])))
    with pytest.raises(asfyaml.asfyaml.ASFYAMLException, match="non_fast_forward"):
        _run(_tp_repo(atr_repo), TP_YAML)


def test_tp_missing_pull_request_rule_raises(atr_repo, cache_dir, monkeypatch):
    _wire_github(monkeypatch, FakeSuiteRequester(_suite(rules=[_rule("non_fast_forward")])))
    with pytest.raises(asfyaml.asfyaml.ASFYAMLException, match="pull_request"):
        _run(_tp_repo(atr_repo), TP_YAML)


def test_tp_evaluate_mode_rule_does_not_count(atr_repo, cache_dir, monkeypatch):
    rules = [_rule("pull_request"), _rule("non_fast_forward", enforcement="evaluate")]
    _wire_github(monkeypatch, FakeSuiteRequester(_suite(rules=rules)))
    with pytest.raises(asfyaml.asfyaml.ASFYAMLException) as excinfo:
        _run(_tp_repo(atr_repo), TP_YAML)
    message = str(excinfo.value)
    assert "non_fast_forward" in message
    assert "evaluate" in message


def test_tp_failure_message_tells_the_project_what_to_add(atr_repo, cache_dir, monkeypatch):
    _wire_github(monkeypatch, FakeSuiteRequester())
    with pytest.raises(asfyaml.asfyaml.ASFYAMLException) as excinfo:
        _run(_tp_repo(atr_repo), TP_YAML)
    message = str(excinfo.value)
    assert "main" in message and PUSH_SHA in message
    assert "github: rulesets:" in message
    assert "pull request" in message.lower() and "force push" in message.lower()
    assert "github_vote_workflow_path" in message
    assert "protected_branches" in message  # classic protection is called out as not counting


def test_tp_no_suite_after_retries_raises(atr_repo, cache_dir, monkeypatch):
    # A suite exists for the branch, but not for this push.
    requester = FakeSuiteRequester(_suite(sha=OTHER_SHA))
    _wire_github(monkeypatch, requester)
    with pytest.raises(asfyaml.asfyaml.ASFYAMLException, match="none for push"):
        _run(_tp_repo(atr_repo), TP_YAML)
    assert len(requester.list_calls) == _RULE_SUITE_ATTEMPTS


def test_tp_list_error_raises(atr_repo, cache_dir, monkeypatch):
    _wire_github(monkeypatch, FakeSuiteRequester(list_status=403))
    with pytest.raises(asfyaml.asfyaml.ASFYAMLException, match="403"):
        _run(_tp_repo(atr_repo), TP_YAML)


def test_tp_noop_without_token_skips_check(atr_repo, cache_dir, tmp_path, capsys, monkeypatch):
    monkeypatch.delenv("GH_TOKEN", raising=False)
    monkeypatch.setattr("asfyaml.feature.project.GH_TOKEN_FILE", str(tmp_path / "no-such-token"))

    def explode(self, token):
        raise AssertionError("no client should be built without a token")

    monkeypatch.setattr(ASFATRFeature, "_connect_github", explode)
    _run(_tp_repo(atr_repo), TP_YAML)
    out = capsys.readouterr().out
    assert "protection check skipped" in out and "token" in out
    assert _payload(out)["policy"]["github_repository_name"] == "tooling-trusted-releases"


def test_tp_live_without_token_file_raises(atr_repo, cache_dir, tmp_path, monkeypatch):
    monkeypatch.delenv("GH_TOKEN", raising=False)
    monkeypatch.setattr("asfyaml.feature.project.GH_TOKEN_FILE", str(tmp_path / "no-such-token"))
    with pytest.raises(asfyaml.asfyaml.ASFYAMLException, match="no-such-token"):
        _run(_tp_repo(atr_repo), TP_YAML, noop=False)


def test_tp_sha_from_reflog_picks_the_default_branch_push(atr_repo, cache_dir, capsys, monkeypatch):
    reflog = f"{'0' * 40} {OTHER_SHA} refs/heads/feature\n{MAIN_REFLOG}"
    requester = FakeSuiteRequester(_suite(sha=OTHER_SHA, suite_id=1, result="bypass"), _suite(sha=PUSH_SHA, suite_id=2))
    _wire_github(monkeypatch, requester)
    _run(_tp_repo(atr_repo, reflog=reflog), TP_YAML)
    out = capsys.readouterr().out
    assert PUSH_SHA in out
    assert requester.calls[-1][1].endswith("/rule-suites/2")


_GIT_ENV = {
    **os.environ,
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@x",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@x",
}


def _git(repo_path, *args):
    import subprocess

    return subprocess.run(["git", *args], cwd=repo_path, check=True, capture_output=True, text=True, env=_GIT_ENV).stdout.strip()


def _git_repo(tmp_path, *asf_yamls):
    """A real repository named like the ATR project, with one commit per .asf.yaml given.

    None commits without an .asf.yaml at all. Returns the path and the commit SHAs in order.
    """
    repo_path = tmp_path / "tooling-trusted-releases"
    repo_path.mkdir()
    _git(repo_path, "init", "-q", "-b", "main")
    shas = []
    for n, content in enumerate(asf_yamls):
        asf_yaml = repo_path / ".asf.yaml"
        if content is None:
            if asf_yaml.exists():
                _git(repo_path, "rm", "-q", ".asf.yaml")
        else:
            asf_yaml.write_text(content)
            _git(repo_path, "add", ".asf.yaml")
        _git(repo_path, "commit", "-q", "--allow-empty", "-m", f"commit {n}")
        shas.append(_git(repo_path, "rev-parse", "HEAD"))
    return repo_path, shas


def _push_repo(repo_path, old_sha, new_sha):
    """The repository as the gitbox hook sees it: with the reflog line for this push to main."""
    return asfyaml.dataobjects.Repository(str(repo_path), reflog=f"{old_sha} {new_sha} refs/heads/main\n")


def test_tp_sha_from_git_head_without_reflog(tmp_path, cache_dir, capsys, monkeypatch):
    # asfyaml-run has no reflog, so the SHA comes from HEAD of the repository path, and the
    # push is taken to be the one that changed the fields since there is no old state to check.
    repo_path, (head,) = _git_repo(tmp_path, TP_YAML)
    requester = FakeSuiteRequester(_suite(sha=head))
    _wire_github(monkeypatch, requester)
    _run(asfyaml.dataobjects.Repository(str(repo_path)), TP_YAML)
    out = capsys.readouterr().out
    assert head in out
    assert "treating this push as the one that changed" in out
    assert requester.list_calls


def test_tp_push_that_changed_the_fields_is_checked(tmp_path, cache_dir, capsys, monkeypatch):
    # The fields differ at oldsha, so this push wrote them and its own suite is the evidence.
    repo_path, (old, new) = _git_repo(tmp_path, NO_TP_YAML, TP_YAML)
    requester = FakeSuiteRequester(_suite(sha=new))
    _wire_github(monkeypatch, requester)
    _run(_push_repo(repo_path, old, new), TP_YAML)
    assert "passed the protection check" in capsys.readouterr().out
    assert requester.list_calls


def test_tp_push_that_changed_a_workflow_path_is_checked(tmp_path, cache_dir, monkeypatch):
    repo_path, (old, new) = _git_repo(tmp_path, TP_YAML, TP_YAML_NEW_WORKFLOW)
    _wire_github(monkeypatch, FakeSuiteRequester(_suite(sha=new, result="bypass")))
    with pytest.raises(asfyaml.asfyaml.ASFYAMLException, match="bypass"):
        _run(_push_repo(repo_path, old, new), TP_YAML_NEW_WORKFLOW)


def test_tp_fields_from_an_earlier_unverified_push_are_refused(tmp_path, cache_dir, monkeypatch):
    # The fields were already there at oldsha, and nothing in the cache says they reached ATR:
    # an earlier push introduced them and was never verified. This push's own suite proves
    # nothing about that push, so no GitHub call is made and the block is refused.
    repo_path, (old, new) = _git_repo(tmp_path, TP_YAML, TP_YAML_NEW_METADATA)
    _forbid_github(monkeypatch)
    with pytest.raises(asfyaml.asfyaml.ASFYAMLException) as excinfo:
        _run(_push_repo(repo_path, old, new), TP_YAML_NEW_METADATA)
    message = str(excinfo.value)
    assert "earlier push" in message
    assert "did not pass the check" in message and "sync did not complete" in message
    assert "changed again through a pull request" in message
    assert "github: rulesets:" in message
    assert not _cache_file(cache_dir, asfyaml.dataobjects.Repository(str(repo_path))).exists()


def test_tp_earlier_push_refusal_does_not_touch_the_cache(tmp_path, cache_dir, monkeypatch):
    repo_path, (old, new) = _git_repo(tmp_path, TP_YAML, TP_YAML_NEW_METADATA)
    repo = _push_repo(repo_path, old, new)
    _write_cache(cache_dir, repo, NO_TP_YAML)
    before = _cache_file(cache_dir, repo).read_text()
    _forbid_github(monkeypatch)
    _wire_atr(monkeypatch)
    with pytest.raises(asfyaml.asfyaml.ASFYAMLException, match="earlier push"):
        _run(repo, TP_YAML_NEW_METADATA, noop=False)
    assert _cache_file(cache_dir, repo).read_text() == before


def test_tp_cache_still_wins_over_the_old_file(tmp_path, cache_dir, capsys, monkeypatch):
    # Fields identical at oldsha *and* in the cache: they reached ATR already, so skip as before.
    repo_path, (old, new) = _git_repo(tmp_path, TP_YAML, TP_YAML_NEW_METADATA)
    repo = _push_repo(repo_path, old, new)
    _write_cache(cache_dir, repo, TP_YAML)
    _forbid_github(monkeypatch)
    _run(repo, TP_YAML_NEW_METADATA)
    assert "unchanged" in capsys.readouterr().out


def test_tp_branch_creation_is_checked(tmp_path, cache_dir, monkeypatch):
    # An all-zero oldsha is the branch being created; there is no old state, so this push wrote the fields.
    repo_path, (new,) = _git_repo(tmp_path, TP_YAML)
    requester = FakeSuiteRequester(_suite(sha=new))
    _wire_github(monkeypatch, requester)
    _run(_push_repo(repo_path, "0" * 40, new), TP_YAML)
    assert requester.list_calls


@pytest.mark.parametrize(
    "old_content",
    [
        None,  # no .asf.yaml at oldsha
        "github:\n    description: Apache Foo\n",  # .asf.yaml without a project block
        "project:\n    metadata:\n        key: tooling-trusted-releases\n        committee: tooling\n",  # no policy
        "project: [unclosed",  # unparseable history
        "- just\n- a list\n",  # not a mapping
    ],
    ids=["absent", "no-project-block", "no-policy", "unparseable", "not-a-mapping"],
)
def test_tp_fields_absent_at_oldsha_means_this_push_wrote_them(tmp_path, cache_dir, monkeypatch, old_content):
    repo_path, (old, new) = _git_repo(tmp_path, old_content, TP_YAML)
    requester = FakeSuiteRequester(_suite(sha=new))
    _wire_github(monkeypatch, requester)
    _run(_push_repo(repo_path, old, new), TP_YAML)
    assert requester.list_calls


def test_tp_cache_identical_fields_skips_check(atr_repo, cache_dir, capsys, monkeypatch):
    repo = _tp_repo(atr_repo)
    _write_cache(cache_dir, repo, TP_YAML)
    _forbid_github(monkeypatch)
    _run(repo, TP_YAML)
    out = capsys.readouterr().out
    assert "unchanged" in out and "skipped" in out
    assert _payload(out)["policy"]["github_repository_name"] == "tooling-trusted-releases"


def test_tp_cache_metadata_only_change_skips_check(atr_repo, cache_dir, capsys, monkeypatch):
    repo = _tp_repo(atr_repo)
    _write_cache(cache_dir, repo, TP_YAML)
    _forbid_github(monkeypatch)
    _run(repo, TP_YAML_NEW_METADATA)
    assert "unchanged" in capsys.readouterr().out


def test_tp_cache_changed_field_runs_check(atr_repo, cache_dir, monkeypatch):
    repo = _tp_repo(atr_repo)
    _write_cache(cache_dir, repo, TP_YAML)
    requester = FakeSuiteRequester(_suite())
    _wire_github(monkeypatch, requester)
    _run(repo, TP_YAML_NEW_WORKFLOW)
    assert requester.list_calls


def test_tp_cache_added_fields_run_check(atr_repo, cache_dir, monkeypatch):
    # The previous block had no trusted publishing fields at all.
    repo = _tp_repo(atr_repo)
    _write_cache(cache_dir, repo, NO_TP_YAML)
    requester = FakeSuiteRequester(_suite())
    _wire_github(monkeypatch, requester)
    _run(repo, TP_YAML)
    assert requester.list_calls


def test_tp_no_cache_file_runs_check(atr_repo, cache_dir, monkeypatch):
    requester = FakeSuiteRequester(_suite())
    _wire_github(monkeypatch, requester)
    _run(_tp_repo(atr_repo), TP_YAML)
    assert requester.list_calls


def test_tp_unparseable_cache_runs_check(atr_repo, cache_dir, capsys, monkeypatch):
    repo = _tp_repo(atr_repo)
    _cache_file(cache_dir, repo).write_text("policy: [unclosed")
    requester = FakeSuiteRequester(_suite())
    _wire_github(monkeypatch, requester)
    _run(repo, TP_YAML)
    assert requester.list_calls
    assert "Failed to parse" in capsys.readouterr().out


def test_tp_meta_cache_false_runs_check(atr_repo, cache_dir, monkeypatch):
    repo = _tp_repo(atr_repo)
    _write_cache(cache_dir, repo, TP_YAML)
    requester = FakeSuiteRequester(_suite())
    _wire_github(monkeypatch, requester)
    _run(repo, TP_YAML, no_cache=True)
    assert requester.list_calls


def test_tp_failed_gate_leaves_cache_untouched(atr_repo, cache_dir, monkeypatch):
    repo = _tp_repo(atr_repo)
    _write_cache(cache_dir, repo, NO_TP_YAML)
    before = _cache_file(cache_dir, repo).read_text()
    _wire_github(monkeypatch, FakeSuiteRequester(_suite(result="bypass")))
    _wire_atr(monkeypatch)
    with pytest.raises(asfyaml.asfyaml.ASFYAMLException):
        _run(repo, TP_YAML, noop=False)
    assert _cache_file(cache_dir, repo).read_text() == before


def test_tp_noop_leaves_cache_untouched(atr_repo, cache_dir, monkeypatch):
    repo = _tp_repo(atr_repo)
    _wire_github(monkeypatch, FakeSuiteRequester(_suite()))
    _run(repo, TP_YAML)
    assert not _cache_file(cache_dir, repo).exists()


def test_tp_successful_live_post_writes_cache(atr_repo, cache_dir, monkeypatch):
    repo = _tp_repo(atr_repo)
    _wire_github(monkeypatch, FakeSuiteRequester(_suite()))
    posted = _wire_atr(monkeypatch)
    _run(repo, TP_YAML, noop=False)
    assert posted["json"]["policy"]["github_repository_name"] == "tooling-trusted-releases"
    cached = pyyaml.safe_load(_cache_file(cache_dir, repo).read_text())
    # The cache holds the block as authored, so the comparison next time is like for like.
    assert cached["policy"] == {"github_vote_workflow_path": [".github/workflows/vote.yml"]}
    assert cached["metadata"]["key"] == "tooling-trusted-releases"


def test_tp_atr_error_leaves_cache_unwritten(atr_repo, cache_dir, monkeypatch):
    repo = _tp_repo(atr_repo)
    _wire_github(monkeypatch, FakeSuiteRequester(_suite()))
    _wire_atr(monkeypatch, ok=False)
    with pytest.raises(asfyaml.asfyaml.ASFYAMLException, match="ATR API call failed"):
        _run(repo, TP_YAML, noop=False)
    assert not _cache_file(cache_dir, repo).exists()


def test_no_tp_fields_live_post_still_writes_cache(atr_repo, cache_dir, monkeypatch):
    # So a later push that adds trusted publishing fields is seen as a change.
    repo = _tp_repo(atr_repo)
    _forbid_github(monkeypatch)
    _wire_atr(monkeypatch)
    _run(repo, NO_TP_YAML, noop=False)
    cached = pyyaml.safe_load(_cache_file(cache_dir, repo).read_text())
    assert cached["policy"] == {"min_hours": 72}


def test_tp_classic_protection_source_does_not_count(atr_repo, cache_dir, monkeypatch):
    # Classic branch protection is evaluated into the suite too, under rule_source protected_branch.
    # Only a ruleset counts, so a passing pull_request rule from classic protection is still refused.
    rules = [_rule("pull_request", source="protected_branch"), _rule("non_fast_forward")]
    _wire_github(monkeypatch, FakeSuiteRequester(_suite(rules=rules)))
    with pytest.raises(asfyaml.asfyaml.ASFYAMLException) as excinfo:
        _run(_tp_repo(atr_repo), TP_YAML)
    message = str(excinfo.value)
    assert "pull_request" in message
    assert "classic branch protection" in message
    assert "active ruleset is required" in message


def test_tp_failing_rule_result_raises(atr_repo, cache_dir, monkeypatch):
    # The suite as a whole can say pass while an individual rule says fail; the rule's own result counts.
    rules = [_rule("pull_request", result="fail"), _rule("non_fast_forward")]
    _wire_github(monkeypatch, FakeSuiteRequester(_suite(rules=rules)))
    with pytest.raises(asfyaml.asfyaml.ASFYAMLException) as excinfo:
        _run(_tp_repo(atr_repo), TP_YAML)
    message = str(excinfo.value)
    assert "pull_request" in message and "'fail'" in message


def test_tp_suite_on_second_page_is_found(atr_repo, cache_dir, capsys, monkeypatch):
    filler = [_suite(sha=f"{i:040x}", suite_id=100 + i) for i in range(100)]
    requester = FakeSuiteRequester(*filler, _suite(suite_id=42))
    _wire_github(monkeypatch, requester)
    _run(_tp_repo(atr_repo), TP_YAML)
    assert "passed the protection check" in capsys.readouterr().out
    pages = [call[2]["page"] for call in requester.list_calls]
    assert pages == [1, 2]
    assert requester.calls[-1][1].endswith("/rule-suites/42")


def test_tp_suite_found_on_second_attempt(atr_repo, cache_dir, capsys, monkeypatch):
    requester = FakeSuiteRequester(_suite(), hidden_for=1)
    _wire_github(monkeypatch, requester)
    _run(_tp_repo(atr_repo), TP_YAML)
    out = capsys.readouterr().out
    assert "retrying" in out
    assert "passed the protection check" in out
    assert len(requester.list_calls) == 2


def test_tp_summary_for_another_ref_is_ignored(atr_repo, cache_dir, monkeypatch):
    summary, detail = _suite()
    summary["ref"] = "refs/heads/other"
    _wire_github(monkeypatch, FakeSuiteRequester((summary, detail)))
    with pytest.raises(asfyaml.asfyaml.ASFYAMLException, match="no rule suite"):
        _run(_tp_repo(atr_repo), TP_YAML)


def test_tp_no_suite_for_this_push_says_so(atr_repo, cache_dir, monkeypatch):
    _wire_github(monkeypatch, FakeSuiteRequester(_suite(sha=OTHER_SHA)))
    with pytest.raises(asfyaml.asfyaml.ASFYAMLException) as excinfo:
        _run(_tp_repo(atr_repo), TP_YAML)
    message = str(excinfo.value)
    assert "none for push" in message and "classic branch protection alone leaves no record" in message
    assert "github: rulesets:" in message


def test_tp_no_suite_at_all_says_so(atr_repo, cache_dir, monkeypatch):
    _wire_github(monkeypatch, FakeSuiteRequester())
    with pytest.raises(asfyaml.asfyaml.ASFYAMLException) as excinfo:
        _run(_tp_repo(atr_repo), TP_YAML)
    message = str(excinfo.value)
    assert "no rule suite at all" in message and "refs/heads/main" in message
    assert "github: rulesets:" in message


def test_tp_success_line_lists_rules_seen(atr_repo, cache_dir, capsys, monkeypatch):
    rules = [*PASSING_RULES, _rule("required_signatures")]
    _wire_github(monkeypatch, FakeSuiteRequester(_suite(rules=rules)))
    _run(_tp_repo(atr_repo), TP_YAML)
    out = capsys.readouterr().out
    assert "non_fast_forward, pull_request, required_signatures" in out


def test_tp_reflog_without_default_branch_raises(atr_repo, cache_dir, monkeypatch):
    # A reflog that does not mention the default branch is not a reason to guess from HEAD.
    _wire_github(monkeypatch, FakeSuiteRequester(_suite()))
    reflog = f"{'0' * 40} {OTHER_SHA} refs/heads/feature\n"
    with pytest.raises(asfyaml.asfyaml.ASFYAMLException, match="refs/heads/main"):
        _run(_tp_repo(atr_repo, reflog=reflog), TP_YAML)


def test_tp_empty_token_file_noop_skips(atr_repo, cache_dir, tmp_path, capsys, monkeypatch):
    monkeypatch.delenv("GH_TOKEN", raising=False)
    token_file = tmp_path / "empty-token"
    token_file.write_text("\n")
    monkeypatch.setattr("asfyaml.feature.project.GH_TOKEN_FILE", str(token_file))

    def explode(self, token):
        raise AssertionError("no client should be built with an empty token")

    monkeypatch.setattr(ASFATRFeature, "_connect_github", explode)
    _run(_tp_repo(atr_repo), TP_YAML)
    assert "protection check skipped" in capsys.readouterr().out


def test_tp_empty_token_file_live_raises(atr_repo, cache_dir, tmp_path, monkeypatch):
    monkeypatch.delenv("GH_TOKEN", raising=False)
    token_file = tmp_path / "empty-token"
    token_file.write_text("")
    monkeypatch.setattr("asfyaml.feature.project.GH_TOKEN_FILE", str(token_file))
    with pytest.raises(asfyaml.asfyaml.ASFYAMLException, match="empty"):
        _run(_tp_repo(atr_repo), TP_YAML, noop=False)


def test_tp_cache_round_trip_through_the_feature(atr_repo, cache_dir, capsys, monkeypatch):
    # What the feature writes after a live POST must compare equal to the strictyaml-derived
    # values of the next push, or the skip would never happen in production.
    repo = _tp_repo(atr_repo)
    _wire_github(monkeypatch, FakeSuiteRequester(_suite()))
    _wire_atr(monkeypatch)
    _run(repo, TP_YAML, noop=False)
    capsys.readouterr()

    _forbid_github(monkeypatch)
    _run(repo, TP_YAML_NEW_METADATA)
    assert "unchanged" in capsys.readouterr().out
