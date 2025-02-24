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

"""Unit tests for .asf.yaml GitHub pages feature"""

import asfyaml.asfyaml
import asfyaml.dataobjects
from helpers import YamlTest

# Set .asf.yaml to debug mode
asfyaml.asfyaml.DEBUG = True


valid_github_pages = YamlTest(
    None,
    None,
    """
github:
    ghp_branch: main
    ghp_path: /docs
""",
)

# Something isn't a string
invalid_github_pages_garbage = YamlTest(
    asfyaml.asfyaml.ASFYAMLException,
    "when expecting a str",
    """
github:
    ghp_branch:
     - 1
     - 2
    ghp_path: /docs
""",
)

# branch isn't a valid setting
invalid_github_pages_bad_branch = YamlTest(
    asfyaml.asfyaml.ASFYAMLException,
    "Invalid GitHub Pages branch",
    """
github:
    ghp_branch: foo
    ghp_path: /docs
""",
)


def test_basic_yaml(test_repo: asfyaml.dataobjects.Repository):
    print("[github] Testing GitHub Pages features")

    tests_to_run = (
        valid_github_pages,
        invalid_github_pages_garbage,
        invalid_github_pages_bad_branch,
    )

    for test in tests_to_run:
        with test.ctx() as vs:
            a = asfyaml.asfyaml.ASFYamlInstance(test_repo, "humbedooh", test.yaml)
            a.environments_enabled.add("noop")
            a.no_cache = True
            a.run_parts()
