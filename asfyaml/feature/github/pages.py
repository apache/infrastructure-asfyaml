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

"""GitHub pages feature"""

from typing import Any

from . import directive, ASFGitHubFeature
import requests


@directive
def config_pages(self: ASFGitHubFeature):
    # GitHub pages
    ghp_type = self.yaml.get("ghp_type")

    if ghp_type == "legacy":
        _config_legacy(self)
    elif ghp_type == "workflow":
        _config_workflow(self)
    elif ghp_type == "disabled":
        _disable_gh_pages(self)
    else:
        raise Exception(f".asf.yaml: Invalid GitHub Pages type '{ghp_type}' - must be 'workflow' or 'legacy'!")


def _config_workflow(self: ASFGitHubFeature):
    ghp_branch = self.yaml.get("ghp_branch")
    ghp_path = self.yaml.get("ghp_path")

    if ghp_branch is not None:
        raise Exception(
            f".asf.yaml: Invalid GitHub Pages branch '{ghp_branch}' when ghp_type is 'workflow', remove parameter!"
        )

    if ghp_path is not None:
        raise Exception(
            f".asf.yaml: Invalid GitHub Pages path '{ghp_path}' when ghp_type is 'workflow', remove parameter!"
        )

    if self.noop("pages"):
        print("Would have set GitHub Pages to type 'workflow'.")
        return

    data = {"build_type": "workflow"}
    _config_ghp(self, data)


def _disable_gh_pages(self: ASFGitHubFeature):
    ghp_branch = self.yaml.get("ghp_branch")
    ghp_path = self.yaml.get("ghp_path")

    if ghp_branch is not None:
        raise Exception(
            f".asf.yaml: Invalid GitHub Pages branch '{ghp_branch}' when ghp_type is 'disabled', remove parameter!"
        )

    if ghp_path is not None:
        raise Exception(
            f".asf.yaml: Invalid GitHub Pages path '{ghp_path}' when ghp_type is 'disabled', remove parameter!"
        )

    if self.noop("pages"):
        print("Would have deleted GitHub Pages.")
        return

    status_code, _, body = self.ghrepo._requester.requestJson(
        "DELETE",
        f"/repos/{self.repository.org_id}/{self.repository.name}/pages",
    )

    if status_code == 204 or status_code == 404:
        print("Disabled GitHub Pages.")
    else:
        raise Exception(f"Failed to disable GitHub Pages: {status_code} -> {body}")


def _config_legacy(self: ASFGitHubFeature):
    ghp_branch = self.yaml.get("ghp_branch")
    ghp_path = self.yaml.get("ghp_path", "/docs")
    if ghp_branch:
        # determine the default branch of the repo, if the repo is not accessible locally, query the GH API
        default_branch = self.repository.default_branch_if_known or self.ghrepo.default_branch

        if ghp_branch not in (
            default_branch,
            "gh-pages",
        ):
            raise Exception(
                f".asf.yaml: Invalid GitHub Pages branch '{ghp_branch}' - must be the default branch "
                f"('{default_branch}') or 'gh-pages'!"
            )

        # Construct configuration for GitHub's API
        if ghp_path not in ["/docs", "/"]:
            raise Exception(f".asf.yaml: Invalid GitHub Pages path '{ghp_path}' - must be either '/docs' or '/'!")

        if self.noop("pages"):
            print(f"Would have set GitHub Pages to branch '{ghp_branch}' and path '{ghp_path}'.")
            return

        data = {"build_type": "legacy", "source": {"branch": ghp_branch, "path": ghp_path}}

        _config_ghp(self, data)


def _config_ghp(self: ASFGitHubFeature, data: dict[str, Any]) -> None:
    # Test if GHP is enabled already
    status_code, headers, body = self.ghrepo._requester.requestJson(
        "GET",
        f"/repos/{self.repository.org_id}/{self.repository.name}/pages",
    )

    # Not enabled yet, enable?!
    if status_code == 404:
        try:
            status_code, _, body = self.ghrepo._requester.requestJson(
                "POST",
                f"/repos/{self.repository.org_id}/{self.repository.name}/pages",
                input=data,
            )

            if status_code == 201:
                print("GitHub Pages set to %r" % data)
            else:
                raise Exception(f"Failed to create GitHub Pages: {status_code} -> {body}")
        except requests.exceptions.RequestException:
            print("Could not set GitHub Pages configuration!")
    # Enabled, update settings?
    elif 200 <= status_code < 300:
        try:
            status_code, _, body = self.ghrepo._requester.requestJson(
                "PUT",
                f"/repos/{self.repository.org_id}/{self.repository.name}/pages",
                input=data,
            )

            if status_code == 204:
                print("GitHub Pages updated to %r" % data)
            else:
                raise Exception(f"Failed to update GitHub Pages: {status_code} -> {body}")
        except requests.exceptions.RequestException:
            print("Could not set GitHub Pages configuration!")
