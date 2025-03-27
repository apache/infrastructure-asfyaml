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

from typing import Mapping, Any
import github as pygithub
from github.GithubObject import NotSet, Opt, is_defined
from . import directive, ASFGitHubFeature


def _run_paged_graphql_query(
    self: ASFGitHubFeature,
    input_variables: Mapping[str, Any],
    query: str,
) -> list[Mapping[str, Any]]:
    finished = False
    end_cursor = None
    total_result = []

    while not finished:
        variables = {"endCursor": end_cursor}
        variables.update(input_variables)

        headers, data = self.ghrepo._requester.graphql_query(query, variables)
        result = data["data"]["repository"]["refs"]["nodes"]

        for rule in result:
            total_result.append(rule)

        page_info = data["data"]["repository"]["refs"]["pageInfo"]
        if page_info["hasNextPage"]:
            end_cursor = page_info["endCursor"]
        else:
            finished = True

    return total_result


def get_head_refs(self: ASFGitHubFeature) -> list[Mapping[str, Any]]:
    variables = {"organization": self.repository.org_id, "repository": self.repository.name, "refPrefix": "refs/heads/"}

    try:
        result = _run_paged_graphql_query(
            self,
            variables,
            """
query($endCursor: String, $organization: String!, $repository: String!, $refPrefix: String!) {
  repository(owner: $organization, name: $repository) {
    refs(first: 100, refPrefix: $refPrefix, after: $endCursor) {
      nodes {
        name
        branchProtectionRule {
          pattern
        }
      }
      pageInfo {
        hasNextPage
        endCursor
      }
    }
  }
}
""",
        )
        return result
    except KeyError as ex:
        print(f"Error: failed to retrieve current refs: {ex!s}")
        return []


@directive
def branch_protection(self: ASFGitHubFeature):
    # Branch protections
    if "protected_branches" not in self.yaml:
        return

    # Collect all branches and whether they have active branch protection rules
    try:
        refs = get_head_refs(self)
    except Exception as ex:
        print(f"Error: failed to retrieve current refs: {ex!s}")
        refs = []

    protected_branches = set()
    for ref in refs:
        name = ref["name"]
        branch_protection_rule = ref.get("branchProtectionRule")
        if branch_protection_rule is not None:
            protected_branches.add(name)

    branches = self.yaml.get("protected_branches", {})
    # If protected_branches is set to ~ (None), reset it to an empty map
    # We still need to remove existing branch protection rules from all existing branches later on
    if branches is None:
        branches = {}

    protection_changes = {}
    for branch, brsettings in branches.items():
        if branch in protected_branches:
            protected_branches.remove(branch)

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

        # Required linear history
        required_linear = brsettings.get("required_linear_history", NotSet)

        # Required conversation resolution
        # Requires all conversations to be resolved before merging is possible
        required_conversation_resolution = brsettings.get("required_conversation_resolution", NotSet)

        # Required pull requests reviews
        # As this is a nested object, we check for existence of the key to check if we should enable it
        if "required_pull_request_reviews" in brsettings:
            required_pull_request_reviews = brsettings.get("required_pull_request_reviews", {})

            required_approving_review_count = required_pull_request_reviews.get("required_approving_review_count", 0)
            require_code_owner_reviews = required_pull_request_reviews.get("require_code_owner_reviews")
            dismiss_stale_reviews = required_pull_request_reviews.get("dismiss_stale_reviews", NotSet)
        else:
            required_pull_request_reviews = NotSet
            required_approving_review_count = NotSet
            dismiss_stale_reviews = NotSet
            require_code_owner_reviews = NotSet

        required_checks: Opt[list[tuple[str, int]]]

        # Required status checks
        if "required_status_checks" in brsettings:
            required_status_checks = brsettings.get("required_status_checks", {})

            # strict means "Require branches to be up to date before merging".
            require_strict = required_status_checks.get("strict", NotSet)

            contexts = required_status_checks.get("contexts", [])
            checks = required_status_checks.get("checks", [])
            checks_as_dict = {**{ctx: -1 for ctx in contexts}, **{c["context"]: int(c["app_id"]) for c in checks}}

            required_checks = list(checks_as_dict.items())

            # if no checks are defined, we remove the status checks completely
            if len(required_checks) == 0:
                required_status_checks = NotSet
        else:
            required_status_checks = NotSet
            require_strict = NotSet
            required_checks = NotSet

        # Log changes that will be applied
        try:
            live_branch_protection_settings = ghbranch.get_protection()
        except pygithub.GithubException:
            live_branch_protection_settings = None

        if (
            live_branch_protection_settings is None
            or allow_force_push != live_branch_protection_settings.allow_force_pushes
        ):
            branch_changes.append(f"Set allow force push to {allow_force_push}")

        if is_defined(required_signatures) and (
            live_branch_protection_settings is None
            or required_signatures != live_branch_protection_settings.required_signatures
        ):
            branch_changes.append(f"Set required signatures to {required_signatures}")

        if is_defined(required_linear) and (
            live_branch_protection_settings is None
            or required_linear != live_branch_protection_settings.required_linear_history
        ):
            branch_changes.append(f"Set required linear history to {required_linear}")

        if is_defined(required_conversation_resolution) and (
            live_branch_protection_settings is None
            or required_conversation_resolution != live_branch_protection_settings.required_conversation_resolution
        ):
            branch_changes.append(f"Set required conversation resolution to {required_conversation_resolution}")

        if is_defined(required_pull_request_reviews):
            if live_branch_protection_settings is None:
                live_reviews = None
            else:
                live_reviews = live_branch_protection_settings.required_pull_request_reviews

            if is_defined(required_approving_review_count) and (
                live_reviews is None or required_approving_review_count != live_reviews.required_approving_review_count
            ):
                branch_changes.append(f"Set required approving review count to {required_approving_review_count}")

            if is_defined(require_code_owner_reviews) and (
                live_reviews is None or require_code_owner_reviews != live_reviews.require_code_owner_reviews
            ):
                branch_changes.append(f"Set required code owner reviews to {require_code_owner_reviews}")

            if is_defined(dismiss_stale_reviews) and (
                live_reviews is None or dismiss_stale_reviews != live_reviews.dismiss_stale_reviews
            ):
                branch_changes.append(f"Set dismiss stale reviews to {dismiss_stale_reviews}")

        if is_defined(required_status_checks):
            if live_branch_protection_settings is None:
                live_status_checks = None
            else:
                live_status_checks = live_branch_protection_settings.required_status_checks

            if is_defined(require_strict) and (
                live_status_checks is None or require_strict != live_status_checks.strict
            ):
                branch_changes.append(
                    f"Set require branches to be up to date before merging (strict) to {require_strict}"
                )

            # Always log the required checks that will be set for now. We will need to parse
            # the context field in a RequiredStatusChecks object.
            if is_defined(required_checks):
                branch_changes.append("Set required status contexts to the following:")
                for ctx, appid in required_checks:
                    branch_changes.append(f"  - {ctx} (app_id: {appid})")

        # Apply all the changes
        if not self.noop("protected_branches"):
            branch_protection_settings = ghbranch.edit_protection(
                allow_force_pushes=allow_force_push,
                required_linear_history=required_linear,
                required_conversation_resolution=required_conversation_resolution,
                required_approving_review_count=required_approving_review_count,
                dismiss_stale_reviews=dismiss_stale_reviews,
                require_code_owner_reviews=require_code_owner_reviews,
                require_last_push_approval=require_last_push_approval,
                strict=require_strict,
                checks=required_checks,  # type: ignore
            )

            if is_defined(required_signatures):
                if required_signatures and branch_protection_settings.required_signatures is False:
                    ghbranch.add_required_signatures()
                elif not required_signatures and branch_protection_settings.required_signatures is True:
                    ghbranch.remove_required_signatures()

            # if required pull requests are not enabled but present live, we need to explicitly remove them
            if (
                not is_defined(required_pull_request_reviews)
                and branch_protection_settings.required_pull_request_reviews is not None
            ):
                branch_changes.append("Remove required pull request reviews")
                ghbranch.remove_required_pull_request_reviews()

            # if required status checks are not enabled but present live, we need to explicitly remove them
            if not is_defined(required_status_checks) and branch_protection_settings.required_status_checks is not None:
                branch_changes.append("Remove required status checks")
                ghbranch.remove_required_status_checks()

        # Log all the changes we made to this branch
        if branch_changes:
            protection_changes[branch] = branch_changes

    # remove branch protection from all remaining protected branches
    for branch_name in protected_branches:
        branch = self.ghrepo.get_branch(branch_name)
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
