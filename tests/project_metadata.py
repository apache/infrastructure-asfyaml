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
from asfyaml.feature.project import _doap_metadata, _parse_doap, _validate_doap_url
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
        vote_recipients:
            to: private@tooling.apache.org
        min_hours: 72
        preserve_download_files: true
        vote_mode: email
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
        valid_metadata_with_doap,
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


def test_noop_payload_policy_types(atr_repo: asfyaml.dataobjects.Repository, capsys):
    yaml = """
project:
    metadata:
        key: tooling-trusted-releases
        committee: tooling
        name: Apache Trusted Releases
    policy:
        min_hours: 72
        preserve_download_files: true
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
    assert policy["preserve_download_files"] is True  # bool, not "true"
    assert policy["license_check_mode"] == "RAT"
    assert policy["binary_artifact_paths"] == ["dist/*.jar"]
    assert policy["file_tag_mappings"] == {"sources": ["*.tar.gz"]}


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
