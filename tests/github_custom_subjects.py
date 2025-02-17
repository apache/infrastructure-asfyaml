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


valid_custom_subjects = YamlTest(
    None,
    None,
    """
github:
    custom_subjects:
        close_pr: "{title} was closed..."
        new_issue: "issue #{pr_id} opened: {title}"
""",
)

invalid_custom_subjects_keyerror = YamlTest(
    asfyaml.asfyaml.ASFYAMLException,
    "unexpected key not in schema 'new_issues'",
    """
github:
    custom_subjects:
        close_pr: "{title} was closed..."
        new_issues: "issue #{pr_id} opened: {title}"
""",
)


invalid_custom_subjects_interpolation_error = YamlTest(
    asfyaml.asfyaml.ASFYAMLException,
    "Unknown variable 'psr_id' found in subject template",
    """
github:
    custom_subjects:
        close_pr: "{title} was closed..."
        new_issue: "issue #{psr_id} opened: {xtitle}"
""",
)


def test_basic_yaml(test_repo: asfyaml.dataobjects.Repository):
    print("[github] Testing merge buttons")

    tests_to_run = (
        valid_custom_subjects,
        invalid_custom_subjects_keyerror,
        invalid_custom_subjects_interpolation_error,
    )

    for test in tests_to_run:
        with test.ctx() as vs:
            a = asfyaml.asfyaml.ASFYamlInstance(test_repo, "humbedooh", test.yaml)
            a.environments_enabled.add("noop")
            a.no_cache = True
            a.run_parts()
