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

"""GitHub merge buttons"""

from github.GithubObject import NotSet

from . import directive, ASFGitHubFeature


@directive
def enabled_merge_buttons(self: ASFGitHubFeature):
    # Merge buttons
    merges = self.yaml.get("enabled_merge_buttons")
    if not merges:
        return

    allow_squash_merge = merges.get("squash", NotSet)
    allow_merge_commits = merges.get("merge", NotSet)
    allow_rebase_merge = merges.get("rebase", NotSet)

    if not allow_squash_merge and not allow_merge_commits and not allow_rebase_merge:
        raise Exception("enabled_merge_buttons: at least one of 'squash', 'merge' or 'rebase' must be enabled")

    squash_commit_message = merges.get("squash_commit_message")
    if squash_commit_message and not allow_squash_merge:
        print("ignoring squash_commit_message as squash_merges are disallowed")
        squash_commit_message = None

    match squash_commit_message:
        case "DEFAULT":
            squash_merge_commit_title = "COMMIT_OR_PR_TITLE"
            squash_merge_commit_message = "COMMIT_MESSAGES"

        case "PR_TITLE":
            squash_merge_commit_title = "PR_TITLE"
            squash_merge_commit_message = "BLANK"

        case "PR_TITLE_AND_COMMIT_DETAILS":
            squash_merge_commit_title = "PR_TITLE"
            squash_merge_commit_message = "COMMIT_MESSAGES"

        case "PR_TITLE_AND_DESC":
            squash_merge_commit_title = "PR_TITLE"
            squash_merge_commit_message = "PR_BODY"

        case None:
            squash_merge_commit_title = NotSet
            squash_merge_commit_message = NotSet

        case _:
            raise Exception("enabled_merge_buttons: squash_commit_message must be one of "
                            "'DEFAULT', 'PR_TITLE', 'PR_TITLE_AND_COMMIT_DETAILS' or 'PR_TITLE_AND_DESC'")

    merge_commit_message = merges.get("merge_commit_message")
    if merge_commit_message and not allow_merge_commits:
        print("ignoring merge_commit_message as merge commits are disallowed")
        merge_commit_message = None

    match merge_commit_message:
        case "DEFAULT":
            merge_commit_title = "MERGE_MESSAGE"
            merge_commit_message = "PR_TITLE"

        case "PR_TITLE":
            merge_commit_title = "PR_TITLE"
            merge_commit_message = "BLANK"

        case "PR_TITLE_AND_DESC":
            merge_commit_title = "PR_TITLE"
            merge_commit_message = "PR_BODY"

        case None:
            merge_commit_title = NotSet
            merge_commit_message = NotSet

        case _:
            raise Exception("enabled_merge_buttons: merge_commit_message must be one of "
                            "'DEFAULT', 'PR_TITLE' or 'PR_TITLE_AND_DESC'")

    if not self.noop("enabled_merge_buttons"):
        self.ghrepo.edit(
            allow_squash_merge=allow_squash_merge,
            allow_merge_commit=allow_merge_commits,
            allow_rebase_merge=allow_rebase_merge,
            merge_commit_title=merge_commit_title,
            merge_commit_message=merge_commit_message,
            squash_merge_commit_title=squash_merge_commit_title,
            squash_merge_commit_message=squash_merge_commit_message
        )
