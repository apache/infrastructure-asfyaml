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
import os
import subprocess
import time
from typing import Any
from urllib.parse import urlparse

import github as pygithub
import github.Auth as pygithubAuth
import github.Repository as pygithubrepo
import requests
import strictyaml
from defusedxml.ElementTree import ParseError, fromstring

import asfyaml.dataobjects as dataobjects
from asfyaml.asfyaml import ASFYamlFeature, ASFYamlInstance
from asfyaml.feature.github import GH_TOKEN_FILE

# DOAP / RDF / ASF-extension XML namespaces, as used in ASF project DOAP files.
_DOAP_NS = "{http://usefulinc.com/ns/doap#}"
_RDF_NS = "{http://www.w3.org/1999/02/22-rdf-syntax-ns#}"
_ASFEXT_NS = "{http://projects.apache.org/ns/asfext#}"

# Path to the ATR client config, rendered onto the box by puppet (eyaml).
# Expected JSON shape: {"url": "https://atr.example", "token": "<system-pat>"}
ATR_CONFIG_PATH = "/x1/gitbox/auth/atr.json"

# ATR mints system JWTs against a fixed service identity, so the uid we send at exchange
# time must match its SYSTEM_SERVICE_UID — it comes back as the subject of the JWT.
_ATR_SYSTEM_UID = "system"

# ATR hands back a 5xx while it's restarting or momentarily overloaded. Those are
# transient, so rather than bounce the push over one, give ATR a few moments and try
# again before giving up. Deliberately short: this runs synchronously inside the git
# hook, so we can't sit here for minutes waiting on it.
_ATR_RETRY_STATUSES = frozenset({502, 503, 504})
_ATR_RETRY_ATTEMPTS = 4
_ATR_RETRY_BACKOFF_SECONDS = 5

# A redeploy can also surface as a plain 500 rather than one of the codes above. While the
# backend restarts, the reverse proxy in front of it can't finish the SSL handshake upstream
# and serves its own "500 Proxy Error" HTML page. That's the same transient restart wearing a
# different status, so a 500 carrying this signature is retryable too — but only that shape: a
# genuine ATR 500 comes back as JSON and still bounces, so we don't hammer real errors.
_ATR_PROXY_ERROR_MARKERS = ("Proxy Error", "Error during SSL Handshake")

_METADATA_SCHEMA = strictyaml.Map(
    {
        # The ATR project key and its owning committee. Both required.
        "key": strictyaml.Str(),
        "committee": strictyaml.Str(),
        # When set, the project fields are sourced from this DOAP file (downloaded
        # at run time) instead of the keys below — `key` and `committee` are still required.
        strictyaml.Optional("doap"): strictyaml.Str(),
        strictyaml.Optional("name"): strictyaml.Str(),
        strictyaml.Optional("description"): strictyaml.Str(),
        strictyaml.Optional("short_description"): strictyaml.Str(),
        strictyaml.Optional("homepage"): strictyaml.Str(),
        strictyaml.Optional("lifecycle_page"): strictyaml.Str(),
        strictyaml.Optional("download_page"): strictyaml.Str(),
        strictyaml.Optional("bug_database"): strictyaml.Str(),
        strictyaml.Optional("mailing_lists"): strictyaml.Str(),
        # Security fields. ATR checks the values: the contact must be security@apache.org
        # or security@<committee>.apache.org, and the two links must be URLs.
        strictyaml.Optional("security_contact"): strictyaml.Str(),
        strictyaml.Optional("threat_model_link"): strictyaml.Str(),
        strictyaml.Optional("threat_model_src_link"): strictyaml.Str(),
        strictyaml.Optional("repositories"): strictyaml.Seq(strictyaml.Str()),
        strictyaml.Optional("standards"): strictyaml.Seq(strictyaml.Str()),
        strictyaml.Optional("categories"): strictyaml.Seq(strictyaml.Str()),
        strictyaml.Optional("programming_languages"): strictyaml.Seq(strictyaml.Str()),
        # Version scheme. Changing any of these makes ATR reassign existing releases to
        # whichever cycle their version string now maps to. A calver project describes its
        # cycles with calver_format and ATR compiles cycle_match from it; everything else
        # sets cycle_match directly.
        strictyaml.Optional("version_method"): strictyaml.Enum(["simple", "semver", "calver"]),
        strictyaml.Optional("version_pattern"): strictyaml.Str(),
        strictyaml.Optional("cycle_match"): strictyaml.Str(),
        strictyaml.Optional("calver_format"): strictyaml.Str(),
        strictyaml.Optional("branch_template"): strictyaml.Str(),
    }
)

# Fields with no DOAP equivalent, so a project that takes the rest from a DOAP file
# still authors these here.
_NON_DOAP_FIELDS = frozenset(
    {
        "lifecycle_page",
        "security_contact",
        "threat_model_link",
        "threat_model_src_link",
        "version_method",
        "version_pattern",
        "cycle_match",
        "calver_format",
        "branch_template",
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

# Release policy, mirroring ATR's PolicyArgsBase. All fields optional.
_POLICY_SCHEMA = strictyaml.Map(
    {
        strictyaml.Optional("announce_release_subject"): strictyaml.Str(),
        strictyaml.Optional("announce_release_template"): strictyaml.Str(),
        strictyaml.Optional("announce_release_template_url"): strictyaml.Str(),
        strictyaml.Optional("binary_artifact_paths"): strictyaml.Seq(strictyaml.Str()),
        # Subdirectory the release is published under, as a per-release template that may
        # use {{PROJECT_KEY}}/{{VERSION}}. ATR checks it resolves to a valid relative path.
        strictyaml.Optional("download_path_suffix"): strictyaml.Str(),
        strictyaml.Optional("file_tag_mappings"): strictyaml.MapPattern(
            strictyaml.Str(), strictyaml.Seq(strictyaml.Str())
        ),
        strictyaml.Optional("github_compose_workflow_path"): strictyaml.Seq(strictyaml.Str()),
        strictyaml.Optional("github_finish_workflow_path"): strictyaml.Seq(strictyaml.Str()),
        strictyaml.Optional("github_repository_branch"): strictyaml.Str(),
        strictyaml.Optional("github_repository_name"): strictyaml.Str(),
        strictyaml.Optional("github_vote_workflow_path"): strictyaml.Seq(strictyaml.Str()),
        strictyaml.Optional("license_check_mode"): strictyaml.Enum(["Both", "Lightweight", "RAT"]),
        strictyaml.Optional("vote_recipients"): _RECIPIENTS_SCHEMA,
        strictyaml.Optional("announce_recipients"): _RECIPIENTS_SCHEMA,
        strictyaml.Optional("manual_vote"): strictyaml.Bool(),
        strictyaml.Optional("min_hours"): strictyaml.Int(),
        strictyaml.Optional("release_checklist"): strictyaml.Str(),
        strictyaml.Optional("source_artifact_paths"): strictyaml.Seq(strictyaml.Str()),
        strictyaml.Optional("source_excludes_lightweight"): strictyaml.Seq(strictyaml.Str()),
        strictyaml.Optional("source_excludes_rat"): strictyaml.Seq(strictyaml.Str()),
        strictyaml.Optional("rat_excludes_url"): strictyaml.Str(),
        strictyaml.Optional("start_vote_subject"): strictyaml.Str(),
        strictyaml.Optional("start_vote_template"): strictyaml.Str(),
        strictyaml.Optional("start_vote_template_url"): strictyaml.Str(),
        strictyaml.Optional("finish_vote_template"): strictyaml.Str(),
        strictyaml.Optional("finish_vote_template_url"): strictyaml.Str(),
        strictyaml.Optional("vote_comment_template"): strictyaml.Str(),
        strictyaml.Optional("vote_comment_template_url"): strictyaml.Str(),
        strictyaml.Optional("vote_mode"): strictyaml.Enum(["manual", "email", "trusted"]),
    }
)

_FEATURES_SCHEMA = strictyaml.Map(
    {
        strictyaml.Optional("atr_sync"): strictyaml.Bool(),
        # merge (the default) updates only the fields this file sets; full also resets
        # every field the file leaves out to its ATR default
        strictyaml.Optional("atr_sync_mode"): strictyaml.Enum(["merge", "full"]),
    }
)

# The trusted publishing fields. Registering a workflow with ATR lets that workflow act as the
# PMC with no login or MFA, so a block carrying any of these is a credential and gets the
# default-branch protection check before it is sent. Everything else in the policy is not.
_TP_FIELDS = (
    "github_repository_name",
    "github_repository_branch",
    "github_compose_workflow_path",
    "github_vote_workflow_path",
    "github_finish_workflow_path",
)
_TP_WORKFLOW_FIELDS = (
    "github_compose_workflow_path",
    "github_vote_workflow_path",
    "github_finish_workflow_path",
)

# The rules the push must have been evaluated against, in a ruleset enforced as active. In
# the language of tooling-trusted-releases#1776: pull_request is PUSH, non_fast_forward is
# MOVE. creation is not needed - the default branch already exists - and a review count is
# deliberately not required, matching the line ATR takes for the workflows themselves.
_REQUIRED_RULES = ("pull_request", "non_fast_forward")

# GitHub indexes a rule suite shortly after the push rather than in the same instant, so
# give it a moment and look again before deciding there is none. Short on purpose: this runs
# inside the gitbox hook, so the total wait is a few seconds, not minutes.
_RULE_SUITE_ATTEMPTS = 3
_RULE_SUITE_RETRY_SECONDS = 3

# Pages of rule suites to walk per attempt. A busy branch can have more than one page in a
# month; five pages of a hundred is far more than any push has to look back through.
_RULE_SUITE_MAX_PAGES = 5

_PROTECTION_HELP = (
    "Add an active ruleset on the default branch with 'Require a pull request before merging' and "
    "'Block force pushes' (for example through the `github: rulesets:` directive in this file - classic "
    "branch protection under `github: protected_branches:` is not accepted for this, as only a ruleset "
    "records explicitly, per push, whether its rules were bypassed), then land the .asf.yaml change "
    "through a pull request. See 'Trusted publishing requirements' in the .asf.yaml README."
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

    def __init__(self, parent: ASFYamlInstance, yaml: strictyaml.YAML, **kwargs):
        super().__init__(parent, yaml)
        # Only built when the block carries trusted publishing fields; a metadata-only block
        # never contacts GitHub at all.
        self._gh: pygithub.Github | None = None
        self._ghrepo: pygithubrepo.Repository | None = None

    @property
    def ghrepo(self) -> pygithubrepo.Repository:
        if self._ghrepo is None:
            raise RuntimeError("something went wrong, ghrepo is not set")
        return self._ghrepo

    def run(self):
        """
        Sync project metadata to ATR. Sample entry:
            project:
              metadata:
                key: tooling-test    # required; ATR project key
                committee: tooling   # required; repo must be named <committee>-xxx
                name: Apache Foo
                homepage: https://foo.apache.org/
                security_contact: security@apache.org   # or security@<committee>.apache.org
                threat_model_link: https://foo.apache.org/security/threat-model
                threat_model_src_link: https://github.com/apache/foo/blob/main/THREATS.md
                version_method: calver      # simple (default), semver or calver
                calver_format: "(YY.MM).N"  # calver only; ATR compiles cycle_match from it
                # ...or, instead of the fields above, point at a DOAP file. The ATR-only
                # fields (security, threat model, version scheme) can still sit alongside it:
                doap: https://foo.apache.org/doap.rdf
              policy:
                vote_recipients:
                  to: private@foo.apache.org
                download_path_suffix: "{{PROJECT_KEY}}/{{VERSION}}"   # subdir releases land under
                # Email templates can come from a URL instead of inline text. ATR fetches it each
                # time it shows the email form; use it in place of the matching *_template field.
                start_vote_template_url: https://raw.githubusercontent.com/apache/foo/main/.atr/start-vote.txt
                # Trusted publishing: workflows in this repository that act as the PMC in ATR.
                # Setting any of these requires the default branch to be protected by an active
                # ruleset (pull request required, force pushes blocked) and the change to have
                # landed through a pull request. Otherwise the sync fails, nothing from this
                # block reaches ATR, and the committer gets the error by email.
                github_repository_name: foo    # optional, must be this repository; filled in if left out
                github_repository_branch: main
                github_vote_workflow_path:
                  - .github/workflows/vote.yml
              features:
                atr_sync: true       # set false to opt out of syncing
                atr_sync_mode: full  # merge (default) updates only the fields set here; full resets the rest
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
        project_key = metadata.pop("key")
        committee_key = metadata.pop("committee")
        # Guard against a repo configuring another project's committee: the committee must
        # match the start of the repository name (e.g. tooling-trusted-releases -> tooling).
        repo_name = self.repository.name
        if repo_name != committee_key and not repo_name.startswith(f"{committee_key}-"):
            raise Exception(f"committee '{committee_key}' does not match repository name '{repo_name}'")

        policy = dict(self.yaml.get("policy") or {})
        self._gate_trusted_publishing(policy)

        # A DOAP file, if given, is the authoritative source for the project fields it can
        # express. The ATR-only fields, which DOAP has no vocabulary for, stay as authored.
        doap_url = metadata.pop("doap", None)
        if doap_url:
            local = {key: value for key, value in metadata.items() if key in _NON_DOAP_FIELDS}
            metadata = _parse_doap(doap_url) | local
        payload: dict[str, Any] = {
            "project_key": project_key,
            "committee_key": committee_key,
            "project": metadata,
        }
        if policy:
            payload["policy"] = policy
        # Only forwarded when authored, so ATR's own default (merge) applies otherwise
        sync_mode = features.get("atr_sync_mode")
        if sync_mode:
            payload["sync_mode"] = sync_mode

        if self.noop("atr"):
            print(json.dumps(payload, indent=2))
            return

        config = _load_config(ATR_CONFIG_PATH)
        base_url = "https://releases.apache.org"
        jwt = _exchange_token_for_jwt(base_url, config["token"])
        url = f"{base_url}/api/project/config"
        headers = {
            "Authorization": f"Bearer {jwt}",
            "Content-Type": "application/json",
        }
        print(f"[project] POST {url} for project {project_key}")
        resp = _post_with_retry(url, json=payload, headers=headers, timeout=30)
        if not resp.ok:
            # Surface the API's error body — it's the most useful thing to put in the bounce email.
            raise Exception(f"ATR API call failed ({resp.status_code}): {resp.text}")
        print(f"[project] ok: {resp.text}")
        # The cache means "this block reached ATR", and the trusted publishing gate relies on
        # exactly that: it is only saved here, after a live POST that ATR accepted. Not in noop,
        # not after an ATR error, and never after a failed gate (which raised long before this).
        self.save_cached_yaml()

    def _gate_trusted_publishing(self, policy: dict) -> None:
        """Refuse to send trusted publishing fields unless the default branch is protected.

        Mutates `policy` to pin `github_repository_name` to this repository when workflow paths
        are given without one. Returns quietly when there is nothing to gate, or when the
        fields are the same as the last block that reached ATR.
        """
        authored = {key: policy[key] for key in _TP_FIELDS if key in policy}
        if not authored:
            return

        # The workflows must live in the repository whose protection we are about to check.
        # ATR prepends apache/ itself, so this is the bare name on both sides.
        repo_name = self.repository.name
        if "github_repository_name" in authored and authored["github_repository_name"] != repo_name:
            raise Exception(
                f"policy github_repository_name '{authored['github_repository_name']}' must be this repository "
                f"('{repo_name}'); trusted publishing workflows can only be registered from the repository "
                "that holds them"
            )
        if "github_repository_name" not in authored and any(key in authored for key in _TP_WORKFLOW_FIELDS):
            policy["github_repository_name"] = repo_name

        # Compare authored values against the last block that reached ATR, so a push that only
        # touches metadata does not re-run the check. No cache (or meta: cache: false) means
        # the check runs, which is the safe direction for a pusher to be able to force.
        previous_policy = self.load_cached_yaml().get("policy") or {}
        previous = {key: previous_policy[key] for key in _TP_FIELDS if key in previous_policy}
        if previous == authored:
            print(
                "[project] Trusted publishing fields are unchanged since the last applied .asf.yaml, "
                "default branch protection check skipped"
            )
            return

        branch = self.repository.default_branch
        sha, old_sha = self._push_to_default_branch(branch)
        if old_sha is None:
            print(
                f"[project] No reflog, so the old state of .asf.yaml is not available: treating this push "
                f"as the one that changed the trusted publishing fields and checking {sha}"
            )
        elif old_sha != "0" * 40 and _tp_fields_at(self.repository.path, old_sha) == authored:
            fields = ", ".join(sorted(authored))
            raise Exception(
                f"Trusted publishing configuration refused: the trusted publishing field(s) {fields} under "
                f"policy: were introduced by an earlier push to '{branch}' (they are already present at "
                f"{old_sha}) that did not pass the check, or whose sync did not complete, and they have not "
                "reached ATR. This push did not change them, so its own rule suite says nothing about how "
                "they got there. They must be changed again through a pull request so that a protected push "
                f"carries them. {_PROTECTION_HELP}"
            )

        self._check_default_branch_protection(sorted(authored), branch, sha)

    def _check_default_branch_protection(self, fields: list[str], branch: str, sha: str) -> None:
        """Check the rule suite GitHub recorded for the push that put this .asf.yaml on the default branch.

        The per-push record is used rather than the branch's current rules because the same
        push can add a ruleset through the github: feature, which may run in the same push
        before or after this one; the current rules would then pass on protection that did not
        exist when the push landed.
        """
        noop_mode = "noop" in self.instance.environments_enabled
        token = _github_token(noop_mode)
        if token is None:
            print(
                f"[project] No GitHub token available in noop mode, protection check skipped for push {sha} "
                f"to '{branch}' - a live run would check it"
            )
            return
        self._connect_github(token)

        ref = f"refs/heads/{branch}"
        suite, suites_seen = self._find_rule_suite(ref, sha)
        trigger = f"The trusted publishing field(s) {', '.join(fields)} under policy: triggered this check."
        where = f"default branch '{branch}' (push {sha} to {ref})"
        problem = _protection_problem(suite, suites_seen, sha, ref)
        if problem or suite is None:
            raise Exception(
                f"Trusted publishing configuration refused: {where}: {problem}. {_PROTECTION_HELP} {trigger}"
            )
        print(
            f"[project] default branch '{branch}' passed the protection check for push {sha}: "
            f"rule suite {suite['id']} passed with active ruleset rules {', '.join(_passing_ruleset_rules(suite))}"
        )

    def _push_to_default_branch(self, branch: str) -> tuple[str, str | None]:
        """The SHA this push left the default branch at, and the SHA it was at before.

        The gitbox hook (and asfyaml-run --old-sha) hand us a reflog, so both come from the
        changeset for the branch. Plain asfyaml-run has no reflog and runs against a checkout,
        so HEAD of the repository path is the new SHA and the old one is None: there is no old
        state to compare against. dataobjects.gitcmd runs in the current directory, hence -C.
        """
        ref = f"refs/heads/{branch}"
        changesets = list(self.repository.changesets)
        for changeset in changesets:
            if changeset.name == ref:
                return changeset.newsha, changeset.oldsha
        if changesets:
            # A reflog that does not mention the default branch means we are not looking at
            # the push that changed it; HEAD would be a guess, so say so instead.
            refs = ", ".join(changeset.name for changeset in changesets)
            raise Exception(
                f"could not work out the SHA pushed to '{branch}': the reflog has no {ref} entry (saw {refs})"
            )
        sha = dataobjects.gitcmd("-C", str(self.repository.path), "rev-parse", "HEAD").strip()
        if not sha:
            raise Exception(
                f"could not work out the SHA pushed to '{branch}': no reflog and git rev-parse HEAD "
                f"failed in {self.repository.path}"
            )
        return sha, None

    def _connect_github(self, token: str) -> None:
        self._gh = pygithub.Github(auth=pygithubAuth.Token(token))
        self._ghrepo = self._gh.get_repo(f"{self.repository.org_id}/{self.repository.name}")

    def _find_rule_suite(self, ref: str, sha: str) -> tuple[dict | None, int]:
        """The rule suite for this push, with its rule evaluations, and how many suites the branch had.

        The suite must be for `ref` and have `after_sha` equal to the push. Pages are walked
        in order until a match or a short page; the count of suites seen lets the caller tell
        "none for this push yet" from "none for this branch at all". time_period defaults to a
        day; month is the widest GitHub offers, and keeps a sandbox .asf.yaml that landed
        yesterday findable.
        """
        endpoint = f"/repos/{self.repository.org_id}/{self.repository.name}/rulesets/rule-suites"
        per_page = 100
        suites_seen = 0
        for attempt in range(1, _RULE_SUITE_ATTEMPTS + 1):
            suites_seen = 0
            for page in range(1, _RULE_SUITE_MAX_PAGES + 1):
                parameters = {"ref": ref, "time_period": "month", "per_page": per_page, "page": page}
                status, _headers, body = self.ghrepo._requester.requestJson("GET", endpoint, parameters=parameters)
                if status != 200:
                    raise Exception(f"GitHub returned {status} while listing rule suites for {ref}: {body}")
                summaries = [summary for summary in json.loads(body) if isinstance(summary, dict)]
                suites_seen += sum(1 for summary in summaries if summary.get("ref") == ref)
                for summary in summaries:
                    if summary.get("ref") == ref and summary.get("after_sha") == sha:
                        status, _headers, body = self.ghrepo._requester.requestJson(
                            "GET", f"{endpoint}/{summary['id']}"
                        )
                        if status != 200:
                            raise Exception(
                                f"GitHub returned {status} while fetching rule suite {summary['id']}: {body}"
                            )
                        return json.loads(body), suites_seen
                if len(summaries) < per_page:
                    break
            if attempt < _RULE_SUITE_ATTEMPTS:
                print(
                    f"[project] No rule suite for {sha} on {ref} yet, retrying in {_RULE_SUITE_RETRY_SECONDS}s "
                    f"(attempt {attempt}/{_RULE_SUITE_ATTEMPTS})"
                )
                time.sleep(_RULE_SUITE_RETRY_SECONDS)
        return None, suites_seen


def _github_token(noop_mode: bool) -> str | None:
    """The GitHub token, the same way the github: feature finds it.

    GH_TOKEN from the environment first, else the token file on gitbox. In noop mode with
    neither, None - a dry run elsewhere has no token and should not fail for that. In live
    mode the file is required, and a missing one raises as it does for the github: feature.
    """
    token = os.environ.get("GH_TOKEN")
    if token:
        return token
    if noop_mode and not os.path.exists(GH_TOKEN_FILE):
        return None
    token = open(GH_TOKEN_FILE).read().strip()
    if not token:
        if noop_mode:
            return None
        raise Exception(f"GitHub token file {GH_TOKEN_FILE} is empty")
    return token


def _tp_fields_at(repo_path: Any, sha: str) -> dict:
    """The trusted publishing fields in .asf.yaml as it was at `sha`, or {} if there were none.

    The old file is history we do not control, so anything short of a mapping with a
    `project.policy` mapping in it - no file, unparseable, a list, no project block - is
    simply "the fields did not exist before", which makes this push the one that wrote them.
    """
    result = subprocess.run(
        [dataobjects.GIT_CMD, "-C", str(repo_path), "show", f"{sha}:.asf.yaml"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return {}
    try:
        data = strictyaml.load(result.stdout).data
    except strictyaml.ruamel.error.YAMLError:
        return {}
    project = data.get("project") if isinstance(data, dict) else None
    policy = project.get("policy") if isinstance(project, dict) else None
    if not isinstance(policy, dict):
        return {}
    return {key: policy[key] for key in _TP_FIELDS if key in policy}


def _from_ruleset(evaluation: dict) -> bool:
    """Whether a rule evaluation came from a ruleset, as opposed to classic branch protection.

    GitHub evaluates classic protection into the suite too, under rule_source type
    protected_branch. It is not accepted here: only a ruleset records explicitly, per push,
    whether its rules were bypassed, and that record is what the bar is built on.
    """
    source = evaluation.get("rule_source")
    return isinstance(source, dict) and source.get("type") == "ruleset"


def _passing_ruleset_rules(suite: dict) -> list[str]:
    """The rule types in the suite that an active ruleset evaluated and passed, sorted."""
    return sorted(
        {
            str(e.get("rule_type"))
            for e in suite.get("rule_evaluations") or []
            if isinstance(e, dict)
            and _from_ruleset(e)
            and e.get("enforcement") == "active"
            and e.get("result") == "pass"
        }
    )


def _protection_problem(suite: dict | None, suites_seen: int, sha: str, ref: str) -> str | None:
    """Why the rule suite fails the bar, or None when it passes.

    The bar: the suite exists, its result is pass (a bypass means GitHub let the push through
    around the rules, which is exactly what we are checking did not happen), and each required
    rule was evaluated from an active ruleset and passed. A rule from an evaluate-mode ruleset
    was only logged, never enforced, so it does not count, and nor does one from classic branch
    protection. `enforcement` reflects the ruleset as it is now rather than as it was for the
    push, so the per-rule result from a ruleset source is the check that carries the weight.
    """
    if suite is None:
        if suites_seen:
            # Seen in the sandbox: a branch that once had a ruleset keeps its old suites, but a
            # push made under classic protection alone leaves no new one. Say both possibilities.
            return (
                f"rule suites exist for {ref} but none for push {sha}: either no ruleset applied to that push "
                "(classic branch protection alone leaves no record) or GitHub is still indexing it, "
                "so it cannot be shown that a ruleset was enforced on this push"
            )
        return f"no rule suite at all was recorded for {ref}, so no ruleset was enforced on this push"
    result = suite.get("result")
    if result != "pass":
        detail = "the push bypassed the rules" if result == "bypass" else "the rules were not passed"
        return f"the rule suite recorded result '{result}' ({detail})"
    evaluations = [e for e in suite.get("rule_evaluations") or [] if isinstance(e, dict)]
    for rule in _REQUIRED_RULES:
        seen = [e for e in evaluations if e.get("rule_type") == rule]
        if not seen:
            return f"no '{rule}' rule was evaluated for the push"
        from_rulesets = [e for e in seen if _from_ruleset(e)]
        if not from_rulesets:
            return (
                f"only classic branch protection evaluated the '{rule}' rule; an active ruleset is required "
                "to count for this"
            )
        if not any(e.get("enforcement") == "active" and e.get("result") == "pass" for e in from_rulesets):
            states = ", ".join(
                f"enforcement '{e.get('enforcement')}' result '{e.get('result')}'" for e in from_rulesets
            )
            return f"the '{rule}' rule was not active and passing in a ruleset ({states})"
    return None


def _load_config(path: str) -> dict:
    with open(path) as fh:
        config = json.load(fh)
    for required in ("url", "token"):
        if required not in config:
            raise Exception(f"ATR config at {path} is missing required key '{required}'")
    return config


def _post_with_retry(url: str, **kwargs):
    """POST to ATR, retrying the transient 5xx codes it returns while it's unavailable.

    Returns the final response either way — the caller still checks resp.ok, so a real
    4xx (or a 5xx that never clears within our budget) bounces exactly as before, just
    after we've given ATR a chance to come back.
    """
    for attempt in range(1, _ATR_RETRY_ATTEMPTS + 1):
        resp = requests.post(url, **kwargs)
        if not _is_transient(resp) or attempt == _ATR_RETRY_ATTEMPTS:
            return resp
        print(
            f"[project] ATR returned {resp.status_code}, retrying in {_ATR_RETRY_BACKOFF_SECONDS}s "
            f"(attempt {attempt}/{_ATR_RETRY_ATTEMPTS})"
        )
        time.sleep(_ATR_RETRY_BACKOFF_SECONDS)


def _is_transient(resp) -> bool:
    """Whether a failed response looks like a restart blip worth another attempt.

    The 5xx codes ATR emits while restarting are always retryable. A 500 is retryable only
    when it's the fronting proxy's SSL-handshake error page — the shape a redeploy produces
    while the backend has no TLS listener yet. A real ATR 500 comes back as JSON, so it has
    neither the proxy markers nor an HTML content type, and bounces exactly as before.
    """
    if resp.status_code in _ATR_RETRY_STATUSES:
        return True
    if resp.status_code == 500 and "json" not in resp.headers.get("Content-Type", "").lower():
        return any(marker in resp.text for marker in _ATR_PROXY_ERROR_MARKERS)
    return False


def _exchange_token_for_jwt(base_url: str, token: str) -> str:
    """Swap the configured system PAT for a short-lived ATR JWT.

    /project/config is gated to system bearer tokens, and ATR issues those JWTs via
    /api/jwt/create.
    """
    resp = _post_with_retry(
        f"{base_url}/api/jwt/create",
        json={"asfuid": _ATR_SYSTEM_UID, "pat": token},
        timeout=30,
    )
    if not resp.ok:
        raise Exception(f"ATR token exchange failed ({resp.status_code}): {resp.text}")
    jwt = resp.json().get("jwt")
    if not jwt:
        raise Exception(f"ATR token exchange returned no JWT: {resp.text}")
    return jwt


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
        raise Exception(f"Could not parse {source}: {e}")

    project = root.find(f"{_DOAP_NS}Project")
    if project is None:
        raise Exception(f"No doap:Project element found in {source}")

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
