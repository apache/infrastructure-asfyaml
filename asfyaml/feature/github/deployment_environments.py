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
import os

from . import directive, ASFGitHubFeature, GH_TOKEN_FILE
import requests
import urllib
import github as pygithub
import github.Auth as pygithubAuth

def validate_environment_configs(environments: dict):
    config_environment_errors = []

    for env, env_config in environments.items():
        if not env_config.get("required_reviewers"):

            config_environment_errors.append(
                {"env": env, "error": "required_reviewers is missing, minimum 1 reviewer is required"})

        if len(env_config.get("required_reviewers", [])) > 6:
            config_environment_errors.append(
                {"env": env, "error": "required_reviewers cannot be more than 6 reviewers"})


        is_custom_branch_policies = env_config.get("deployment_branch_policy", {}).get("custom_branch_policies")
        is_protected_branches = env_config.get("deployment_branch_policy", {}).get("protected_branches")

        if is_custom_branch_policies and is_protected_branches:
            config_environment_errors.append({"env": env,
                                              "error": "protected_branches and custom_branch_policies cannot be enabled at the same"
                                                       " time, set one of them to false"})

        if is_custom_branch_policies and not env_config.get("deployment_branch_policy", {}).get("policies"):
            config_environment_errors.append({"env": env,
                                                "error": "Policies is missing, when custom_branch_policies is enabled, minimum 1 policy is required"})
    return config_environment_errors

def get_deployment_policies(repo_name, token, environment_name):
    url = "https://api.github.com/repos/apache/%s/environments/%s/deployment-branch-policies"

    parsed_env_name = urllib.parse.quote(environment_name, safe="")

    parsed_url = url % (repo_name, parsed_env_name)
    rsp = requests.get(
        parsed_url,
        headers={"Authorization": "token %s" % token, "Accept": "application/vnd.github+json"}
    )

    parsed_response = rsp.json()
    return parsed_response.get("branch_policies", [])

def create_deployment_environment(gh_session, repo_name, token, env_name, env_config):
    env_name = urllib.parse.quote(env_name, safe="")


    url = "https://api.github.com/repos/apache/%s/environments/%s" % (repo_name, env_name)

    required_reviewers = env_config.get("required_reviewers")
    prevent_self_review = env_config.get("prevent_self_review", True)
    wait_timer = env_config.get("wait_timer", 5) # default 5 minutes
    deployment_branch_policy = env_config.get("deployment_branch_policy", None)

    # Get the user id for the required reviewers, this endpoint only accepts user ids not usernames
    required_reviewers_with_id = [
        {
            "type":reviewer.get("type"),
            "id": get_user_id(gh_session, reviewer.get("id"))
        } for reviewer in required_reviewers
    ]

    payload = {
        "wait_timer": wait_timer,
        "prevent_self_review": prevent_self_review,
        "reviewers": required_reviewers_with_id,
        "deployment_branch_policy": deployment_branch_policy
    }

    response = requests.put(
                        url=url,
                        headers={"Authorization": "token %s" % token, "Accept": "application/vnd.github+json"},
                        json=payload
                        )

    if not (200 <= response.status_code < 300):
        js = response.json()
        raise Exception(
            "[GitHub] Request error with message: \"%s\". (status code: %s)" % (
                js.get("message"),
                response.status_code
            )
        )

def get_user_id(gh_session, username):
    if isinstance(username, int):
        return username
    user = gh_session.get_user(username)
    return user.id

def create_deployment_branch_policy(repo_name, token, env_name, deployment_branch_policies):
    if not deployment_branch_policies:
        return

    env_name = urllib.parse.quote(env_name, safe="")
    url = "https://api.github.com/repos/apache/%s/environments/%s/deployment-branch-policies" % (repo_name, env_name)

    for policy in deployment_branch_policies:
        response = requests.post(
            url=url,
            headers={"Authorization": "token %s" % token, "Accept": "application/vnd.github+json"},
            json=policy
        )

        if not (200 <= response.status_code <= 303):
            js = response.json()
            raise Exception(
                "[GitHub] Request error with message: \"%s\". (status code: %s)" % (
                    js.get("message"),
                    response.status_code
                )
            )

def delete_deployment_environment(repo_name, token, env_name):
    env_name = urllib.parse.quote(env_name, safe="")

    url = "https://api.github.com/repos/apache/%s/environments/%s" % (repo_name, env_name)

    requests.delete(
        url=url,
        headers= {"Authorization": "token %s" % token, "Accept": "application/vnd.github+json"},
    )

def delete_deployment_branch_policy(repo_name: str, token: str, env_name: str, policy_id: int):
    env_name = urllib.parse.quote(env_name, safe="")

    url = "https://api.github.com/repos/apache/%s/environments/%s/deployment-branch-policies/%s" % (repo_name, env_name, policy_id)

    requests.delete(
        url=url,
        headers= {"Authorization": "token %s" % token, "Accept": "application/vnd.github+json"}
    )

@directive
def deployment_environments(self: ASFGitHubFeature):

    environments = self.yaml.get("environments", [])
    if self.noop("environments"):
        return
    repo_name = self.repository.name
    gh_token = os.environ.get("GH_TOKEN")
    if not gh_token:
        gh_token = open(GH_TOKEN_FILE).read().strip()
    gh_session = pygithub.Github(auth=pygithubAuth.Token(gh_token))

    if environments:
        config_environment_errors = validate_environment_configs(environments)

        if config_environment_errors:
            raise Exception("Invalid Environment Configurations Found: %s" % config_environment_errors)

        for env_name, env_config in environments.items():

            create_deployment_environment(gh_session, repo_name, gh_token, env_name, env_config)

            if env_config.get("deployment_branch_policy", {}).get("custom_branch_policies"):
                create_deployment_branch_policy(
                    repo_name, gh_token, env_name,
                    env_config.get("deployment_branch_policy", {}).get("policies")
                )

    if "environments" in self.yaml:

        repo_environment_names = [env.name for env in self.ghrepo.get_environments()]

        # Exclude the environments that are in the asf yml file, and delete the rest
        # These filtered environments are considered as old and no configuration is provided in the asf yml file.
        # To get all non active environments, we can subtract repo_environment_names( all the environments exists in repository)
        # with asf yml file environments
        if environments:
            environments_to_be_removed = list(set(repo_environment_names) - set(environments.keys()))
        else:
            environments_to_be_removed = repo_environment_names

        for env_to_delete in environments_to_be_removed:
            delete_deployment_environment(repo_name, gh_token, env_to_delete)

        # If there are no environments in the asf yml file, we can consider all the environments prior to this step
        # has deleted already, so we can ignore the branch policies deletion process.

        # To delete deployment branch policies, we get all the environment deployment branch policies from repository
        # which includes new and old ones. We filter out the branch policies that are in asf yml file, and delete the
        # rest of deployment branch policies.
        if environments:
            environment_names = environments.keys()

            for env_name in environment_names:
                env_config = environments.get(env_name)
                is_protected_branches = env_config.get("deployment_branch_policy", {}).get(
                    "protected_branches")

                # If protected_branches is selected in deployment_branch_policy for environment,
                # we can assume that there will be no custom branch policies to delete, as the protected_branches
                # will override the custom branch policies.
                if is_protected_branches:
                    continue

                repo_deployment_branch_policies = get_deployment_policies(repo_name, gh_token, env_name)

                asf_config_environment_policies = env_config.get("deployment_branch_policy", {}
                                                                 ).get("policies", [])

                asf_config_environment_policy_names = [
                    policy.get("name") for policy in
                    asf_config_environment_policies
                ]

                for repo_deployment_branch_policy in repo_deployment_branch_policies:

                    repo_deployment_branch_policy_name = repo_deployment_branch_policy.get("name")

                    if repo_deployment_branch_policy_name not in asf_config_environment_policy_names:
                        delete_deployment_branch_policy(repo_name, gh_token, env_name,
                                                        repo_deployment_branch_policy.get("id"))