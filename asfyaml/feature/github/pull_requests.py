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

"""Settings related to GitHub Pull Requests"""

from github.GithubObject import NotSet, is_defined

from . import directive, ASFGitHubFeature


@directive
def pull_requests(self: ASFGitHubFeature):
    # retrieve the legacy "del_branch_on_merge" setting from the github object
    legacy_del_branch_on_merge = self.yaml.get("del_branch_on_merge", NotSet)

    pull_requests = self.yaml.get("pull_requests")
    if pull_requests:
        allow_auto_merge = pull_requests.get("allow_auto_merge", NotSet)
        allow_update_branch = pull_requests.get("allow_update_branch", NotSet)
        del_branch_on_merge = pull_requests.get("del_branch_on_merge", NotSet)

        if is_defined(legacy_del_branch_on_merge):
            raise Exception(
                "found legacy setting 'github.del_branch_on_merge' while "
                "'github.pull_requests' is present. Move setting to 'github.pull_requests'"
            )
    else:
        allow_auto_merge = NotSet
        allow_update_branch = NotSet
        del_branch_on_merge = legacy_del_branch_on_merge

    # check if we have any defined property
    any_defined_property = any(
        map(lambda x: is_defined(x), (del_branch_on_merge, allow_auto_merge, allow_update_branch))
    )

    if any_defined_property and not self.noop("pull_requests"):
        if is_defined(allow_auto_merge):
            print(f"Setting allow_auto_merge to '{allow_auto_merge}'")

        if is_defined(allow_update_branch):
            print(f"Setting allow_update_branch to '{allow_update_branch}'")

        if is_defined(del_branch_on_merge):
            print(f"Setting del_branch_on_merge to '{del_branch_on_merge}'")

        self.ghrepo.edit(
            allow_auto_merge=allow_auto_merge,
            allow_update_branch=allow_update_branch,
            delete_branch_on_merge=del_branch_on_merge,
        )
