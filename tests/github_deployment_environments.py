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
            - id: 1234
          wait_timer: 60
          deployment_branch_policy:
             protected_branches: true
""",
)

invalid_wait_timer = YamlTest(
    asfyaml.asfyaml.ASFYAMLException,
    re.escape("Deployment Environment validation failed: \n{\n  \"test-pypi\": [\n    \"wait_timer must be between 0 and 43200\"\n  ]\n}"),
    """
github:
    environments:
        test-pypi:
          required_reviewers:
            - id: 1234
          wait_timer: -1
""",
)

invalid_deployment_branch_policy = YamlTest(
    asfyaml.asfyaml.ASFYAMLException,
    re.escape("Deployment Environment validation failed: \n{\n  \"test-pypi\": [\n    \"protected_branches and policies cannot be enabled at the same time\"\n  ]\n}"),
    """
github:
    environments:
        test-pypi:
          required_reviewers:
            - id: 1234
          wait_timer: 15
          deployment_branch_policy:
            protected_branches: true
            policies:
             - name: main
""",
)


def test_basic_yaml(test_repo: asfyaml.dataobjects.Repository):
    print("[github] Testing deployment environments")

    tests_to_run = (
        valid_github_deployment_environments,
        invalid_wait_timer,
        invalid_deployment_branch_policy
    )

    for test in tests_to_run:
        with test.ctx():
            a = asfyaml.asfyaml.ASFYamlInstance(test_repo, "anonymous", test.yaml)
            a.environments_enabled.add("noop")
            a.no_cache = True
            a.run_parts()
