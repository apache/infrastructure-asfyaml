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

"""GitHub Actions repository settings support.

Configures the contributor approval policy for running GitHub Actions workflows on pull
requests from forks. See
https://docs.github.com/rest/actions/permissions#set-fork-pr-contributor-approval-permissions-for-a-repository
"""

import json

from . import ASFGitHubFeature, constants, directive


def _fork_pr_approval_url(self: ASFGitHubFeature) -> str:
    return f"/repos/{self.repository.org_id}/{self.repository.name}/actions/permissions/fork-pr-contributor-approval"


def _check_fork_pr_approval_response(self: ASFGitHubFeature, status: int, body: str) -> None:
    """Raise unless GitHub accepted the fork PR contributor approval update."""
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
            raise Exception(f"Not allowed to set the fork PR contributor approval policy on '{repo}': {detail}")
        case 404:
            raise Exception(f"Repository '{repo}' not found or not accessible: {detail}")
        case 422:
            raise Exception(f"Validation failed while setting the fork PR contributor approval policy: {detail}")
        case 500:
            raise Exception(f"GitHub server error while setting the fork PR contributor approval policy: {detail}")
        case _:
            raise Exception(
                f"Unexpected response while setting the fork PR contributor approval policy: HTTP {status}: {detail}"
            )


@directive
def fork_pr_contributor_approval(self: ASFGitHubFeature):
    actions = self.yaml.get("actions") or {}
    approval_policy = actions.get("fork_pr_contributor_approval")

    previous_yaml = self.previous_yaml if isinstance(self.previous_yaml, dict) else {}
    previous_actions = previous_yaml.get("actions") or {}
    was_previously_configured = (
        isinstance(previous_actions, dict) and previous_actions.get("fork_pr_contributor_approval") is not None
    )

    if approval_policy is not None:
        # Validated by strictyaml.Enum; kept as defense in depth.
        if approval_policy not in constants.VALID_FORK_PR_APPROVAL_POLICIES:
            valid = ", ".join(constants.VALID_FORK_PR_APPROVAL_POLICIES)
            raise Exception(
                f"github.actions.fork_pr_contributor_approval must be one of {valid}, got {approval_policy}"
            )
        policy = approval_policy
    elif was_previously_configured:
        # The setting was removed; revert to the strictest policy (ASF default).
        policy = constants.DEFAULT_FORK_PR_APPROVAL_POLICY
    else:
        return

    print(f"Setting fork pull request workflow approval policy to '{policy}'")

    if not self.noop("fork_pr_contributor_approval"):
        status, _headers, body = self.ghrepo._requester.requestJson(
            "PUT",
            _fork_pr_approval_url(self),
            input={"approval_policy": policy},
        )
        _check_fork_pr_approval_response(self, status, body)
