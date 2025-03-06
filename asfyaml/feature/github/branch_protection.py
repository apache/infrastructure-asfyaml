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

from . import directive, ASFGitHubFeature
import github as pygithub

@directive
def branch_protection(self: ASFGitHubFeature):
    # Merge buttons
    branches = self.yaml.get("protected_branches")
    if not branches:
        return

    protection_changes = {}
    for branch, brsettings in branches.items():
        branch_changes = []
        try:
            ghbranch = self.ghrepo.get_branch(branch=branch)
        except pygithub.GithubException as e:
            if e.status == 404:  # No such branch, skip to next rule
                protection_changes[branch] = ["Branch does not exist, protection could not be configured"]
                continue
        if ghbranch:
            try:
                ghbranch.edit_protection()  # Causes protection to be initialized if not already so.
                branch_protection_settings = ghbranch.get_protection()
            except pygithub.GithubException as e:
                if e.status != 404: # Not a 404? something is wrong then
                    raise e

            # Required signatures
            #required_signatures = brsettings.get("required_signatures", False)
            required_signatures = brsettings.get("required_signatures", "false") == "true"
            if branch_protection_settings.required_signatures != required_signatures:
                if required_signatures:
                    if not self.noop("github::protected_branches"):
                        ghbranch.add_required_signatures()
                    branch_changes.append("Set required signatures to True")
                else:
                    if not self.noop("github::protected_branches"):
                        ghbranch.remove_required_signatures()
                    branch_changes.append("Set required signatures to False")

            # Required linear history
            #required_linear = bool(brsettings.get("required_linear_history", False))
            required_linear = brsettings.get("required_linear_history", "false") == "true"
            if branch_protection_settings.required_linear_history != required_linear:
                if required_linear:
                    if not self.noop("github::protected_branches"):
                        ghbranch.edit_protection(required_linear_history=True)
                    branch_changes.append("Set required linear history to True")
                else:
                    if not self.noop("github::protected_branches"):
                        ghbranch.edit_protection(required_linear_history=False)
                    branch_changes.append("Set required linear history to False")

            # Required conversation resolution
            # Requires all conversations to be resolved before merging is possible
            #required_conversation_resolution = bool(brsettings.get("required_conversation_resolution", False))
            required_conversation_resolution = brsettings.get("required_conversation_resolution", "false") == "true"
            if branch_protection_settings.required_conversation_resolution != required_conversation_resolution:
                if required_conversation_resolution:
                    if not self.noop("github::protected_branches"):
                        ghbranch.edit_protection(required_conversation_resolution=True)
                    branch_changes.append("Set required conversation resolution to True")
                else:
                    if not self.noop("github::protected_branches"):
                        ghbranch.edit_protection(required_conversation_resolution=False)
                    branch_changes.append("Set required conversation resolution to False")


            # Required status checks
            required_status_checks = brsettings.get("required_status_checks", {})
            if required_status_checks:
                # strict means "Require branches to be up to date before merging".
                # While we build a better schema, jury-rig this bool
                require_strict = required_status_checks.get("strict", "false") == "true"
                # require_strict = bool(required_status_checks.get("strict", False))
                contexts = required_status_checks.get("contexts", [])
                checks = required_status_checks.get("checks", [])
                checks_as_dict = {**{ctx: -1 for ctx in contexts}, **{c["context"]: int(c["app_id"]) for c in checks}}
                if (not branch_protection_settings.required_status_checks or branch_protection_settings.required_status_checks.strict != require_strict):
                    if not checks_as_dict:
                        if not self.noop("github::protected_branches"):
                            #ghbranch.edit_required_status_checks(strict=require_strict, checks=[])
                            pass
                        branch_changes.append(
                            f"Set require branches to be up to date before merging (strict) to {require_strict}"
                        )
                try:
                    existing_contexts = ghbranch.get_required_status_checks().contexts
                except pygithub.GithubException as e:
                    if e.status == 404:  # No existing contexts, set to blank dict
                        existing_contexts = {}
                    else:
                        raise e
                # TODO: existing contexts don't tend to fetch the actual values. pygithub bug?
                if checks_as_dict != existing_contexts:  # Something changed, update contexts
                    if checks_as_dict:
                        if not self.noop("github::protected_branches"):
                            ghbranch.edit_protection(strict=require_strict, checks=list(checks_as_dict.items()))
                        branch_changes.append(f"Set required status contexts to the following:")
                        for ctx, appid in checks_as_dict.items():
                            branch_changes.append(f"  - {ctx} (app_id: {appid})")
                    else:
                        if not self.noop("github::protected_branches"):
                            ghbranch.remove_required_status_checks()
                        branch_changes.append(f"Removed all required status contexts from branch")

            else:
                if branch_protection_settings.required_status_checks:  # Set but not defined? remove it then
                    if not self.noop("github::protected_branches"):
                        ghbranch.edit_protection(strict=False, checks=[])
                        ghbranch.remove_required_status_checks()
                    branch_changes.append(f"Removed required status checks")

            # Required pull requests reviews
            required_pull_request_reviews = brsettings.get("required_pull_request_reviews", {})
            if required_pull_request_reviews:
                dismiss_stale_reviews = required_pull_request_reviews.get("dismiss_stale_reviews", "false") == "true"
                required_approving_review_count = required_pull_request_reviews.get(
                    "required_approving_review_count", 0
                )
                required_approving_review_count = int(required_approving_review_count)
                assert isinstance(
                    required_approving_review_count, int
                ), "required_approving_review_count MUST be an integer value"
                if (not branch_protection_settings.required_pull_request_reviews or
                        branch_protection_settings.required_pull_request_reviews.required_approving_review_count
                        != required_approving_review_count
                ):
                    if not self.noop("github::protected_branches"):
                        ghbranch.remove_required_pull_request_reviews()
                        ghbranch.edit_required_pull_request_reviews(required_approving_review_count=required_approving_review_count)
                    branch_changes.append(f"Set required approving review count to {required_approving_review_count}")
                grp = ghbranch.get_required_pull_request_reviews()
                if (not grp or
                        grp.dismiss_stale_reviews
                        != dismiss_stale_reviews
                ):
                    if not self.noop("github::protected_branches"):
                        ghbranch.edit_required_pull_request_reviews(dismiss_stale_reviews=dismiss_stale_reviews, required_approving_review_count=required_approving_review_count)
                    branch_changes.append(f"Set dismiss stale reviews to {dismiss_stale_reviews}")


            # Log all the changes we made to this branch
            if branch_changes:
                protection_changes[branch] = branch_changes

    if protection_changes:
        summary = ""
        for branch, changes in protection_changes.items():
            summary += f"Updates to the {branch} branch:\n"
            for change in changes:
                summary += f"  - {change}\n"
        print(summary)
