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

"""Unit tests for .asf.yaml GitHub branch protection"""
import strictyaml.exceptions

from helpers import YamlTest
import asfyaml.asfyaml
import asfyaml.dataobjects

# Set .asf.yaml to debug mode
asfyaml.asfyaml.DEBUG = True


valid_github_checks = YamlTest(
    None,
    None,
    """
github:
  protected_branches:
    main:
      required_status_checks:
        checks:
            # Only slug
          - context: "check1"
            app_slug: github-actions
            # Only id
          - context: "check2"
            app_id: 15368
            # Only context
          - context: "check3"
""",
)


def test_basic_yaml(test_repo: asfyaml.dataobjects.Repository):
    print("[github] Testing branch protection")

    tests_to_run = (
        valid_github_checks,
    )

    for test in tests_to_run:
        with test.ctx():
            a = asfyaml.asfyaml.ASFYamlInstance(
                repo=test_repo, committer="humbedooh", config_data=test.yaml, branch=asfyaml.dataobjects.DEFAULT_BRANCH
            )
            a.environments_enabled.add("noop")
            a.no_cache = True
            a.run_parts()
