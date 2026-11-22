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

"""GitHub general features: wiki, issues, projects, discussions, pull requests"""

import json

from . import directive, ASFGitHubFeature


def _desired_pull_requests(self: ASFGitHubFeature) -> bool | None:
    """Return the has_pull_requests value to send to GitHub, or None to leave it alone.

    Unlike the other features, pull requests are only touched when the key is set: a
    `features` block without `pullrequests` must not switch pull requests off for every
    repository that already has one. If the key was removed after being set to false,
    pull requests are switched back on, GitHub's default.
    """
    features = self.yaml.get("features") or {}
    if "pullrequests" in features:
        return bool(features["pullrequests"])
    previous_yaml = self.previous_yaml if isinstance(getattr(self, "previous_yaml", None), dict) else {}
    previous_features = previous_yaml.get("features") or {}
    if previous_features.get("pullrequests") is False:
        return True
    return None


def _set_pull_requests(self: ASFGitHubFeature, enabled: bool) -> None:
    # PyGithub's Repository.edit() does not know has_pull_requests, so send it directly.
    url = f"/repos/{self.repository.org_id}/{self.repository.name}"
    status, _headers, body = self.ghrepo._requester.requestJson("PATCH", url, input={"has_pull_requests": enabled})
    if 200 <= status < 300:
        return
    try:
        parsed = json.loads(body)
        detail = str(parsed.get("errors") or parsed.get("message") or body)
    except (json.JSONDecodeError, AttributeError, TypeError):
        detail = body
    action = "enable" if enabled else "disable"
    raise Exception(
        f"Failed to {action} pull requests on '{self.repository.org_id}/{self.repository.name}': "
        f"HTTP {status}: {detail}"
    )


@directive
def config_features(self: ASFGitHubFeature):
    # Generic features: issues, wiki, projects, discussions
    features = self.yaml.get("features")
    if features:
        if features.get("discussions", False):
            notifs = self.instance.features.notifications
            if (not notifs) or "discussions" not in notifs.valid_targets:
                raise Exception("GitHub discussions can only be enabled if a mailing list target exists for it.")

        # Apply the changes to GitHub, unless we are in no-op (test) mode.
        if not self.noop("features"):
            self.ghrepo.edit(
                has_issues=features.get("issues", False),
                has_wiki=features.get("wiki", False),
                has_projects=features.get("projects", False),
                has_discussions=features.get("discussions", False),
            )

    # Pull requests: handled apart from the rest, as they are only changed when asked for.
    pull_requests_enabled = _desired_pull_requests(self)
    if pull_requests_enabled is not None:
        print(f"Setting has_pull_requests to '{pull_requests_enabled}'")
        if not self.noop("features"):
            _set_pull_requests(self, pull_requests_enabled)
