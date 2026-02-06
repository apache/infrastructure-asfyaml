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

"""Settings related to GitHub Immutable Releases"""

from github.GithubObject import NotSet, is_defined
from typing import TYPE_CHECKING
from . import directive, ASFGitHubFeature

if TYPE_CHECKING:
    from github.Requester import Requester


@directive
def immutable_releases(self: ASFGitHubFeature):
    immutable_releases_setting = self.yaml.get("immutable_releases", NotSet)
    enable = immutable_releases_setting is True if is_defined(immutable_releases_setting) else False
    print(f"GitHub immutable releases shall be {'enabled' if enable else 'disabled'}")

    url = f"/repos/{self.repository.org_id}/{self.repository.name}/immutable-releases"

    if not self.noop("immutable_releases"):
        requester: Requester = self.ghrepo.requester
        is_enabled_status, _, _ = requester.requestJson("GET", url)
        # HTTP status code 404 means that immutable releases are not enabled.
        # See https://docs.github.com/en/rest/repos/repos?apiVersion=2022-11-28#check-if-immutable-releases-are-enabled-for-a-repository
        is_enabled = is_enabled_status == 200
        print(f"GitHub immutable releases are currently {'enabled' if is_enabled else 'disabled'}")

        if is_enabled != enable:
            if enable:
                # https://docs.github.com/en/rest/repos/repos?apiVersion=2022-11-28#enable-immutable-releases
                status, _, _ = requester.requestJson("PUT", url)
            else:
                # https://docs.github.com/en/rest/repos/repos?apiVersion=2022-11-28#disable-immutable-releases
                status, _, _ = requester.requestJson("DELETE", url)
            assert status == 204, f"Failed to set immutable releases to {enable}"

            print(f"GitHub immutable releases are now {'enabled' if enable else 'disabled'}")
