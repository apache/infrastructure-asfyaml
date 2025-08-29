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

import re
from typing import Mapping, Any, Dict, List, Tuple, Set
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


def compile_protection_rules(branches_config: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Separate and validate exact branch rules from pattern rules
    
    Returns:
        Tuple of (pattern_rules, exact_rules)
    """
    pattern_rules = {}
    exact_rules = {}
    
    for rule_name, settings in branches_config.items():
        if "pattern" in settings:
            # This is a pattern rule
            pattern_str = settings["pattern"]
            try:
                compiled_pattern = re.compile(pattern_str)
                pattern_rules[rule_name] = {
                    "regex": compiled_pattern,
                    "pattern_str": pattern_str,
                    "settings": settings
                }
            except re.error as e:
                raise Exception(f"Invalid regex pattern in rule '{rule_name}': {e}")
        else:
            # This is an exact branch rule (existing behavior)
            exact_rules[rule_name] = settings
    
    return pattern_rules, exact_rules


def match_branches_to_patterns(all_branches: List[str], pattern_rules: Dict[str, Any]) -> Dict[str, List[str]]:
    """Match all repository branches against compiled pattern rules
    
    Returns:
        Dict mapping branch_name -> list of matching rule names
    """
    branch_matches = {}
    
    for branch_name in all_branches:
        matching_rules = []
        for rule_name, rule_data in pattern_rules.items():
            if rule_data["regex"].match(branch_name):
                matching_rules.append(rule_name)
        
        if matching_rules:
            branch_matches[branch_name] = matching_rules
    
    return branch_matches


def resolve_protection_rules(
    all_branches: Dict[str, Any],
    pattern_rules: Dict[str, Any], 
    exact_rules: Dict[str, Any]
) -> Tuple[Dict[str, Dict], List[str]]:
    """Resolve final protection rules with precedence handling
    
    Precedence:
    1. Exact branch names override pattern matches
    2. First matching pattern wins for conflicts
    
    Returns:
        Tuple of (final_rules_dict, warnings_list)
    """
    warnings = []
    final_rules = {}
    
    # Get all branch names from the repository
    branch_names = list(all_branches.keys())
    
    # Match branches against patterns
    branch_pattern_matches = match_branches_to_patterns(branch_names, pattern_rules)
    
    # Apply pattern matches first
    for branch_name, matching_rule_names in branch_pattern_matches.items():
        if len(matching_rule_names) > 1:
            warnings.append(
                f"Branch '{branch_name}' matches multiple patterns: {matching_rule_names}. "
                f"Using first match: '{matching_rule_names[0]}'"
            )
        
        # Use first matching pattern
        first_rule = matching_rule_names[0]
        final_rules[branch_name] = {
            "settings": pattern_rules[first_rule]["settings"],
            "source": f'pattern rule "{first_rule}" ({pattern_rules[first_rule]["pattern_str"]})',
            "rule_type": "pattern"
        }
    
    # Apply exact rules (these override pattern matches)
    for branch_name, settings in exact_rules.items():
        if branch_name in all_branches:
            if branch_name in final_rules:
                warnings.append(
                    f"Exact rule '{branch_name}' overrides pattern match from {final_rules[branch_name]['source']}"
                )
            
            final_rules[branch_name] = {
                "settings": settings,
                "source": f'exact rule "{branch_name}"',
                "rule_type": "exact"
            }
        else:
            warnings.append(f"Exact branch rule '{branch_name}' does not match any existing branch")
    
    # Check for patterns with no matches
    pattern_match_counts = {}
    for rule_name in pattern_rules:
        pattern_match_counts[rule_name] = 0
    
    for matching_rules in branch_pattern_matches.values():
        for rule_name in matching_rules:
            pattern_match_counts[rule_name] += 1
    
    for rule_name, match_count in pattern_match_counts.items():
        if match_count == 0:
            warnings.append(
                f"Pattern rule '{rule_name}' with pattern '{pattern_rules[rule_name]['pattern_str']}' matches no branches"
            )
    
    return final_rules, warnings


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

    # Build dict of all repository branches
    all_branches = {}
    currently_protected_branches = set()
    for ref in refs:
        name = ref["name"]
        all_branches[name] = ref
        branch_protection_rule = ref.get("branchProtectionRule")
        if branch_protection_rule is not None:
            currently_protected_branches.add(name)

    branches_config = self.yaml.get("protected_branches", {})
    # If protected_branches is set to ~ (None), reset it to an empty map
    if branches_config is None:
        branches_config = {}

    # NEW: Compile pattern and exact rules with validation
    try:
        pattern_rules, exact_rules = compile_protection_rules(branches_config)
        final_rules, rule_warnings = resolve_protection_rules(all_branches, pattern_rules, exact_rules)
        
        # Print warnings about rule conflicts and missing matches
        for warning in rule_warnings:
            print(f"Warning: {warning}")
            
    except Exception as e:
        print(f"Error processing branch protection rules: {e}")
        return

    protection_changes = {}
    
    # Process final resolved rules (both exact and pattern-matched branches)
    for branch_name, rule_data in final_rules.items():
        brsettings = rule_data["settings"]
        
        # Remove this branch from currently protected (so we don't remove protection later)
        currently_protected_branches.discard(branch_name)

        branch_changes = []
        try:
            ghbranch = self.ghrepo.get_branch(branch=branch_name)
        except pygithub.GithubException as e:
            if e.status == 404:  # No such branch, skip to next rule
                protection_changes[branch_name] = [f"Branch {branch_name} does not exist, protection could not be configured"]
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
            require_last_push_approval = required_pull_request_reviews.get("require_last_push_approval", NotSet)
        else:
            required_pull_request_reviews = NotSet
            required_approving_review_count = NotSet
            dismiss_stale_reviews = NotSet
            require_last_push_approval = NotSet
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

            if is_defined(require_last_push_approval) and (
                live_reviews is None or require_last_push_approval != live_reviews.require_last_push_approval
            ):
                branch_changes.append(f"Set require last push approval to {require_last_push_approval}")

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
            protection_changes[branch_name] = branch_changes

    # remove branch protection from all remaining currently protected branches
    # (these are branches that had protection but are no longer in our rules)
    for branch_name in currently_protected_branches:
        branch = self.ghrepo.get_branch(branch_name)
        protection_changes[branch_name] = [f"Remove branch protection from branch '{branch_name}' (no longer matches any rules)"]

        if not self.noop("github::protected_branches"):
            branch.remove_protection()

    if protection_changes:
        summary = "Branch Protection Changes:\n"
        
        # Show pattern rule matches first
        pattern_applied = []
        exact_applied = []
        removed = []
        
        for branch_name, changes in protection_changes.items():
            if branch_name in final_rules:
                rule_data = final_rules[branch_name]
                if rule_data["rule_type"] == "pattern":
                    pattern_applied.append((branch_name, changes, rule_data["source"]))
                else:
                    exact_applied.append((branch_name, changes, rule_data["source"]))
            else:
                removed.append((branch_name, changes))
        
        # Group output by rule type for clarity
        if pattern_applied:
            summary += "\n=== Branches Protected by Pattern Rules ===\n"
            for branch, changes, source in pattern_applied:
                summary += f"\n{branch} (via {source}):\n"
                for change in changes:
                    summary += f"  - {change}\n"
        
        if exact_applied:
            summary += "\n=== Branches Protected by Exact Rules ===\n"
            for branch, changes, source in exact_applied:
                summary += f"\n{branch} (via {source}):\n"
                for change in changes:
                    summary += f"  - {change}\n"
        
        if removed:
            summary += "\n=== Branch Protection Removed ===\n"
            for branch, changes in removed:
                summary += f"\n{branch}:\n"
                for change in changes:
                    summary += f"  - {change}\n"
        
        print(summary)
