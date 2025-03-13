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

"""GitHub branch protections"""

import github as pygithub
from github.GithubObject import NotSet

from . import directive, ASFGitHubFeature


@directive
def branch_protection(self: ASFGitHubFeature):
    # Branch protections
    if "protected_branches" not in self.yaml:
        return

    # a map to keep track of all branches to determine from which we should remove protections
    all_branches = {branch.name: branch for branch in self.ghrepo.get_branches()}

    branches = self.yaml.get("protected_branches", {})
    protection_changes = {}
    for branch, brsettings in branches.items():
        if branch in all_branches:
            all_branches.pop(branch)

        branch_changes = []
        try:
            ghbranch = self.ghrepo.get_branch(branch=branch)
        except pygithub.GithubException as e:
            if e.status == 404:  # No such branch, skip to next rule
                protection_changes[branch] = [f"Branch {branch} does not exist, protection could not be configured"]
                continue
            else:
                # propagate other errors, GitHub API might have an outage
                raise e

        # We explicitly disable force pushes when branch protections are enabled
        allow_force_push = False

        # Required signatures
        required_signatures = brsettings.get("required_signatures", NotSet)
        if required_signatures is not NotSet:
            branch_changes.append(f"Set required signatures to {required_signatures}")

        # Required linear history
        required_linear = brsettings.get("required_linear_history", NotSet)
        if required_linear is not NotSet:
            branch_changes.append(f"Set required linear history to {required_linear}")

        # Required conversation resolution
        # Requires all conversations to be resolved before merging is possible
        required_conversation_resolution = brsettings.get("required_conversation_resolution", NotSet)
        if required_conversation_resolution is not NotSet:
            branch_changes.append(f"Set required conversation resolution to {required_conversation_resolution}")

        # Required pull requests reviews
        # As this is a nested object, we check for existence of the key to check if we should enable it
        # If no further properties are provided, we use the default setting of required_approving_review_count = 0
        if "required_pull_request_reviews" in brsettings:
            required_pull_request_reviews = brsettings.get("required_pull_request_reviews", {})

            required_approving_review_count = required_pull_request_reviews.get("required_approving_review_count", 0)
            if required_approving_review_count is not NotSet:
                branch_changes.append(f"Set required approving review count to {required_approving_review_count}")

            dismiss_stale_reviews = required_pull_request_reviews.get("dismiss_stale_reviews", NotSet)
            if dismiss_stale_reviews is not NotSet:
                branch_changes.append(f"Set dismiss stale reviews to {dismiss_stale_reviews}")
        else:
            required_pull_request_reviews = NotSet
            required_approving_review_count = NotSet
            dismiss_stale_reviews = NotSet

        # Required status checks
        if "required_status_checks" in brsettings:
            required_status_checks = brsettings.get("required_status_checks", {})

            # strict means "Require branches to be up to date before merging".
            require_strict = required_status_checks.get("strict", NotSet)

            contexts = required_status_checks.get("contexts", [])
            checks = required_status_checks.get("checks", [])
            checks_as_dict = {**{ctx: -1 for ctx in contexts}, **{c["context"]: int(c["app_id"]) for c in checks}}

            required_checks = list(checks_as_dict.items())

            if len(required_checks) > 0:
                branch_changes.append(f"Set required status contexts to the following:")
                for ctx, appid in checks_as_dict.items():
                    branch_changes.append(f"  - {ctx} (app_id: {appid})")

                if require_strict is not NotSet:
                    branch_changes.append(
                        f"Set require branches to be up to date before merging (strict) to {require_strict}"
                    )
            else:
                require_strict = NotSet
                required_checks = NotSet
                branch_changes.append(f"Remove required status checks")

        else:
            required_status_checks = NotSet
            require_strict = NotSet
            required_checks = NotSet

        # Apply all the changes
        if not self.noop("github::protected_branches"):
            branch_protection_settings = ghbranch.edit_protection(
                allow_force_pushes=allow_force_push,
                required_linear_history=required_linear,
                required_conversation_resolution=required_conversation_resolution,
                required_approving_review_count=required_approving_review_count,
                dismiss_stale_reviews=dismiss_stale_reviews,
                strict=require_strict,
                checks=required_checks,)

            if required_signatures is not NotSet:
                if required_signatures:
                    ghbranch.add_required_signatures()
                else:
                    ghbranch.remove_required_signatures()

            # if required pull requests are not enabled but present live, we need to explicitly remove them
            if (required_pull_request_reviews is NotSet and
                    branch_protection_settings.required_pull_request_reviews is not None):
                ghbranch.remove_required_pull_request_reviews()

            # if required status checks are not enabled but present live, we need to explicitly remove them
            if (required_status_checks is NotSet and
                    branch_protection_settings.required_status_checks is not None):
                ghbranch.remove_required_status_checks()

        # Log all the changes we made to this branch
        if branch_changes:
            protection_changes[branch] = branch_changes

    # remove branch protection from all remaining branches
    for branch_name, branch in all_branches.items():
        try:
            branch.get_protection()
        except pygithub.GithubException as e:
            if e.status == 404:  # No existing branch protection, skip
                continue
            else:
                # propagate other errors, GitHub API might have an outage
                raise e

        protection_changes[branch] = [f"Remove branch protection from branch '{branch_name}'"]

        if not self.noop("github::protected_branches"):
            branch.remove_protection()

    if protection_changes:
        summary = ""
        for branch, changes in protection_changes.items():
            summary += f"Updates to the {branch} branch:\n"
            for change in changes:
                summary += f"  - {change}\n"
        print(summary)
