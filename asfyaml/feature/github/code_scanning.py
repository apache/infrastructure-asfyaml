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

"""GitHub code scanning (CodeQL default setup) support."""

import json
from typing import Any

from . import directive, ASFGitHubFeature


def _default_setup_endpoint(self: ASFGitHubFeature) -> str:
    return f"/repos/{self.repository.org_id}/{self.repository.name}/code-scanning/default-setup"


def _parse_detail(body: str) -> str:
    try:
        parsed = json.loads(body)
        return str(parsed.get("errors") or parsed.get("message") or body)
    except (json.JSONDecodeError, AttributeError):
        return body


def get_default_setup(self: ASFGitHubFeature) -> dict[str, Any]:
    status, _headers, body = self.ghrepo._requester.requestJson("GET", _default_setup_endpoint(self))
    repo = f"{self.repository.org_id}/{self.repository.name}"
    if status == 200:
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            raise Exception(
                f"Unexpected response format while fetching code scanning default setup: "
                f"expected JSON, got: {body[:200]}"
            )
        if isinstance(payload, dict):
            return payload
        raise Exception(
            f"Unexpected response format while fetching code scanning default setup: "
            f"expected an object, got {type(payload).__name__}"
        )
    detail = _parse_detail(body)
    match status:
        case 403:
            raise Exception(f"Code scanning is not permitted for repository '{repo}': {detail}")
        case 404:
            raise Exception(f"Code scanning is not available for repository '{repo}': {detail}")
        case _:
            raise Exception(f"Unexpected response while fetching code scanning default setup: HTTP {status}: {detail}")


def update_default_setup(self: ASFGitHubFeature, payload: dict[str, Any]) -> None:
    status, _headers, body = self.ghrepo._requester.requestJson("PATCH", _default_setup_endpoint(self), input=payload)
    if 200 <= status < 300:
        return
    detail = _parse_detail(body)
    repo = f"{self.repository.org_id}/{self.repository.name}"
    match status:
        case 403:
            raise Exception(
                f"Code scanning is not permitted for repository '{repo}' (the repository may be archived): {detail}"
            )
        case 404:
            raise Exception(f"Code scanning is not available for repository '{repo}': {detail}")
        case 409:
            raise Exception(
                f"Could not update code scanning default setup for '{repo}': a setup change is already "
                f"in progress, or GitHub Actions is disabled for this repository. Ensure GitHub Actions "
                f"is enabled and try again later: {detail}"
            )
        case 422:
            raise Exception(
                f"Validation failed while updating code scanning default setup for '{repo}': {detail}. "
                "Note that CodeQL default setup requires at least one CodeQL-supported language in the repository."
            )
        case _:
            raise Exception(f"Unexpected response while updating code scanning default setup: HTTP {status}: {detail}")


def _matches_current(current: dict[str, Any], diff: dict[str, Any]) -> bool:
    """True if every field explicitly set in the PATCH diff already has the same value
    in the current GET response.

    Fields absent from the diff (unmanaged query_suite/threat_model, auto-detected
    languages) are not compared; languages compare as sets."""
    for key, value in diff.items():
        if key == "languages":
            if set(value) != set(current.get("languages") or []):
                return False
        elif current.get(key) != value:
            return False
    return True


@directive
def code_scanning(self: ASFGitHubFeature):
    scanning = self.yaml.get("code_scanning")
    previous_yaml = self.previous_yaml if isinstance(self.previous_yaml, dict) else {}
    was_previously_configured = "code_scanning" in previous_yaml

    settings: dict[str, Any] = {}
    if scanning is None:
        # Section absent
        configured = False
    elif isinstance(scanning, bool):
        # Simple form: code_scanning: true/false
        configured = scanning
    else:
        # Map form: the presence of settings implies the setup is enabled.
        configured = True
        settings = scanning

    if not configured and not was_previously_configured:
        return

    if self.noop("code_scanning"):
        return

    current = get_default_setup(self)
    currently_configured = current.get("state") == "configured"

    if configured:
        desired: dict[str, Any] = {"state": "configured"}
        # Fields not specified in .asf.yaml are left for GitHub to manage (auto-detection).
        if "query_suite" in settings:
            desired["query_suite"] = settings["query_suite"]
        if "threat_model" in settings:
            desired["threat_model"] = settings["threat_model"]
        if "languages" in settings:
            desired["languages"] = list(settings["languages"])
        if currently_configured and _matches_current(current, desired):
            return
        print(
            f"[github] Enabling CodeQL code scanning default setup (query_suite={desired.get('query_suite', 'unmanaged')})"
        )
        update_default_setup(self, desired)
    else:
        if not currently_configured:
            return
        print("[github] Disabling CodeQL code scanning default setup")
        update_default_setup(self, {"state": "not-configured"})
