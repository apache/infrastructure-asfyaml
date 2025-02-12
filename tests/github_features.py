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

"""Unit tests for .asf.yaml GitHub features"""

import asfyaml.asfyaml
import asfyaml.dataobjects
from helpers import YamlTest
# Set .asf.yaml to debug mode
asfyaml.asfyaml.DEBUG = True


valid_github_features = YamlTest(
    None,
    None,
    """
github:
    features:
        issues: true
        wiki: false
        projects: true
        discussions: false
    labels:
        - a
        - b
        - c
    description: Apache Foo
    homepage: https://foo.apache.org/
""",
)

# Something isn't a bool
invalid_github_features_not_bool = YamlTest(
    asfyaml.asfyaml.ASFYAMLException,
    "expecting a boolean value",
    """
github:
    features:
        issues: maybe
        wiki: false
        projects: true
        discussions: false
""",
)

# Something isn't a valid directive
invalid_github_features_unknown_directive = YamlTest(
    asfyaml.asfyaml.ASFYAMLException,
    "unexpected key not in schema 'foobar'",
    """
github:
    features:
        foobar: true
        wiki: false
        projects: true
        discussions: false
""",
)


# Discussions enabled but no mailing list target set
invalid_github_features_no_disc_target = YamlTest(
    asfyaml.asfyaml.ASFYAMLException,
    "GitHub discussions can only be enabled if a mailing list target exists",
    """
github:
    features:
        issues: true
        wiki: false
        projects: true
        discussions: true
""",
)


def test_basic_yaml(test_repo: asfyaml.dataobjects.Repository):
    print("[github] Testing features")

    tests_to_run = (
        valid_github_features,
        invalid_github_features_not_bool,
        invalid_github_features_unknown_directive,
        invalid_github_features_no_disc_target
    )

    for test in tests_to_run:
        with test.ctx() as vs:
            a = asfyaml.asfyaml.ASFYamlInstance(test_repo, "humbedooh", test.yaml)
            a.environments_enabled.add("noop")
            a.no_cache = True
            a.run_parts()
