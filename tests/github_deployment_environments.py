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

import asfyaml.asfyaml
import asfyaml.dataobjects
from helpers import YamlTest
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