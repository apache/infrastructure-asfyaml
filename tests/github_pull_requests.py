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

"""Unit tests for .asf.yaml GitHub pull request features"""

from helpers import YamlTest
import asfyaml.asfyaml
import asfyaml.dataobjects

# Set .asf.yaml to debug mode
asfyaml.asfyaml.DEBUG = True


legacy_setting = YamlTest(
    None,
    None,
    """
github:
    del_branch_on_merge: true
""",
)


valid_pull_request_settings = YamlTest(
    None,
    None,
    """
github:
    pull_requests:
      del_branch_on_merge: true
      allow_auto_merge: true
      allow_update_branch: true
""",
)


invalid_legacy_and_pull_requests = YamlTest(
    asfyaml.asfyaml.ASFYAMLException,
    "found legacy setting 'github.del_branch_on_merge' while 'github.pull_requests' is present. Move setting to 'github.pull_requests'",
    """
github:
    del_branch_on_merge: true
    pull_requests:
      del_branch_on_merge: false
      allow_auto_merge: true
      allow_update_branch: true
""",
)


def test_basic_yaml(test_repo: asfyaml.dataobjects.Repository):
    print("[github] Testing pull requests")

    tests_to_run = (
        legacy_setting,
        valid_pull_request_settings,
        invalid_legacy_and_pull_requests,
    )

    for test in tests_to_run:
        with test.ctx():
            a = asfyaml.asfyaml.ASFYamlInstance(
                repo=test_repo, committer="humbedooh", config_data=test.yaml, branch=asfyaml.dataobjects.DEFAULT_BRANCH
            )
            a.environments_enabled.add("noop")
            a.no_cache = True
            a.run_parts()
