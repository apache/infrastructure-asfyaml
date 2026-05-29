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

import json
from urllib.parse import urlparse

import requests
import strictyaml
from defusedxml.ElementTree import ParseError, fromstring

from asfyaml.asfyaml import ASFYamlFeature

# DOAP / RDF / ASF-extension XML namespaces, as used in ASF project DOAP files.
_DOAP_NS = "{http://usefulinc.com/ns/doap#}"
_RDF_NS = "{http://www.w3.org/1999/02/22-rdf-syntax-ns#}"
_ASFEXT_NS = "{http://projects.apache.org/ns/asfext#}"

# Path to the ATR client config, rendered onto the box by puppet (eyaml).
# Expected JSON shape: {"url": "https://atr.example/api", "token": "<bearer-jwt>"}
ATR_CONFIG_PATH = "/x1/gitbox/auth/atr.json"

_METADATA_SCHEMA = strictyaml.Map(
    {
        # The ATR project key. Defaults to the repository's project name when unset.
        strictyaml.Optional("key"): strictyaml.Str(),
        strictyaml.Optional("committee"): strictyaml.Str(),
        # When set, the project fields are sourced from this DOAP file (downloaded
        # at run time) instead of the keys below — only `committee` is still honoured.
        strictyaml.Optional("doap"): strictyaml.Str(),
        strictyaml.Optional("name"): strictyaml.Str(),
        strictyaml.Optional("description"): strictyaml.Str(),
        strictyaml.Optional("short_description"): strictyaml.Str(),
        strictyaml.Optional("homepage"): strictyaml.Str(),
        strictyaml.Optional("lifecycle_page"): strictyaml.Str(),
        strictyaml.Optional("download_page"): strictyaml.Str(),
        strictyaml.Optional("bug_database"): strictyaml.Str(),
        strictyaml.Optional("mailing_lists"): strictyaml.Str(),
        strictyaml.Optional("repositories"): strictyaml.Seq(strictyaml.Str()),
        strictyaml.Optional("standards"): strictyaml.Seq(strictyaml.Str()),
        strictyaml.Optional("categories"): strictyaml.Seq(strictyaml.Str()),
        strictyaml.Optional("programming_languages"): strictyaml.Seq(strictyaml.Str()),
    }
)

# Email recipients for a policy action.
_RECIPIENTS_SCHEMA = strictyaml.Map(
    {
        strictyaml.Optional("to"): strictyaml.Str(),
        strictyaml.Optional("cc"): strictyaml.Seq(strictyaml.Str()),
        strictyaml.Optional("bcc"): strictyaml.Seq(strictyaml.Str()),
    }
)

# Release policy. Only the recipient defaults are exposed via .asf.yaml for now.
_POLICY_SCHEMA = strictyaml.Map(
    {
        strictyaml.Optional("vote_recipients"): _RECIPIENTS_SCHEMA,
        strictyaml.Optional("announce_recipients"): _RECIPIENTS_SCHEMA,
    }
)

_FEATURES_SCHEMA = strictyaml.Map(
    {
        strictyaml.Optional("atr_sync"): strictyaml.Bool(),
    }
)


class ASFATRFeature(ASFYamlFeature, name="project", env="production", priority=5):
    """Push project metadata from .asf.yaml to the Apache Trusted Releases (ATR) platform."""

    schema = strictyaml.Map(
        {
            "metadata": _METADATA_SCHEMA,
            strictyaml.Optional("policy"): _POLICY_SCHEMA,
            strictyaml.Optional("features"): _FEATURES_SCHEMA,
        }
    )

    def run(self):
        """
        Sync project metadata to ATR. Sample entry:
            project:
              metadata:
                key: tooling-test    # optional; ATR project key, defaults to the repo name
                committee: tooling   # optional; defaults to the project key
                name: Apache Foo
                homepage: https://foo.apache.org/
                # ...or, instead of the fields above, point at a DOAP file:
                doap: https://foo.apache.org/doap.rdf
              policy:
                vote_recipients:
                  to: private@foo.apache.org
              features:
                atr_sync: true       # set false to opt out of syncing
        """
        # Only sync from the default branch — metadata is repo-wide, not per-branch.
        if self.instance.branch != self.repository.default_branch:
            return

        # `features.atr_sync: false` is an explicit opt-out without removing the block.
        features = self.yaml.get("features") or {}
        if features.get("atr_sync") is False:
            return

        metadata = dict(self.yaml.get("metadata") or {})
        # `key` and `committee` are authored inside metadata but map to top-level ATR API
        # fields, so pop them before forwarding the rest as the project payload.
        # Both default to the repository's project name (the repo's LDAP key).
        project_key = metadata.pop("key", self.repository.project)
        committee_key = metadata.pop("committee", project_key)
        # A DOAP file, if given, is the authoritative source for the project fields.
        doap_url = metadata.pop("doap", None)
        if doap_url:
            metadata = _parse_doap(doap_url)
        payload = {
            "project_key": project_key,
            "committee_key": committee_key,
            "project": metadata,
        }
        policy = self.yaml.get("policy")
        if policy:
            payload["policy"] = dict(policy)

        if self.noop("atr"):
            print(json.dumps(payload, indent=2))
            return

        config = _load_config(ATR_CONFIG_PATH)
        url = f"{config['url'].rstrip('/')}/project/config"
        headers = {
            "Authorization": f"Bearer {config['token']}",
            "Content-Type": "application/json",
        }
        print(f"[project] POST {url} for project {project_key}")
        resp = requests.post(url, json=payload, headers=headers, timeout=30)
        if not resp.ok:
            # Surface the API's error body — it's the most useful thing to put in the bounce email.
            raise Exception(f"ATR API call failed ({resp.status_code}): {resp.text}")
        print(f"[project] ok: {resp.text}")


def _load_config(path: str) -> dict:
    with open(path) as fh:
        config = json.load(fh)
    for required in ("url", "token"):
        if required not in config:
            raise Exception(f"ATR config at {path} is missing required key '{required}'")
    return config


def _doap_text(parent, tag):
    """Inner text of the first `tag` child, stripped, or None."""
    el = parent.find(f"{_DOAP_NS}{tag}")
    if el is not None and el.text and el.text.strip():
        return el.text.strip()
    return None


def _doap_resource(parent, tag):
    """rdf:resource attribute of the first `tag` child, or None."""
    el = parent.find(f"{_DOAP_NS}{tag}")
    if el is not None:
        return el.get(f"{_RDF_NS}resource")
    return None


def _validate_doap_url(url: str) -> None:
    """Restrict DOAP fetches to trusted public hosts, to guard against SSRF.

    The URL is operator-supplied via .asf.yaml and fetched from ASF infrastructure,
    so only https URLs on apache.org (or its subdomains) and raw.githubusercontent.com/apache
    are permitted. (github.com is excluded as it redirects, and redirects are not followed.)
    """
    parsed = urlparse(url)
    if parsed.scheme != "https":
        raise Exception(f"DOAP URL must use https: {url}")
    host = (parsed.hostname or "").lower().rstrip(".")
    if host == "apache.org" or host.endswith(".apache.org"):
        return
    if host == "raw.githubusercontent.com" and (parsed.path == "/apache" or parsed.path.startswith("/apache/")):
        return
    raise Exception(f"DOAP URL host not allowed: {url} (must be an apache.org or raw.githubusercontent.com/apache URL)")


def _parse_doap(url: str) -> dict:
    """Download an ASF DOAP file and map it onto the project metadata payload."""
    _validate_doap_url(url)
    # Don't follow redirects: a redirect could hop off an allowed host (SSRF), and the
    # validation above only vetted the URL we were given.
    resp = requests.get(url, timeout=30, allow_redirects=False)
    if resp.is_redirect:
        raise Exception(
            f"DOAP URL {url} returned a redirect ({resp.status_code}); point at the final https URL instead"
        )
    if not resp.ok:
        raise Exception(f"Could not download DOAP file from {url} ({resp.status_code})")
    return _doap_metadata(resp.content, url)


def _doap_metadata(content: bytes, source: str = "DOAP file") -> dict:
    """Map DOAP XML content onto the project metadata payload.

    Field mapping mirrors what ATR itself derives from DOAP (see ATR's
    datasources/apache.py). Only fields present in the DOAP file are included.
    """
    try:
        root = fromstring(content)
    except ParseError as e:
        raise Exception(f"Could not parse DOAP file from {source}: {e}")

    project = root.find(f"{_DOAP_NS}Project")
    if project is None:
        raise Exception(f"No doap:Project element found in DOAP file {source}")

    metadata: dict = {}
    for key, tag in (
        ("name", "name"),
        ("description", "description"),
        ("short_description", "shortdesc"),
    ):
        value = _doap_text(project, tag)
        if value:
            metadata[key] = value
    for key, tag in (
        ("homepage", "homepage"),
        ("download_page", "download-page"),
        ("bug_database", "bug-database"),
        ("mailing_lists", "mailing-list"),
    ):
        value = _doap_resource(project, tag)
        if value:
            metadata[key] = value

    languages = [
        el.text.strip() for el in project.findall(f"{_DOAP_NS}programming-language") if el.text and el.text.strip()
    ]
    if languages:
        metadata["programming_languages"] = languages

    # Categories are rdf:resource URLs like .../category/build-management; keep the trailing label.
    categories = [
        res.rstrip("/").rsplit("/", 1)[-1]
        for el in project.findall(f"{_DOAP_NS}category")
        if (res := el.get(f"{_RDF_NS}resource") or (el.text or "").strip())
    ]
    if categories:
        metadata["categories"] = categories

    # Repositories are nested as <repository><GitRepository><location rdf:resource=.../></...>.
    repositories = [
        location
        for repository in project.findall(f"{_DOAP_NS}repository")
        for vcs in repository
        if (location := _doap_resource(vcs, "location"))
    ]
    if repositories:
        metadata["repositories"] = repositories

    # Implemented standards live under asfext:implements/asfext:Standard/asfext:url.
    standards = []
    for implements in project.findall(f"{_ASFEXT_NS}implements"):
        standard = implements.find(f"{_ASFEXT_NS}Standard")
        if standard is None:
            continue
        url_el = standard.find(f"{_ASFEXT_NS}url")
        if url_el is not None:
            value = url_el.get(f"{_RDF_NS}resource") or (url_el.text or "").strip()
            if value:
                standards.append(value)
    if standards:
        metadata["standards"] = standards

    return metadata
