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

"""GitHub pull request creation cap support.

Limits the number of open pull requests a user without write access may have open
at one time, via the repository interaction-limits API, and keeps the list of users
allowed to bypass that cap in sync with `.asf.yaml`. See
https://github.com/community/maintainers/discussions/840 and
https://docs.github.com/rest/interactions/repos#update-pull-request-creation-cap-for-a-repository
"""

import json
from typing import Any

from . import directive, ASFGitHubFeature
from .collaborators import GITHUB_LOGIN_RE

# Bounds enforced by the GitHub API for max_open_pull_requests.
MIN_OPEN_PULL_REQUESTS = 1
MAX_OPEN_PULL_REQUESTS = 1000
# The bypass list holds at most this many users, and one request may add or remove at most this many.
MAX_BYPASS_USERS = 100


def _creation_cap_url(self: ASFGitHubFeature) -> str:
    return f"/repos/{self.repository.org_id}/{self.repository.name}/interaction-limits/pulls/creation-cap"


def _bypass_list_url(self: ASFGitHubFeature) -> str:
    return f"/repos/{self.repository.org_id}/{self.repository.name}/interaction-limits/pulls/bypass-list"


def _check_creation_cap_response(self: ASFGitHubFeature, status: int, body: str) -> None:
    """Raise unless GitHub accepted the creation cap update."""
    if 200 <= status < 300:
        return
    try:
        parsed = json.loads(body)
        detail = str(parsed.get("errors") or parsed.get("message") or body)
    except (json.JSONDecodeError, AttributeError):
        detail = body
    repo = f"{self.repository.org_id}/{self.repository.name}"
    match status:
        case 403:
            raise Exception(f"Not allowed to set the pull request creation cap on '{repo}': {detail}")
        case 404:
            raise Exception(f"Repository '{repo}' not found or not accessible: {detail}")
        case 422:
            raise Exception(f"Validation failed while setting the pull request creation cap: {detail}")
        case 500:
            raise Exception(f"GitHub server error while setting the pull request creation cap: {detail}")
        case _:
            raise Exception(f"Unexpected response while setting the pull request creation cap: HTTP {status}: {detail}")


def _check_bypass_list_response(self: ASFGitHubFeature, status: int, body: str, action: str) -> None:
    """Raise unless GitHub accepted the bypass list request."""
    if 200 <= status < 300:
        return
    try:
        parsed = json.loads(body)
        detail = str(parsed.get("errors") or parsed.get("message") or body)
    except (json.JSONDecodeError, AttributeError):
        detail = body
    repo = f"{self.repository.org_id}/{self.repository.name}"
    raise Exception(f"Failed {action} the pull request creation cap bypass list on '{repo}': HTTP {status}: {detail}")


def _parse_bypass_users(bypass_users: Any) -> list[str]:
    """Validate the configured bypass list and return it without duplicates, in the configured order."""
    if bypass_users is None:
        return []
    if not isinstance(bypass_users, list):
        raise Exception("github.pull_requests.creation_cap.bypass_users must be a list of GitHub logins")
    users: list[str] = []
    seen: set[str] = set()
    for user in bypass_users:
        if not isinstance(user, str) or not user.strip():
            raise Exception("github.pull_requests.creation_cap.bypass_users entries must be non-empty GitHub logins")
        login = user.strip()
        if not GITHUB_LOGIN_RE.match(login):
            raise Exception(f"github.pull_requests.creation_cap.bypass_users entry '{login}' is not a valid GitHub ID")
        if login.lower() in seen:
            continue
        seen.add(login.lower())
        users.append(login)
    if len(users) > MAX_BYPASS_USERS:
        raise Exception(
            f"github.pull_requests.creation_cap.bypass_users may list at most {MAX_BYPASS_USERS} users, got {len(users)}"
        )
    return users


def _find_unknown_logins(self: ASFGitHubFeature, logins: list[str]) -> list[str]:
    """Return the logins in `logins` that GitHub does not know."""
    unknown: list[str] = []
    for login in logins:
        status, _headers, body = self.ghrepo._requester.requestJson("GET", f"/users/{login}")
        if status == 404:
            unknown.append(login)
        elif not 200 <= status < 300:
            _check_bypass_list_response(self, status, body, f"looking up '{login}' for")
    return unknown


def _plan_bypass_list_changes(self: ASFGitHubFeature, desired: list[str]) -> tuple[list[str], list[str]]:
    """Return the logins to add to and remove from the repository's bypass list so it matches `desired`."""
    url = _bypass_list_url(self)
    # The list holds at most MAX_BYPASS_USERS entries, so one page covers it.
    status, _headers, body = self.ghrepo._requester.requestJson("GET", f"{url}?per_page={MAX_BYPASS_USERS}")
    _check_bypass_list_response(self, status, body, "reading")
    current = [entry["login"] for entry in json.loads(body)]

    # GitHub logins are case-insensitive; compare accordingly but send each side's own spelling.
    desired_by_key = {login.lower(): login for login in desired}
    current_by_key = {login.lower(): login for login in current}
    to_add = [login for key, login in desired_by_key.items() if key not in current_by_key]
    to_remove = [login for key, login in current_by_key.items() if key not in desired_by_key]

    # GitHub rejects the whole PUT when any login is unknown, without saying which one.
    unknown = _find_unknown_logins(self, to_add)
    if unknown:
        raise Exception(
            "github.pull_requests.creation_cap.bypass_users lists GitHub users that do not exist: " + ", ".join(unknown)
        )
    return to_add, to_remove


def _apply_bypass_list_changes(self: ASFGitHubFeature, to_add: list[str], to_remove: list[str]) -> None:
    url = _bypass_list_url(self)
    if to_add:
        print(f"Adding to pull request creation cap bypass list: {', '.join(to_add)}")
        status, _headers, body = self.ghrepo._requester.requestJson("PUT", url, input={"users": to_add})
        _check_bypass_list_response(self, status, body, "adding users to")
    if to_remove:
        print(f"Removing from pull request creation cap bypass list: {', '.join(to_remove)}")
        status, _headers, body = self.ghrepo._requester.requestJson("DELETE", url, input={"users": to_remove})
        _check_bypass_list_response(self, status, body, "removing users from")
    if not to_add and not to_remove:
        print("Pull request creation cap bypass list is already up to date")


@directive
def pr_creation_cap(self: ASFGitHubFeature):
    pull_requests = self.yaml.get("pull_requests") or {}
    creation_cap = pull_requests.get("creation_cap")

    previous_yaml = self.previous_yaml if isinstance(self.previous_yaml, dict) else {}
    previous_pull_requests = previous_yaml.get("pull_requests") or {}
    was_previously_configured = "creation_cap" in previous_pull_requests

    # The bypass list is only reconciled when the key is present; an absent key leaves
    # whatever is configured on GitHub untouched.
    manage_bypass_list = False
    bypass_users: list[str] = []
    if creation_cap:
        enabled = creation_cap.get("enabled", False)
        # Optional: when omitted (None), the key is left out of the payload below and
        # GitHub applies its own default cap.
        max_open_pull_requests = creation_cap.get("max_open_pull_requests")
        manage_bypass_list = "bypass_users" in creation_cap
        bypass_users = _parse_bypass_users(creation_cap.get("bypass_users"))
    elif was_previously_configured:
        # The section was removed; disable the cap that .asf.yaml previously managed.
        enabled = False
        max_open_pull_requests = None
    else:
        return

    payload: dict[str, Any] = {"enabled": enabled}
    if enabled and max_open_pull_requests is not None:
        if not MIN_OPEN_PULL_REQUESTS <= max_open_pull_requests <= MAX_OPEN_PULL_REQUESTS:
            raise Exception(
                "github.pull_requests.creation_cap.max_open_pull_requests must be between "
                f"{MIN_OPEN_PULL_REQUESTS} and {MAX_OPEN_PULL_REQUESTS}, got {max_open_pull_requests}"
            )
        payload["max_open_pull_requests"] = max_open_pull_requests

    if enabled:
        if "max_open_pull_requests" in payload:
            print(f"Setting pull request creation cap to enabled, max {max_open_pull_requests} open per user")
        else:
            print("Setting pull request creation cap to enabled")
    else:
        print("Disabling pull request creation cap")
    if manage_bypass_list:
        print(f"Setting pull request creation cap bypass list to: {', '.join(bypass_users) or '(empty)'}")

    if not self.noop("pr_creation_cap"):
        # Plan the bypass list first so an unknown login fails the run before the cap is changed.
        if manage_bypass_list:
            to_add, to_remove = _plan_bypass_list_changes(self, bypass_users)
        status, _headers, body = self.ghrepo._requester.requestJson("PATCH", _creation_cap_url(self), input=payload)
        _check_creation_cap_response(self, status, body)
        if manage_bypass_list:
            _apply_bypass_list_changes(self, to_add, to_remove)
