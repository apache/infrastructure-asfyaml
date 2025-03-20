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

"""GitHub deployment environments"""

import json
from typing import Mapping, Any

from github.GithubObject import NonCompletableGithubObject, Attribute, NotSet
from github.PaginatedList import PaginatedList
from github.EnvironmentDeploymentBranchPolicy import EnvironmentDeploymentBranchPolicyParams
from github.EnvironmentProtectionRuleReviewer import ReviewerParams

from . import directive, ASFGitHubFeature


def _validate_environment_configs(environments: Mapping[str, Any]) -> Mapping[str, list[str]]:
    config_errors = {}

    for env, env_config in environments.items():
        env_errors = []

        wait_timer = env_config.get("wait_timer")
        if wait_timer is not None and wait_timer not in range(0, 43200):
            env_errors.append("wait_timer must be between 0 and 43200")

        required_reviewers = env_config.get("required_reviewers")
        if required_reviewers is not None:
            if len(required_reviewers) > 6:
                env_errors.append("required_reviewers cannot contain more than 6 reviewers")

            for reviewer in required_reviewers:
                if reviewer["type"] not in ("User", "Team"):
                    reviewer_id = reviewer.get("id")
                    env_errors.append(
                        f"required_reviewer with id '{reviewer_id}' must have type of either 'User' or 'Team'"
                    )

        deployment_branch_policy = env_config.get("deployment_branch_policy")
        if deployment_branch_policy is not None:
            protected_branches = deployment_branch_policy.get("protected_branches")
            policies = deployment_branch_policy.get("policies", [])

            if protected_branches and len(policies) > 0:
                env_errors.append("protected_branches and policies cannot be enabled at the same time")

            if not protected_branches and len(policies) == 0:
                env_errors.append(
                    "either protected_branches or policies must be enabled when specifying a deployment branch policy"
                )

            for policy in policies:
                if policy["type"] not in ("branch", "tag"):
                    env_errors.append(
                        f"deployment branch policy with name '{policy['name']}' must have type of either 'branch' or 'tag'"
                    )

        if len(env_errors) > 0:
            config_errors[env] = env_errors

    return config_errors


def _create_or_update_deployment_environment(self: ASFGitHubFeature, env_name, env_config):
    wait_timer = env_config.get("wait_timer", 0)  # by default disabled

    # Get the user id for the required reviewers, this endpoint only accepts user ids not usernames
    def get_reviewer(reviewer: Mapping[str, Any]) -> ReviewerParams:
        reviewer_id = reviewer["id"]
        reviewer_type = reviewer.get("type", "User")
        github_id = _get_user_id(self, reviewer_id) if reviewer_type == "User" else _get_team_id(self, reviewer_id)
        return ReviewerParams(type_=reviewer_type, id_=github_id)

    required_reviewers = env_config.get("required_reviewers", [])
    required_reviewers_with_id = [get_reviewer(reviewer) for reviewer in required_reviewers]

    # prevent_self_review is not supported by pygithub yet, https://github.com/PyGithub/PyGithub/pull/3246 is open
    # prevent_self_review = env_config.get("prevent_self_review", True)

    if "deployment_branch_policy" in env_config:
        deployment_branch_policy = env_config.get("deployment_branch_policy")
        protected_branches = deployment_branch_policy.get("protected_branches", False)
        policies = deployment_branch_policy.get("policies", [])

        deployment_branch_policy = EnvironmentDeploymentBranchPolicyParams(
            protected_branches=protected_branches,
            custom_branch_policies=len(policies) > 0,
        )
    else:
        deployment_branch_policy = None
        policies = []

    print(f"Updates to deployment environment {env_name}")
    print(f"  - Set required_reviewers to {[r.id for r in required_reviewers_with_id]}")
    print(f"  - Set wait_timer to {wait_timer}")
    if deployment_branch_policy is None:
        print("  - Set deployment branch policy = None")
    else:
        print(
            f"  - Set deployment branch policy = "
            f"(protected_branches={deployment_branch_policy.protected_branches}, "
            f"custom_branch_policies={deployment_branch_policy.custom_branch_policies})"
        )

    if not self.noop("environment"):
        self.ghrepo.create_environment(
            environment_name=env_name,
            wait_timer=wait_timer,
            reviewers=required_reviewers_with_id,
            deployment_branch_policy=deployment_branch_policy,
        )

        if deployment_branch_policy is not None and deployment_branch_policy.custom_branch_policies is True:
            _create_or_update_deployment_branch_policy(self, env_name, policies)


def _get_user_id(self: ASFGitHubFeature, username: Any) -> int:
    if isinstance(username, int):
        return username
    user = self.gh.get_user(username)
    return user.id


def _get_team_id(self: ASFGitHubFeature, team_name: Any) -> int:
    if isinstance(team_name, int):
        return team_name
    team = self.gh.get_organization(self.repository.org_id).get_team_by_slug(team_name)
    return team.id


class DeploymentBranchPolicy(NonCompletableGithubObject):
    def _initAttributes(self) -> None:  # noqa: N802
        self._id: Attribute[int] = NotSet
        self._name: Attribute[str] = NotSet

    def __repr__(self) -> str:
        return self.get__repr__({"id": self.id, "name": self.name})

    @property
    def id(self) -> int:
        return self._id.value

    @property
    def name(self) -> str:
        return self._name.value

    def _useAttributes(self, attributes: dict[str, Any]) -> None:  # noqa: N802
        if "id" in attributes:
            self._id = self._makeIntAttribute(attributes["id"])
        if "name" in attributes:  # pragma no branch
            self._name = self._makeStringAttribute(attributes["name"])


def _get_deployment_branch_policies(self: ASFGitHubFeature, env_name: str) -> list[DeploymentBranchPolicy]:
    return list(
        PaginatedList(
            DeploymentBranchPolicy,
            self.ghrepo._requester,
            f"/repos/{self.repository.org_id}/{self.repository.name}/environments/{env_name}/deployment-branch-policies",
            None,
            list_item="branch_policies",
        )
    )


# https://github.com/PyGithub/PyGithub/issues/3250 is open to add support for deployment branch policies in pygithub
def _create_or_update_deployment_branch_policy(
    self: ASFGitHubFeature, env_name: str, deployment_branch_policies: list[Mapping[str, Any]]
) -> None:
    current_policies = {p.name: p for p in _get_deployment_branch_policies(self, env_name)}
    for policy in deployment_branch_policies:
        name = policy["name"]
        if name not in current_policies:
            print(f"  - Create deployment branch policy: {name}")

            if not self.noop("environments"):
                self.ghrepo._requester.requestJson(
                    "POST",
                    f"/repos/{self.repository.org_id}/{self.repository.name}/environments/{env_name}/deployment-branch-policies",
                    input=policy,
                )
        else:
            current_policies.pop(name)

    for name, p in current_policies.items():
        print(f"  - Delete deployment branch policy: {name}")

        if not self.noop("environments"):
            self.ghrepo._requester.requestJson(
                "DELETE",
                f"/repos/{self.repository.org_id}/{self.repository.name}/environments/{env_name}/deployment-branch-policies/{p.id}",
            )


@directive
def deployment_environments(self: ASFGitHubFeature):
    environments = self.yaml.get("environments", [])

    if environments:
        config_errors = _validate_environment_configs(environments)
        if len(config_errors) > 0:
            raise Exception("Deployment Environment validation failed: \n%s" % json.dumps(config_errors, indent=2))

        for env_name, env_config in environments.items():
            _create_or_update_deployment_environment(self, env_name, env_config)
