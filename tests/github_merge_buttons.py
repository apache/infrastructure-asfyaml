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

"""Unit tests for .asf.yaml GitHub merge buttons"""

from helpers import YamlTest
import asfyaml.asfyaml
import asfyaml.dataobjects

# Set .asf.yaml to debug mode
asfyaml.asfyaml.DEBUG = True


valid_github_merge_buttons = YamlTest(
    None,
    None,
    """
github:
    enabled_merge_buttons:
      squash: true
      merge: true
      rebase: true
      auto_merge: true
""",
)


invalid_github_merge_buttons_all_false = YamlTest(
    asfyaml.asfyaml.ASFYAMLException,
    "enabled_merge_buttons: at least one of 'squash', 'merge' or 'rebase' must be enabled",
    """
github:
    enabled_merge_buttons:
      squash: false
      merge: false
      rebase: false
""",
)


valid_merge_commit_message = YamlTest(
    None,
    None,
    """
github:
    enabled_merge_buttons:
      merge: true
      merge_commit_message: DEFAULT
""",
)


invalid_merge_commit_message = YamlTest(
    asfyaml.asfyaml.ASFYAMLException,
    "merge_commit_message must be one of 'DEFAULT', 'PR_TITLE' or 'PR_TITLE_AND_DESC'",
    """
github:
    enabled_merge_buttons:
      merge: true
      merge_commit_message: BLABLA
""",
)


valid_squash_merge_commit_message = YamlTest(
    None,
    None,
    """
github:
    enabled_merge_buttons:
      squash: true
      squash_commit_message: PR_TITLE
""",
)


invalid_squash_merge_commit_message = YamlTest(
    asfyaml.asfyaml.ASFYAMLException,
    "enabled_merge_buttons: squash_commit_message must be one of 'DEFAULT', 'PR_TITLE', 'PR_TITLE_AND_COMMIT_DETAILS' or 'PR_TITLE_AND_DESC'",
    """
github:
    enabled_merge_buttons:
      squash: true
      squash_commit_message: BLABLA
""",
)


def test_basic_yaml(test_repo: asfyaml.dataobjects.Repository):
    print("[github] Testing merge buttons")

    tests_to_run = (
        valid_github_merge_buttons,
        invalid_github_merge_buttons_all_false,
        valid_merge_commit_message,
        invalid_merge_commit_message,
        valid_squash_merge_commit_message,
        invalid_squash_merge_commit_message
    )

    for test in tests_to_run:
        with test.ctx() as vs:
            a = asfyaml.asfyaml.ASFYamlInstance(
                repo=test_repo, committer="humbedooh", config_data=test.yaml, branch=asfyaml.dataobjects.DEFAULT_BRANCH
            )
            a.environments_enabled.add("noop")
            a.no_cache = True
            a.run_parts()
