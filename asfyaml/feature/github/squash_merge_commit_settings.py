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

"""GitHub squash merge commit settings feature"""
from . import directive, ASFGitHubFeature


@directive
def squash_merge_commit_settings(self: ASFGitHubFeature):
    squash_merge_commit_title = self.yaml.get("squash_merge_commit_title")
    squash_merge_commit_message = self.yaml.get("squash_merge_commit_message")

    # if neither a title nor message is specified, just return
    if not squash_merge_commit_title and not squash_merge_commit_message:
        return

    # if only one of the 2 properties is set,
    # retrieve the other one from the current live setting
    if squash_merge_commit_title and not squash_merge_commit_message:
        squash_merge_commit_message = self.ghrepo.squash_merge_commit_message

    if squash_merge_commit_message and not squash_merge_commit_title:
        squash_merge_commit_title = self.ghrepo.squash_merge_commit_title

    # check if we have a valid combination
    if (squash_merge_commit_title, squash_merge_commit_message) not in [
        ("PR_TITLE", "PR_BODY"),
        ("PR_TITLE", "BLANK"),
        ("PR_TITLE", "COMMIT_MESSAGES"),
        ("COMMIT_OR_PR_TITLE", "COMMIT_MESSAGES"),
    ]:
        raise Exception(
            f".asf.yaml: Invalid squash_merge_commit title / message settings: - must be a combination of "
            "('PR_TITLE', 'PR_BODY') | ('PR_TITLE', 'BLANK') | ('PR_TITLE', 'COMMIT_MESSAGES') | "
            "('COMMIT_OR_PR_TITLE', 'COMMIT_MESSAGES')."
        )

    if not self.noop("squash_merge_commit_title") and not self.noop("squash_merge_commit_message"):
        self.ghrepo.edit(
            squash_merge_commit_title=squash_merge_commit_title,
            squash_merge_commit_message=squash_merge_commit_message,
        )
