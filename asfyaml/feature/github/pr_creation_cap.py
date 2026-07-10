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
at one time, via the repository interaction-limits API. See
https://github.com/community/maintainers/discussions/840 and
https://docs.github.com/rest/interactions/repos#update-pull-request-creation-cap-for-a-repository
"""

from typing import Any

from . import directive, ASFGitHubFeature

# Bounds enforced by the GitHub API for max_open_pull_requests.
MIN_OPEN_PULL_REQUESTS = 1
MAX_OPEN_PULL_REQUESTS = 1000


def _creation_cap_url(self: ASFGitHubFeature) -> str:
    return f"/repos/{self.repository.org_id}/{self.repository.name}/interaction-limits/pulls/creation-cap"


@directive
def pr_creation_cap(self: ASFGitHubFeature):
    pull_requests = self.yaml.get("pull_requests") or {}
    creation_cap = pull_requests.get("creation_cap")

    previous_yaml = self.previous_yaml if isinstance(self.previous_yaml, dict) else {}
    previous_pull_requests = previous_yaml.get("pull_requests") or {}
    was_previously_configured = "creation_cap" in previous_pull_requests

    if creation_cap:
        enabled = creation_cap.get("enabled", False)
        max_open_pull_requests = creation_cap.get("max_open_pull_requests")
    elif was_previously_configured:
        # The section was removed; disable the cap that .asf.yaml previously managed.
        enabled = False
        max_open_pull_requests = None
    else:
        return

    if not enabled and not was_previously_configured:
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

    if not self.noop("pr_creation_cap"):
        self.ghrepo._requester.requestJson("PATCH", _creation_cap_url(self), input=payload)
