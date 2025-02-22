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

"""Unit tests for .asf.yaml GitHub Deployment Environments feature"""
import re
from unittest.mock import patch, Mock

import pytest

import asfyaml.asfyaml
import asfyaml.dataobjects
from helpers import YamlTest
from asfyaml.feature.github.deployment_environments import validate_environment_configs, get_deployment_policies, \
    create_deployment_environment, get_user_id, create_deployment_branch_policy, delete_deployment_environment, \
    delete_deployment_branch_policy, deployment_environments

# Set .asf.yaml to debug mode
asfyaml.asfyaml.DEBUG = True

valid_github_deployment_environments = YamlTest(
    None,
    None,
    """
github:
    environments:
        test-pypi:
          required_reviewers:
            - id: gopidesupavan
              type: User
          prevent_self_review: true
          wait_timer: 60
          deployment_branch_policy:
             protected_branches: true
             custom_branch_policies: false
""",
)

# Something isn't a bool
invalid_github_deployment_environment_prevent_self_review_not_bool = YamlTest(
    asfyaml.asfyaml.ASFYAMLException,
    "expecting a boolean value",
    """
github:
    environments:
        test-pypi:
          required_reviewers:
            - id: gopidesupavan
              type: User
          prevent_self_review: dummy
          wait_timer: 60
          deployment_branch_policy:
             protected_branches: true
             custom_branch_policies: false
""",
)

# Something isn't a valid directive
missing_required_section = YamlTest(
    asfyaml.asfyaml.ASFYAMLException,
    "\'protected_branches\' not found",
    """
github:
    environments:
        test-pypi:
          required_reviewers:
            - id: gopidesupavan
              type: User
          prevent_self_review: true
          wait_timer: 60
          deployment_branch_policy:
             custom_branch_policies: false
""",
)


def test_basic_yaml(test_repo: asfyaml.dataobjects.Repository):
    print("[github] Testing deployment environments")

    tests_to_run = (
        valid_github_deployment_environments,
        invalid_github_deployment_environment_prevent_self_review_not_bool,
        missing_required_section
    )

    for test in tests_to_run:
        with test.ctx() as vs:
            a = asfyaml.asfyaml.ASFYamlInstance(test_repo, "humbedooh", test.yaml)
            a.environments_enabled.add("noop")
            a.no_cache = True
            a.run_parts()

def test_validate_environment_configs_valid():
    errors = validate_environment_configs(
        {
            "test-pypi": {
                "required_reviewers": [
                    {
                        "id": "gopidesupavan",
                        "type": "User"
                    }
                ],
                "prevent_self_review": True,
                "wait_timer": 60,
                "deployment_branch_policy": {
                    "protected_branches": True,
                    "custom_branch_policies": False
                }
            }
        }
    )
    assert not errors

def test_validate_environment_configs_invalid():
    errors = validate_environment_configs(
        {
            "test-pypi": {
                "required_reviewers": [
                    {
                        "id": "gopidesupavan",
                        "type": "User"
                    }
                ],
                "prevent_self_review": True,
                "wait_timer": 60,
                "deployment_branch_policy": {
                    "protected_branches": True,
                    "custom_branch_policies": True
                }
            }
        }
    )
    assert "protected_branches and custom_branch_policies cannot be enabled at the same time" in errors[0]["error"]

@patch('requests.get')
def test_get_deployment_policies_has_some_policies(mock_get):
    mock_response = Mock()
    expected_policies = [{
        "id": 361471,
        "node_id": "MDE2OkdhdGVCcmFuY2hQb2xpY3kzNjE0NzE=",
        "name": "release/*"
        },
        {
            "id": 361472,
            "node_id": "MDE2OkdhdGVCcmFuY2hQb2xpY3kzNjE0NzI=",
            "name": "main"
        }]

    mock_response.json.return_value = {
        "total_count": 2,
        "branch_policies": [{
            "id": 361471,
            "node_id": "MDE2OkdhdGVCcmFuY2hQb2xpY3kzNjE0NzE=",
            "name": "release/*"
        },
            {
                "id": 361472,
                "node_id": "MDE2OkdhdGVCcmFuY2hQb2xpY3kzNjE0NzI=",
                "name": "main"
            }
        ]
    }

    mock_get.return_value = mock_response

    repo_name = "test-repo"
    token = "test-token"
    environment_name = "test-environment"

    policies = get_deployment_policies(repo_name, token, environment_name)
    assert policies == expected_policies
    mock_get.assert_called_once_with(
        "https://api.github.com/repos/apache/test-repo/environments/test-environment/deployment-branch-policies",
        headers={"Authorization": "token test-token", "Accept": "application/vnd.github+json"}
    )

@patch('requests.get')
def test_get_deployment_policies_has_no_policies(mock_get):
    mock_response = Mock()

    mock_response.json.return_value = {}
    mock_get.return_value = mock_response

    repo_name = "test-repo"
    token = "test-token"
    environment_name = "test-environment"

    policies = get_deployment_policies(repo_name, token, environment_name)
    assert policies == []
    mock_get.assert_called_once_with(
        "https://api.github.com/repos/apache/test-repo/environments/test-environment/deployment-branch-policies",
        headers={"Authorization": "token test-token", "Accept": "application/vnd.github+json"}
    )

@patch('requests.put')
@patch("asfyaml.feature.github.deployment_environments.get_user_id")
def test_create_deployment_environment_success(mock_get_user_id, mock_put):
    mock_get_user_id.return_value = 123456
    gh_session = Mock()
    mock_response = Mock()
    mock_response.json.return_value = {
        "id": 123456
    }
    mock_response.status_code = 200
    mock_put.return_value = mock_response

    env_config = {
        "required_reviewers": [
            {
                "id": "gopidesupavan",
                "type": "User"
            }
        ],
        "prevent_self_review": True,
        "wait_timer": 60,
        "deployment_branch_policy": {
            "protected_branches": True,
            "custom_branch_policies": False
        }
    }

    create_deployment_environment(
        gh_session,
        "test-repo",
        "test-token",
        "test-environment",
        env_config,
    )

    mock_put.assert_called_once_with(
        url="https://api.github.com/repos/apache/test-repo/environments/test-environment",
        headers={"Authorization": "token test-token", "Accept": "application/vnd.github+json"},
        json={
            "wait_timer": 60,
            "prevent_self_review": True,
            "reviewers": [
                {
                    "type": "User",
                    "id": 123456
                }
            ],
            "deployment_branch_policy": {
                "protected_branches": True,
                "custom_branch_policies": False
            }
        }
    )

@patch('requests.put')
@patch("asfyaml.feature.github.deployment_environments.get_user_id")
def test_create_deployment_environment_failed(mock_get_user_id, mock_put):
    mock_get_user_id.return_value = 123456
    gh_session = Mock()
    mock_response = Mock()
    mock_response.json.return_value = {"message": "Validation error"}
    mock_response.status_code = 422
    mock_put.return_value = mock_response

    env_config = {
        "required_reviewers": [
            {
                "id": "gopidesupavan",
                "type": "User"
            }
        ],
        "prevent_self_review": True,
        "wait_timer": 60,
        "deployment_branch_policy": {
            "protected_branches": True,
            "custom_branch_policies": True
        }
    }

    with pytest.raises(Exception, match=re.escape('[GitHub] Request error with message: "Validation error". (status code: 422)')):
        create_deployment_environment(
            gh_session,
            "test-repo",
            "test-token",
            "test-environment",
            env_config,
        )

def test_get_user_id_with_user_name():
    mock_gh_session = Mock()
    mock_user = Mock()
    mock_user.id = 123456
    mock_gh_session.get_user.return_value = mock_user
    user_id = get_user_id(mock_gh_session,"gopidesupavan")
    assert user_id == 123456

def test_get_user_id_with_id():
    mock_gh_session = Mock()
    user_id = get_user_id(mock_gh_session,123456)
    assert user_id == 123456

@patch('requests.post')
def test_create_deployment_branch_policy_success(mock_post):
    mock_response = Mock()
    mock_response.json.return_value = {
        "id": 364663,
        "node_id": "MDE2OkdhdGVCcmFuY2hQb2xpY3kzNjQ2NjM=",
        "name": "main"
    }
    mock_response.status_code = 200
    mock_post.return_value = mock_response

    create_deployment_branch_policy(
        "test-repo",
        "test-token",
        "test-environment",
        [{"type": "branch", "name": "main"}]
    )
    mock_post.assert_called_once_with(
        url="https://api.github.com/repos/apache/test-repo/environments/test-environment/deployment-branch-policies",
        headers={"Authorization": "token test-token", "Accept": "application/vnd.github+json"},
        json={"type": "branch", "name": "main"}
    )

@patch('requests.post')
def test_create_deployment_branch_policy_failed(mock_post):
    mock_response = Mock()
    mock_response.json.return_value = {
        "message": "Not Found"
    }
    mock_response.status_code = 404
    mock_post.return_value = mock_response

    with pytest.raises(Exception, match=re.escape('[GitHub] Request error with message: "Not Found". (status code: 404)')):
        create_deployment_branch_policy(
            "test-repo",
            "test-token",
            "test-environment",
            [{"type": "branch", "name": "main"}]
        )

@patch('requests.delete')
def test_delete_deployment_environment_success(mock_delete):
    mock_response = Mock()
    mock_response.status_code = 204
    mock_delete.return_value = mock_response

    delete_deployment_environment(
        "test-repo",
        "test-token",
        "test-environment"
    )
    mock_delete.assert_called_once_with(
        url="https://api.github.com/repos/apache/test-repo/environments/test-environment",
        headers = {"Authorization": "token test-token", "Accept": "application/vnd.github+json"}
    )

@patch('requests.delete')
def test_delete_deployment_environment_failed(mock_delete):
    mock_response = Mock()
    mock_response.status_code = 404
    mock_response.json.return_value = {
        "message": "Not Found"
    }
    mock_delete.return_value = mock_response

    with pytest.raises(Exception, match=re.escape('[GitHub] Request error with message: "Not Found". (status code: 404)')):
        delete_deployment_environment(
            "test-repo",
            "test-token",
            "test-environment"
        )

@patch('requests.delete')
def test_delete_deployment_branch_policy_success(mock_delete):
    mock_response = Mock()
    mock_response.status_code = 204
    mock_delete.return_value = mock_response

    delete_deployment_branch_policy(
        "test-repo",
        "test-token",
        "test-environment",
        123456
    )
    mock_delete.assert_called_once_with(
        url="https://api.github.com/repos/apache/test-repo/environments/test-environment/deployment-branch-policies/123456",
        headers={"Authorization": "token test-token", "Accept": "application/vnd.github+json"}
    )

@patch('requests.delete')
def test_delete_deployment_branch_policy_failed(mock_delete):
    mock_response = Mock()
    mock_response.status_code = 404
    mock_response.json.return_value = {
        "message": "Not Found"
    }
    mock_delete.return_value = mock_response

    with pytest.raises(Exception, match=re.escape('[GitHub] Request error with message: "Not Found". (status code: 404)')):
        delete_deployment_branch_policy(
            "test-repo",
            "test-token",
            "test-environment",
            123456
        )