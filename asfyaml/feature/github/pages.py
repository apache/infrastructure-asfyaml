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
from . import directive, ASFGitHubFeature, GH_TOKEN_FILE
import requests


@directive
def config_pages(self: ASFGitHubFeature):
    # GitHub pages
    ghp_branch = self.yaml.get("ghp_branch")
    ghp_path = self.yaml.get("ghp_path", "/docs")
    if ghp_branch:
        if ghp_branch not in (
            self.repository.default_branch,
            "gh-pages",
        ):
            raise Exception(
                f".asf.yaml: Invalid GitHub Pages branch '{ghp_branch}' - must be default branch or gh-pages!"
            )

        # Construct configuration for GitHub's API
        if ghp_path not in ["/docs", "/"]:
            print(f"GitHub Pages path '{ghp_path}' is invalid, setting to /")
            ghp_path = "/"
        ghps = {"branch": ghp_branch, "path": ghp_path}

        # The processing below only happens in non-test mode. Return otherwise.
        if self.noop("pages"):
            print(f"Would have set GHP to branch '{ghp_branch}' and path '{ghp_path}'.")
            return

        GHP_URL = f"https://api.github.com/repos/{self.repository.org_id}/{self.repository.name}/pages"
        GHP_TOKEN = open(GH_TOKEN_FILE).read().strip()
        
        # Test if GHP is enabled already
        rv = requests.get(
            GHP_URL,
            headers={
                "Authorization": "token %s" % GHP_TOKEN,
                "Accept": "application/vnd.github.switcheroo-preview+json",
            },
        )

        # Not enabled yet, enable?!
        if rv.status_code == 404:
            try:
                rv = requests.post(
                    GHP_URL,
                    headers={
                        "Authorization": "token %s" % GHP_TOKEN,
                        "Accept": "application/vnd.github.switcheroo-preview+json",
                    },
                    json={"source": ghps},
                )
                print("GitHub Pages set to branch=%s, path=%s" % (ghp_branch, ghp_path))
            except requests.exceptions.RequestException:
                print("Could not set GitHub Pages configuration!")
        # Enabled, update settings?
        elif 200 <= rv.status_code < 300:
            try:
                rv = requests.put(
                    GHP_URL,
                    headers={
                        "Authorization": "token %s" % GHP_TOKEN,
                        "Accept": "application/vnd.github.switcheroo-preview+json",
                    },
                    json={
                        "source": ghps,
                    },
                )
                print("GitHub Pages updated to %r" % ghps)
                print(rv.status_code)
                print(rv.text)
            except requests.exceptions.RequestException:
                print("Could not set GitHub Pages configuration!")
    # TODO: Allow disabling GitHub Pages by removing the entries..
